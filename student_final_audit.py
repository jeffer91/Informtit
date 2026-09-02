from __future__ import annotations

import json
import re
from collections import defaultdict
from contextvars import ContextVar
from typing import Any, Callable

import eligibility_service as eligibility
import report_completion
import report_decoupled
import report_quality
import student_domain_bridge as bridge
import student_domain_integrations as integrations
import student_domain_read_model as read_model
import student_domain_runtime as domain_runtime
import student_domain_service as domain
import student_period_service as period_service
import student_period_runtime as period_runtime
import student_report_integration as report_integration
from db import connection, rows_to_dicts, utcnow
from parser import canonical_name_key, clean_moodle_name

MATCH_DUPLICATE = "DUPLICATE"
MATCH_IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
MATCH_MODALITY_CONFLICT = "MODALITY_CONFLICT"

_MATCH_CACHE: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "informtit_student_match_cache",
    default=None,
)

_INSTALLED_PRE = False
_INSTALLED_POST = False
_API_INSTALLED = False

_BASE_ENSURE_SCHEMA = domain.ensure_student_domain_schema
_BASE_SYNC = domain.sync_report_students
_BASE_GET_STUDENTS = domain.get_period_students
_BASE_MATCH = domain.match_source_record
_BASE_SAVE_LINK = domain.save_source_link
_BASE_MANUAL_RECOVERY = bridge._manual_match_by_identity
_BASE_BRIDGE_MATCH = bridge._match
_BASE_RECONCILE_NUCLEI = bridge.reconcile_nuclei
_BASE_RECONCILE_COMPLEXIVE = bridge.reconcile_complexive
_BASE_RECONCILE_THESIS = bridge.reconcile_thesis
_BASE_RECONCILE_ALL = bridge.reconcile_all
_BASE_PERIOD_REFRESH = period_service._refresh_report
_BASE_PERIOD_GET = period_service.get_period_student_domain

_INTEGRATED_CONCLUSION = (
    "Los resultados se integran sobre la población maestra de Requisitos: cada "
    "evidencia de Núcleos, Examen Complexivo o Trabajo de Titulación se atribuye "
    "al estudiante conciliado y a la ruta que le corresponde."
)


def _table_exists(conn: Any, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def _columns(conn: Any, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _ensure_column(conn: Any, table: str, name: str, definition: str) -> None:
    if not _table_exists(conn, table):
        return
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def ensure_schema() -> None:
    """Extiende el dominio maestro sin alterar ni depender de Firebase."""
    _BASE_ENSURE_SCHEMA()
    with connection() as conn:
        _ensure_column(
            conn,
            "period_students",
            "requirements_present",
            "INTEGER NOT NULL DEFAULT 1",
        )
        _ensure_column(
            conn,
            "period_students",
            "modality_conflict",
            "INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            conn,
            "student_source_links",
            "source_active",
            "INTEGER NOT NULL DEFAULT 1",
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_student_source_links_active "
            "ON student_source_links(report_id, source_module, source_active)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_period_students_present "
            "ON period_students(report_id, requirements_present, reconciliation_status)"
        )


def _official_identification(value: Any) -> str:
    return domain._id_number(value)


def _public_identification(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.startswith("NOID:") or raw.startswith("REQ-"):
        return ""
    return raw


def _fold(value: Any) -> str:
    return canonical_name_key(clean_moodle_name(str(value or "")))


def _email(value: Any) -> str:
    return str(value or "").strip().casefold()


def _migration_candidates(
    current: dict[str, Any],
    masters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_email = _email(current.get("email"))
    personal_email = _email(current.get("personal_email"))
    current_name = _fold(current.get("full_name"))
    current_career = _fold(current.get("career_name"))
    current_modality = str(current.get("modality") or "").strip().casefold()
    current_campus = _fold(current.get("campus"))

    def unique(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[int] = set()
        result: list[dict[str, Any]] = []
        for item in items:
            item_id = int(item["id"])
            if item_id in seen:
                continue
            seen.add(item_id)
            result.append(item)
        return result

    if current_email:
        matches = [
            item
            for item in masters
            if _email(item.get("email")) == current_email
        ]
        if len(matches) == 1:
            return matches

    if personal_email:
        matches = [
            item
            for item in masters
            if _email(item.get("personal_email")) == personal_email
        ]
        if len(matches) == 1:
            return matches

    if not current_name:
        return []

    name_matches = [
        item
        for item in masters
        if _fold(item.get("full_name")) == current_name
        and (
            not current_career
            or not _fold(item.get("career_name"))
            or _fold(item.get("career_name")) == current_career
        )
    ]
    if len(name_matches) <= 1:
        return name_matches

    narrowed = [
        item
        for item in name_matches
        if (
            not current_modality
            or not str(item.get("modality") or "").strip()
            or str(item.get("modality") or "").strip().casefold()
            == current_modality
        )
        and (
            not current_campus
            or not _fold(item.get("campus"))
            or _fold(item.get("campus")) == current_campus
        )
    ]
    return unique(narrowed) if len(narrowed) == 1 else []


def _migrate_identity_keys(report_id: int) -> None:
    """Conserva la misma entidad cuando Requisitos corrige o incorpora la cédula."""
    with connection() as conn:
        if not _table_exists(conn, "requirements_students"):
            return
        current = rows_to_dicts(
            conn.execute(
                "SELECT * FROM requirements_students WHERE report_id=? ORDER BY id",
                (report_id,),
            ).fetchall()
        )
        masters = rows_to_dicts(
            conn.execute(
                "SELECT * FROM period_students WHERE report_id=? ORDER BY id",
                (report_id,),
            ).fetchall()
        )
        if not current or not masters:
            return

        now = utcnow()
        occupied = {
            str(item.get("identification") or ""): int(item["id"])
            for item in masters
            if item.get("identification")
        }
        for row in current:
            target_key = domain._stable_identification(row)
            if target_key in occupied:
                continue
            candidates = _migration_candidates(row, masters)
            if len(candidates) != 1:
                continue
            candidate = candidates[0]
            student_id = int(candidate["id"])
            old_key = str(candidate.get("identification") or "")
            if not old_key or old_key == target_key:
                continue
            if target_key in occupied and occupied[target_key] != student_id:
                continue
            conn.execute(
                "UPDATE period_students SET identification=?, updated_at=? WHERE id=?",
                (target_key, now, student_id),
            )
            conn.execute(
                """
                INSERT INTO student_audit_log
                (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
                VALUES (?, ?, 'MIGRATE_IDENTITY_KEY', 'identification', ?, ?,
                        'La identidad maestra se conservó al corregirse o incorporarse la cédula en Requisitos.', ?)
                """,
                (report_id, student_id, old_key, target_key, now),
            )
            occupied.pop(old_key, None)
            occupied[target_key] = student_id
            candidate["identification"] = target_key


def _source_duplicate_groups(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[domain._stable_identification(row)].append(row)
    return {key: items for key, items in groups.items() if len(items) > 1}


def _duplicate_emails(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        email = _email(row.get("email"))
        if email:
            groups[email].append(row)
    result: dict[str, list[dict[str, Any]]] = {}
    for email, items in groups.items():
        identities = {domain._stable_identification(item) for item in items}
        if len(items) > 1 and len(identities) > 1:
            result[email] = items
    return result


def _recompute_base_reconciliation(conn: Any, row: Any) -> tuple[str, str]:
    if not int(row["requirements_present"] or 0):
        return domain.MATCH_REVIEW, "El estudiante ya no aparece en la carga actual de Requisitos."
    try:
        snapshot = json.loads(row["source_snapshot_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        snapshot = {}
    conflicts = domain._official_conflicts(snapshot) if snapshot else []
    if conflicts:
        return domain.MATCH_OFFICIAL_CONFLICT, " ".join(conflicts)
    return domain.MATCH_OK, ""


def _refresh_modality_conflicts(period_project_id: int | None) -> set[int]:
    if not period_project_id:
        return set()
    ensure_schema()
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM period_students
                WHERE period_project_id=? AND requirements_present=1
                ORDER BY report_id, id
                """,
                (period_project_id,),
            ).fetchall()
        )
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            identification = _official_identification(row.get("identification"))
            if identification:
                groups[identification].append(row)

        conflict_ids: set[int] = set()
        for items in groups.values():
            report_ids = {int(item["report_id"]) for item in items}
            if len(report_ids) > 1:
                conflict_ids.update(int(item["id"]) for item in items)

        existing = conn.execute(
            "SELECT * FROM period_students WHERE period_project_id=?",
            (period_project_id,),
        ).fetchall()
        for row in existing:
            student_id = int(row["id"])
            if student_id in conflict_ids:
                conn.execute(
                    """
                    UPDATE period_students
                    SET modality_conflict=1, reconciliation_status=?,
                        reconciliation_detail=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        MATCH_MODALITY_CONFLICT,
                        "La misma cédula aparece simultáneamente en los datasets Presencial y Online del período.",
                        utcnow(),
                        student_id,
                    ),
                )
            else:
                status = str(row["reconciliation_status"] or "")
                if status == MATCH_MODALITY_CONFLICT:
                    base_status, detail = _recompute_base_reconciliation(conn, row)
                    conn.execute(
                        """
                        UPDATE period_students
                        SET modality_conflict=0, reconciliation_status=?,
                            reconciliation_detail=?, updated_at=?
                        WHERE id=?
                        """,
                        (base_status, detail, utcnow(), student_id),
                    )
                elif int(row["modality_conflict"] or 0):
                    conn.execute(
                        "UPDATE period_students SET modality_conflict=0, updated_at=? WHERE id=?",
                        (utcnow(), student_id),
                    )
        return conflict_ids


def _apply_source_duplicates(report_id: int, source: list[dict[str, Any]]) -> None:
    duplicates = _source_duplicate_groups(source)
    email_duplicates = _duplicate_emails(source)
    with connection() as conn:
        for identity, items in duplicates.items():
            row = conn.execute(
                "SELECT id FROM period_students WHERE report_id=? AND identification=?",
                (report_id, identity),
            ).fetchone()
            if not row:
                continue
            conn.execute(
                """
                UPDATE period_students
                SET reconciliation_status=?, reconciliation_detail=?, updated_at=?
                WHERE id=?
                """,
                (
                    MATCH_DUPLICATE,
                    f"Requisitos contiene {len(items)} filas para la misma identidad; debe conservarse un único registro oficial.",
                    utcnow(),
                    int(row["id"]),
                ),
            )

        for email, items in email_duplicates.items():
            identities = {domain._stable_identification(item) for item in items}
            placeholders = ",".join("?" for _ in identities)
            if not placeholders:
                continue
            conn.execute(
                f"""
                UPDATE period_students
                SET reconciliation_status=?, reconciliation_detail=?, updated_at=?
                WHERE report_id=? AND identification IN ({placeholders})
                """,
                (
                    MATCH_DUPLICATE,
                    f"El correo institucional {email} está asignado a más de una identidad en Requisitos.",
                    utcnow(),
                    report_id,
                    *sorted(identities),
                ),
            )


def sync_report_students(report_id: int) -> dict[str, Any]:
    ensure_schema()
    _migrate_identity_keys(report_id)
    result = _BASE_SYNC(report_id)

    with connection() as conn:
        source = (
            rows_to_dicts(
                conn.execute(
                    "SELECT * FROM requirements_students WHERE report_id=? ORDER BY id",
                    (report_id,),
                ).fetchall()
            )
            if _table_exists(conn, "requirements_students")
            else []
        )
        current_ids = {int(row["id"]) for row in source}
        conn.execute(
            "UPDATE period_students SET requirements_present=0 WHERE report_id=?",
            (report_id,),
        )
        if current_ids:
            placeholders = ",".join("?" for _ in current_ids)
            conn.execute(
                f"""
                UPDATE period_students SET requirements_present=1
                WHERE report_id=? AND requirements_student_id IN ({placeholders})
                """,
                (report_id, *sorted(current_ids)),
            )
        conn.execute(
            """
            UPDATE period_students
            SET reconciliation_status=?, reconciliation_detail=?, updated_at=?
            WHERE report_id=? AND requirements_present=0
            """,
            (
                domain.MATCH_REVIEW,
                "El estudiante ya no aparece en la carga actual de Requisitos.",
                utcnow(),
                report_id,
            ),
        )
        project_row = conn.execute(
            "SELECT period_project_id FROM reports WHERE id=?",
            (report_id,),
        ).fetchone()
        project_id = (
            int(project_row["period_project_id"])
            if project_row and project_row["period_project_id"] is not None
            else None
        )

    _apply_source_duplicates(report_id, source)
    _refresh_modality_conflicts(project_id)
    return result


def _active_source_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        link
        for link in links
        if int(link.get("source_active", 1) or 0) == 1
    ]


def get_period_students(report_id: int, *, sync: bool = True) -> dict[str, Any]:
    data = _BASE_GET_STUDENTS(report_id, sync=sync)
    rows = data.get("students", [])
    for row in rows:
        row["source_links"] = _active_source_links(list(row.get("source_links", [])))
        raw_identification = str(row.get("identification") or "")
        row["identity_key"] = raw_identification
        row["identification"] = _public_identification(raw_identification)
        row["requirements_present"] = int(row.get("requirements_present", 1) or 0)
        row["modality_conflict"] = int(row.get("modality_conflict", 0) or 0)
    summary = data.get("summary") or {}
    summary["students"] = len(rows)
    summary["review"] = sum(
        str(row.get("reconciliation_status") or domain.MATCH_OK) != domain.MATCH_OK
        or not int(row.get("requirements_present", 1) or 0)
        for row in rows
    )
    data["summary"] = summary
    return data


def _candidate_payload(score: float, student: dict[str, Any]) -> dict[str, Any]:
    return {
        "student_id": int(student["id"]),
        "identification": _public_identification(student.get("identification")),
        "full_name": student.get("full_name") or "",
        "email": student.get("email") or "",
        "career_name": student.get("career_name") or "",
        "similarity": round(score * 100, 1),
    }


def _matching_students(report_id: int) -> list[dict[str, Any]]:
    cached = _MATCH_CACHE.get()
    if cached is not None:
        return cached
    return [
        row
        for row in get_period_students(report_id).get("students", [])
        if int(row.get("requirements_present", 1) or 0) == 1
    ]


def match_source_record(
    report_id: int,
    source_module: str,
    source_key: str,
    source: dict[str, Any],
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Matcher conservador: los identificadores fuertes nunca se contradicen en silencio."""
    students = _matching_students(report_id)
    ranked = sorted(
        ((domain._candidate_score(source, student), student) for student in students),
        key=lambda item: (-item[0], str(item[1].get("full_name") or "")),
    )
    score, student = ranked[0] if ranked else (0.0, None)
    second = ranked[1][0] if len(ranked) > 1 else 0.0

    sid = domain._id_number(source.get("identification"))
    semail = _email(source.get("email"))
    if semail.endswith("@excel.local"):
        semail = ""

    id_matches = [
        item for item in students
        if sid and domain._id_number(item.get("identification")) == sid
    ]
    email_matches = [
        item for item in students
        if semail and _email(item.get("email")) == semail
    ]

    status = domain.MATCH_UNMATCHED
    method = ""
    selected_id: int | None = None
    detail = ""

    if sid:
        if len(id_matches) == 1:
            target = id_matches[0]
            conflicting_email_ids = {
                int(item["id"])
                for item in email_matches
                if int(item["id"]) != int(target["id"])
            }
            if conflicting_email_ids:
                status = MATCH_IDENTITY_CONFLICT
                method = "CEDULA_CORREO_CONFLICTO"
                detail = "La cédula y el correo apuntan a estudiantes distintos; se requiere confirmación manual."
            else:
                status = domain.MATCH_OK
                method = "CEDULA"
                selected_id = int(target["id"])
        elif len(id_matches) > 1:
            status = MATCH_IDENTITY_CONFLICT
            method = "CEDULA_DUPLICADA"
            detail = "La cédula coincide con más de un estudiante maestro."
        elif email_matches or (student and score >= 0.85):
            status = MATCH_IDENTITY_CONFLICT
            method = "CEDULA_NO_COINCIDE"
            detail = "El registro trae una cédula que no coincide con la identidad sugerida por correo o nombre."
    elif semail:
        if len(email_matches) == 1:
            status = domain.MATCH_OK
            method = "CORREO"
            selected_id = int(email_matches[0]["id"])
        elif len(email_matches) > 1:
            status = MATCH_IDENTITY_CONFLICT
            method = "CORREO_DUPLICADO"
            detail = "El correo coincide con más de un estudiante maestro."
    if not sid and not selected_id and status == domain.MATCH_UNMATCHED and student:
        gap = score - second
        if score >= 0.85 and len(ranked) > 1 and abs(gap) < 0.03:
            status = domain.MATCH_AMBIGUOUS
            method = "NOMBRE_AMBIGUO"
        elif score >= 0.97 and gap >= 0.04:
            status = domain.MATCH_OK
            method = "NOMBRE_ALTA_CONFIANZA"
            selected_id = int(student["id"])
        elif score >= 0.85:
            status = domain.MATCH_REVIEW
            method = "NOMBRE_POSIBLE"

    candidates = [_candidate_payload(item[0], item[1]) for item in ranked[:8]]
    result = {
        "status": status,
        "method": method,
        "confidence": round(score * 100, 1) if score else 0.0,
        "period_student_id": selected_id,
        "candidates": candidates,
        "detail": detail,
    }
    if persist:
        save_source_link(report_id, source_module, source_key, source, result)
    return result


def save_source_link(
    report_id: int,
    source_module: str,
    source_key: str,
    source: dict[str, Any],
    match: dict[str, Any],
) -> None:
    ensure_schema()
    _BASE_SAVE_LINK(report_id, source_module, source_key, source, match)
    with connection() as conn:
        conn.execute(
            """
            UPDATE student_source_links
            SET source_active=1, updated_at=?
            WHERE report_id=? AND source_module=? AND source_key=?
            """,
            (utcnow(), report_id, source_module, source_key),
        )


def _safe_manual_recovery(
    report_id: int,
    source_module: str,
    source: dict[str, Any],
) -> dict[str, Any] | None:
    recovered = _BASE_MANUAL_RECOVERY(report_id, source_module, source)
    if not recovered:
        return None

    identification = bridge._source_identification(source.get("identification"))
    email = bridge._source_email(source.get("email"))
    name = _fold(source.get("full_name"))
    career = bridge.normalize(source.get("career_name"))

    with connection() as conn:
        candidates = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM period_students
                WHERE report_id=? AND COALESCE(requirements_present, 1)=1
                ORDER BY id
                """,
                (report_id,),
            ).fetchall()
        )

    if identification:
        matches = [
            row for row in candidates
            if bridge._source_identification(row.get("identification")) == identification
        ]
    elif email:
        matches = [
            row for row in candidates
            if bridge._source_email(row.get("email")) == email
        ]
    else:
        matches = [
            row for row in candidates
            if _fold(row.get("full_name")) == name
            and (
                not career
                or not bridge.normalize(row.get("career_name"))
                or bridge.normalize(row.get("career_name")) == career
            )
        ]

    if len(matches) != 1:
        return None
    return recovered if int(matches[0]["id"]) == int(recovered["period_student_id"]) else None


def _manual_review_decision(
    report_id: int,
    source_module: str,
    source_key: str,
    source: dict[str, Any],
) -> dict[str, Any] | None:
    with connection() as conn:
        exact = conn.execute(
            """
            SELECT match_confidence, candidates_json, detail
            FROM student_source_links
            WHERE report_id=? AND source_module=? AND source_key=?
              AND match_method='MANUAL_REVIEW' AND period_student_id IS NULL
            """,
            (report_id, source_module, source_key),
        ).fetchone()
    if exact:
        try:
            candidates = json.loads(exact["candidates_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            candidates = []
        return {
            "status": domain.MATCH_REVIEW,
            "method": "MANUAL_REVIEW",
            "confidence": exact["match_confidence"],
            "period_student_id": None,
            "candidates": candidates,
            "detail": exact["detail"] or "Vínculo desasociado manualmente; requiere una nueva decisión.",
        }
    return None


def _audited_bridge_match(
    report_id: int,
    source_module: str,
    source_key: str,
    source: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    manual_review = _manual_review_decision(
        report_id,
        source_module,
        source_key,
        source,
    )
    if manual_review:
        return manual_review
    return _BASE_BRIDGE_MATCH(report_id, source_module, source_key, source, **kwargs)


def _mark_current_source_keys(
    report_id: int,
    source_module: str,
    keys: set[str],
) -> None:
    ensure_schema()
    with connection() as conn:
        conn.execute(
            """
            UPDATE student_source_links
            SET source_active=0, updated_at=?
            WHERE report_id=? AND source_module=?
            """,
            (utcnow(), report_id, source_module),
        )
        if keys:
            conn.executemany(
                """
                UPDATE student_source_links
                SET source_active=1, updated_at=?
                WHERE report_id=? AND source_module=? AND source_key=?
                """,
                [
                    (utcnow(), report_id, source_module, key)
                    for key in sorted(keys)
                ],
            )


def _nuclei_source_keys(report_id: int) -> set[str]:
    keys: set[str] = set()
    for course in bridge.nuclei_service.get_nuclei(report_id).get("courses", []):
        context = bridge._nucleus_context(course)
        for source in course.get("students", []):
            candidate = {
                "identification": source.get("identification") or "",
                "full_name": source.get("full_name") or "",
                "email": source.get("email") or "",
                "career_name": course.get("career_name") or "",
            }
            keys.add(bridge._stable_source_key("NUCLEI", candidate, context))
    return keys


def _complexive_source_keys(report_id: int) -> set[str]:
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT s.*, c.name AS career_name
                FROM students s JOIN careers c ON c.id=s.career_id
                WHERE c.report_id=?
                """,
                (report_id,),
            ).fetchall()
        )
    return {bridge._stable_source_key("COMPLEXIVE", row) for row in rows}


def _thesis_source_keys(report_id: int) -> set[str]:
    with connection() as conn:
        if not _table_exists(conn, "thesis_projects"):
            return set()
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM thesis_projects WHERE report_id=?",
                (report_id,),
            ).fetchall()
        )
    return {bridge._stable_source_key("THESIS", row) for row in rows}


def _with_match_cache(
    report_id: int,
    callback: Callable[[int], dict[str, Any]],
    *,
    students: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ejecuta una conciliación con una sola población maestra en memoria."""
    current = _MATCH_CACHE.get()
    if current is not None:
        return callback(report_id)
    if students is None:
        students = [
            row
            for row in get_period_students(report_id).get("students", [])
            if int(row.get("requirements_present", 1) or 0) == 1
        ]
    token = _MATCH_CACHE.set(students)
    try:
        return callback(report_id)
    finally:
        _MATCH_CACHE.reset(token)


def reconcile_nuclei(
    report_id: int,
    *,
    students: list[dict[str, Any]] | None = None,
    match_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def run(rid: int) -> dict[str, Any]:
        result = _BASE_RECONCILE_NUCLEI(
            rid,
            students=students,
            match_index=match_index,
        )
        _mark_current_source_keys(rid, "NUCLEI", _nuclei_source_keys(rid))
        return result

    return _with_match_cache(report_id, run, students=students)


def reconcile_complexive(
    report_id: int,
    *,
    students: list[dict[str, Any]] | None = None,
    match_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def run(rid: int) -> dict[str, Any]:
        result = _BASE_RECONCILE_COMPLEXIVE(
            rid,
            students=students,
            match_index=match_index,
        )
        _mark_current_source_keys(rid, "COMPLEXIVE", _complexive_source_keys(rid))
        return result

    return _with_match_cache(report_id, run, students=students)


def reconcile_thesis(
    report_id: int,
    *,
    students: list[dict[str, Any]] | None = None,
    match_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def run(rid: int) -> dict[str, Any]:
        result = _BASE_RECONCILE_THESIS(
            rid,
            students=students,
            match_index=match_index,
        )
        _mark_current_source_keys(rid, "THESIS", _thesis_source_keys(rid))
        return result

    if students is not None:
        return run(report_id)
    return _with_match_cache(report_id, run)


def reconcile_all(
    report_id: int,
    *,
    students: list[dict[str, Any]] | None = None,
    match_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def run(rid: int) -> dict[str, Any]:
        shared = students if students is not None else (_MATCH_CACHE.get() or [])
        shared_index = match_index
        if shared_index is None:
            shared_index = domain.build_match_index(shared)
        return {
            "ok": True,
            "nuclei": reconcile_nuclei(rid, students=shared, match_index=shared_index),
            "complexive": reconcile_complexive(rid, students=shared, match_index=shared_index),
            "thesis": reconcile_thesis(rid, students=shared, match_index=shared_index),
        }

    return _with_match_cache(report_id, run, students=students)


def _effective_reconciliation(row: dict[str, Any]) -> tuple[str, str]:
    current = str(row.get("reconciliation_status") or domain.MATCH_OK)
    detail = str(row.get("reconciliation_detail") or "")
    candidates: list[tuple[int, str, str]] = []
    priority = {
        MATCH_DUPLICATE: 120,
        MATCH_MODALITY_CONFLICT: 115,
        MATCH_IDENTITY_CONFLICT: 110,
        domain.MATCH_ROUTE_CONFLICT: 100,
        domain.MATCH_GRADE_CONFLICT: 90,
        domain.MATCH_OFFICIAL_CONFLICT: 85,
        domain.MATCH_AMBIGUOUS: 80,
        domain.MATCH_REVIEW: 70,
        domain.MATCH_UNMATCHED: 60,
    }
    if current != domain.MATCH_OK:
        candidates.append((priority.get(current, 75), current, detail))
    for link in row.get("source_links", []):
        if int(link.get("source_active", 1) or 0) != 1:
            continue
        status = str(link.get("match_status") or domain.MATCH_OK)
        if status == domain.MATCH_OK:
            continue
        link_detail = (
            str(link.get("detail") or "")
            or f"Revise la conciliación del módulo {link.get('source_module') or 'académico'}."
        )
        candidates.append((priority.get(status, 65), status, link_detail))
    for status, academic_detail in read_model._academic_consistency(row):
        candidates.append((priority.get(status, 50), status, academic_detail))
    if not candidates:
        return domain.MATCH_OK, detail
    _, selected_status, selected_detail = max(candidates, key=lambda item: item[0])
    return selected_status, selected_detail


def _open_links(report_ids: list[int]) -> list[dict[str, Any]]:
    if not report_ids:
        return []
    placeholders = ",".join("?" for _ in report_ids)
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT l.*, r.modality AS dataset_modality
                FROM student_source_links l
                JOIN reports r ON r.id=l.report_id
                WHERE l.report_id IN ({placeholders})
                  AND COALESCE(l.source_active, 1)=1
                  AND COALESCE(l.match_status, 'UNMATCHED') <> 'OK'
                ORDER BY
                  CASE l.match_status
                    WHEN '{MATCH_DUPLICATE}' THEN 1
                    WHEN '{MATCH_MODALITY_CONFLICT}' THEN 2
                    WHEN '{MATCH_IDENTITY_CONFLICT}' THEN 3
                    WHEN 'ROUTE_CONFLICT' THEN 4
                    WHEN 'GRADE_CONFLICT' THEN 5
                    WHEN 'AMBIGUOUS' THEN 6
                    WHEN 'REVIEW_REQUIRED' THEN 7
                    WHEN 'UNMATCHED' THEN 8
                    ELSE 9
                  END,
                  l.source_module, l.source_name, l.id
                """,
                tuple(report_ids),
            ).fetchall()
        )
    for row in rows:
        try:
            row["candidates"] = json.loads(row.get("candidates_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            row["candidates"] = []
    return rows


def _refresh_report(report_id: int) -> dict[str, Any]:
    sync_report_students(report_id)
    reconciliation = reconcile_all(report_id)
    data = read_model.consolidated_students(report_id)
    data["reconciliation"] = reconciliation
    return data


def get_period_student_domain(period_project_id: int) -> dict[str, Any]:
    data = _BASE_PERIOD_GET(period_project_id)
    conflict_ids = _refresh_modality_conflicts(period_project_id)
    with connection() as conn:
        status_rows = rows_to_dicts(
            conn.execute(
                """
                SELECT id, reconciliation_status, reconciliation_detail,
                       requirements_present, modality_conflict
                FROM period_students
                WHERE period_project_id=?
                """,
                (period_project_id,),
            ).fetchall()
        )
    status_map = {int(row["id"]): row for row in status_rows}
    for row in data.get("students", []):
        student_id = int(row["id"])
        state = status_map.get(student_id)
        if state:
            row["requirements_present"] = int(state["requirements_present"] or 0)
            row["modality_conflict"] = int(state["modality_conflict"] or 0)
            probe = dict(row)
            probe["reconciliation_status"] = state["reconciliation_status"]
            probe["reconciliation_detail"] = state["reconciliation_detail"]
            effective_status, effective_detail = _effective_reconciliation(probe)
            row["reconciliation_status"] = effective_status
            row["reconciliation_detail"] = effective_detail
        if student_id in conflict_ids:
            row["reconciliation_status"] = MATCH_MODALITY_CONFLICT
            row["reconciliation_detail"] = (
                "La misma cédula aparece simultáneamente en los datasets Presencial y Online del período."
            )
        dataset_modality = str(row.get("dataset_modality") or row.get("modality") or "")
        row["modality"] = dataset_modality

    report_ids = [int(item["id"]) for item in data.get("members", [])]
    open_links = _open_links(report_ids)
    data["open_links"] = open_links
    rows = data.get("students", [])
    review_students = sum(
        str(row.get("reconciliation_status") or domain.MATCH_OK) != domain.MATCH_OK
        for row in rows
    )
    data["summary"] = {
        **(data.get("summary") or {}),
        "students": len(rows),
        "complexive": sum(row.get("route") == domain.ROUTE_COMPLEXIVE for row in rows),
        "thesis": sum(row.get("route") == domain.ROUTE_THESIS for row in rows),
        "graduated": sum(bool(row.get("official_graduated")) for row in rows),
        "retired": sum(row.get("process_status") == domain.PROCESS_RETIRED for row in rows),
        "one_missing": sum(
            row.get("process_status") == domain.PROCESS_WITH_ONE_MISSING
            for row in rows
        ),
        "review": review_students,
        "review_students": review_students,
        "open_links": len(open_links),
        "source_alerts": len(open_links),
        "presencial": sum(row.get("modality") == "presencial" for row in rows),
        "online": sum(row.get("modality") == "en_linea" for row in rows),
    }
    return data


def reset_process_status(report_id: int, student_id: int) -> dict[str, Any]:
    ensure_schema()
    with connection() as conn:
        master = conn.execute(
            "SELECT * FROM period_students WHERE id=? AND report_id=?",
            (student_id, report_id),
        ).fetchone()
        if not master:
            raise ValueError("El estudiante no existe en este período.")
        req_id = master["requirements_student_id"]
        requirement = None
        if req_id and _table_exists(conn, "requirements_students"):
            requirement = conn.execute(
                "SELECT * FROM requirements_students WHERE id=? AND report_id=?",
                (int(req_id), report_id),
            ).fetchone()
        if requirement:
            status, _missing = domain._derived_process(dict(requirement))
        else:
            status = domain.PROCESS_RETIRED
        old = str(master["process_status"])
        now = utcnow()
        conn.execute(
            """
            UPDATE period_students
            SET process_status=?, process_status_source='DERIVED', updated_at=?
            WHERE id=?
            """,
            (status, now, student_id),
        )
        conn.execute(
            """
            INSERT INTO student_audit_log
            (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
            VALUES (?, ?, 'RESET_PROCESS_STATUS', 'process_status', ?, ?,
                    'Se restableció el estado calculado desde Requisitos.', ?)
            """,
            (report_id, student_id, old, status, now),
        )
    return {
        "ok": True,
        "student_id": student_id,
        "process_status": status,
        "process_status_source": "DERIVED",
    }


def _link_for_period(period_project_id: int, link_id: int) -> Any:
    members = period_service._member_reports(period_project_id)
    report_ids = {int(item["id"]) for item in members}
    with connection() as conn:
        link = conn.execute(
            "SELECT * FROM student_source_links WHERE id=?",
            (link_id,),
        ).fetchone()
    if (
        not link
        or int(link["report_id"]) not in report_ids
        or int(link["source_active"] if "source_active" in link.keys() else 1) != 1
    ):
        raise ValueError("La discrepancia ya no existe en este período.")
    return link


def unlink_period_source(
    period_project_id: int,
    link_id: int,
) -> dict[str, Any]:
    link = _link_for_period(period_project_id, link_id)
    report_id = int(link["report_id"])
    old_student_id = int(link["period_student_id"]) if link["period_student_id"] else None
    now = utcnow()
    with connection() as conn:
        conn.execute(
            """
            UPDATE student_source_links
            SET period_student_id=NULL, match_status=?, match_method='MANUAL_REVIEW',
                match_confidence=NULL,
                detail='Vínculo desasociado manualmente; requiere una nueva decisión.',
                source_active=1, updated_at=?
            WHERE id=?
            """,
            (domain.MATCH_REVIEW, now, link_id),
        )
        conn.execute(
            """
            INSERT INTO student_audit_log
            (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
            VALUES (?, ?, 'UNLINK_SOURCE', 'source_link', ?, '',
                    'El vínculo académico fue desasociado manualmente.', ?)
            """,
            (
                report_id,
                old_student_id,
                str(old_student_id or ""),
                now,
            ),
        )
    reconcile_all(report_id)
    return {"ok": True, "link_id": link_id, "report_id": report_id}


def search_period_candidates(
    period_project_id: int,
    link_id: int,
    query: str,
) -> dict[str, Any]:
    link = _link_for_period(period_project_id, link_id)
    report_id = int(link["report_id"])
    rows = [
        row
        for row in get_period_students(report_id).get("students", [])
        if int(row.get("requirements_present", 1) or 0) == 1
    ]
    q = str(query or "").strip().casefold()
    q_fold = _fold(q)
    if q:
        def matches(row: dict[str, Any]) -> bool:
            haystack = " ".join(
                (
                    str(row.get("identification") or ""),
                    str(row.get("full_name") or ""),
                    str(row.get("email") or ""),
                    str(row.get("career_name") or ""),
                )
            ).casefold()
            return q in haystack or (q_fold and q_fold in _fold(row.get("full_name")))
        rows = [row for row in rows if matches(row)]
    return {
        "ok": True,
        "candidates": [
            {
                "student_id": int(row["id"]),
                "identification": row.get("identification") or "",
                "full_name": row.get("full_name") or "",
                "email": row.get("email") or "",
                "career_name": row.get("career_name") or "",
                "modality": row.get("modality") or "",
                "campus": row.get("campus") or "",
            }
            for row in rows[:50]
        ],
    }


def _safe_get_eligibility(report_id: int) -> dict[str, Any]:
    """Evita monkeypatches globales durante solicitudes concurrentes."""
    result = integrations._BASE_GET_ELIGIBILITY(report_id)
    master_by_req = integrations._requirements_id_map(report_id)
    for row in result.get("rows", []):
        master = master_by_req.get(int(row.get("student_id") or 0))
        if not master:
            continue
        row["period_student_id"] = int(master["id"])
        row["route"] = master["route"]
        row["route_source"] = master["route_source"]
        row["process_status"] = master["process_status"]
        row["official_graduated"] = bool(master["official_graduated"])
        row["official_titulation_completed"] = bool(
            master["official_titulation_completed"]
        )
        if master["route"] == domain.ROUTE_THESIS:
            row["option"] = "Trabajo de Titulación"
            row["eligible_for_complexive"] = False
            row["status"] = "Trabajo de Titulación"
            row["stage_status"] = "Trabajo de Titulación"
        elif row.get("eligible_for_nuclei"):
            row["option"] = "Examen Complexivo"

    summary = result.get("summary") or {}
    master_rows = list(master_by_req.values())
    summary["thesis_students"] = sum(
        row.get("route") == domain.ROUTE_THESIS for row in master_rows
    )
    summary["complexive_candidates"] = sum(
        row.get("route") == domain.ROUTE_COMPLEXIVE
        and row.get("process_status") != domain.PROCESS_RETIRED
        for row in master_rows
    )
    summary["official_graduated"] = sum(
        bool(row.get("official_graduated")) for row in master_rows
    )
    result["summary"] = summary
    return result


def _install_report_narrative_guard() -> None:
    """Corrige la narrativa heredada sin monkeypatches temporales ni estado por hilo."""
    if getattr(report_quality, "_student_final_narrative_guard", False):
        return
    old_sentence = (
        "Los resultados de las cuatro secciones son independientes y no implican "
        "correspondencia automática de estudiantes entre módulos."
    )
    base_docx_bullet = report_quality._docx_bullet
    base_pdf_bullet = report_quality._pdf_bullet

    def docx_bullet(document: Any, text: str) -> Any:
        value = _INTEGRATED_CONCLUSION if str(text).strip() == old_sentence else text
        return base_docx_bullet(document, value)

    def pdf_bullet(story: list[Any], styles: Any, text: str) -> Any:
        value = _INTEGRATED_CONCLUSION if str(text).strip() == old_sentence else text
        return base_pdf_bullet(story, styles, value)

    report_quality._docx_bullet = docx_bullet
    report_quality._pdf_bullet = pdf_bullet
    report_quality._student_final_narrative_guard = True


def _active_for_route(row: dict[str, Any] | None, route: str) -> bool:
    if not row:
        return False
    if row.get("route") != route or row.get("process_status") != domain.PROCESS_ACTIVE:
        return False
    if int(row.get("requirements_present", 1) or 0) != 1:
        return False
    if int(row.get("modality_conflict", 0) or 0) == 1:
        return False
    if str(row.get("reconciliation_status") or "") == MATCH_DUPLICATE:
        return False
    return True


def _install_api() -> None:
    global _API_INSTALLED
    if _API_INSTALLED:
        return
    import app as core

    base_get = core.InformtitHandler._handle_api_get
    base_write = core.InformtitHandler._handle_api_write

    def api_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(
            r"/api/period-projects/(\d+)/students-domain/matches/(\d+)/candidates",
            path,
        )
        if match:
            q = str(query.get("q", [""])[0] or "")
            self._send_json(
                search_period_candidates(
                    int(match.group(1)),
                    int(match.group(2)),
                    q,
                )
            )
            return
        base_get(self, path, query)

    def api_write(
        self: Any,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> None:
        match = re.fullmatch(
            r"/api/period-projects/(\d+)/students-domain/(\d+)/process-status",
            path,
        )
        if match and method in {"POST", "PUT"}:
            requested = str(payload.get("process_status") or "").strip().upper()
            if requested in {"DERIVED", "AUTO", "AUTOMATICO", "AUTOMÁTICO"}:
                report_id = period_service._student_report(
                    int(match.group(1)),
                    int(match.group(2)),
                )
                self._send_json(
                    reset_process_status(
                        report_id,
                        int(match.group(2)),
                    )
                )
                return

        match = re.fullmatch(
            r"/api/period-projects/(\d+)/students-domain/matches/(\d+)/unlink",
            path,
        )
        if match and method in {"POST", "PUT"}:
            self._send_json(
                unlink_period_source(
                    int(match.group(1)),
                    int(match.group(2)),
                )
            )
            return
        base_write(self, method, path, payload)

    core.InformtitHandler._handle_api_get = api_get
    core.InformtitHandler._handle_api_write = api_write
    _API_INSTALLED = True


def install_pre_report() -> None:
    """Endurece identidad, matching y conciliación antes de integrar reportes."""
    global _INSTALLED_PRE
    if _INSTALLED_PRE:
        return

    ensure_schema()

    domain.MATCH_DUPLICATE = MATCH_DUPLICATE
    domain.MATCH_IDENTITY_CONFLICT = MATCH_IDENTITY_CONFLICT
    domain.MATCH_MODALITY_CONFLICT = MATCH_MODALITY_CONFLICT

    domain.ensure_student_domain_schema = ensure_schema
    domain.sync_report_students = sync_report_students
    domain.get_period_students = get_period_students
    domain.match_source_record = match_source_record
    domain.save_source_link = save_source_link

    bridge.get_period_students = get_period_students
    bridge.match_source_record = match_source_record
    bridge.save_source_link = save_source_link
    bridge._manual_match_by_identity = _safe_manual_recovery
    bridge._match = _audited_bridge_match
    bridge.reconcile_nuclei = reconcile_nuclei
    bridge.reconcile_complexive = reconcile_complexive
    bridge.reconcile_thesis = reconcile_thesis
    bridge.reconcile_all = reconcile_all

    domain_runtime.sync_report_students = sync_report_students
    domain_runtime.reconcile_all = reconcile_all

    read_model.get_period_students = get_period_students
    read_model._effective_reconciliation = _effective_reconciliation

    period_service.sync_report_students = sync_report_students
    period_service.reconcile_all = reconcile_all
    period_service._open_links = _open_links
    period_service._refresh_report = _refresh_report
    period_service.get_period_student_domain = get_period_student_domain
    period_runtime.get_period_student_domain = get_period_student_domain

    integrations.get_period_students = get_period_students
    integrations._get_eligibility = _safe_get_eligibility
    eligibility.get_eligibility = _safe_get_eligibility

    report_integration.get_period_students = get_period_students
    report_integration.reconcile_all = reconcile_all

    # La corrección narrativa es permanente y reentrante; no se mutan funciones
    # globales durante cada PDF/DOCX.
    _install_report_narrative_guard()
    report_integration._wrap_docx_post = lambda original: original
    report_integration._wrap_pdf_post = lambda original: original

    _install_api()
    _INSTALLED_PRE = True


def install_post_report() -> None:
    """Aplica el último guard a las poblaciones que consumen los informes."""
    global _INSTALLED_POST
    if _INSTALLED_POST:
        return
    report_integration._active_for_route = _active_for_route
    report_integration.get_period_students = get_period_students
    report_integration.reconcile_all = reconcile_all
    _INSTALLED_POST = True
