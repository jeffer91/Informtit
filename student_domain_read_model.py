from __future__ import annotations

from typing import Any

from db import connection, rows_to_dicts
from student_domain_service import MATCH_OK, get_period_students


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()} if _table_exists(conn, table) else set()


def _complexive_records(report_id: int) -> dict[int, list[dict[str, Any]]]:
    with connection() as conn:
        if "period_student_id" not in _columns(conn, "students"):
            return {}
        rows = rows_to_dicts(conn.execute(
            """
            SELECT s.*, c.name AS source_career
            FROM students s JOIN careers c ON c.id=s.career_id
            WHERE c.report_id=? AND s.period_student_id IS NOT NULL
            ORDER BY s.id
            """,
            (report_id,),
        ).fetchall())
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["period_student_id"]), []).append(row)
    return grouped


def _thesis_records(report_id: int) -> dict[int, list[dict[str, Any]]]:
    with connection() as conn:
        if "period_student_id" not in _columns(conn, "thesis_projects"):
            return {}
        rows = rows_to_dicts(conn.execute(
            "SELECT * FROM thesis_projects WHERE report_id=? AND period_student_id IS NOT NULL ORDER BY id",
            (report_id,),
        ).fetchall())
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["period_student_id"]), []).append(row)
    return grouped


def _nuclei_records(report_id: int) -> dict[int, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    with connection() as conn:
        if "period_student_id" in _columns(conn, "nucleus_instance_students") and _table_exists(conn, "nucleus_course_instances"):
            rows = rows_to_dicts(conn.execute(
                """
                SELECT ns.*, nc.nucleus_number, nc.career_name AS source_career,
                       nc.id AS course_id, nc.campus, nc.group_code, nc.module_code
                FROM nucleus_instance_students ns
                JOIN nucleus_course_instances nc ON nc.id=ns.course_id
                WHERE nc.report_id=? AND ns.period_student_id IS NOT NULL
                ORDER BY nc.nucleus_number, ns.id
                """,
                (report_id,),
            ).fetchall())
        elif "period_student_id" in _columns(conn, "nucleus_students") and _table_exists(conn, "nucleus_courses"):
            rows = rows_to_dicts(conn.execute(
                """
                SELECT ns.*, nc.nucleus_number, nc.career_name AS source_career, nc.id AS course_id
                FROM nucleus_students ns JOIN nucleus_courses nc ON nc.id=ns.course_id
                WHERE nc.report_id=? AND ns.period_student_id IS NOT NULL
                ORDER BY nc.nucleus_number, ns.id
                """,
                (report_id,),
            ).fetchall())
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["period_student_id"]), []).append(row)
    return grouped


def _effective_reconciliation(row: dict[str, Any]) -> tuple[str, str]:
    current = str(row.get("reconciliation_status") or MATCH_OK)
    detail = str(row.get("reconciliation_detail") or "")
    if current != MATCH_OK:
        return current, detail
    bad_links = [link for link in row.get("source_links", []) if str(link.get("match_status") or MATCH_OK) != MATCH_OK]
    if not bad_links:
        return MATCH_OK, detail
    priority = {
        "ROUTE_CONFLICT": 100,
        "GRADE_CONFLICT": 90,
        "AMBIGUOUS": 80,
        "REVIEW_REQUIRED": 70,
        "UNMATCHED": 60,
    }
    selected = max(bad_links, key=lambda link: priority.get(str(link.get("match_status") or ""), 50))
    selected_status = str(selected.get("match_status") or "REVIEW_REQUIRED")
    selected_detail = str(selected.get("detail") or "") or f"Revise la conciliación del módulo {selected.get('source_module') or 'académico'}."
    return selected_status, selected_detail


def consolidated_students(report_id: int) -> dict[str, Any]:
    students = get_period_students(report_id)
    complexive = _complexive_records(report_id)
    thesis = _thesis_records(report_id)
    nuclei = _nuclei_records(report_id)
    rows: list[dict[str, Any]] = []
    for student in students.get("students", []):
        sid = int(student["id"])
        row = dict(student)
        row["nuclei_records"] = nuclei.get(sid, [])
        row["complexive_records"] = complexive.get(sid, [])
        row["thesis_records"] = thesis.get(sid, [])
        row["has_nuclei"] = bool(row["nuclei_records"])
        row["has_complexive"] = bool(row["complexive_records"])
        row["has_thesis"] = bool(row["thesis_records"])
        effective_status, effective_detail = _effective_reconciliation(row)
        row["reconciliation_status"] = effective_status
        row["reconciliation_detail"] = effective_detail
        rows.append(row)

    summary = dict(students.get("summary", {}))
    summary["review"] = sum(row.get("reconciliation_status") != MATCH_OK for row in rows)
    summary["with_nuclei"] = sum(bool(row.get("has_nuclei")) for row in rows)
    summary["with_complexive"] = sum(bool(row.get("has_complexive")) for row in rows)
    summary["with_thesis_data"] = sum(bool(row.get("has_thesis")) for row in rows)
    return {"ok": True, "summary": summary, "students": rows}
