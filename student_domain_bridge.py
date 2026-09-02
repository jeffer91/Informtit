from __future__ import annotations

import json
from typing import Any

import nuclei_service
from coordinator_registry import normalize
from db import connection, rows_to_dicts
from parser import canonical_name_key, clean_moodle_name
from student_domain_service import (
    MATCH_OK,
    ROUTE_COMPLEXIVE,
    ROUTE_THESIS,
    build_match_index,
    get_period_students,
    match_source_record,
    save_source_link,
    sync_report_students,
)


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _ensure_columns(conn: Any, table: str, additions: dict[str, str]) -> None:
    if not _table_exists(conn, table):
        return
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def ensure_bridge_schema() -> None:
    """Añade referencias solo a tablas locales propias de Informtit."""
    with connection() as conn:
        for table in ("nucleus_students", "nucleus_instance_students"):
            _ensure_columns(
                conn,
                table,
                {
                    "period_student_id": "INTEGER",
                    "match_status": "TEXT DEFAULT ''",
                    "match_method": "TEXT DEFAULT ''",
                    "match_confidence": "REAL",
                },
            )
        _ensure_columns(conn, "students", {"period_student_id": "INTEGER"})
        _ensure_columns(conn, "thesis_projects", {"period_student_id": "INTEGER"})


def _nucleus_student_table(conn: Any, course_id: int) -> str | None:
    if _table_exists(conn, "nucleus_course_instances"):
        row = conn.execute("SELECT 1 FROM nucleus_course_instances WHERE id=?", (course_id,)).fetchone()
        if row and _table_exists(conn, "nucleus_instance_students"):
            return "nucleus_instance_students"
    if _table_exists(conn, "nucleus_courses"):
        row = conn.execute("SELECT 1 FROM nucleus_courses WHERE id=?", (course_id,)).fetchone()
        if row and _table_exists(conn, "nucleus_students"):
            return "nucleus_students"
    return None


def _source_identification(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or any(character.isalpha() for character in raw):
        return ""
    return "".join(character for character in raw if character.isdigit())


def _source_email(value: Any) -> str:
    email = str(value or "").strip().casefold()
    # El importador Excel genera correos técnicos que dependen del curso y no
    # representan la identidad real del estudiante.
    return "" if email.endswith("@excel.local") else email


def _stable_source_key(source_module: str, source: dict[str, Any], context: str = "") -> str:
    identification = _source_identification(source.get("identification"))
    email = _source_email(source.get("email"))
    name = canonical_name_key(clean_moodle_name(str(source.get("full_name") or "")))
    career = normalize(source.get("career_name"))
    prefix = source_module.lower()
    if identification:
        identity = f"id:{identification}"
    elif email:
        identity = f"email:{email}"
    elif name:
        identity = f"name:{career}|{name}"
    else:
        identity = "unknown"
    return f"{prefix}:{context}:{identity}" if context else f"{prefix}:{identity}"


def _nucleus_context(course: dict[str, Any]) -> str:
    """Contexto estable del curso, independiente del id autoincremental SQLite."""
    parts = (
        normalize(course.get("career_name")),
        str(int(course.get("nucleus_number") or 0)),
        normalize(course.get("course_title")),
        normalize(course.get("campus")),
        normalize(course.get("module_code")),
        normalize(course.get("period_label")),
        normalize(course.get("group_code")),
        normalize(course.get("schedule")),
        normalize(course.get("teacher_name")),
    )
    return "course:" + "|".join(parts)


def _manual_match(report_id: int, source_module: str, source_key: str) -> dict[str, Any] | None:
    """Las decisiones humanas prevalecen sobre cualquier nuevo cálculo automático."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT period_student_id, match_confidence, candidates_json
            FROM student_source_links
            WHERE report_id=? AND source_module=? AND source_key=?
              AND match_method='MANUAL' AND period_student_id IS NOT NULL
            """,
            (report_id, source_module, source_key),
        ).fetchone()
    if not row:
        return None
    try:
        candidates = json.loads(row["candidates_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        candidates = []
    return {
        "status": MATCH_OK,
        "method": "MANUAL",
        "confidence": float(row["match_confidence"] or 100.0),
        "period_student_id": int(row["period_student_id"]),
        "candidates": candidates,
    }


def _manual_match_by_identity(
    report_id: int,
    source_module: str,
    source: dict[str, Any],
) -> dict[str, Any] | None:
    """Recupera una decisión manual aunque el registro fuente haya sido recreado.

    Solo reutiliza la asociación si todas las coincidencias manuales compatibles
    apuntan al mismo estudiante; así no se fuerza un enlace en homónimos.
    """
    identification = _source_identification(source.get("identification"))
    email = _source_email(source.get("email"))
    name = canonical_name_key(clean_moodle_name(str(source.get("full_name") or "")))
    career = normalize(source.get("career_name"))
    if not any((identification, email, name)):
        return None

    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT period_student_id, source_name, source_email, source_identification,
                       source_career, match_confidence, candidates_json
                FROM student_source_links
                WHERE report_id=? AND source_module=? AND match_method='MANUAL'
                  AND period_student_id IS NOT NULL
                ORDER BY id DESC
                """,
                (report_id, source_module),
            ).fetchall()
        )

    matches: list[dict[str, Any]] = []
    for row in rows:
        row_id = _source_identification(row.get("source_identification"))
        row_email = _source_email(row.get("source_email"))
        row_name = canonical_name_key(clean_moodle_name(str(row.get("source_name") or "")))
        row_career = normalize(row.get("source_career"))
        compatible = False
        if identification and row_id:
            compatible = identification == row_id
        elif email and row_email:
            compatible = email == row_email
        elif name and row_name:
            compatible = name == row_name and (not career or not row_career or career == row_career)
        if compatible:
            matches.append(row)

    student_ids = {int(row["period_student_id"]) for row in matches if row.get("period_student_id")}
    if len(student_ids) != 1:
        return None
    selected = matches[0]
    try:
        candidates = json.loads(selected.get("candidates_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        candidates = []
    return {
        "status": MATCH_OK,
        "method": "MANUAL",
        "confidence": float(selected.get("match_confidence") or 100.0),
        "period_student_id": next(iter(student_ids)),
        "candidates": candidates,
    }


def _legacy_nucleus_manual_match(report_id: int, source: dict[str, Any]) -> dict[str, Any] | None:
    """Migra en lectura las asociaciones manuales del sistema anterior de Núcleos."""
    email = _source_email(source.get("email"))
    name = canonical_name_key(clean_moodle_name(str(source.get("full_name") or "")))
    career = normalize(source.get("career_name"))
    keys: list[str] = []
    if email:
        keys.append(f"email:{email}")
    if name:
        keys.append(f"name:{career}|{name}")
    if not keys:
        return None
    with connection() as conn:
        if not _table_exists(conn, "nucleus_manual_matches"):
            return None
        placeholders = ",".join("?" for _ in keys)
        legacy = conn.execute(
            f"""
            SELECT student_id FROM nucleus_manual_matches
            WHERE report_id=? AND source_key IN ({placeholders})
            ORDER BY id DESC LIMIT 1
            """,
            (report_id, *keys),
        ).fetchone()
        if not legacy:
            return None
        master = conn.execute(
            """
            SELECT id FROM period_students
            WHERE report_id=? AND requirements_student_id=?
            """,
            (report_id, int(legacy["student_id"])),
        ).fetchone()
    if not master:
        return None
    return {
        "status": MATCH_OK,
        "method": "MANUAL",
        "confidence": 100.0,
        "period_student_id": int(master["id"]),
        "candidates": [],
    }


def _match(
    report_id: int,
    source_module: str,
    source_key: str,
    source: dict[str, Any],
    *,
    students: list[dict[str, Any]] | None = None,
    match_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manual = _manual_match(report_id, source_module, source_key)
    if manual:
        return manual

    recovered = _manual_match_by_identity(report_id, source_module, source)
    if recovered:
        save_source_link(report_id, source_module, source_key, source, recovered)
        return recovered

    if source_module == "NUCLEI":
        legacy = _legacy_nucleus_manual_match(report_id, source)
        if legacy:
            save_source_link(report_id, source_module, source_key, source, legacy)
            return legacy
    return match_source_record(
        report_id,
        source_module,
        source_key,
        source,
        students=students,
        match_index=match_index,
    )


def reconcile_nuclei(
    report_id: int,
    *,
    students: list[dict[str, Any]] | None = None,
    match_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_bridge_schema()
    courses = nuclei_service.get_nuclei(report_id).get("courses", [])
    matched = 0
    pending = 0
    conflicts = 0
    route_conflicts = 0
    if students is None:
        students = get_period_students(report_id, sync=False).get("students", [])
    if match_index is None:
        match_index = build_match_index(students)
    masters = {int(row["id"]): row for row in students}
    with connection() as conn:
        for course in courses:
            course_id = int(course.get("id") or 0)
            if not course_id:
                continue
            table = _nucleus_student_table(conn, course_id)
            context = _nucleus_context(course)
            for source in course.get("students", []):
                candidate = {
                    "identification": source.get("identification") or "",
                    "full_name": source.get("full_name") or "",
                    "email": source.get("email") or "",
                    "career_name": course.get("career_name") or "",
                }
                source_key = _stable_source_key("NUCLEI", candidate, context)
                result = _match(
                    report_id,
                    "NUCLEI",
                    source_key,
                    candidate,
                    students=students,
                    match_index=match_index,
                )
                sid = result.get("period_student_id")
                status = result.get("status") or "UNMATCHED"
                detail = ""
                if status == MATCH_OK and sid:
                    master = masters.get(int(sid))
                    if master and master.get("route") != ROUTE_COMPLEXIVE:
                        status = "ROUTE_CONFLICT"
                        detail = "El estudiante tiene ruta Trabajo de Titulación pero aparece en Núcleos."
                        route_conflicts += 1
                        save_source_link(
                            report_id,
                            "NUCLEI",
                            source_key,
                            candidate,
                            {**result, "status": status, "detail": detail},
                        )
                    else:
                        matched += 1
                        if result.get("method") == "MANUAL":
                            save_source_link(report_id, "NUCLEI", source_key, candidate, result)
                elif status in {"REVIEW_REQUIRED", "AMBIGUOUS"}:
                    conflicts += 1
                else:
                    pending += 1
                source_id = source.get("id")
                if table and source_id:
                    conn.execute(
                        f"""
                        UPDATE {table} SET period_student_id=?, match_status=?, match_method=?, match_confidence=?
                        WHERE id=? AND course_id=?
                        """,
                        (
                            sid,
                            status,
                            result.get("method") or "",
                            result.get("confidence"),
                            int(source_id),
                            course_id,
                        ),
                    )
    return {
        "ok": True,
        "matched": matched,
        "pending": pending,
        "conflicts": conflicts,
        "route_conflicts": route_conflicts,
    }


def reconcile_complexive(
    report_id: int,
    *,
    students: list[dict[str, Any]] | None = None,
    match_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_bridge_schema()
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT s.*, c.name AS career_name
                FROM students s JOIN careers c ON c.id=s.career_id
                WHERE c.report_id=? ORDER BY c.name, s.full_name, s.id
                """,
                (report_id,),
            ).fetchall()
        )
    matched = 0
    route_conflicts = 0
    pending = 0
    if students is None:
        students = get_period_students(report_id, sync=False).get("students", [])
    if match_index is None:
        match_index = build_match_index(students)
    masters = {int(row["id"]): row for row in students}
    with connection() as conn:
        for row in rows:
            source_key = _stable_source_key("COMPLEXIVE", row)
            result = _match(
                report_id,
                "COMPLEXIVE",
                source_key,
                row,
                students=students,
                match_index=match_index,
            )
            sid = result.get("period_student_id")
            status = result.get("status") or "UNMATCHED"
            if status == MATCH_OK and sid:
                master = masters.get(int(sid))
                if master and master.get("route") != ROUTE_COMPLEXIVE:
                    status = "ROUTE_CONFLICT"
                    detail = "El estudiante tiene ruta Trabajo de Titulación pero existen notas de Complexivo."
                    route_conflicts += 1
                    save_source_link(
                        report_id,
                        "COMPLEXIVE",
                        source_key,
                        row,
                        {**result, "status": status, "detail": detail},
                    )
                else:
                    matched += 1
                    if result.get("method") == "MANUAL":
                        save_source_link(report_id, "COMPLEXIVE", source_key, row, result)
            else:
                pending += 1
            conn.execute("UPDATE students SET period_student_id=? WHERE id=?", (sid, int(row["id"])))
    return {"ok": True, "matched": matched, "pending": pending, "route_conflicts": route_conflicts}


def reconcile_thesis(
    report_id: int,
    *,
    students: list[dict[str, Any]] | None = None,
    match_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_bridge_schema()
    with connection() as conn:
        if not _table_exists(conn, "thesis_projects"):
            return {"ok": True, "matched": 0, "pending": 0, "route_conflicts": 0}
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM thesis_projects WHERE report_id=? ORDER BY full_name, id",
                (report_id,),
            ).fetchall()
        )
    matched = 0
    route_conflicts = 0
    pending = 0
    if students is None:
        students = get_period_students(report_id, sync=False).get("students", [])
    if match_index is None:
        match_index = build_match_index(students)
    masters = {int(row["id"]): row for row in students}
    with connection() as conn:
        for row in rows:
            source_key = _stable_source_key("THESIS", row)
            result = _match(
                report_id,
                "THESIS",
                source_key,
                row,
                students=students,
                match_index=match_index,
            )
            sid = result.get("period_student_id")
            status = result.get("status") or "UNMATCHED"
            if status == MATCH_OK and sid:
                master = masters.get(int(sid))
                if master and master.get("route") != ROUTE_THESIS:
                    status = "ROUTE_CONFLICT"
                    detail = "Existe Trabajo de Titulación para un estudiante cuya ruta sigue siendo Complexivo."
                    route_conflicts += 1
                    save_source_link(
                        report_id,
                        "THESIS",
                        source_key,
                        row,
                        {**result, "status": status, "detail": detail},
                    )
                else:
                    matched += 1
                    if result.get("method") == "MANUAL":
                        save_source_link(report_id, "THESIS", source_key, row, result)
            else:
                pending += 1
            conn.execute("UPDATE thesis_projects SET period_student_id=? WHERE id=?", (sid, int(row["id"])))
    return {"ok": True, "matched": matched, "pending": pending, "route_conflicts": route_conflicts}


def reconcile_all(report_id: int) -> dict[str, Any]:
    """Conciliación completa incremental en memoria.

    Requisitos se sincroniza una sola vez; la población y sus índices se
    reutilizan en Núcleos, Complexivo y Trabajo de Titulación.
    """
    sync_report_students(report_id)
    students = get_period_students(report_id, sync=False).get("students", [])
    match_index = build_match_index(students)
    return {
        "ok": True,
        "nuclei": reconcile_nuclei(report_id, students=students, match_index=match_index),
        "complexive": reconcile_complexive(report_id, students=students, match_index=match_index),
        "thesis": reconcile_thesis(report_id, students=students, match_index=match_index),
    }
