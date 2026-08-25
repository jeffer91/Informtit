from __future__ import annotations

import json
from typing import Any

from db import connection, rows_to_dicts
from student_domain_bridge import reconcile_all
from student_domain_read_model import consolidated_students
from student_domain_service import (
    confirm_source_link,
    set_process_status,
    set_student_route,
    sync_report_students,
)


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


def _open_links(report_ids: list[int]) -> list[dict[str, Any]]:
    if not report_ids:
        return []
    placeholders = ",".join("?" for _ in report_ids)
    with connection() as conn:
        rows = rows_to_dicts(conn.execute(
            f"""
            SELECT l.*, r.modality AS dataset_modality
            FROM student_source_links l
            JOIN reports r ON r.id=l.report_id
            WHERE l.report_id IN ({placeholders})
              AND COALESCE(l.match_status, 'UNMATCHED') <> 'OK'
            ORDER BY
              CASE l.match_status
                WHEN 'ROUTE_CONFLICT' THEN 1
                WHEN 'GRADE_CONFLICT' THEN 2
                WHEN 'AMBIGUOUS' THEN 3
                WHEN 'REVIEW_REQUIRED' THEN 4
                WHEN 'UNMATCHED' THEN 5
                ELSE 6
              END,
              l.source_module, l.source_name, l.id
            """,
            tuple(report_ids),
        ).fetchall())
    for row in rows:
        try:
            row["candidates"] = json.loads(row.get("candidates_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            row["candidates"] = []
    return rows


def get_period_student_domain(period_project_id: int) -> dict[str, Any]:
    members = _member_reports(period_project_id)
    rows: list[dict[str, Any]] = []
    reconciliations: dict[str, Any] = {}
    report_ids: list[int] = []
    for member in members:
        report_id = int(member["id"])
        report_ids.append(report_id)
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
    open_links = _open_links(report_ids)
    review_students = sum(row.get("reconciliation_status") != "OK" for row in rows)
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
            "review": review_students + len(open_links),
            "review_students": review_students,
            "open_links": len(open_links),
            "presencial": sum(row.get("modality") == "presencial" for row in rows),
            "online": sum(row.get("modality") == "en_linea" for row in rows),
        },
        "students": rows,
        "open_links": open_links,
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


def confirm_period_source_link(period_project_id: int, link_id: int, student_id: int) -> dict[str, Any]:
    members = _member_reports(period_project_id)
    report_ids = {int(item["id"]) for item in members}
    with connection() as conn:
        link = conn.execute("SELECT * FROM student_source_links WHERE id=?", (link_id,)).fetchone()
        if not link or int(link["report_id"]) not in report_ids:
            raise ValueError("La discrepancia ya no existe en este período.")
        report_id = int(link["report_id"])
        student = conn.execute(
            "SELECT id FROM period_students WHERE id=? AND report_id=? AND period_project_id=?",
            (student_id, report_id, period_project_id),
        ).fetchone()
        if not student:
            raise ValueError("El estudiante seleccionado no pertenece al mismo dataset de la discrepancia.")
        source_module = str(link["source_module"])
        source_key = str(link["source_key"])
    result = confirm_source_link(report_id, source_module, source_key, student_id)
    reconcile_all(report_id)
    return result
