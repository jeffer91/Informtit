from __future__ import annotations

from typing import Any

from db import connection, rows_to_dicts
from student_domain_bridge import reconcile_all
from student_domain_read_model import consolidated_students
from student_domain_service import set_process_status, set_student_route, sync_report_students


def _member_reports(period_project_id: int) -> list[dict[str, Any]]:
    with connection() as conn:
        row = conn.execute("SELECT id FROM period_projects WHERE id=?", (period_project_id,)).fetchone()
        if not row:
            raise ValueError("El período solicitado no existe.")
        return rows_to_dicts(conn.execute(
            "SELECT id, modality, period, name FROM reports WHERE period_project_id=? ORDER BY modality, id",
            (period_project_id,),
        ).fetchall())


def _refresh_report(report_id: int) -> dict[str, Any]:
    sync_report_students(report_id)
    reconcile_all(report_id)
    return consolidated_students(report_id)


def get_period_student_domain(period_project_id: int) -> dict[str, Any]:
    members = _member_reports(period_project_id)
    rows: list[dict[str, Any]] = []
    reconciliations: dict[str, Any] = {}
    for member in members:
        report_id = int(member["id"])
        data = _refresh_report(report_id)
        modality = str(member.get("modality") or "")
        reconciliations[modality or str(report_id)] = data.get("reconciliation") or {}
        for row in data.get("students", []):
            item = dict(row)
            item["dataset_report_id"] = report_id
            item["dataset_modality"] = modality
            rows.append(item)

    rows.sort(key=lambda row: (
        str(row.get("career_name") or "").casefold(),
        str(row.get("full_name") or "").casefold(),
        int(row.get("id") or 0),
    ))
    return {
        "ok": True,
        "period_project_id": period_project_id,
        "summary": {
            "students": len(rows),
            "complexive": sum(row.get("route") == "COMPLEXIVO" for row in rows),
            "thesis": sum(row.get("route") == "TRABAJO_TITULACION" for row in rows),
            "graduated": sum(bool(row.get("official_graduated")) for row in rows),
            "retired": sum(row.get("process_status") == "RETIRADO" for row in rows),
            "one_missing": sum(row.get("process_status") == "NO_APROBADO_REQUISITO" for row in rows),
            "review": sum(row.get("reconciliation_status") != "OK" for row in rows),
            "presencial": sum(row.get("modality") == "presencial" for row in rows),
            "online": sum(row.get("modality") == "en_linea" for row in rows),
        },
        "students": rows,
        "members": members,
        "reconciliations": reconciliations,
    }


def _student_report(period_project_id: int, student_id: int) -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT report_id FROM period_students WHERE id=? AND period_project_id=?",
            (student_id, period_project_id),
        ).fetchone()
    if not row:
        raise ValueError("El estudiante no pertenece al período seleccionado.")
    return int(row["report_id"])


def set_period_student_route(period_project_id: int, student_id: int, route: str) -> dict[str, Any]:
    report_id = _student_report(period_project_id, student_id)
    result = set_student_route(report_id, student_id, route)
    reconcile_all(report_id)
    return result


def set_period_student_process_status(period_project_id: int, student_id: int, status: str) -> dict[str, Any]:
    report_id = _student_report(period_project_id, student_id)
    return set_process_status(report_id, student_id, status)
