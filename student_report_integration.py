from __future__ import annotations

from statistics import mean
from typing import Any

import nuclei_export
import nuclei_multicampus
import report_final_overhaul
import report_full_detail
import report_integrity_core
import report_quality
from process_service import get_projects as raw_get_projects
from student_domain_bridge import reconcile_all
from student_domain_service import ROUTE_COMPLEXIVE, ROUTE_THESIS, get_period_students

_INSTALLED = False
_BASE_REPORT_DATA = report_quality._report_data
_BASE_INTEGRITY_PROCESS_SERVICE = report_integrity_core.process_service


def _master(report_id: int) -> dict[int, dict[str, Any]]:
    return {int(row["id"]): row for row in get_period_students(report_id).get("students", [])}


def _active_for_route(row: dict[str, Any] | None, route: str) -> bool:
    return bool(
        row
        and row.get("route") == route
        and row.get("process_status") == "ACTIVO"
    )


def _grade(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _recalculate_nucleus(course: dict[str, Any]) -> None:
    students = list(course.get("students", []))
    grades = [_grade(student.get("final_grade")) for student in students]
    evaluated = [grade for grade in grades if grade is not None]
    approved = sum(grade is not None and grade >= 7 for grade in grades)
    failed = sum(grade is not None and grade < 7 for grade in grades)
    unevaluated = len(students) - approved - failed
    course["participant_students"] = len(students)
    course["graded_students"] = len(evaluated)
    course["matched_students"] = len(students)
    course["missing_grades"] = unevaluated
    course["extra_grades"] = 0
    course["approved_count"] = approved
    course["failed_count"] = failed
    course["unevaluated_count"] = unevaluated
    course["course_average"] = round(mean(evaluated), 2) if evaluated else None

    recalculated: list[dict[str, Any]] = []
    for assessment in course.get("assessments", []):
        assessment_id = int(assessment.get("id") or 0)
        name = str(assessment.get("name") or "")
        values: list[float] = []
        for student in students:
            for score in student.get("scores", []):
                same_id = assessment_id and int(score.get("assessment_id") or 0) == assessment_id
                same_name = name and str(score.get("assessment_name") or "") == name
                if not (same_id or same_name):
                    continue
                value = _grade(score.get("grade"))
                if value is not None:
                    values.append(value)
                break
        average = round(mean(values), 2) if values else None
        assessment["average"] = average
        recalculated.append({
            "name": name,
            "source_average": None,
            "calculated_average": average,
        })
    if recalculated:
        course["activity_averages"] = recalculated


def filtered_nuclei(report_id: int) -> dict[str, Any]:
    """Filtra solo para reportes; la pantalla de carga conserva todos los registros crudos."""
    reconcile_all(report_id)
    masters = _master(report_id)
    data = nuclei_multicampus.get_nuclei(report_id)
    courses: list[dict[str, Any]] = []
    for source_course in data.get("courses", []):
        course = dict(source_course)
        course["assessments"] = [dict(item) for item in source_course.get("assessments", [])]
        students: list[dict[str, Any]] = []
        for source_student in source_course.get("students", []):
            sid = source_student.get("period_student_id")
            master = masters.get(int(sid)) if sid else None
            if _active_for_route(master, ROUTE_COMPLEXIVE):
                student = dict(source_student)
                student["scores"] = [dict(score) for score in source_student.get("scores", [])]
                student["master_identification"] = master.get("identification") or ""
                student["master_name"] = master.get("full_name") or ""
                student["official_graduated"] = bool(master.get("official_graduated"))
                students.append(student)
        course["students"] = students
        _recalculate_nucleus(course)
        # El curso permanece como evidencia de carga incluso si queda sin población
        # válida; sus métricas se recalculan a cero en lugar de contaminar el reporte.
        courses.append(course)
    return {"courses": courses}


def filtered_projects(report_id: int) -> dict[str, Any]:
    reconcile_all(report_id)
    masters = _master(report_id)
    data = raw_get_projects(report_id)
    projects: list[dict[str, Any]] = []
    omitted_route_conflicts = 0
    for source in data.get("projects", []):
        sid = source.get("period_student_id")
        master = masters.get(int(sid)) if sid else None
        if _active_for_route(master, ROUTE_THESIS):
            item = dict(source)
            item["official_graduated"] = bool(master.get("official_graduated"))
            item["official_titulation_completed"] = bool(master.get("official_titulation_completed"))
            projects.append(item)
        else:
            omitted_route_conflicts += 1
    result = dict(data)
    result["projects"] = projects
    # Recalcula el resumen sobre la población realmente válida para el informe.
    approved = 0
    failed = 0
    for item in projects:
        status = str(item.get("final_status") or "").upper()
        grade = _grade(item.get("final_grade"))
        if status == "APROBADO" or (grade is not None and grade >= 7):
            approved += 1
        elif status == "REPROBADO" or (grade is not None and grade < 7):
            failed += 1
    result["summary"] = {
        **(data.get("summary") or {}),
        "total": len(projects),
        "approved": approved,
        "failed": failed,
        "incomplete": max(0, len(projects) - approved - failed),
    }
    result["omitted_route_conflicts"] = omitted_route_conflicts
    return result


def filtered_report_data(report_id: int) -> dict[str, Any]:
    """Complexivo: solo ruta Complexivo y estudiantes habilitados por requisitos."""
    reconcile_all(report_id)
    masters = _master(report_id)
    report = _BASE_REPORT_DATA(report_id)
    for career in report.get("careers", []):
        filtered: list[dict[str, Any]] = []
        for source in career.get("students", []):
            sid = source.get("period_student_id")
            master = masters.get(int(sid)) if sid else None
            if _active_for_route(master, ROUTE_COMPLEXIVE):
                item = dict(source)
                item["identification"] = master.get("identification") or item.get("identification") or ""
                item["official_graduated"] = bool(master.get("official_graduated"))
                item["official_titulation_completed"] = bool(master.get("official_titulation_completed"))
                filtered.append(item)
        career["students"] = filtered
    report["student_domain_applied"] = True
    return report


class _IntegrityProcessProxy:
    """Evita alterar process_service global; solo cambia la lectura usada por integridad."""

    def __getattr__(self, name: str) -> Any:
        if name == "get_projects":
            return filtered_projects
        return getattr(_BASE_INTEGRITY_PROCESS_SERVICE, name)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    # Los servicios de carga/UI siguen usando sus fuentes crudas. Solo las capas
    # de construcción y validación del informe reciben la población reconciliada.
    report_quality._report_data = filtered_report_data
    report_quality.get_nuclei = filtered_nuclei
    report_quality.get_projects = filtered_projects
    nuclei_export.get_nuclei = filtered_nuclei
    report_final_overhaul.get_nuclei = filtered_nuclei
    report_final_overhaul.get_projects = filtered_projects
    report_full_detail.get_nuclei = filtered_nuclei
    report_full_detail.get_projects = filtered_projects
    report_integrity_core.set_raw_nuclei_provider(filtered_nuclei)
    report_integrity_core.process_service = _IntegrityProcessProxy()
    _INSTALLED = True
