from __future__ import annotations

import copy
import re
from typing import Any

import nuclei_excel_import
import report_full_detail as full
import report_pdf_polish as polish
import report_quality
from coordinator_registry import normalize
from nuclei_catalog import catalog_for_career


EXCLUDED_CAREER_PHRASES = ("administracion de centros infantiles",)


def _is_excluded_career(value: Any) -> bool:
    key = normalize(value)
    return any(phrase in key for phrase in EXCLUDED_CAREER_PHRASES)


def _display_career(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return "Sin carrera"
    online = polish._is_online(text)
    if _is_excluded_career(text):
        # Este valor no debe llegar al PDF; se conserva una salida limpia por
        # seguridad para cualquier llamada aislada a la función.
        return "Administración de Centros Infantiles"
    catalog = catalog_for_career(text)
    if catalog:
        base = str(catalog["career"])
        return f"{base} Online" if online else base
    text = re.sub(
        r"^(TECNOLOG[IÍ]A|T[EÉ]CNICO)(?:\s+SUPERIOR)?\s+EN\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"^UNIVERSITARIA\s+EN\s+", "", text, flags=re.I)
    text = re.sub(r"\s+(ONLINE|EN\s+L[IÍ]NEA|PRESENCIAL)\s*$", "", text, flags=re.I)
    if text.isupper():
        text = text.title()
    return f"{text} Online" if online else text


def _allowed_nuclei_career(
    career: Any,
    report: dict[str, Any],
    source_modality: Any = "",
) -> bool:
    if _is_excluded_career(career):
        return False

    report_modality = str(report.get("modality") or "").strip().lower()
    explicit = normalize(source_modality)
    if explicit in {"en linea", "online", "en_linea"}:
        online = True
    elif explicit == "presencial":
        online = False
    else:
        # Compatibilidad con fuentes históricas que todavía no llevan modalidad
        # explícita. Las cargas conciliadas usan la modalidad oficial.
        online = polish._is_online(career)

    if report_modality == "en_linea":
        return online
    if report_modality == "presencial":
        return not online
    return True


def _display_report(report: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(report)
    result["careers"] = [
        career for career in result.get("careers", [])
        if not _is_excluded_career(career.get("name"))
    ]
    for career in result.get("careers", []):
        career["name"] = _display_career(career.get("name"))
    return result


def _parse_excel_filtered(payload: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    records, filename = polish._ORIGINAL_PARSE_EXCEL(payload)
    filtered = [
        record for record in records
        if not _is_excluded_career(record.get("nombre_carrera"))
    ]
    if not filtered:
        raise ValueError("El Excel no contiene carreras válidas para el informe de Núcleos.")
    return filtered, filename


def _catalogs_for_pdf(report: dict[str, Any], report_id: int) -> list[dict[str, Any]]:
    names = [
        career.get("name") for career in report.get("careers", [])
        if not _is_excluded_career(career.get("name"))
    ]
    names.extend(
        course.get("career_name")
        for course in polish._filtered_nuclei_data(report_id)["courses"]
        if not _is_excluded_career(course.get("career_name"))
    )
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in names:
        if not name or _is_excluded_career(name):
            continue
        catalog = catalog_for_career(str(name))
        if not catalog:
            continue
        key = normalize(catalog["career"])
        if key not in seen:
            found.append(catalog)
            seen.add(key)
    return found


def install() -> None:
    if getattr(report_quality, "_pdf_guard_installed", False):
        return

    # Las funciones de report_pdf_polish consultan estos símbolos en tiempo de
    # ejecución; sustituirlos aquí corrige también build_pdf y su validación.
    polish._display_career = _display_career
    polish._allowed_nuclei_career = _allowed_nuclei_career
    polish._display_report = _display_report
    polish._catalogs_for_pdf = _catalogs_for_pdf
    nuclei_excel_import.parse_excel_payload = _parse_excel_filtered

    # Mantener las referencias ya expuestas por la capa anterior.
    full._nuclei_data = polish._filtered_nuclei_data
    full.validate_pdf_report = polish.validate_pdf_report
    report_quality._pdf_guard_installed = True
