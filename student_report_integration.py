from __future__ import annotations

from typing import Any

import nuclei_export
import nuclei_multicampus
import report_final_overhaul
import report_full_detail
import report_quality
from process_service import get_projects as raw_get_projects
from student_domain_bridge import reconcile_all
from student_domain_service import ROUTE_COMPLEXIVE, ROUTE_THESIS, get_period_students

_INSTALLED = False
_BASE_REPORT_DATA = report_quality._report_data


def _master(report_id: int) -> dict[int, dict[str, Any]]:
    return {int(row["id"]): row for row in get_period_students(report_id).get("students", [])}


def _active_for_route(row: dict[str, Any] | None, route: str) -> bool:
    return bool(
        row
        and row.get("route") == route
        and row.get("process_status") == "ACTIVO"
    )


def filtered_nuclei(report_id: int) -> dict[str, Any]:
    """Filtra solo para reportes; la pantalla de carga conserva todos los registros crudos."""
    reconcile_all(report_id)
    masters = _master(report_id)
    data = nuclei_multicampus.get_nuclei(report_id)
    courses: list[dict[str, Any]] = []
    for source_course in data.get("courses", []):
        course = dict(source_course)
        students: list[dict[str, Any]] = []
        for source_student in source_course.get("students", []):
            sid = source_student.get("period_student_id")
            master = masters.get(int(sid)) if sid else None
            if _active_for_route(master, ROUTE_COMPLEXIVE):
                student = dict(source_student)
                student["master_identification"] = master.get("identification") or ""
                student["master_name"] = master.get("full_name") or ""
                student["official_graduated"] = bool(master.get("official_graduated"))
                students.append(student)
        course["students"] = students
        # Conservamos cursos cargados aunque queden sin población válida para que
        # el reporte pueda evidenciar que existió una carga, pero sin contaminar métricas.
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


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    # Los servicios de carga/UI siguen usando sus fuentes crudas. Solo las capas
    # de construcción del informe reciben la población reconciliada.
    report_quality._report_data = filtered_report_data
    report_quality.get_nuclei = filtered_nuclei
    nuclei_export.get_nuclei = filtered_nuclei
    report_final_overhaul.get_nuclei = filtered_nuclei
    report_final_overhaul.get_projects = filtered_projects
    report_full_detail.get_nuclei = filtered_nuclei
    report_full_detail.get_projects = filtered_projects
    _INSTALLED = True
