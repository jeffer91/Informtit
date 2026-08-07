from __future__ import annotations

import html
from typing import Any

from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

import report_completion
import report_quality
from completion_service import get_completion_data
from nuclei_multicampus import get_nuclei
from process_service import get_projects


def _nucleus_summary(report_id: int) -> dict[str, int]:
    courses = get_nuclei(report_id).get("courses", [])
    graded = 0
    approved = 0
    failed = 0
    unevaluated = 0
    for course in courses:
        students = course.get("students", [])
        for student in students:
            grade = student.get("final_grade")
            if grade is None:
                unevaluated += 1
                continue
            graded += 1
            if float(grade) >= 7.0:
                approved += 1
            else:
                failed += 1
    return {
        "courses": len(courses),
        "records": graded + unevaluated,
        "graded": graded,
        "approved": approved,
        "failed": failed,
        "unevaluated": unevaluated,
    }


def _executive_data(report_id: int) -> dict[str, Any]:
    report = report_quality._report_data(report_id)
    requirements = report_completion.corrected_requirement_analysis(report_id)
    nuclei = _nucleus_summary(report_id)
    complexive = report_completion._complexive_data(report)
    projects = get_projects(report_id)
    schedules = report_completion._schedule_data(report_id)
    completion = get_completion_data(report_id)
    totals = complexive["totals"]

    indicators: list[tuple[str, Any]] = []
    if requirements:
        indicators.extend(
            [
                ("Registros en Requisitos", requirements["total"]),
                ("Cumplimiento integral de Requisitos", requirements["complete"]),
            ]
        )
    if nuclei["courses"]:
        indicators.extend(
            [
                ("Cursos de Núcleos cargados", nuclei["courses"]),
                ("Registros de notas de Núcleos", nuclei["records"]),
                ("Registros aprobados en Núcleos", nuclei["approved"]),
            ]
        )
    if totals["registered"]:
        indicators.extend(
            [
                ("Registrados en Examen Complexivo", totals["registered"]),
                ("Aprobados finales en Complexivo", totals["final_approved"]),
                ("Reprobados finales en Complexivo", totals["final_failed"]),
                ("No evaluados en Complexivo", totals["not_evaluated"]),
            ]
        )
    if projects["summary"]["total"]:
        indicators.extend(
            [
                ("Registrados en Trabajo de Titulación", projects["summary"]["total"]),
                ("Aprobados en Trabajo de Titulación", projects["summary"]["approved"]),
            ]
        )

    return {
        "report": report,
        "requirements": requirements,
        "nuclei": nuclei,
        "complexive": complexive,
        "projects": projects,
        "schedules": schedules,
        "completion": completion,
        # Se conserva una estructura vacía por compatibilidad con funciones antiguas,
        # pero no se utiliza para relacionar módulos.
        "eligibility": {"summary": {}},
        "indicators": indicators,
    }


def _automatic_incidents(data: dict[str, Any]) -> list[dict[str, str]]:
    incidents: list[dict[str, str]] = []
    requirements = data["requirements"]
    nuclei = data["nuclei"]
    complexive = data["complexive"]["totals"]
    schedules = data["schedules"]

    if requirements and (requirements["pending"] or requirements["incomplete"]):
        incidents.append(
            {
                "category": "Requisitos",
                "description": (
                    f"Se registraron {requirements['pending']} casos con al menos un requisito en NO CUMPLE "
                    f"y {requirements['incomplete']} con información incompleta."
                ),
                "responsible": "Áreas responsables de requisitos",
                "treatment": "Revisar y completar la información de este módulo.",
                "status": "En seguimiento",
                "evidence": "Matriz de Requisitos",
            }
        )

    if nuclei["unevaluated"]:
        incidents.append(
            {
                "category": "Núcleos",
                "description": f"Existen {nuclei['unevaluated']} registros de estudiantes sin nota final en los cursos de Núcleos cargados.",
                "responsible": "Coordinaciones de carrera",
                "treatment": "Completar o corregir las calificaciones faltantes dentro del módulo de Núcleos.",
                "status": "En seguimiento",
                "evidence": "Cursos de Núcleos cargados",
            }
        )

    if complexive["not_evaluated"]:
        incidents.append(
            {
                "category": "Examen Complexivo",
                "description": f"Se registraron {complexive['not_evaluated']} estudiantes sin evaluación completa en el Examen Complexivo.",
                "responsible": "Coordinaciones de carrera",
                "treatment": "Revisar las notas del Examen Complexivo dentro de su propio módulo.",
                "status": "En seguimiento",
                "evidence": "Consolidado del Examen Complexivo",
            }
        )

    if schedules["total"] and schedules["evaluated"] < schedules["total"]:
        incidents.append(
            {
                "category": "Cronograma",
                "description": f"La ejecución fue evaluada en {schedules['evaluated']} de {schedules['total']} actividades planificadas.",
                "responsible": "Responsables de cada actividad",
                "treatment": "Completar la información de ejecución pendiente.",
                "status": "Abierto",
                "evidence": "Matriz de evaluación de cronogramas",
            }
        )
    return incidents


def _automatic_actions(data: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for incident in _automatic_incidents(data):
        actions.append(
            {
                "finding": incident["description"],
                "action": incident["treatment"],
                "responsible": incident["responsible"],
                "due_date": "",
                "indicator": "Porcentaje de registros corregidos",
                "evidence": incident["evidence"],
                "status": "Pendiente",
            }
        )
    return actions


def _add_docx_objectives(document: Any, context: Any, report: dict[str, Any]) -> None:
    report_quality._docx_heading(document, context, 1, "Objetivos")
    report_quality._docx_heading(document, context, 2, "Objetivo general")
    report_quality._docx_body(
        document,
        f"Analizar la información registrada para el período académico {report.get('period') or 'analizado'} mediante cuatro componentes independientes: Requisitos, Núcleos, Examen Complexivo y Trabajo de Titulación.",
    )
    report_quality._docx_heading(document, context, 2, "Objetivos específicos")
    for item in (
        "Analizar el cumplimiento de los requisitos registrados.",
        "Analizar los cursos, participantes y calificaciones cargados en Núcleos.",
        "Analizar de forma independiente los resultados del Examen Complexivo.",
        "Analizar de forma independiente los resultados y seguimiento del Trabajo de Titulación.",
        "Identificar novedades y oportunidades de mejora dentro de cada componente.",
    ):
        report_quality._docx_bullet(document, item)


def _add_pdf_objectives(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> None:
    report_quality._pdf_heading(story, context, styles, 1, "Objetivos")
    report_quality._pdf_heading(story, context, styles, 2, "Objetivo general")
    report_quality._pdf_body(
        story,
        styles,
        f"Analizar la información registrada para el período académico {report.get('period') or 'analizado'} mediante cuatro componentes independientes: Requisitos, Núcleos, Examen Complexivo y Trabajo de Titulación.",
    )
    report_quality._pdf_heading(story, context, styles, 2, "Objetivos específicos")
    for item in (
        "Analizar el cumplimiento de los requisitos registrados.",
        "Analizar los cursos, participantes y calificaciones cargados en Núcleos.",
        "Analizar de forma independiente los resultados del Examen Complexivo.",
        "Analizar de forma independiente los resultados y seguimiento del Trabajo de Titulación.",
        "Identificar novedades y oportunidades de mejora dentro de cada componente.",
    ):
        report_quality._pdf_bullet(story, styles, item)


def _methodology_paragraphs(report_id: int, report: dict[str, Any]) -> list[str]:
    requirements = report_completion.corrected_requirement_analysis(report_id)
    nuclei = _nucleus_summary(report_id)
    complexive = report_completion._complexive_data(report)["totals"]
    projects = get_projects(report_id)["summary"]
    cutoff = report_quality.base.format_date(report.get("cutoff_date")) if report.get("cutoff_date") else "no registrada"
    return [
        f"La información fue procesada con fecha de corte {cutoff} para el período {report.get('period') or 'analizado'}.",
        "Informtit organiza el informe en módulos independientes. Requisitos, Núcleos, Examen Complexivo y Trabajo de Titulación se analizan con la información cargada específicamente en cada módulo.",
        "No se utiliza el resultado de Requisitos para habilitar o excluir registros de Núcleos; tampoco se utiliza Núcleos para habilitar o excluir registros del Examen Complexivo. El Trabajo de Titulación mantiene igualmente su propia población y seguimiento.",
        f"El módulo de Requisitos contiene {requirements['total'] if requirements else 0} registros; el módulo de Núcleos contiene {nuclei['courses']} cursos y {nuclei['records']} registros de estudiante; el Examen Complexivo contiene {complexive['registered']} registros; y Trabajo de Titulación contiene {projects['total']} registros.",
        "Las coincidencias de nombre, correo, cédula o sede entre módulos no generan relaciones automáticas. Cada sección conserva sus propios datos y cálculos.",
        "En Núcleos, la aprobación de cada registro se determina con una nota final igual o superior a 7,00/10. En Examen Complexivo se mantienen las reglas de evaluación propias del módulo, sin depender de las notas de Núcleos.",
    ]


def _add_docx_post_sections(document: Any, context: Any, report: dict[str, Any]) -> None:
    report_id = int(report["id"])
    data = _executive_data(report_id)
    incidents = _automatic_incidents(data) + data["completion"]["incidents"]
    actions = _automatic_actions(data) + data["completion"]["actions"]

    if incidents:
        report_quality._docx_heading(document, context, 1, "Novedades e incidencias del proceso")
        report_quality._docx_caption(document, context.table_caption("Novedades e incidencias registradas"))
        report_quality._docx_table(
            document,
            ["Categoría", "Descripción", "Responsable", "Tratamiento", "Estado", "Evidencia"],
            [[item.get("category") or "—", item.get("description") or "—", item.get("responsible") or "—", item.get("treatment") or "—", item.get("status") or "—", item.get("evidence") or "—"] for item in incidents],
            [0.8, 1.75, 1.2, 1.55, 0.75, 0.95],
        )

    report_quality._docx_heading(document, context, 1, "Conclusiones")
    if data["requirements"]:
        report_quality._docx_bullet(
            document,
            f"En Requisitos, {data['requirements']['complete']} de {data['requirements']['total']} registros presentan cumplimiento integral según la información cargada en ese módulo.",
        )
    if data["nuclei"]["courses"]:
        report_quality._docx_bullet(
            document,
            f"En Núcleos se cargaron {data['nuclei']['courses']} cursos con {data['nuclei']['records']} registros de estudiante; {data['nuclei']['approved']} registros aprobaron y {data['nuclei']['failed']} reprobaron.",
        )
    totals = data["complexive"]["totals"]
    if totals["registered"]:
        report_quality._docx_bullet(
            document,
            f"En Examen Complexivo se registraron {totals['registered']} estudiantes, con {totals['final_approved']} aprobados finales, {totals['final_failed']} reprobados y {totals['not_evaluated']} no evaluados.",
        )
    projects = data["projects"]["summary"]
    if projects["total"]:
        report_quality._docx_bullet(
            document,
            f"En Trabajo de Titulación se registraron {projects['total']} estudiantes, con {projects['approved']} aprobados y {projects['failed']} reprobados.",
        )
    report_quality._docx_bullet(
        document,
        "Los resultados de las cuatro secciones son independientes y no implican correspondencia automática de estudiantes entre módulos.",
    )

    if actions:
        report_quality._docx_heading(document, context, 1, "Recomendaciones")
        for action in actions:
            report_quality._docx_bullet(document, action["action"])

    report_quality._docx_heading(document, context, 1, "Referencias legales e institucionales")
    for reference in getattr(report_completion, "_REFERENCE_LIST", (
        "Constitución de la República del Ecuador.",
        "Ley Orgánica de Educación Superior.",
        "Reglamento de Régimen Académico.",
        "Normativa institucional aplicable al proceso de titulación.",
    )):
        report_quality._docx_bullet(document, reference)


def _add_pdf_post_sections(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> None:
    report_id = int(report["id"])
    data = _executive_data(report_id)
    incidents = _automatic_incidents(data) + data["completion"]["incidents"]
    actions = _automatic_actions(data) + data["completion"]["actions"]

    if incidents:
        report_quality._pdf_heading(story, context, styles, 1, "Novedades e incidencias del proceso")
        rows = [
            [
                Paragraph(html.escape(str(item.get("category") or "—")), styles["TableCell"]),
                Paragraph(html.escape(str(item.get("description") or "—")), styles["TableCell"]),
                Paragraph(html.escape(str(item.get("responsible") or "—")), styles["TableCell"]),
                Paragraph(html.escape(str(item.get("treatment") or "—")), styles["TableCell"]),
                item.get("status") or "—",
                Paragraph(html.escape(str(item.get("evidence") or "—")), styles["TableCell"]),
            ]
            for item in incidents
        ]
        report_quality._pdf_caption(story, styles, context.table_caption("Novedades e incidencias registradas"))
        story += [
            report_quality._pdf_table(
                ["Categoría", "Descripción", "Responsable", "Tratamiento", "Estado", "Evidencia"],
                rows,
                [2.0 * cm, 4.2 * cm, 3.0 * cm, 4.0 * cm, 2.0 * cm, 2.6 * cm],
            ),
            Spacer(1, 0.2 * cm),
        ]

    report_quality._pdf_heading(story, context, styles, 1, "Conclusiones")
    if data["requirements"]:
        report_quality._pdf_bullet(
            story,
            styles,
            f"En Requisitos, {data['requirements']['complete']} de {data['requirements']['total']} registros presentan cumplimiento integral según la información cargada en ese módulo.",
        )
    if data["nuclei"]["courses"]:
        report_quality._pdf_bullet(
            story,
            styles,
            f"En Núcleos se cargaron {data['nuclei']['courses']} cursos con {data['nuclei']['records']} registros de estudiante; {data['nuclei']['approved']} registros aprobaron y {data['nuclei']['failed']} reprobaron.",
        )
    totals = data["complexive"]["totals"]
    if totals["registered"]:
        report_quality._pdf_bullet(
            story,
            styles,
            f"En Examen Complexivo se registraron {totals['registered']} estudiantes, con {totals['final_approved']} aprobados finales, {totals['final_failed']} reprobados y {totals['not_evaluated']} no evaluados.",
        )
    projects = data["projects"]["summary"]
    if projects["total"]:
        report_quality._pdf_bullet(
            story,
            styles,
            f"En Trabajo de Titulación se registraron {projects['total']} estudiantes, con {projects['approved']} aprobados y {projects['failed']} reprobados.",
        )
    report_quality._pdf_bullet(
        story,
        styles,
        "Los resultados de las cuatro secciones son independientes y no implican correspondencia automática de estudiantes entre módulos.",
    )

    if actions:
        report_quality._pdf_heading(story, context, styles, 1, "Recomendaciones")
        for action in actions:
            report_quality._pdf_bullet(story, styles, action["action"])

    report_quality._pdf_heading(story, context, styles, 1, "Referencias legales e institucionales")
    for reference in getattr(report_completion, "_REFERENCE_LIST", (
        "Constitución de la República del Ecuador.",
        "Ley Orgánica de Educación Superior.",
        "Reglamento de Régimen Académico.",
        "Normativa institucional aplicable al proceso de titulación.",
    )):
        report_quality._pdf_bullet(story, styles, reference)


def _noop(*args: Any, **kwargs: Any) -> None:
    return None


def install() -> None:
    """Elimina relaciones automáticas entre las cuatro áreas del informe."""

    report_completion._executive_data = _executive_data
    report_completion._automatic_incidents = _automatic_incidents
    report_completion._automatic_actions = _automatic_actions
    report_completion._add_docx_objectives = _add_docx_objectives
    report_completion._add_pdf_objectives = _add_pdf_objectives
    report_completion._methodology_paragraphs = _methodology_paragraphs
    report_completion._add_docx_eligibility = _noop
    report_completion._add_pdf_eligibility = _noop
    report_completion._add_docx_global_process = _noop
    report_completion._add_pdf_global_process = _noop
    report_completion._add_docx_post_sections = _add_docx_post_sections
    report_completion._add_pdf_post_sections = _add_pdf_post_sections
