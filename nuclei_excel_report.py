from __future__ import annotations

import html
from collections import defaultdict
from typing import Any

from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

import nuclei_multicampus_report
import report_decoupled
import report_enhancements
import report_quality
from nuclei_multicampus import get_nuclei


def _status(student: dict[str, Any]) -> str:
    value = str(student.get("final_status") or "").strip().casefold()
    if value == "aprobado":
        return "approved"
    if value == "reprobado":
        return "failed"
    if value in {"no evaluado", "sin nota", ""}:
        return "pending"
    grade = student.get("final_grade")
    if grade is None:
        return "pending"
    return "approved" if float(grade) >= 7 else "failed"


def _nucleus_summary(report_id: int) -> dict[str, int]:
    courses = get_nuclei(report_id).get("courses", [])
    records = 0
    approved = 0
    failed = 0
    unevaluated = 0
    for course in courses:
        for student in course.get("students", []):
            records += 1
            state = _status(student)
            if state == "approved":
                approved += 1
            elif state == "failed":
                failed += 1
            else:
                unevaluated += 1
    return {
        "courses": len(courses),
        "records": records,
        "graded": approved + failed,
        "approved": approved,
        "failed": failed,
        "unevaluated": unevaluated,
    }


def _independent_course(course: dict[str, Any]) -> dict[str, Any]:
    result = dict(course)
    students = [dict(student) for student in course.get("students", [])]
    result["students"] = students
    approved = [student for student in students if _status(student) == "approved"]
    failed = [student for student in students if _status(student) == "failed"]
    pending = [student for student in students if _status(student) == "pending"]
    evaluated_numeric = [
        float(student["final_grade"])
        for student in approved + failed
        if student.get("final_grade") is not None
    ]
    result["participant_students"] = len(students)
    result["graded_students"] = len(approved) + len(failed)
    result["approved_count"] = len(approved)
    result["failed_count"] = len(failed)
    result["unevaluated_count"] = len(pending)
    result["course_average"] = (
        round(sum(evaluated_numeric) / len(evaluated_numeric), 2)
        if evaluated_numeric
        else None
    )
    result["activity_averages"] = []
    return result


def _title(course: dict[str, Any]) -> str:
    subject = str(course.get("course_title") or "").strip()
    if subject:
        return f"{course.get('career_name') or 'Sin carrera'} – {subject}"
    return f"{course.get('career_name') or 'Sin carrera'} – Núcleo {course.get('nucleus_number') or '—'}"


def _course_analysis(course: dict[str, Any]) -> str:
    students = course.get("students", [])
    approved = sum(_status(student) == "approved" for student in students)
    failed = sum(_status(student) == "failed" for student in students)
    pending = sum(_status(student) == "pending" for student in students)
    evaluated = approved + failed
    rate = approved / evaluated * 100 if evaluated else 0
    return (
        f"De {len(students)} registros importados desde el Excel, {approved} constan como aprobados, "
        f"{failed} como reprobados y {pending} como no evaluados. La aprobación entre los registros "
        f"con estado académico definido fue del {report_quality._pct(rate)}. El promedio de las notas "
        f"numéricas evaluadas fue {report_quality._fmt(course.get('course_average'))}. Para este módulo, "
        "el campo estado del archivo Excel se considera el resultado académico oficial."
    )


def _career_rates(courses: list[dict[str, Any]]) -> tuple[list[str], list[float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for course in courses:
        grouped[str(course.get("career_name") or "Sin carrera")].extend(course.get("students", []))
    labels: list[str] = []
    values: list[float] = []
    for career in sorted(grouped, key=lambda value: value.casefold()):
        students = grouped[career]
        approved = sum(_status(student) == "approved" for student in students)
        failed = sum(_status(student) == "failed" for student in students)
        evaluated = approved + failed
        labels.append(career)
        values.append(round(approved / evaluated * 100, 2) if evaluated else 0.0)
    return labels, values


def _docx_nuclei(document: Any, context: Any, report_id: int) -> None:
    courses = [_independent_course(course) for course in get_nuclei(report_id).get("courses", [])]
    if not courses:
        return
    report_quality._docx_heading(document, context, 1, "Resultados de los núcleos estructurantes")
    report_quality._docx_body(
        document,
        "La información de esta sección proviene del Excel consolidado de Núcleos. Cada registro conserva "
        "la carrera, el docente, el estudiante, la materia, la nota final y el estado académico reportados "
        "en el archivo de origen.",
    )
    for index, course in enumerate(courses):
        report_quality._docx_heading(document, context, 2, _title(course), page_break=index > 0)
        report_quality._docx_body(
            document,
            f"Docente registrado: {course.get('teacher_name') or 'no indicado'}. La tabla presenta únicamente "
            "la nota final y el estado académico importados desde el Excel consolidado.",
        )
        report_quality._docx_caption(
            document,
            context.table_caption(f"Resultados de {course.get('course_title') or 'Núcleos'} – {course.get('career_name') or 'Sin carrera'}"),
        )
        report_enhancements._docx_nucleus_score(document, course)
        report_quality._docx_body(document, _course_analysis(course))

    labels, rates = _career_rates(courses)
    if labels:
        chart = report_enhancements._save_bar(
            labels,
            rates,
            "Aprobación de Núcleos por carrera",
            "Aprobación (%)",
            report_enhancements._chart_path(report_id, "nuclei_excel"),
            100,
        )
        report_enhancements._add_docx_figure(
            document,
            context,
            chart,
            "Porcentaje de aprobación de Núcleos por carrera",
            "Elaboración propia a partir del estado académico registrado en el Excel consolidado de Núcleos.",
        )


def _pdf_nuclei(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    courses = [_independent_course(course) for course in get_nuclei(report_id).get("courses", [])]
    if not courses:
        return
    if "NucleusCell" not in styles:
        from reportlab.lib.styles import ParagraphStyle
        styles.add(ParagraphStyle("NucleusCell", parent=styles["BodyText"], fontSize=6.5, leading=7.5))
    report_quality._pdf_heading(story, context, styles, 1, "Resultados de los núcleos estructurantes")
    report_quality._pdf_body(
        story,
        styles,
        "La información de esta sección proviene del Excel consolidado de Núcleos y conserva el estado académico reportado en el archivo de origen.",
    )
    for index, course in enumerate(courses):
        report_quality._pdf_heading(story, context, styles, 2, _title(course), page_break=index > 0)
        report_quality._pdf_body(
            story,
            styles,
            f"Docente registrado: {course.get('teacher_name') or 'no indicado'}. La tabla presenta la nota final y el estado académico importados.",
        )
        report_quality._pdf_caption(
            story,
            styles,
            context.table_caption(f"Resultados de {course.get('course_title') or 'Núcleos'} – {course.get('career_name') or 'Sin carrera'}"),
        )
        story += [report_enhancements._pdf_nucleus_score(course, styles), Spacer(1, 0.15 * cm)]
        report_quality._pdf_body(story, styles, _course_analysis(course))


def install() -> None:
    report_decoupled._nucleus_summary = _nucleus_summary
    nuclei_multicampus_report._independent_course = _independent_course
    report_enhancements._course_analysis = _course_analysis
    report_quality._docx_nucleus_results = _docx_nuclei
    report_quality._pdf_nucleus_results = _pdf_nuclei
