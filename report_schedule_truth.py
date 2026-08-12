from __future__ import annotations

import html
from statistics import mean
from typing import Any

from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

import report_enhancements as enh
import report_quality
from completion_service import get_schedules_extended
from optional_content import is_present


def _schedule_data(report_id: int) -> dict[str, Any]:
    schedules = get_schedules_extended(report_id)
    filtered = {
        "complexive": schedules.get("complexive", []) if is_present(report_id, "schedule_complexive") else [],
        "thesis": schedules.get("thesis", []) if is_present(report_id, "schedule_thesis") else [],
    }
    all_rows = filtered["complexive"] + filtered["thesis"]
    evaluated = [
        row for row in all_rows
        if row.get("execution_status")
        or row.get("compliance_percentage") is not None
        or row.get("executed_date")
    ]
    percentages = [
        float(row["compliance_percentage"])
        for row in evaluated
        if row.get("compliance_percentage") is not None
    ]
    return {
        "schedules": filtered,
        "total": len(all_rows),
        "evaluated": len(evaluated),
        "average": round(mean(percentages), 2) if percentages else None,
        "pending": len(all_rows) - len(evaluated),
        "delayed": sum("retras" in str(row.get("execution_status") or "").lower() for row in evaluated),
        "partial": sum("parcial" in str(row.get("execution_status") or "").lower() for row in evaluated),
        "not_complied": sum(str(row.get("execution_status") or "").lower() == "no cumplido" for row in evaluated),
    }


def _rows(rows: list[dict[str, Any]], show_phase: bool) -> tuple[list[str], list[list[Any]]]:
    headers = (["Fase"] if show_phase else []) + [
        "Actividad",
        "Fecha planificada",
        "Fecha ejecutada",
        "Estado",
        "% cumplimiento",
        "Evidencia",
        "Observación",
    ]
    values: list[list[Any]] = []
    for row in rows:
        start = str(row.get("start_date") or "—")
        end = str(row.get("end_date") or start)
        planned = start if start == end else f"{start} a {end}"
        current = [
            row.get("activity") or "—",
            planned,
            row.get("executed_date") or "—",
            row.get("execution_status") or "Sin evaluar",
            report_quality._pct(row.get("compliance_percentage")) if row.get("compliance_percentage") is not None else "—",
            row.get("evidence") or "—",
            row.get("observation") or "—",
        ]
        if show_phase:
            current.insert(0, row.get("phase") or "—")
        values.append(current)
    return headers, values


def _analysis_text(data: dict[str, Any]) -> str:
    if not data["total"]:
        return ""
    if not data["evaluated"]:
        return (
            f"Se registraron {data['total']} actividades planificadas, pero ninguna contiene todavía datos suficientes de ejecución. "
            "Por esta razón no se asigna automáticamente un porcentaje de cumplimiento; la evaluación deberá completarse con fecha ejecutada, estado, porcentaje, evidencia y observación."
        )
    average = report_quality._pct(data["average"]) if data["average"] is not None else "no calculable"
    return (
        f"De {data['total']} actividades planificadas, {data['evaluated']} cuentan con información de ejecución y {data['pending']} permanecen sin evaluar. "
        f"El cumplimiento promedio registrado es {average}. Se identificaron {data['delayed']} actividades con retraso, "
        f"{data['partial']} parcialmente cumplidas y {data['not_complied']} no cumplidas."
    )


def _docx_schedules(document: Any, context: Any, report_id: int) -> None:
    data = _schedule_data(report_id)
    available = [
        ("Cronograma de Núcleos y Examen Complexivo", data["schedules"]["complexive"], False),
        ("Cronograma del Trabajo de Titulación", data["schedules"]["thesis"], True),
    ]
    available = [item for item in available if item[1]]
    if not available:
        return
    report_quality._docx_heading(document, context, 1, "Evaluación del cumplimiento de los cronogramas")
    report_quality._docx_body(document, "La evaluación compara la planificación registrada con la información real de ejecución. La existencia de una fecha planificada no se interpreta por sí sola como evidencia de cumplimiento.")
    for title, rows, show_phase in available:
        report_quality._docx_heading(document, context, 2, title)
        report_quality._docx_body(document, f"La tabla presenta {len(rows)} actividades y diferencia las fechas previstas de los datos de ejecución efectivamente registrados.")
        headers, values = _rows(rows, show_phase)
        report_quality._docx_caption(document, context.table_caption(f"Planificación y ejecución: {title}"))
        widths = [0.5, 1.1, .85, .75, .72, .62, .95, 1.0] if show_phase else [1.25, .9, .8, .75, .65, 1.0, 1.05]
        enh._docx_table_pretty(document, headers, values, widths)
    report_quality._docx_body(document, _analysis_text(data))


def _pdf_schedules(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    data = _schedule_data(report_id)
    available = [
        ("Cronograma de Núcleos y Examen Complexivo", data["schedules"]["complexive"], False),
        ("Cronograma del Trabajo de Titulación", data["schedules"]["thesis"], True),
    ]
    available = [item for item in available if item[1]]
    if not available:
        return
    report_quality._pdf_heading(story, context, styles, 1, "Evaluación del cumplimiento de los cronogramas")
    report_quality._pdf_body(story, styles, "La evaluación compara planificación con ejecución real y no asigna automáticamente un 100 % por la sola existencia de fechas planificadas.")
    for title, rows, show_phase in available:
        report_quality._pdf_heading(story, context, styles, 2, title)
        headers, values = _rows(rows, show_phase)
        pdf_rows = [[Paragraph(html.escape(str(value)), styles["TableCell"]) for value in row] for row in values]
        report_quality._pdf_caption(story, styles, context.table_caption(f"Planificación y ejecución: {title}"))
        widths = [1.3, 2.8, 2.3, 2.0, 2.0, 1.8, 3.0, 3.0] if show_phase else [3.4, 2.5, 2.2, 2.0, 1.9, 3.1, 3.2]
        story += [enh._pdf_table_pretty(headers, pdf_rows, [width * cm for width in widths]), Spacer(1, .16 * cm)]
    report_quality._pdf_body(story, styles, _analysis_text(data))


def install() -> None:
    report_quality._docx_schedules = _docx_schedules
    report_quality._pdf_schedules = _pdf_schedules
