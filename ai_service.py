from __future__ import annotations

import json
import re
from typing import Any

import requests

from analytics import summary

SYSTEM_RULES = """
Eres un asistente de redacción académica institucional para informes de titulación.
Usa exclusivamente las cifras entregadas. No inventes causas, no modifiques notas y no menciones nombres o correos.
Redacta en tercera persona, con tono formal, claro y verificable.
Devuelve únicamente JSON válido con esta estructura:
{
  "texto_antes": "introducción breve de 1 o 2 párrafos",
  "texto_despues": "análisis de 1 a 3 párrafos",
  "hallazgos": ["hallazgo sustentado"],
  "alertas": ["alerta si existe inconsistencia"]
}
""".strip()


def analysis_payload(career_name: str, phase: str, students: list[dict[str, Any]], period: str, modality: str) -> dict[str, Any]:
    data = summary(students, phase)
    data.pop("rows", None)
    return {
        "carrera": career_name,
        "periodo": period,
        "modalidad": modality,
        "apartado": phase,
        "indicadores": data,
        "reglas": {
            "nota_minima": 70,
            "ponderacion_teorica": 40,
            "ponderacion_practica": 60,
            "supletorio": "reemplaza únicamente el componente rendido",
        },
    }


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError("La IA no devolvió un objeto JSON reconocible.")
        parsed = json.loads(match.group(0))
    return {
        "texto_antes": str(parsed.get("texto_antes", "")).strip(),
        "texto_despues": str(parsed.get("texto_despues", "")).strip(),
        "hallazgos": parsed.get("hallazgos", []) if isinstance(parsed.get("hallazgos", []), list) else [],
        "alertas": parsed.get("alertas", []) if isinstance(parsed.get("alertas", []), list) else [],
    }


def call_provider(provider: dict[str, Any], prompt: str) -> dict[str, Any]:
    if not provider.get("api_key"):
        raise ValueError(f"{provider['name']} no tiene una clave API configurada.")
    if not provider.get("model"):
        raise ValueError(f"{provider['name']} no tiene un modelo configurado.")

    timeout = int(provider.get("timeout") or 45)
    temperature = float(provider.get("temperature") or 0.2)
    max_tokens = int(provider.get("max_tokens") or 1400)
    endpoint = provider["endpoint"]

    if provider["provider_type"] == "gemini":
        endpoint = endpoint.format(model=provider["model"])
        response = requests.post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": provider["api_key"],
            },
            json={
                "contents": [{"parts": [{"text": SYSTEM_RULES + "\n\n" + prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                    "responseMimeType": "application/json",
                },
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        return extract_json(text)

    headers = {
        "Authorization": f"Bearer {provider['api_key']}",
        "Content-Type": "application/json",
    }
    if provider["name"].casefold() == "openrouter":
        headers["HTTP-Referer"] = "http://localhost:8765"
        headers["X-Title"] = "Informtit"

    response = requests.post(
        endpoint,
        headers=headers,
        json={
            "model": provider["model"],
            "messages": [
                {"role": "system", "content": SYSTEM_RULES},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload["choices"][0]["message"]["content"]
    return extract_json(text)


def generate_analysis(
    providers: list[dict[str, Any]],
    career_name: str,
    phase: str,
    students: list[dict[str, Any]],
    period: str,
    modality: str,
    mode: str = "single",
) -> tuple[dict[str, Any], list[str]]:
    available = [provider for provider in providers if provider.get("enabled") and provider.get("api_key") and provider.get("model")]
    if not available:
        raise ValueError("No existe una IA habilitada con clave y modelo configurados.")
    available.sort(key=lambda item: item.get("priority", 99))

    source = analysis_payload(career_name, phase, students, period, modality)
    initial_prompt = (
        "Redacta el texto introductorio que irá antes de la tabla y el análisis que irá después. "
        "No repitas todas las cifras; destaca únicamente los resultados relevantes.\n\n"
        + json.dumps(source, ensure_ascii=False, indent=2)
    )

    chain: list[str] = []
    result = call_provider(available[0], initial_prompt)
    chain.append(available[0]["name"])

    if mode == "cascade":
        for provider in available[1:3]:
            revision_prompt = (
                "Verifica y mejora el siguiente borrador. Corrige cualquier cifra que no coincida con los datos. "
                "Mantén la salida JSON solicitada.\n\nDATOS:\n"
                + json.dumps(source, ensure_ascii=False, indent=2)
                + "\n\nBORRADOR:\n"
                + json.dumps(result, ensure_ascii=False, indent=2)
            )
            result = call_provider(provider, revision_prompt)
            chain.append(provider["name"])

    return result, chain
