from __future__ import annotations

import html
from statistics import mean
from typing import Any

from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

import report_completion
import report_quality
from completion_service import get_schedules_extended
from optional_content import is_present
from process_service import get_projects


FOLLOWUP_FIELDS = (
    "project_modality",
    "topic",
    "tutor_name",
    "draft_1_status",
    "draft_2_status",
    "tutor_approval",
    "plagiarism_result",
    "defense_eligible",
    "supplementary_defense",
    "process_status",
)


def _filtered_schedule_data(report_id: int) -> dict[str, Any]:
    schedules = get_schedules_extended(report_id)
    filtered = {
        "complexive": schedules.get("complexive", [])
        if is_present(report_id, "schedule_complexive")
        else [],
        "thesis": schedules.get("thesis", [])
        if is_present(report_id, "schedule_thesis")
        else [],
    }
    all_rows = filtered["complexive"] + filtered["thesis"]
    evaluated = [
        row
        for row in all_rows
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
        "average_compliance": round(mean(percentages), 2) if percentages else None,
        "not_complied": sum(row.get("execution_status") == "No cumplido" for row in evaluated),
        "delayed": sum(row.get("execution_status") == "Cumplido con retraso" for row in evaluated),
        "partial": sum(row.get("execution_status") == "Cumplido parcialmente" for row in evaluated),
    }


def _docx_schedules(document: Any, context: Any, report_id: int) -> None:
    data = _filtered_schedule_data(report_id)
    schedules = data["schedules"]
    available = [
        ("Cronograma de Núcleos y Examen Complexivo", schedules["complexive"], False),
        ("Cronograma del Trabajo de Titulación", schedules["thesis"], True),
    ]
    available = [item for item in available if item[1]]
    if not available:
        return

    report_quality._docx_heading(
        document, context, 1, "Evaluación del cumplimiento de los cronogramas"
    )
    for title, rows, show_phase in available:
        report_quality._docx_heading(document, context, 2, title)
        headers, values = report_completion._schedule_rows(rows, show_phase)
        report_quality._docx_caption(
            document,
            context.table_caption(f"Planificación y ejecución: {title}"),
        )
        widths = (
            [0.55, 1.05, 0.75, 0.65, 0.72, 0.52, 0.70, 0.86]
            if show_phase
            else [1.30, 0.82, 0.72, 0.80, 0.58, 0.82, 0.96]
        )
        report_quality._docx_table(document, headers, values, widths)

    if data["evaluated"]:
        report_quality._docx_body(
            document,
            f"Se evaluó la ejecución de {data['evaluated']} de {data['total']} actividades. "
            f"El cumplimiento promedio registrado fue {report_quality._pct(data['average_compliance'])}. "
            f"Se identificaron {data['delayed']} actividades cumplidas con retraso, "
            f"{data['partial']} cumplidas parcialmente y {data['not_complied']} no cumplidas.",
        )
    else:
        report_quality._docx_body(
            document,
            "Los cronogramas contienen las fechas planificadas, pero todavía no se ha registrado "
            "la información de ejecución necesaria para evaluar su cumplimiento.",
        )


def _pdf_schedules(
    story: list[Any],
    context: Any,
    styles: Any,
    report_id: int,
) -> None:
    data = _filtered_schedule_data(report_id)
    schedules = data["schedules"]
    available = [
        ("Cronograma de Núcleos y Examen Complexivo", schedules["complexive"], False),
        ("Cronograma del Trabajo de Titulación", schedules["thesis"], True),
    ]
    available = [item for item in available if item[1]]
    if not available:
        return

    report_quality._pdf_heading(
        story, context, styles, 1, "Evaluación del cumplimiento de los cronogramas"
    )
    for title, rows, show_phase in available:
        report_quality._pdf_heading(story, context, styles, 2, title)
        headers, values = report_completion._schedule_rows(rows, show_phase)
        pdf_rows = [
            [
                Paragraph(html.escape(str(value)), styles["TableCell"])
                for value in row
            ]
            for row in values
        ]
        report_quality._pdf_caption(
            story,
            styles,
            context.table_caption(f"Planificación y ejecución: {title}"),
        )
        widths = (
            [1.6, 2.9, 2.0, 1.7, 1.9, 1.4, 2.1, 2.4]
            if show_phase
            else [3.5, 2.2, 1.8, 2.0, 1.5, 2.3, 2.7]
        )
        story += [
            report_quality._pdf_table(
                headers,
                pdf_rows,
                [width * cm for width in widths],
            ),
            Spacer(1, 0.2 * cm),
        ]

    if data["evaluated"]:
        report_quality._pdf_body(
            story,
            styles,
            f"Se evaluó la ejecución de {data['evaluated']} de {data['total']} actividades. "
            f"El cumplimiento promedio registrado fue {report_quality._pct(data['average_compliance'])}. "
            f"Se identificaron {data['delayed']} actividades cumplidas con retraso, "
            f"{data['partial']} cumplidas parcialmente y {data['not_complied']} no cumplidas.",
        )
    else:
        report_quality._pdf_body(
            story,
            styles,
            "Los cronogramas contienen las fechas planificadas, pero todavía no se ha registrado "
            "la información de ejecución necesaria para evaluar su cumplimiento.",
        )


def _has_followup(project: dict[str, Any]) -> bool:
    return any(str(project.get(field) or "").strip() for field in FOLLOWUP_FIELDS)


def _add_docx_followup(document: Any, context: Any, report_id: int) -> None:
    projects = [
        project
        for project in get_projects(report_id).get("projects", [])
        if _has_followup(project)
    ]
    if not projects:
        return
    report_quality._docx_heading(
        document, context, 1, "Seguimiento documental del Trabajo de Titulación"
    )
    report_quality._docx_caption(
        document,
        context.table_caption("Seguimiento de los trabajos registrados"),
    )
    rows = [
        [
            project.get("full_name") or "—",
            project.get("career_name") or "—",
            project.get("project_modality") or "—",
            project.get("topic") or "—",
            project.get("tutor_name") or "—",
            project.get("draft_1_status") or "—",
            project.get("draft_2_status") or "—",
            project.get("tutor_approval") or "—",
            project.get("plagiarism_result") or "—",
            project.get("defense_eligible") or "—",
            project.get("process_status") or "—",
        ]
        for project in projects
    ]
    report_quality._docx_table(
        document,
        [
            "Estudiante",
            "Carrera",
            "Modalidad",
            "Tema",
            "Tutor",
            "Borrador 1",
            "Borrador 2",
            "Aprobación tutor",
            "Antiplagio",
            "Defensa",
            "Estado",
        ],
        rows,
        [0.90, 0.75, 0.65, 1.05, 0.75, 0.55, 0.55, 0.65, 0.60, 0.55, 0.55],
    )


def _add_pdf_followup(
    story: list[Any],
    context: Any,
    styles: Any,
    report_id: int,
) -> None:
    projects = [
        project
        for project in get_projects(report_id).get("projects", [])
        if _has_followup(project)
    ]
    if not projects:
        return
    report_quality._pdf_heading(
        story, context, styles, 1, "Seguimiento documental del Trabajo de Titulación"
    )
    rows = [
        [
            Paragraph(html.escape(str(project.get("full_name") or "—")), styles["TableCell"]),
            Paragraph(html.escape(str(project.get("career_name") or "—")), styles["TableCell"]),
            project.get("project_modality") or "—",
            Paragraph(html.escape(str(project.get("topic") or "—")), styles["TableCell"]),
            Paragraph(html.escape(str(project.get("tutor_name") or "—")), styles["TableCell"]),
            project.get("draft_1_status") or "—",
            project.get("draft_2_status") or "—",
            project.get("tutor_approval") or "—",
            project.get("plagiarism_result") or "—",
            project.get("defense_eligible") or "—",
            project.get("process_status") or "—",
        ]
        for project in projects
    ]
    report_quality._pdf_caption(
        story,
        styles,
        context.table_caption("Seguimiento de los trabajos registrados"),
    )
    story += [
        report_quality._pdf_table(
            ["Estudiante", "Carrera", "Modalidad", "Tema", "Tutor", "B1", "B2", "Tutor", "Antiplagio", "Defensa", "Estado"],
            rows,
            [2.4 * cm, 2.0 * cm, 1.5 * cm, 2.6 * cm, 2.0 * cm, 1.0 * cm, 1.0 * cm, 1.2 * cm, 1.5 * cm, 1.2 * cm, 1.2 * cm],
        ),
        Spacer(1, 0.2 * cm),
    ]


def install() -> None:
    if getattr(report_quality, "_completion_fixes_installed", False):
        return

    report_completion._schedule_data = _filtered_schedule_data
    report_quality._docx_schedules = _docx_schedules
    report_quality._pdf_schedules = _pdf_schedules

    for title, values in list(report_quality.METHODOLOGY.items()):
        report_quality.METHODOLOGY[title] = [
            str(value).replace(
                "Instituto Tecnológico Superior Quito Metropolitano",
                "Instituto Superior Tecnológico Quito Metropolitano",
            )
            for value in values
        ]

    current_docx_projects = report_quality._docx_projects
    current_pdf_projects = report_quality._pdf_projects

    def docx_projects(document: Any, context: Any, report_id: int) -> None:
        projects = get_projects(report_id).get("projects", [])
        if projects or is_present(report_id, "schedule_thesis"):
            current_docx_projects(document, context, report_id)
        else:
            report = report_quality._report_data(report_id)
            report_completion._add_docx_global_process(
                document, context, report_id, report
            )
        _add_docx_followup(document, context, report_id)

    def pdf_projects(
        story: list[Any], context: Any, styles: Any, report_id: int
    ) -> None:
        projects = get_projects(report_id).get("projects", [])
        if projects or is_present(report_id, "schedule_thesis"):
            current_pdf_projects(story, context, styles, report_id)
        else:
            report = report_quality._report_data(report_id)
            report_completion._add_pdf_global_process(
                story, context, styles, report_id, report
            )
        _add_pdf_followup(story, context, styles, report_id)

    report_quality._docx_projects = docx_projects
    report_quality._pdf_projects = pdf_projects
    report_quality._completion_fixes_installed = True
