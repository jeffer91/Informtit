from __future__ import annotations

from typing import Any

import eligibility_service as eligibility
import thesis_independent as thesis
from student_domain_service import (
    ROUTE_ARTICLE,
    ROUTE_COMPLEXIVE,
    ROUTE_THESIS,
    get_period_students,
    resolve_master_student,
)

_INSTALLED = False
_BASE_GET_ELIGIBILITY = eligibility.get_eligibility
_BASE_SAVE_PROJECT = getattr(thesis, "save_project", None)


def _master_rows(report_id: int) -> dict[int, dict[str, Any]]:
    data = get_period_students(report_id)
    return {int(row["id"]): row for row in data.get("students", [])}


def _requirements_id_map(report_id: int) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in get_period_students(report_id).get("students", []):
        req_id = row.get("requirements_student_id")
        if req_id:
            result[int(req_id)] = row
    return result


def _project_student_keys(report_id: int):
    """Compatibilidad: la ruta ya no se infiere por existir una tesis."""
    master = get_period_students(report_id).get("students", [])
    student_ids: set[int] = set()
    identifications: set[str] = set()
    emails: set[str] = set()
    names: set[tuple[str, str]] = set()
    for row in master:
        if row.get("route") != ROUTE_THESIS:
            continue
        req_id = row.get("requirements_student_id")
        if req_id:
            student_ids.add(int(req_id))
        identification = str(row.get("identification") or "").strip()
        if identification:
            identifications.add(identification)
        email = eligibility._email_key(row.get("email"))
        if email:
            emails.add(email)
        name = eligibility._student_name_key(row.get("full_name"))
        career = eligibility._career_key(row.get("career_name"))
        if name:
            names.add((career, name))
    return student_ids, identifications, emails, names


def _get_eligibility(report_id: int) -> dict[str, Any]:
    """Ejecuta la conciliación existente usando la ruta manual como fuente de verdad."""
    original = eligibility._project_student_keys
    eligibility._project_student_keys = _project_student_keys
    try:
        result = _BASE_GET_ELIGIBILITY(report_id)
    finally:
        eligibility._project_student_keys = original

    master_by_req = _requirements_id_map(report_id)
    for row in result.get("rows", []):
        master = master_by_req.get(int(row.get("student_id") or 0))
        if not master:
            continue
        row["period_student_id"] = int(master["id"])
        row["route"] = master["route"]
        row["route_source"] = master["route_source"]
        row["process_status"] = master["process_status"]
        row["official_graduated"] = bool(master["official_graduated"])
        row["official_titulation_completed"] = bool(master["official_titulation_completed"])
        if master["route"] == ROUTE_THESIS:
            row["option"] = "Trabajo de Titulación"
            row["eligible_for_complexive"] = False
            row["eligible_for_nuclei"] = False
            row["status"] = "Trabajo de Titulación"
            row["stage_status"] = "Trabajo de Titulación"
        elif master["route"] == ROUTE_ARTICLE:
            row["option"] = "Artículo Académico"
            row["eligible_for_complexive"] = False
            row["eligible_for_nuclei"] = False
            row["status"] = "Artículo Académico"
            row["stage_status"] = "Artículo Académico"
        elif row.get("eligible_for_nuclei"):
            row["option"] = "Examen Complexivo"
    summary = result.get("summary") or {}
    master_rows = list(master_by_req.values())
    summary["thesis_students"] = sum(row.get("route") == ROUTE_THESIS for row in master_rows)
    summary["article_students"] = sum(row.get("route") == ROUTE_ARTICLE for row in master_rows)
    summary["complexive_candidates"] = sum(
        row.get("route") == ROUTE_COMPLEXIVE and row.get("process_status") != "RETIRADO"
        for row in master_rows
    )
    summary["official_graduated"] = sum(bool(row.get("official_graduated")) for row in master_rows)
    result["summary"] = summary
    return result


def _resolve_project_student(report_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    return resolve_master_student(
        report_id,
        identification=payload.get("identification"),
        email=payload.get("email"),
        full_name=payload.get("full_name"),
        career_name=payload.get("career_name"),
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    eligibility._project_student_keys = _project_student_keys
    eligibility.get_eligibility = _get_eligibility
    # Exponemos el resolver a Trabajo de Titulación sin tocar Firebase ni forzar
    # un cambio de ruta: los parsers/UI pueden advertir la discrepancia y el usuario
    # decide desde Estudiantes.
    thesis.resolve_master_student = _resolve_project_student
    _INSTALLED = True
