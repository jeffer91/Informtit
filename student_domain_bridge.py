from __future__ import annotations

from typing import Any

import nuclei_service
import process_service
from db import connection, rows_to_dicts, utcnow
from student_domain_service import (
    MATCH_OK,
    ROUTE_COMPLEXIVE,
    ROUTE_THESIS,
    get_period_students,
    match_source_record,
    save_source_link,
)


def ensure_bridge_schema() -> None:
    with connection() as conn:
        # Se añaden referencias opcionales a las tablas locales propias de Informtit.
        # No se modifica ninguna colección compartida de Firebase.
        for table in ("nucleus_students", "students", "thesis_projects"):
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not exists:
                continue
            columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if "period_student_id" not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN period_student_id INTEGER")
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_students'").fetchone():
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(nucleus_students)").fetchall()}
            additions = {
                "match_status": "TEXT DEFAULT ''",
                "match_method": "TEXT DEFAULT ''",
                "match_confidence": "REAL",
            }
            for name, definition in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE nucleus_students ADD COLUMN {name} {definition}")


def reconcile_nuclei(report_id: int) -> dict[str, Any]:
    ensure_bridge_schema()
    courses = nuclei_service.get_nuclei(report_id).get("courses", [])
    matched = 0
    pending = 0
    conflicts = 0
    with connection() as conn:
        for course in courses:
            course_id = int(course.get("id") or 0)
            if not course_id:
                continue
            for index, source in enumerate(course.get("students", []), start=1):
                source_key = f"course:{course_id}:student:{source.get('id') or source.get('email') or index}"
                candidate = {
                    "full_name": source.get("full_name") or "",
                    "email": source.get("email") or "",
                    "career_name": course.get("career_name") or "",
                }
                result = match_source_record(report_id, "NUCLEI", source_key, candidate)
                sid = result.get("period_student_id")
                status = result.get("status") or "UNMATCHED"
                if status == MATCH_OK and sid:
                    matched += 1
                elif status in {"REVIEW_REQUIRED", "AMBIGUOUS"}:
                    conflicts += 1
                else:
                    pending += 1
                source_id = source.get("id")
                if source_id:
                    conn.execute(
                        """
                        UPDATE nucleus_students SET period_student_id=?, match_status=?, match_method=?, match_confidence=?
                        WHERE id=?
                        """,
                        (sid, status, result.get("method") or "", result.get("confidence"), int(source_id)),
                    )
    return {"ok": True, "matched": matched, "pending": pending, "conflicts": conflicts}


def reconcile_complexive(report_id: int) -> dict[str, Any]:
    ensure_bridge_schema()
    with connection() as conn:
        rows = rows_to_dicts(conn.execute(
            """
            SELECT s.*, c.name AS career_name
            FROM students s JOIN careers c ON c.id=s.career_id
            WHERE c.report_id=? ORDER BY c.name, s.full_name, s.id
            """,
            (report_id,),
        ).fetchall())
    matched = 0
    route_conflicts = 0
    pending = 0
    masters = {int(row["id"]): row for row in get_period_students(report_id).get("students", [])}
    with connection() as conn:
        for row in rows:
            source_key = f"complexive:{int(row['id'])}"
            result = match_source_record(report_id, "COMPLEXIVE", source_key, row)
            sid = result.get("period_student_id")
            status = result.get("status") or "UNMATCHED"
            detail = ""
            if status == MATCH_OK and sid:
                master = masters.get(int(sid))
                if master and master.get("route") != ROUTE_COMPLEXIVE:
                    status = "ROUTE_CONFLICT"
                    detail = "El estudiante tiene ruta Trabajo de Titulación pero existen notas de Complexivo."
                    route_conflicts += 1
                    save_source_link(report_id, "COMPLEXIVE", source_key, row, {**result, "status": status, "detail": detail})
                else:
                    matched += 1
            else:
                pending += 1
            conn.execute("UPDATE students SET period_student_id=? WHERE id=?", (sid, int(row["id"])))
    return {"ok": True, "matched": matched, "pending": pending, "route_conflicts": route_conflicts}


def reconcile_thesis(report_id: int) -> dict[str, Any]:
    ensure_bridge_schema()
    with connection() as conn:
        rows = rows_to_dicts(conn.execute(
            "SELECT * FROM thesis_projects WHERE report_id=? ORDER BY full_name, id", (report_id,)
        ).fetchall())
    matched = 0
    route_conflicts = 0
    pending = 0
    masters = {int(row["id"]): row for row in get_period_students(report_id).get("students", [])}
    with connection() as conn:
        for row in rows:
            source_key = f"thesis:{int(row['id'])}"
            result = match_source_record(report_id, "THESIS", source_key, row)
            sid = result.get("period_student_id")
            status = result.get("status") or "UNMATCHED"
            detail = ""
            if status == MATCH_OK and sid:
                master = masters.get(int(sid))
                if master and master.get("route") != ROUTE_THESIS:
                    status = "ROUTE_CONFLICT"
                    detail = "Existe Trabajo de Titulación para un estudiante cuya ruta sigue siendo Complexivo."
                    route_conflicts += 1
                    save_source_link(report_id, "THESIS", source_key, row, {**result, "status": status, "detail": detail})
                else:
                    matched += 1
            else:
                pending += 1
            conn.execute("UPDATE thesis_projects SET period_student_id=? WHERE id=?", (sid, int(row["id"])))
    return {"ok": True, "matched": matched, "pending": pending, "route_conflicts": route_conflicts}


def reconcile_all(report_id: int) -> dict[str, Any]:
    return {
        "ok": True,
        "nuclei": reconcile_nuclei(report_id),
        "complexive": reconcile_complexive(report_id),
        "thesis": reconcile_thesis(report_id),
    }
