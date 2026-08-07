from __future__ import annotations

from collections import defaultdict
from typing import Any

from reportlab.lib.units import cm
from reportlab.platypus import Spacer

import nuclei_export
import report_quality
from eligibility_service import get_eligibility
from nuclei_multicampus import get_nuclei as get_raw_nuclei
from parser import canonical_name_key, clean_moodle_name


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


def _email(value: Any) -> str:
    return str(value or "").strip().casefold()


def _name(value: Any) -> str:
    return canonical_name_key(clean_moodle_name(str(value or "")))


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _eligible_members_by_course(report_id: int) -> dict[int, dict[str, set[str]]]:
    """Obtiene únicamente estudiantes que realmente ingresaron a Núcleos.

    Se usan las fuentes que ya fueron vinculadas por eligibility_service para no
    repetir ni relajar las reglas de correspondencia por correo, nombre, carrera
    y sede.
    """

    eligibility = get_eligibility(report_id)
    members: dict[int, dict[str, set[str]]] = defaultdict(
        lambda: {"emails": set(), "names": set()}
    )
    for row in eligibility.get("rows", []):
        if row.get("option") != "Examen Complexivo" or not row.get("eligible_for_nuclei"):
            continue
        email = _email(row.get("email"))
        name = _name(row.get("full_name"))
        for sources in (row.get("nucleus_sources") or {}).values():
            for source in sources or []:
                course_id = int(source.get("course_id") or 0)
                if not course_id:
                    continue
                if email:
                    members[course_id]["emails"].add(email)
                if name:
                    members[course_id]["names"].add(name)
    return members


def _student_is_allowed(student: dict[str, Any], members: dict[str, set[str]]) -> bool:
    email = _email(student.get("email"))
    name = _name(student.get("full_name"))
    return bool((email and email in members["emails"]) or (name and name in members["names"]))


def _filtered_course(course: dict[str, Any], members: dict[str, set[str]]) -> dict[str, Any] | None:
    students = [
        dict(student)
        for student in course.get("students", [])
        if _student_is_allowed(student, members)
    ]
    if not students:
        return None

    filtered = dict(course)
    filtered["students"] = students
    graded = [student for student in students if student.get("final_grade") is not None]
    filtered["graded_students"] = len(graded)
    filtered["approved_count"] = sum(
        float(student["final_grade"]) >= 7.0 for student in graded
    )
    filtered["failed_count"] = sum(
        float(student["final_grade"]) < 7.0 for student in graded
    )
    filtered["unevaluated_count"] = len(students) - len(graded)
    filtered["course_average"] = _mean(
        [float(student["final_grade"]) for student in graded]
    )
    filtered["participant_students"] = len(students)
    filtered["matched_students"] = len(students)
    filtered["missing_grades"] = 0
    filtered["extra_grades"] = 0
    filtered["excluded_by_requirements"] = max(
        0, len(course.get("students", [])) - len(students)
    )

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
        activity_averages.append(
            {
                "name": assessment.get("name") if isinstance(assessment, dict) else str(assessment),
                "source_average": previous.get("source_average") if isinstance(previous, dict) else None,
                "calculated_average": _mean(values),
            }
        )
    filtered["activity_averages"] = activity_averages
    return filtered


def get_report_nuclei(report_id: int) -> dict[str, Any]:
    """Núcleos aptos para el informe: solo población que aprobó requisitos previos."""

    raw_courses = get_raw_nuclei(report_id).get("courses", [])
    members_by_course = _eligible_members_by_course(report_id)
    courses: list[dict[str, Any]] = []
    for course in raw_courses:
        course_id = int(course.get("id") or 0)
        members = members_by_course.get(course_id)
        if not members:
            continue
        filtered = _filtered_course(course, members)
        if filtered:
            courses.append(filtered)
    return {"courses": courses}


def _docx_nucleus_results(document: Any, context: Any, report_id: int) -> None:
    courses = get_report_nuclei(report_id).get("courses", [])
    if not courses:
        return
    report_quality._docx_heading(document, context, 1, "Resultados de los núcleos estructurantes")
    for index, course in enumerate(courses):
        report_quality._docx_heading(document, context, 2, _label(course), page_break=index > 0)
        location = _course_context(course)
        location_sentence = f" El curso corresponde a {location}." if location else ""
        report_quality._docx_body(
            document,
            f"El curso fue impartido por {course.get('teacher_name') or 'docente pendiente de confirmar'} y contó con el seguimiento de {course.get('coordinator_name') or 'la coordinación de carrera'}.{location_sentence} Para el análisis se consideraron únicamente los {course.get('graded_students', 0)} estudiantes que cumplieron los requisitos previos y registraron calificación en este curso; {course.get('approved_count', 0)} aprobaron y {course.get('failed_count', 0)} reprobaron. El promedio general fue {report_quality._fmt(course.get('course_average'))}.",
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
    courses = get_report_nuclei(report_id).get("courses", [])
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
            f"El curso fue impartido por {course.get('teacher_name') or 'docente pendiente de confirmar'} y contó con el seguimiento de {course.get('coordinator_name') or 'la coordinación de carrera'}.{location_sentence} Para el análisis se consideraron únicamente los {course.get('graded_students', 0)} estudiantes que cumplieron los requisitos previos y registraron calificación en este curso; {course.get('approved_count', 0)} aprobaron y {course.get('failed_count', 0)} reprobaron. El promedio general fue {report_quality._fmt(course.get('course_average'))}.",
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
    # Toda salida del informe que consulte Núcleos recibe la misma población
    # filtrada que ve el usuario en la interfaz minimalista.
    report_quality.get_nuclei = get_report_nuclei
    nuclei_export.get_nuclei = get_report_nuclei
    report_quality._docx_nucleus_results = _docx_nucleus_results
    report_quality._pdf_nucleus_results = _pdf_nucleus_results
