from __future__ import annotations

from typing import Any

from reportlab.lib.units import cm
from reportlab.platypus import Spacer

import nuclei_export
import report_quality
from nuclei_multicampus import get_nuclei as get_raw_nuclei


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
    if course.get("period_label"):
        details.append(f"período {course['period_label']}")
    if course.get("group_code"):
        details.append(f"grupo {course['group_code']}")
    if course.get("schedule"):
        details.append(f"horario {course['schedule']}")
    return ", ".join(details)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _independent_course(course: dict[str, Any]) -> dict[str, Any]:
    """Recalcula el curso usando exclusivamente sus propios registros Moodle."""

    result = dict(course)
    students = [dict(student) for student in course.get("students", [])]
    result["students"] = students
    graded = [student for student in students if student.get("final_grade") is not None]
    result["participant_students"] = len(students)
    result["graded_students"] = len(graded)
    result["approved_count"] = sum(float(student["final_grade"]) >= 7.0 for student in graded)
    result["failed_count"] = sum(float(student["final_grade"]) < 7.0 for student in graded)
    result["unevaluated_count"] = len(students) - len(graded)
    result["course_average"] = _mean([float(student["final_grade"]) for student in graded])

    assessments = course.get("assessments", [])
    previous_averages = course.get("activity_averages", [])
    activity_averages: list[dict[str, Any]] = []
    for index, assessment in enumerate(assessments):
        values: list[float] = []
        for student in students:
            scores = student.get("scores", [])
            if index >= len(scores):
                continue
            grade = scores[index].get("grade")
            if grade is not None:
                values.append(float(grade))
        previous = previous_averages[index] if index < len(previous_averages) else {}
        name = assessment.get("name") if isinstance(assessment, dict) else str(assessment)
        activity_averages.append(
            {
                "name": name,
                "source_average": previous.get("source_average") if isinstance(previous, dict) else None,
                "calculated_average": _mean(values),
            }
        )
    result["activity_averages"] = activity_averages
    return result


def get_report_nuclei(report_id: int) -> dict[str, Any]:
    """Devuelve todos los cursos de Núcleos sin consultar Requisitos ni Complexivo."""

    courses = [
        _independent_course(course)
        for course in get_raw_nuclei(report_id).get("courses", [])
    ]
    return {"courses": courses}


def _docx_nucleus_results(document: Any, context: Any, report_id: int) -> None:
    courses = get_report_nuclei(report_id).get("courses", [])
    if not courses:
        return
    report_quality._docx_heading(document, context, 1, "Resultados de los núcleos estructurantes")
    report_quality._docx_body(
        document,
        "Los resultados de Núcleos corresponden exclusivamente a los cursos y calificaciones cargados en este módulo. No se realiza un cruce automático con Requisitos, Examen Complexivo o Trabajo de Titulación.",
    )
    for index, course in enumerate(courses):
        report_quality._docx_heading(document, context, 2, _label(course), page_break=index > 0)
        location = _course_context(course)
        location_sentence = f" El curso corresponde a {location}." if location else ""
        report_quality._docx_body(
            document,
            f"El curso fue impartido por {course.get('teacher_name') or 'docente pendiente de confirmar'} y contó con el seguimiento de {course.get('coordinator_name') or 'la coordinación de carrera'}.{location_sentence} Se registraron {course.get('graded_students', 0)} estudiantes con calificación; {course.get('approved_count', 0)} aprobaron, {course.get('failed_count', 0)} reprobaron y {course.get('unevaluated_count', 0)} quedaron sin nota. El promedio general fue {report_quality._fmt(course.get('course_average'))}.",
        )
        caption = f"Calificaciones del Núcleo {course['nucleus_number']} de {course['career_name']}"
        if course.get("campus"):
            caption += f" – Sede {course['campus']}"
        report_quality._docx_caption(document, context.table_caption(caption))
        nuclei_export._docx_score_table(document, course)
        if course.get("activity_averages"):
            report_quality._docx_heading(document, context, 3, "Promedios por actividad")
            report_quality._docx_caption(
                document,
                context.table_caption(f"Promedios de las actividades del Núcleo {course['nucleus_number']}")
            )
            nuclei_export._docx_averages(document, course)


def _pdf_nucleus_results(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    courses = get_report_nuclei(report_id).get("courses", [])
    if not courses:
        return
    report_quality._pdf_heading(story, context, styles, 1, "Resultados de los núcleos estructurantes")
    report_quality._pdf_body(
        story,
        styles,
        "Los resultados de Núcleos corresponden exclusivamente a los cursos y calificaciones cargados en este módulo. No se realiza un cruce automático con Requisitos, Examen Complexivo o Trabajo de Titulación.",
    )
    for index, course in enumerate(courses):
        report_quality._pdf_heading(story, context, styles, 2, _label(course), page_break=index > 0)
        location = _course_context(course)
        location_sentence = f" El curso corresponde a {location}." if location else ""
        report_quality._pdf_body(
            story,
            styles,
            f"El curso fue impartido por {course.get('teacher_name') or 'docente pendiente de confirmar'} y contó con el seguimiento de {course.get('coordinator_name') or 'la coordinación de carrera'}.{location_sentence} Se registraron {course.get('graded_students', 0)} estudiantes con calificación; {course.get('approved_count', 0)} aprobaron, {course.get('failed_count', 0)} reprobaron y {course.get('unevaluated_count', 0)} quedaron sin nota. El promedio general fue {report_quality._fmt(course.get('course_average'))}.",
        )
        caption = f"Calificaciones del Núcleo {course['nucleus_number']} de {course['career_name']}"
        if course.get("campus"):
            caption += f" – Sede {course['campus']}"
        report_quality._pdf_caption(story, styles, context.table_caption(caption))
        story += [nuclei_export._pdf_score_table(course, styles), Spacer(1, 0.2 * cm)]
        if course.get("activity_averages"):
            report_quality._pdf_heading(story, context, styles, 3, "Promedios por actividad")
            report_quality._pdf_caption(
                story,
                styles,
                context.table_caption(f"Promedios de las actividades del Núcleo {course['nucleus_number']}")
            )
            story += [nuclei_export._pdf_averages(course), Spacer(1, 0.25 * cm)]


def install() -> None:
    report_quality.get_nuclei = get_report_nuclei
    nuclei_export.get_nuclei = get_report_nuclei
    report_quality._docx_nucleus_results = _docx_nucleus_results
    report_quality._pdf_nucleus_results = _pdf_nucleus_results
