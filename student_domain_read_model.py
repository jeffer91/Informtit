from __future__ import annotations

from typing import Any

from db import connection, rows_to_dicts
from student_domain_service import get_period_students


def _complexive_records(report_id: int) -> dict[int, list[dict[str, Any]]]:
    with connection() as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='students'").fetchone()
        if not exists:
            return {}
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(students)").fetchall()}
        if "period_student_id" not in columns:
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
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='thesis_projects'").fetchone()
        if not exists:
            return {}
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(thesis_projects)").fetchall()}
        if "period_student_id" not in columns:
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
    with connection() as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_students'").fetchone()
        if not exists:
            return {}
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(nucleus_students)").fetchall()}
        if "period_student_id" not in columns:
            return {}
        # Soporta tanto la tabla legacy nucleus_courses como la entidad multicampus.
        rows: list[dict[str, Any]] = []
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_courses'").fetchone():
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
        rows.append(row)
    return {"ok": True, "summary": students.get("summary", {}), "students": rows}
