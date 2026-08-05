from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
NUMBER_RE = re.compile(r"^-?\d{1,3}(?:[.,]\d+)?$")
INITIALS_RE = re.compile(r"^[A-ZÁÉÍÓÚÑ]{1,3}$")

HEADERS = {
    "nombre / apellido(s)",
    "dirección de correo",
    "direccion de correo",
    "cuestionariocomponente teórico examen complexivo",
    "cuestionariocomponente teorico examen complexivo",
    "cuestionariocomponente teórico examen complexivo -supletorio",
    "cuestionariocomponente teorico examen complexivo -supletorio",
    "media de calificacionestotal teórico",
    "media de calificacionestotal teorico",
    "cuestionariocomponente practico examen complexivo",
    "cuestionariocomponente práctico examen complexivo",
    "cuestionariocomponente practico examen complexivo -supletorio",
    "cuestionariocomponente práctico examen complexivo -supletorio",
    "media de calificacionestotal práctico",
    "media de calificacionestotal practico",
    "sumatotal del curso",
    "promedio general",
}


@dataclass
class ParsedStudent:
    full_name: str
    email: str
    ordinary_theory: float | None
    supplementary_theory: float | None
    source_total_theory: float | None
    ordinary_practical: float | None
    supplementary_practical: float | None
    source_total_practical: float | None
    source_total_course: float | None
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_line(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").strip().split())


def is_header(value: str) -> bool:
    compact = value.casefold().replace("  ", " ")
    if compact in HEADERS:
        return True
    return (
        compact.startswith("cuestionariocomponente")
        or compact.startswith("media de calificaciones")
        or compact.startswith("sumatotal")
    )


def parse_number(value: str) -> float | None:
    value = value.strip()
    if value in {"-", "–", "—", ""}:
        return None
    normalized = value.replace(".", "").replace(",", ".") if "," in value else value
    try:
        return float(normalized)
    except ValueError:
        return None


def is_numeric_placeholder(value: str) -> bool:
    return value in {"-", "–", "—"} or bool(NUMBER_RE.match(value.replace(" ", "")))


def find_name(lines: list[str], email_index: int) -> str:
    for index in range(email_index - 1, -1, -1):
        candidate = lines[index]
        if not candidate or candidate.casefold() == "ocultar" or is_header(candidate):
            continue
        if INITIALS_RE.fullmatch(candidate):
            continue
        if EMAIL_RE.fullmatch(candidate):
            continue
        if is_numeric_placeholder(candidate):
            continue
        return candidate
    return "ESTUDIANTE SIN NOMBRE"


def parse_moodle_text(raw_text: str) -> dict[str, Any]:
    lines = [normalize_line(line) for line in raw_text.splitlines()]
    lines = [line for line in lines if line and line.casefold() != "ocultar"]
    email_positions = [index for index, line in enumerate(lines) if EMAIL_RE.fullmatch(line)]

    records: list[ParsedStudent] = []
    global_warnings: list[str] = []

    if not email_positions:
        return {
            "students": [],
            "warnings": ["No se detectaron direcciones de correo en el texto pegado."],
            "detected": 0,
        }

    for position_index, email_index in enumerate(email_positions):
        email = lines[email_index].lower()
        name = find_name(lines, email_index)
        segment_end = email_positions[position_index + 1] if position_index + 1 < len(email_positions) else len(lines)
        segment = lines[email_index + 1 : segment_end]
        values = [item for item in segment if is_numeric_placeholder(item)]
        warnings: list[str] = []

        if len(values) < 7:
            warnings.append(
                f"Se detectaron {len(values)} de 7 valores esperados después del correo. Revise la fila."
            )
            values.extend(["-"] * (7 - len(values)))
        elif len(values) > 7:
            values = values[:7]

        parsed_values = [parse_number(value) for value in values]
        for idx, number in enumerate(parsed_values):
            if number is not None and not 0 <= number <= 100:
                warnings.append(f"El valor {values[idx]} está fuera del rango de 0 a 100.")

        records.append(
            ParsedStudent(
                full_name=name,
                email=email,
                ordinary_theory=parsed_values[0],
                supplementary_theory=parsed_values[1],
                source_total_theory=parsed_values[2],
                ordinary_practical=parsed_values[3],
                supplementary_practical=parsed_values[4],
                source_total_practical=parsed_values[5],
                source_total_course=parsed_values[6],
                warnings=warnings,
            )
        )

    duplicates = sorted({record.email for record in records if sum(r.email == record.email for r in records) > 1})
    if duplicates:
        global_warnings.append("Correos duplicados detectados: " + ", ".join(duplicates))

    return {
        "students": [record.to_dict() for record in records],
        "warnings": global_warnings,
        "detected": len(records),
    }
