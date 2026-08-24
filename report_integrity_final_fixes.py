from __future__ import annotations

import re
from typing import Any

import report_full_detail as full
import report_integrity_core as integrity
import report_integrity_pdf as integrity_pdf


_BASE_TABLE = full._table
_BASE_STATEFUL_TEXT = integrity_pdf.stateful_text


def _percent_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").replace("%", "").replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def dense_ranks(values: list[float | None]) -> list[int]:
    ranks: list[int] = []
    current_rank = 0
    previous: float | None = None
    first = True
    for value in values:
        if first or value != previous:
            current_rank += 1
        ranks.append(current_rank)
        previous = value
        first = False
    return ranks


def table_tie_aware(headers: list[str], rows: list[list[Any]], widths: list[float], styles: Any, font_size: float = 7.2) -> Any:
    adjusted = rows
    if (
        len(headers) >= 3
        and str(headers[0]).strip().casefold() == "puesto"
        and str(headers[1]).strip().casefold() == "carrera"
        and "aprob" in str(headers[2]).casefold()
    ):
        values = [_percent_value(row[2]) if len(row) > 2 else None for row in rows]
        ranks = dense_ranks(values)
        adjusted = []
        for row, rank in zip(rows, ranks):
            current = list(row)
            if current:
                current[0] = rank
            adjusted.append(current)
    return _BASE_TABLE(headers, adjusted, widths, styles, font_size)


def _evaluated_zero_count(report_id: int) -> int:
    return sum(
        integrity.nucleus_state(student) in {"approved", "failed"}
        and integrity.number(student.get("final_grade")) == 0
        for course in integrity.strict_nuclei(report_id).get("courses", [])
        for student in course.get("students", [])
    )


def stateful_text(value: Any) -> str:
    text = _BASE_STATEFUL_TEXT(value)
    report_id = getattr(integrity_pdf._LOCAL, "report_id", None)
    if not report_id or "registros con nota cero" not in text.casefold():
        return text
    total = _evaluated_zero_count(int(report_id))
    replacement = (
        f"Se identificaron {total} calificaciones iguales a cero entre los registros evaluados."
        if total
        else "No se identificaron calificaciones iguales a cero entre los registros evaluados."
    )
    return re.sub(
        r"Se identificaron\s+\d+\s+registros con nota cero\.",
        replacement,
        text,
        count=1,
        flags=re.IGNORECASE,
    )


def install() -> None:
    full._table = table_tie_aware
    integrity_pdf.stateful_text = stateful_text
