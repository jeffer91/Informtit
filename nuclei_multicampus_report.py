from __future__ import annotations

from typing import Any

from reportlab.lib.units import cm
from reportlab.platypus import Spacer

import nuclei_export
import report_quality
from nuclei_multicampus import get_nuclei


def _label(course: dict[str, Any]) -> str:
    campus = str(course.get("campus") or "").strip()
    base = f"{course['career_name']} – Núcleo {course['nucleus_number']}"
    return f"{base} – Sede {campus}" if campus else base


def _course_context(course: dict[str, Any]) -> str:
    details = []
    if course.get("campus"):
        details.append(f"sede {course['campus']}")
    if course.get("module_code"):
        details.append(f"módulo {course['module_code']}")
    if course.get("group_code"):
        details.append(f"grupo {course['group_code']}")
    if course.get("schedule"):
        details.append(f"horario {course['schedule']}")
    return ", ".join(details)


def _docx_nucleus_results(document: Any, context: Any, report_id: int) -> None:
    courses = get_nuclei(report_id).get("courses", [])
    if not courses:
        return
    report_quality._docx_heading(document, context, 1, "Resultados de los núcleos estructurantes")
    for index, course in enumerate(courses):
        report_quality._docx_heading(document, context, 2, _label(course), page_break=index > 0)
        location = _course_context(course)
        location_sentence = f" El curso corresponde a {location}." if location else ""
        report_quality._docx_body(
            document,
            f"El curso fue impartido por {course.get('teacher_name') or 'docente pendiente de confirmar'} y contó con el seguimiento de {course.get('coordinator_name') or 'la coordinación de carrera'}.{location_sentence} Se registraron {course.get('graded_students', 0)} estudiantes con calificaciones; {course.get('approved_count', 0)} aprobaron y {course.get('failed_count', 0)} reprobaron. El promedio general fue {report_quality._fmt(course.get('course_average'))}.",
        )
        caption = f"Calificaciones del Núcleo {course['nucleus_number']} de {course['career_name']}"
        if course.get("campus"):
            caption += f" – Sede {course['campus']}"
        report_quality._docx_caption(document, context.table_caption(caption))
        nuclei_export._docx_score_table(document, course)
        report_quality._docx_heading(document, context, 3, "Promedios por actividad")
        avg_caption = f"Promedios de las actividades del Núcleo {course['nucleus_number']}"
        if course.get("campus"):
            avg_caption += f" – Sede {course['campus']}"
        report_quality._docx_caption(document, context.table_caption(avg_caption))
        nuclei_export._docx_averages(document, course)


def _pdf_nucleus_results(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    courses = get_nuclei(report_id).get("courses", [])
    if not courses:
        return
    report_quality._pdf_heading(story, context, styles, 1, "Resultados de los núcleos estructurantes")
    for index, course in enumerate(courses):
        report_quality._pdf_heading(story, context, styles, 2, _label(course), page_break=index > 0)
        location = _course_context(course)
        location_sentence = f" El curso corresponde a {location}." if location else ""
        report_quality._pdf_body(
            story,
            styles,
            f"El curso fue impartido por {course.get('teacher_name') or 'docente pendiente de confirmar'} y contó con el seguimiento de {course.get('coordinator_name') or 'la coordinación de carrera'}.{location_sentence} Se registraron {course.get('graded_students', 0)} estudiantes con calificaciones; {course.get('approved_count', 0)} aprobaron y {course.get('failed_count', 0)} reprobaron. El promedio general fue {report_quality._fmt(course.get('course_average'))}.",
        )
        caption = f"Calificaciones del Núcleo {course['nucleus_number']} de {course['career_name']}"
        if course.get("campus"):
            caption += f" – Sede {course['campus']}"
        report_quality._pdf_caption(story, styles, context.table_caption(caption))
        story += [nuclei_export._pdf_score_table(course, styles), Spacer(1, 0.2 * cm)]
        report_quality._pdf_heading(story, context, styles, 3, "Promedios por actividad")
        avg_caption = f"Promedios de las actividades del Núcleo {course['nucleus_number']}"
        if course.get("campus"):
            avg_caption += f" – Sede {course['campus']}"
        report_quality._pdf_caption(story, styles, context.table_caption(avg_caption))
        story += [nuclei_export._pdf_averages(course), Spacer(1, 0.25 * cm)]


def install() -> None:
    report_quality.get_nuclei = get_nuclei
    nuclei_export.get_nuclei = get_nuclei
    report_quality._docx_nucleus_results = _docx_nucleus_results
    report_quality._pdf_nucleus_results = _pdf_nucleus_results
