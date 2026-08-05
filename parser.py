from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

EMAIL_RE = re.compile(
    r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE
)
NUMBER_RE = re.compile(r"^-?\d{1,3}(?:[.,]\d+)?$")
INITIALS_RE = re.compile(r"^[A-ZÁÉÍÓÚÑ]{1,3}$")

LEGACY_SCHEMA = [
    "ordinary_theory",
    "supplementary_theory",
    "source_total_theory",
    "ordinary_practical",
    "supplementary_practical",
    "source_total_practical",
    "source_total_course",
]

EXTENDED_SCHEMA = [
    "ordinary_theory",
    "ordinary_theory",  # Versión 2: alternativa del examen ordinario.
    "supplementary_theory",
    "supplementary_theory",  # Segunda columna paralela de supletorio.
    "source_total_theory",
    "ordinary_practical",
    "ordinary_practical",  # Versión 2: alternativa del examen ordinario.
    "supplementary_practical",
    "supplementary_practical",  # Segunda columna paralela de supletorio.
    "source_total_practical",
    "source_total_course",
]


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


def fold_text(value: str) -> str:
    text = unicodedata.normalize("NFD", normalize_line(value)).casefold()
    text = "".join(
        character
        for character in text
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"\s+", " ", text).strip()


def classify_grade_header(value: str) -> str | None:
    """Convierte un encabezado de Moodle en el campo interno correspondiente.

    Moodle puede mostrar varias columnas paralelas para el mismo componente:
    examen ordinario, versión 2 y una o más columnas de supletorio. Las
    versiones ordinarias se consolidan en un solo campo y lo mismo ocurre con
    las columnas paralelas de supletorio.
    """

    compact = re.sub(r"[^a-z0-9]+", " ", fold_text(value)).strip()
    joined = compact.replace(" ", "")

    if "totaldelcurso" in joined:
        return "source_total_course"
    if "totalteorico" in joined:
        return "source_total_theory"
    if "totalpractico" in joined:
        return "source_total_practical"

    if "componente" not in compact or "examen complexivo" not in compact:
        return None

    if "teorico" in compact:
        component = "theory"
    elif "practico" in compact:
        component = "practical"
    else:
        return None

    phase = "supplementary" if "supletorio" in compact else "ordinary"
    return f"{phase}_{component}"


def is_header(value: str) -> bool:
    compact = fold_text(value)
    if classify_grade_header(value) is not None:
        return True
    return (
        compact in {
            "nombre / apellido(s)",
            "direccion de correo",
            "promedio general",
        }
        or compact.startswith("cuestionariocomponente")
        or compact.startswith("media de calificaciones")
        or compact.startswith("sumatotal")
    )


def parse_number(value: str) -> float | None:
    value = value.strip()
    if value in {"-", "–", "—", ""}:
        return None
    normalized = (
        value.replace(".", "").replace(",", ".") if "," in value else value
    )
    try:
        return float(normalized)
    except ValueError:
        return None


def is_numeric_placeholder(value: str) -> bool:
    return value in {"-", "–", "—"} or bool(
        NUMBER_RE.match(value.replace(" ", ""))
    )


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


def detect_schema(lines: list[str], first_email_index: int) -> list[str]:
    schema = [
        field
        for line in lines[:first_email_index]
        if (field := classify_grade_header(line)) is not None
    ]

    required = {
        "ordinary_theory",
        "source_total_theory",
        "ordinary_practical",
        "source_total_practical",
        "source_total_course",
    }
    return schema if required.issubset(schema) else []


def select_parallel_value(
    parsed_values: list[float | None],
    schema: list[str],
    field: str,
    warnings: list[str],
    label: str,
) -> float | None:
    available = [
        parsed_values[index]
        for index, schema_field in enumerate(schema)
        if schema_field == field
        and index < len(parsed_values)
        and parsed_values[index] is not None
    ]

    if len(available) > 1:
        warnings.append(
            f"Se encontraron varias notas en {label}; se utilizó la primera "
            f"({available[0]:.2f})."
        )
    return available[0] if available else None


def values_to_student(
    *,
    name: str,
    email: str,
    raw_values: list[str],
    schema: list[str],
    warnings: list[str],
) -> ParsedStudent:
    expected = len(schema)
    if len(raw_values) < expected:
        warnings.append(
            f"Se detectaron {len(raw_values)} de {expected} valores esperados "
            "después del correo. Revise la fila."
        )
        raw_values.extend(["-"] * (expected - len(raw_values)))
    elif len(raw_values) > expected:
        # En el último estudiante suelen quedar al final los valores de
        # «Promedio general»; no forman parte de su registro.
        raw_values = raw_values[:expected]

    parsed_values = [parse_number(value) for value in raw_values]
    for index, number in enumerate(parsed_values):
        if number is not None and not 0 <= number <= 100:
            warnings.append(
                f"El valor {raw_values[index]} está fuera del rango de 0 a 100."
            )

    return ParsedStudent(
        full_name=name,
        email=email,
        ordinary_theory=select_parallel_value(
            parsed_values,
            schema,
            "ordinary_theory",
            warnings,
            "el componente teórico ordinario",
        ),
        supplementary_theory=select_parallel_value(
            parsed_values,
            schema,
            "supplementary_theory",
            warnings,
            "el componente teórico supletorio",
        ),
        source_total_theory=select_parallel_value(
            parsed_values,
            schema,
            "source_total_theory",
            warnings,
            "el total teórico",
        ),
        ordinary_practical=select_parallel_value(
            parsed_values,
            schema,
            "ordinary_practical",
            warnings,
            "el componente práctico ordinario",
        ),
        supplementary_practical=select_parallel_value(
            parsed_values,
            schema,
            "supplementary_practical",
            warnings,
            "el componente práctico supletorio",
        ),
        source_total_practical=select_parallel_value(
            parsed_values,
            schema,
            "source_total_practical",
            warnings,
            "el total práctico",
        ),
        source_total_course=select_parallel_value(
            parsed_values,
            schema,
            "source_total_course",
            warnings,
            "el total del curso",
        ),
        warnings=warnings,
    )


def parse_moodle_text(raw_text: str) -> dict[str, Any]:
    lines = [normalize_line(line) for line in raw_text.splitlines()]
    lines = [
        line for line in lines if line and line.casefold() != "ocultar"
    ]
    email_positions = [
        index for index, line in enumerate(lines) if EMAIL_RE.fullmatch(line)
    ]

    records: list[ParsedStudent] = []
    global_warnings: list[str] = []

    if not email_positions:
        return {
            "students": [],
            "warnings": [
                "No se detectaron direcciones de correo en el texto pegado."
            ],
            "detected": 0,
        }

    detected_schema = detect_schema(lines, email_positions[0])

    for position_index, email_index in enumerate(email_positions):
        email = lines[email_index].lower()
        name = find_name(lines, email_index)
        segment_end = (
            email_positions[position_index + 1]
            if position_index + 1 < len(email_positions)
            else len(lines)
        )
        segment = lines[email_index + 1 : segment_end]
        values = [item for item in segment if is_numeric_placeholder(item)]
        warnings: list[str] = []

        if detected_schema:
            schema = detected_schema
        elif len(values) >= len(EXTENDED_SCHEMA):
            schema = EXTENDED_SCHEMA
            warnings.append(
                "No se reconocieron todos los encabezados; se aplicó la "
                "estructura extendida de Moodle (versión 2 y supletorios)."
            )
        else:
            schema = LEGACY_SCHEMA
            warnings.append(
                "No se reconocieron todos los encabezados; se aplicó la "
                "estructura clásica de siete columnas."
            )

        records.append(
            values_to_student(
                name=name,
                email=email,
                raw_values=values,
                schema=schema,
                warnings=warnings,
            )
        )

    duplicates = sorted(
        {
            record.email
            for record in records
            if sum(item.email == record.email for item in records) > 1
        }
    )
    if duplicates:
        global_warnings.append(
            "Correos duplicados detectados: " + ", ".join(duplicates)
        )

    schema_name = (
        "encabezados_detectados"
        if detected_schema
        else "extendido_inferido"
        if any(
            len(
                [
                    item
                    for item in lines[email_index + 1 :]
                    if is_numeric_placeholder(item)
                ]
            )
            >= len(EXTENDED_SCHEMA)
            for email_index in email_positions[:1]
        )
        else "clasico_inferido"
    )

    return {
        "students": [record.to_dict() for record in records],
        "warnings": global_warnings,
        "detected": len(records),
        "schema": schema_name,
        "grade_columns": len(detected_schema)
        if detected_schema
        else len(EXTENDED_SCHEMA)
        if schema_name == "extendido_inferido"
        else len(LEGACY_SCHEMA),
    }
