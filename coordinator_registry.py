from __future__ import annotations

import re
import unicodedata
from typing import Any


COORDINATORS: tuple[dict[str, str], ...] = (
    {"career": "Enfermería", "coordinator": "Ana Emilia Guzman", "program": "Técnico Superior", "telegram": "@emiliaguzmant"},
    {"career": "Mecánica Automotriz", "coordinator": "Dario Torres", "program": "Tecnología Superior", "telegram": "@INGEDARIOTORRES"},
    {"career": "Mecánica de Motos", "coordinator": "Dario Torres", "program": "Tecnología Superior", "telegram": "@INGEDARIOTORRES"},
    {"career": "Diseño Multimedia", "coordinator": "Javier Tapia", "program": "Tecnología Superior", "telegram": "@JAVIERTAPIA28"},
    {"career": "Marketing Digital y Comercio Electrónico", "coordinator": "Javier Tapia", "program": "Tecnología Superior", "telegram": "@JAVIERTAPIA28"},
    {"career": "Marketing Digital y Comercio Electrónico TSU", "coordinator": "Javier Tapia", "program": "Tecnología Universitaria", "telegram": "@JAVIERTAPIA28"},
    {"career": "Ventas", "coordinator": "Javier Tapia", "program": "Tecnología Superior", "telegram": "@JAVIERTAPIA28"},
    {"career": "Desarrollo de Software", "coordinator": "Juan Carlos Pazmiño", "program": "Tecnología Superior", "telegram": "@JUANPAZMINO"},
    {"career": "Desarrollo de Software y Ciberseguridad", "coordinator": "Juan Carlos Pazmiño", "program": "Tecnología Universitaria", "telegram": "@JUANPAZMINO"},
    {"career": "Redes y Telecomunicaciones", "coordinator": "Juan Carlos Pazmiño", "program": "Tecnología Superior", "telegram": "@JUANPAZMINO"},
    {"career": "Redes y Telecomunicaciones TSU", "coordinator": "Juan Carlos Pazmiño", "program": "Tecnología Universitaria", "telegram": "@JUANPAZMINO"},
    {"career": "Estética Integral", "coordinator": "Katherine Chamba", "program": "Tecnología Superior", "telegram": "@Katherine_Chamba_21"},
    {"career": "Educación Básica", "coordinator": "Maria Eugenio Barre", "program": "Tecnología Superior", "telegram": "@MBARREAVILA"},
    {"career": "Educación Inicial", "coordinator": "Maria Eugenio Barre", "program": "Tecnología Superior", "telegram": "@MBARREAVILA"},
    {"career": "Educación Inicial TSU", "coordinator": "Maria Eugenio Barre", "program": "Tecnología Universitaria", "telegram": "@MBARREAVILA"},
    {"career": "Pedagogía", "coordinator": "Maria Eugenio Barre", "program": "Tecnología Universitaria", "telegram": "@MBARREAVILA"},
    {"career": "Procesamiento de Alimentos", "coordinator": "Mayra Molina", "program": "Tecnología Superior", "telegram": "0"},
    {"career": "Administración", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Superior", "telegram": "@RODRIGOESPINOZAITSQMET"},
    {"career": "Administración de Empresas e inteligencia de negocios", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Universitaria", "telegram": "@RODRIGOESPINOZAITSQMET"},
    {"career": "Administración del Talento Humano", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Universitaria", "telegram": ""},
    {"career": "Contabilidad", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Superior", "telegram": "@RODRIGOESPINOZAITSQMET"},
    {"career": "Contabilidad y Tributación TSU", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Universitaria", "telegram": "@RODRIGOESPINOZAITSQMET"},
    {"career": "Gestión del Talento Humano", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Superior", "telegram": ""},
    {"career": "Seguridad y Prevención de Riesgos Laborales", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Superior", "telegram": "@RODRIGOESPINOZAITSQMET"},
    {"career": "Rehabilitación Física", "coordinator": "Andrea Moreano", "program": "Tecnología Superior", "telegram": ""},
    {"career": "Seguridad Ciudadana y Orden Publico", "coordinator": "Sonia Moreno", "program": "Tecnología Superior", "telegram": "@Smoreno1"},
    {"career": "Gastronomia", "coordinator": "Amado Chiluisa", "program": "Tecnología Superior", "telegram": ""},
)


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "")).casefold()
    text = "".join(character for character in text if unicodedata.category(character) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def find_coordinator(career_name: str) -> dict[str, str]:
    target = normalize(career_name)
    exact = next((item for item in COORDINATORS if normalize(item["career"]) == target), None)
    if exact:
        return dict(exact)
    target_tokens = set(target.split())
    best: tuple[int, dict[str, str] | None] = (0, None)
    for item in COORDINATORS:
        tokens = set(normalize(item["career"]).split())
        score = len(target_tokens & tokens)
        if score > best[0]:
            best = (score, item)
    return dict(best[1]) if best[1] and best[0] >= 2 else {
        "career": career_name,
        "coordinator": "",
        "program": "",
        "telegram": "",
    }
