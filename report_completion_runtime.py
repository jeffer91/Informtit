from __future__ import annotations

import html
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, Spacer

import report_completion
import report_quality
from optional_content import is_present
from process_service import get_projects


def _has_nucleus_data(data: dict[str, Any]) -> bool:
    eligibility = data["eligibility"]
    return bool(
        eligibility.get("unmatched")
        or any(
            row.get(key) is not None
            for row in eligibility.get("rows", [])
            if row.get("option") == "Examen Complexivo"
            for key in ("nucleus_1", "nucleus_2", "nucleus_3", "nucleus_4")
        )
    )


def _has_thesis_scope(report_id: int, data: dict[str, Any]) -> bool:
    return bool(
        data["projects"]["summary"]["total"]
        or is_present(report_id, "schedule_thesis")
    )


def _executive_data(original):
    def load(report_id: int) -> dict[str, Any]:
        data = original(report_id)
        data["has_nucleus_data"] = _has_nucleus_data(data)
        data["has_thesis_scope"] = _has_thesis_scope(report_id, data)
        data["has_complexive_scope"] = bool(data["complexive"]["totals"]["registered"])

        indicators = []
        for label, value in data["indicators"]:
            if label == "Habilitados por los cuatro núcleos" and not data["has_nucleus_data"]:
                continue
            if label in {
                "Aprobados en ordinario",
                "Enviados a supletorio",
                "Recuperados mediante supletorio",
                "Aprobados finales en Complexivo",
                "Reprobados finales en Complexivo",
                "No evaluados en Complexivo",
            } and not data["has_complexive_scope"]:
                continue
            if label in {
                "Estudiantes en Trabajo de Titulación",
                "Aprobados en Trabajo de Titulación",
            } and not data["has_thesis_scope"]:
                continue
            indicators.append((label, value))
        data["indicators"] = indicators
        return data

    return load


def _automatic_incidents(original):
    def generate(data: dict[str, Any]) -> list[dict[str, str]]:
        incidents = original(data)
        if not data.get("has_nucleus_data", _has_nucleus_data(data)):
            incidents = [
                item
                for item in incidents
                if item.get("category") not in {"Núcleos", "Correspondencia de datos"}
            ]
        if not data["schedules"]["total"]:
            incidents = [
                item for item in incidents if item.get("category") != "Cronograma"
            ]
        return incidents

    return generate


def _global_rows(report_id: int, report: dict[str, Any]) -> list[list[Any]]:
    complexive = report_completion._complexive_data(report)["totals"]
    projects = get_projects(report_id)["summary"]
    rows: list[list[Any]] = []
    if complexive["registered"]:
        rows.append(
            [
                "Examen Complexivo",
                complexive["registered"],
                complexive["registered"] - complexive["not_evaluated"],
                complexive["final_approved"],
                complexive["final_failed"],
                complexive["not_evaluated"],
                report_quality._pct(complexive["approval_percentage"]),
            ]
        )
    if projects["total"] or is_present(report_id, "schedule_thesis"):
        approval = (
            round(projects["approved"] / projects["total"] * 100, 2)
            if projects["total"]
            else 0.0
        )
        rows.append(
            [
                "Trabajo de Titulación",
                projects["total"],
                projects["total"],
                projects["approved"],
                projects["failed"],
                0,
                report_quality._pct(approval),
            ]
        )
    return rows


def _add_docx_global_process(
    document: Any,
    context: Any,
    report_id: int,
    report: dict[str, Any],
) -> None:
    rows = _global_rows(report_id, report)
    if not rows:
        return
    report_quality._docx_heading(document, context, 1, "Consolidado general del proceso")
    report_quality._docx_caption(
        document,
        context.table_caption("Resultados consolidados por opción de titulación"),
    )
    report_quality._docx_table(
        document,
        ["Opción", "Registrados", "Evaluados", "Aprobados", "Reprobados", "No evaluados", "% aprobación"],
        rows,
        [2.0, 0.8, 0.8, 0.8, 0.8, 0.85, 0.95],
    )


def _add_pdf_global_process(
    story: list[Any],
    context: Any,
    styles: Any,
    report_id: int,
    report: dict[str, Any],
) -> None:
    rows = _global_rows(report_id, report)
    if not rows:
        return
    report_quality._pdf_heading(story, context, styles, 1, "Consolidado general del proceso")
    report_quality._pdf_caption(
        story,
        styles,
        context.table_caption("Resultados consolidados por opción de titulación"),
    )
    story += [
        report_quality._pdf_table(
            ["Opción", "Registrados", "Evaluados", "Aprobados", "Reprobados", "No evaluados", "% aprobación"],
            rows,
            [4.5 * cm, 2.0 * cm, 2.0 * cm, 2.0 * cm, 2.0 * cm, 2.2 * cm, 2.3 * cm],
        ),
        Spacer(1, 0.2 * cm),
    ]


def _conclusions(data: dict[str, Any], incident_count: int) -> list[str]:
    conclusions: list[str] = []
    if data["requirements"]:
        conclusions.append(
            f"El cumplimiento integral de requisitos alcanzó "
            f"{report_quality._pct(data['requirements']['percentage'])} sobre "
            f"{data['requirements']['total']} estudiantes únicos."
        )
    if data.get("has_nucleus_data", _has_nucleus_data(data)):
        eligibility = data["eligibility"]["summary"]
        conclusions.append(
            f"La habilitación para el Examen Complexivo fue confirmada para "
            f"{eligibility['habilitated']} de {eligibility['complexive_candidates']} candidatos, "
            "una vez verificada la aprobación individual de los cuatro núcleos."
        )
    if data["complexive"]["totals"]["registered"]:
        totals = data["complexive"]["totals"]
        conclusions.append(
            f"El Examen Complexivo concluyó con {totals['final_approved']} aprobados, "
            f"{totals['final_failed']} reprobados y {totals['not_evaluated']} no evaluados."
        )
    if data.get("has_thesis_scope"):
        projects = data["projects"]["summary"]
        if projects["total"]:
            conclusions.append(
                f"En Trabajo de Titulación se registraron {projects['total']} estudiantes, "
                f"de los cuales {projects['approved']} aprobaron y {projects['failed']} reprobaron."
            )
        else:
            conclusions.append(
                "No se registraron estudiantes en Trabajo de Titulación durante el período analizado."
            )
    conclusions.append(
        "La trazabilidad del proceso requiere mantener correspondencia entre la base institucional, "
        "las notas de núcleos, las evaluaciones, las actas y las evidencias de ejecución. "
        f"Se identificaron {incident_count} novedades automáticas o registradas para seguimiento."
    )
    return conclusions


def _add_docx_post_sections(
    document: Any,
    context: Any,
    report: dict[str, Any],
) -> None:
    report_id = int(report["id"])
    data, incidents, actions = report_completion._all_incidents(report_id)

    if incidents:
        report_quality._docx_heading(document, context, 1, "Novedades e incidencias del proceso")
        report_quality._docx_caption(
            document, context.table_caption("Novedades e incidencias registradas")
        )
        report_quality._docx_table(
            document,
            ["Categoría", "Descripción", "Responsable", "Tratamiento", "Estado", "Evidencia"],
            [[item.get("category") or "—", item.get("description") or "—", item.get("responsible") or "—", item.get("treatment") or "—", item.get("status") or "—", item.get("evidence") or "—"] for item in incidents],
            [0.8, 1.75, 1.2, 1.55, 0.75, 0.95],
        )

    if data["complexive"]["totals"]["registered"] or data.get("has_nucleus_data") or data["schedules"]["evaluated"]:
        report_quality._docx_heading(document, context, 1, "Análisis comparativo y discusión de resultados")
        if data["complexive"]["totals"]["registered"]:
            totals = data["complexive"]["totals"]
            report_quality._docx_body(
                document,
                f"El Examen Complexivo registró una aprobación final global de "
                f"{report_quality._pct(totals['approval_percentage'])}. Participaron "
                f"{totals['supplementary']} estudiantes en supletorio y {totals['recovered']} "
                "lograron recuperar su condición académica mediante esta oportunidad.",
            )
        if data["schedules"]["average_compliance"] is not None:
            report_quality._docx_body(
                document,
                f"El cumplimiento promedio de las actividades evaluadas del cronograma fue "
                f"{report_quality._pct(data['schedules']['average_compliance'])}.",
            )

    report_quality._docx_heading(document, context, 1, "Conclusiones")
    for conclusion in _conclusions(data, len(incidents)):
        report_quality._docx_bullet(document, conclusion)

    if actions:
        report_quality._docx_heading(document, context, 1, "Recomendaciones")
        for action in actions:
            report_quality._docx_bullet(document, action["action"])

        report_quality._docx_heading(document, context, 1, "Plan de mejora")
        report_quality._docx_caption(
            document, context.table_caption("Plan de mejora del proceso de titulación")
        )
        report_quality._docx_table(
            document,
            ["Hallazgo", "Acción de mejora", "Responsable", "Fecha límite", "Indicador", "Evidencia", "Estado"],
            [[item.get("finding") or "—", item.get("action") or "—", item.get("responsible") or "—", item.get("due_date") or "Por definir", item.get("indicator") or "—", item.get("evidence") or "—", item.get("status") or "Pendiente"] for item in actions],
            [1.45, 1.65, 1.1, 0.75, 1.1, 0.9, 0.75],
        )

    report_quality._docx_heading(document, context, 1, "Referencias legales e institucionales")
    for reference in report_completion._REFERENCE_LIST:
        report_quality._docx_bullet(document, reference)


def _add_pdf_post_sections(
    story: list[Any],
    context: Any,
    styles: Any,
    report: dict[str, Any],
) -> None:
    report_id = int(report["id"])
    data, incidents, actions = report_completion._all_incidents(report_id)

    if incidents:
        report_quality._pdf_heading(story, context, styles, 1, "Novedades e incidencias del proceso")
        rows = [[Paragraph(html.escape(str(item.get("category") or "—")), styles["TableCell"]), Paragraph(html.escape(str(item.get("description") or "—")), styles["TableCell"]), Paragraph(html.escape(str(item.get("responsible") or "—")), styles["TableCell"]), Paragraph(html.escape(str(item.get("treatment") or "—")), styles["TableCell"]), item.get("status") or "—", Paragraph(html.escape(str(item.get("evidence") or "—")), styles["TableCell"])] for item in incidents]
        report_quality._pdf_caption(story, styles, context.table_caption("Novedades e incidencias registradas"))
        story += [
            report_quality._pdf_table(
                ["Categoría", "Descripción", "Responsable", "Tratamiento", "Estado", "Evidencia"],
                rows,
                [2.0 * cm, 4.2 * cm, 3.0 * cm, 4.0 * cm, 2.0 * cm, 2.6 * cm],
            ),
            Spacer(1, 0.2 * cm),
        ]

    if data["complexive"]["totals"]["registered"] or data.get("has_nucleus_data") or data["schedules"]["evaluated"]:
        report_quality._pdf_heading(story, context, styles, 1, "Análisis comparativo y discusión de resultados")
        if data["complexive"]["totals"]["registered"]:
            totals = data["complexive"]["totals"]
            report_quality._pdf_body(
                story,
                styles,
                f"El Examen Complexivo registró una aprobación final global de "
                f"{report_quality._pct(totals['approval_percentage'])}. Participaron "
                f"{totals['supplementary']} estudiantes en supletorio y {totals['recovered']} "
                "lograron recuperar su condición académica mediante esta oportunidad.",
            )
        if data["schedules"]["average_compliance"] is not None:
            report_quality._pdf_body(
                story,
                styles,
                f"El cumplimiento promedio de las actividades evaluadas del cronograma fue "
                f"{report_quality._pct(data['schedules']['average_compliance'])}.",
            )

    report_quality._pdf_heading(story, context, styles, 1, "Conclusiones")
    for conclusion in _conclusions(data, len(incidents)):
        report_quality._pdf_bullet(story, styles, conclusion)

    if actions:
        report_quality._pdf_heading(story, context, styles, 1, "Recomendaciones")
        for action in actions:
            report_quality._pdf_bullet(story, styles, action["action"])

        report_quality._pdf_heading(story, context, styles, 1, "Plan de mejora")
        rows = [[Paragraph(html.escape(str(item.get("finding") or "—")), styles["TableCell"]), Paragraph(html.escape(str(item.get("action") or "—")), styles["TableCell"]), Paragraph(html.escape(str(item.get("responsible") or "—")), styles["TableCell"]), item.get("due_date") or "Por definir", Paragraph(html.escape(str(item.get("indicator") or "—")), styles["TableCell"]), Paragraph(html.escape(str(item.get("evidence") or "—")), styles["TableCell"]), item.get("status") or "Pendiente"] for item in actions]
        report_quality._pdf_caption(story, styles, context.table_caption("Plan de mejora del proceso de titulación"))
        story += [
            report_quality._pdf_table(
                ["Hallazgo", "Acción", "Responsable", "Fecha", "Indicador", "Evidencia", "Estado"],
                rows,
                [3.2 * cm, 3.6 * cm, 2.7 * cm, 1.8 * cm, 3.0 * cm, 2.4 * cm, 1.8 * cm],
            ),
            Spacer(1, 0.2 * cm),
        ]

    report_quality._pdf_heading(story, context, styles, 1, "Referencias legales e institucionales")
    for reference in report_completion._REFERENCE_LIST:
        report_quality._pdf_bullet(story, styles, reference)


def install() -> None:
    if getattr(report_quality, "_completion_runtime_installed", False):
        return

    original_executive_data = report_completion._executive_data
    original_incidents = report_completion._automatic_incidents
    original_docx_summary = report_completion._add_docx_executive_summary
    original_pdf_summary = report_completion._add_pdf_executive_summary

    report_completion._executive_data = _executive_data(original_executive_data)
    report_completion._automatic_incidents = _automatic_incidents(original_incidents)
    report_completion._add_docx_global_process = _add_docx_global_process
    report_completion._add_pdf_global_process = _add_pdf_global_process

    def docx_summary(document: Any, report_id: int) -> None:
        original_docx_summary(document, report_id)
        document.add_page_break()

    def pdf_summary(story: list[Any], styles: Any, report_id: int) -> None:
        original_pdf_summary(story, styles, report_id)
        story.append(PageBreak())

    report_completion._add_docx_executive_summary = docx_summary
    report_completion._add_pdf_executive_summary = pdf_summary
    report_quality._docx_post_sections = _add_docx_post_sections
    report_quality._pdf_post_sections = _add_pdf_post_sections
    report_quality._completion_runtime_installed = True
