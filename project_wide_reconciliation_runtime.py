from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Callable

import read_performance_runtime as fast_read
import smart_reconciliation_performance_runtime as perf
import smart_reconciliation_runtime as smart
import student_domain_bridge as bridge
import student_domain_read_model as read_model
import student_domain_service as domain
import student_final_audit as audit
from db import connection, rows_to_dicts, utcnow
from parser import canonical_name_key, clean_moodle_name


_INSTALLED = False
_BASE_BRIDGE_GET: Callable[..., dict[str, Any]] | None = None
_BASE_CONFIRM_GROUP: Callable[..., dict[str, Any]] | None = None
_BASE_SEARCH_CANDIDATES: Callable[..., dict[str, Any]] | None = None

_PLACEHOLDER_NAME_TOKENS = {"na", "nd", "n/a", "n.d", "n-a"}


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
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _identity_fold(value: Any) -> str:
    """Normaliza nombres para identidad, descartando ruido técnico del origen.

    Algunos archivos históricos traen marcadores como ``NA`` o un punto como si
    fueran un segundo nombre. Esos marcadores no deben impedir reconocer a la
    misma persona cuando el resto de componentes coincide.
    """
    base = canonical_name_key(clean_moodle_name(str(value or "")))
    tokens = re.findall(r"[\wáéíóúüñ]+", base.casefold(), flags=re.UNICODE)
    clean = [token for token in tokens if token not in _PLACEHOLDER_NAME_TOKENS]
    return " ".join(clean)


def _report_context(report_id: int) -> tuple[int | None, list[int]]:
    with connection() as conn:
        if "period_project_id" not in _columns(conn, "reports"):
            return None, [report_id]
        row = conn.execute(
            "SELECT period_project_id FROM reports WHERE id=?",
            (report_id,),
        ).fetchone()
        project_id = int(row[0]) if row and row[0] is not None else None
        if not project_id:
            return None, [report_id]
        report_ids = [
            int(item[0])
            for item in conn.execute(
                "SELECT id FROM reports WHERE period_project_id=? ORDER BY id",
                (project_id,),
            ).fetchall()
        ]
    return project_id, report_ids or [report_id]


def _project_master_rows(report_id: int) -> list[dict[str, Any]]:
    project_id, report_ids = _report_context(report_id)
    if not project_id:
        assert _BASE_BRIDGE_GET is not None
        return list(_BASE_BRIDGE_GET(report_id).get("students", []))

    placeholders = ",".join("?" for _ in report_ids)
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT ps.*, r.modality AS dataset_modality
                FROM period_students ps
                JOIN reports r ON r.id=ps.report_id
                WHERE ps.report_id IN ({placeholders})
                  AND COALESCE(ps.requirements_present, 1)=1
                ORDER BY ps.career_name, ps.full_name, ps.id
                """,
                tuple(report_ids),
            ).fetchall()
        )
    return rows


def _project_students_for_bridge(report_id: int, *, sync: bool = True) -> dict[str, Any]:
    """Bridge de conciliación: la persona se busca en todo el período.

    El parámetro sync se acepta por compatibilidad con el lector maestro optimizado.
    Esta función es de solo lectura: la sincronización explícita ocurre una sola vez
    antes de la conciliación completa.

    Solo se usa en las rutinas de conciliación. La lectura normal de la interfaz
    continúa separando Presencial y Online por el report_id oficial de Requisitos.
    """
    rows = _project_master_rows(report_id)
    return {
        "ok": True,
        "summary": {
            "students": len(rows),
            "complexive": sum(row.get("route") == domain.ROUTE_COMPLEXIVE for row in rows),
            "thesis": sum(row.get("route") == domain.ROUTE_THESIS for row in rows),
        },
        "students": rows,
    }


def _project_master_index(report_id: int) -> dict[str, Any]:
    project_id, _report_ids = _report_context(report_id)
    cache = getattr(smart._INDEX_LOCAL, "value", None)
    cache_key = ("project", project_id or report_id)
    if perf._active_job() and cache and cache.get("key") == cache_key:
        return cache["index"]

    masters = _project_master_rows(report_id)
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_email: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_tokens: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    prepared: list[dict[str, Any]] = []

    for master in masters:
        item = dict(master)
        item["_fold_name"] = _identity_fold(item.get("full_name"))
        item["_tokens"] = tuple(sorted(item["_fold_name"].split()))
        item["_career"] = smart._career(item.get("career_name"))
        prepared.append(item)

        sid = smart._identification(item.get("identification"))
        email = smart._email(item.get("email"))
        if sid:
            by_id[sid].append(item)
        if email:
            by_email[email].append(item)
        if item["_fold_name"]:
            by_name[item["_fold_name"]].append(item)
        if item["_tokens"]:
            by_tokens[item["_tokens"]].append(item)

    index = {
        "masters": prepared,
        "by_id": by_id,
        "by_email": by_email,
        "by_name": by_name,
        "by_tokens": by_tokens,
    }
    if perf._active_job():
        smart._INDEX_LOCAL.value = {"key": cache_key, "index": index}
    return index


def _project_manual_recovery(
    report_id: int,
    source_module: str,
    source: dict[str, Any],
) -> dict[str, Any] | None:
    """Recupera decisiones manuales incluso si el destino es la otra modalidad."""
    identification = smart._identification(source.get("identification"))
    email = smart._email(source.get("email"))
    name = _identity_fold(source.get("full_name"))
    if not any((identification, email, name)):
        return None

    project_id, report_ids = _report_context(report_id)
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT period_student_id, source_name, source_email,
                       source_identification, match_confidence, candidates_json
                FROM student_source_links
                WHERE report_id=? AND source_module=? AND match_method='MANUAL'
                  AND period_student_id IS NOT NULL
                ORDER BY id DESC
                """,
                (report_id, source_module),
            ).fetchall()
        )

        compatible: list[dict[str, Any]] = []
        for row in rows:
            row_id = smart._identification(row.get("source_identification"))
            row_email = smart._email(row.get("source_email"))
            row_name = _identity_fold(row.get("source_name"))
            if identification and row_id:
                match = identification == row_id
            elif email and row_email:
                match = email == row_email
            else:
                match = bool(name and row_name and name == row_name)
            if match:
                compatible.append(row)

        student_ids = {
            int(row["period_student_id"])
            for row in compatible
            if row.get("period_student_id")
        }
        if len(student_ids) != 1:
            return None
        selected_id = next(iter(student_ids))
        placeholders = ",".join("?" for _ in report_ids)
        target = conn.execute(
            f"""
            SELECT id FROM period_students
            WHERE id=? AND report_id IN ({placeholders})
              AND COALESCE(requirements_present, 1)=1
            """,
            (selected_id, *report_ids),
        ).fetchone()
        if not target:
            return None

    selected = compatible[0]
    try:
        candidates = json.loads(selected.get("candidates_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        candidates = []
    return {
        "status": domain.MATCH_OK,
        "method": "MANUAL",
        "confidence": float(selected.get("match_confidence") or 100.0),
        "period_student_id": selected_id,
        "candidates": candidates,
        "detail": "Asociación manual recuperada dentro del mismo período académico.",
    }


def _source_report_ids(report_id: int) -> list[int]:
    return _report_context(report_id)[1]


def _complexive_records_project(report_id: int) -> dict[int, list[dict[str, Any]]]:
    source_ids = _source_report_ids(report_id)
    placeholders = ",".join("?" for _ in source_ids)
    with connection() as conn:
        if "period_student_id" not in _columns(conn, "students"):
            return {}
        rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT s.*, c.name AS source_career, c.report_id AS source_report_id
                FROM students s
                JOIN careers c ON c.id=s.career_id
                JOIN period_students ps ON ps.id=s.period_student_id
                WHERE ps.report_id=?
                  AND c.report_id IN ({placeholders})
                  AND s.period_student_id IS NOT NULL
                ORDER BY s.id
                """,
                (report_id, *source_ids),
            ).fetchall()
        )
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["period_student_id"])].append(row)
    return dict(grouped)


def _thesis_records_project(report_id: int) -> dict[int, list[dict[str, Any]]]:
    source_ids = _source_report_ids(report_id)
    placeholders = ",".join("?" for _ in source_ids)
    with connection() as conn:
        if "period_student_id" not in _columns(conn, "thesis_projects"):
            return {}
        rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT tp.*, tp.report_id AS source_report_id
                FROM thesis_projects tp
                JOIN period_students ps ON ps.id=tp.period_student_id
                WHERE ps.report_id=?
                  AND tp.report_id IN ({placeholders})
                  AND tp.period_student_id IS NOT NULL
                ORDER BY tp.id
                """,
                (report_id, *source_ids),
            ).fetchall()
        )
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["period_student_id"])].append(row)
    return dict(grouped)


def _nuclei_records_project(report_id: int) -> dict[int, list[dict[str, Any]]]:
    source_ids = _source_report_ids(report_id)
    placeholders = ",".join("?" for _ in source_ids)
    rows: list[dict[str, Any]] = []
    with connection() as conn:
        if (
            _table_exists(conn, "nucleus_instance_students")
            and _table_exists(conn, "nucleus_course_instances")
            and "period_student_id" in _columns(conn, "nucleus_instance_students")
        ):
            rows = rows_to_dicts(
                conn.execute(
                    f"""
                    SELECT ns.*, nc.nucleus_number, nc.career_name AS source_career,
                           nc.id AS course_id, nc.campus, nc.group_code, nc.module_code,
                           nc.report_id AS source_report_id
                    FROM nucleus_instance_students ns
                    JOIN nucleus_course_instances nc ON nc.id=ns.course_id
                    JOIN period_students ps ON ps.id=ns.period_student_id
                    WHERE ps.report_id=?
                      AND nc.report_id IN ({placeholders})
                      AND ns.period_student_id IS NOT NULL
                    ORDER BY nc.nucleus_number, ns.id
                    """,
                    (report_id, *source_ids),
                ).fetchall()
            )
        elif (
            _table_exists(conn, "nucleus_students")
            and _table_exists(conn, "nucleus_courses")
            and "period_student_id" in _columns(conn, "nucleus_students")
        ):
            rows = rows_to_dicts(
                conn.execute(
                    f"""
                    SELECT ns.*, nc.nucleus_number, nc.career_name AS source_career,
                           nc.id AS course_id, nc.report_id AS source_report_id
                    FROM nucleus_students ns
                    JOIN nucleus_courses nc ON nc.id=ns.course_id
                    JOIN period_students ps ON ps.id=ns.period_student_id
                    WHERE ps.report_id=?
                      AND nc.report_id IN ({placeholders})
                      AND ns.period_student_id IS NOT NULL
                    ORDER BY nc.nucleus_number, ns.id
                    """,
                    (report_id, *source_ids),
                ).fetchall()
            )
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["period_student_id"])].append(row)
    return dict(grouped)


def _distinct_complexive_project(conn: Any, report_id: int) -> int:
    if not _table_exists(conn, "students") or "period_student_id" not in _columns(conn, "students"):
        return 0
    source_ids = _source_report_ids(report_id)
    placeholders = ",".join("?" for _ in source_ids)
    return int(
        conn.execute(
            f"""
            SELECT COUNT(DISTINCT ps.id)
            FROM students s
            JOIN careers c ON c.id=s.career_id
            JOIN period_students ps ON ps.id=s.period_student_id
            WHERE ps.report_id=?
              AND c.report_id IN ({placeholders})
              AND COALESCE(ps.requirements_present, 1)=1
              AND ps.route='COMPLEXIVO' AND ps.process_status<>'RETIRADO'
            """,
            (report_id, *source_ids),
        ).fetchone()[0]
    )


def _distinct_thesis_project(conn: Any, report_id: int) -> int:
    if not _table_exists(conn, "thesis_projects") or "period_student_id" not in _columns(conn, "thesis_projects"):
        return 0
    source_ids = _source_report_ids(report_id)
    placeholders = ",".join("?" for _ in source_ids)
    return int(
        conn.execute(
            f"""
            SELECT COUNT(DISTINCT ps.id)
            FROM thesis_projects tp
            JOIN period_students ps ON ps.id=tp.period_student_id
            WHERE ps.report_id=?
              AND tp.report_id IN ({placeholders})
              AND COALESCE(ps.requirements_present, 1)=1
              AND ps.route='TRABAJO_TITULACION' AND ps.process_status<>'RETIRADO'
            """,
            (report_id, *source_ids),
        ).fetchone()[0]
    )


def _distinct_nuclei_project(conn: Any, report_id: int) -> int:
    source_ids = _source_report_ids(report_id)
    placeholders = ",".join("?" for _ in source_ids)
    if (
        _table_exists(conn, "nucleus_instance_students")
        and _table_exists(conn, "nucleus_course_instances")
        and "period_student_id" in _columns(conn, "nucleus_instance_students")
    ):
        return int(
            conn.execute(
                f"""
                SELECT COUNT(DISTINCT ps.id)
                FROM nucleus_instance_students ns
                JOIN nucleus_course_instances nc ON nc.id=ns.course_id
                JOIN period_students ps ON ps.id=ns.period_student_id
                WHERE ps.report_id=?
                  AND nc.report_id IN ({placeholders})
                  AND COALESCE(ps.requirements_present, 1)=1
                  AND ps.route='COMPLEXIVO' AND ps.process_status<>'RETIRADO'
                """,
                (report_id, *source_ids),
            ).fetchone()[0]
        )
    if (
        _table_exists(conn, "nucleus_students")
        and _table_exists(conn, "nucleus_courses")
        and "period_student_id" in _columns(conn, "nucleus_students")
    ):
        return int(
            conn.execute(
                f"""
                SELECT COUNT(DISTINCT ps.id)
                FROM nucleus_students ns
                JOIN nucleus_courses nc ON nc.id=ns.course_id
                JOIN period_students ps ON ps.id=ns.period_student_id
                WHERE ps.report_id=?
                  AND nc.report_id IN ({placeholders})
                  AND COALESCE(ps.requirements_present, 1)=1
                  AND ps.route='COMPLEXIVO' AND ps.process_status<>'RETIRADO'
                """,
                (report_id, *source_ids),
            ).fetchone()[0]
        )
    return 0


def _search_project_candidates(
    period_project_id: int,
    link_id: int,
    query: str,
) -> dict[str, Any]:
    members = fast_read._member_reports(period_project_id)
    report_ids = {int(item["id"]) for item in members}
    with connection() as conn:
        link = conn.execute(
            "SELECT report_id FROM student_source_links WHERE id=? AND COALESCE(source_active,1)=1",
            (link_id,),
        ).fetchone()
        if not link or int(link["report_id"]) not in report_ids:
            raise ValueError("La discrepancia ya no existe en este período.")
        placeholders = ",".join("?" for _ in report_ids)
        rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT * FROM period_students
                WHERE report_id IN ({placeholders})
                  AND COALESCE(requirements_present, 1)=1
                ORDER BY career_name, full_name, id
                """,
                tuple(sorted(report_ids)),
            ).fetchall()
        )

    q = str(query or "").strip().casefold()
    q_fold = _identity_fold(q)
    if q:
        def matches(row: dict[str, Any]) -> bool:
            haystack = " ".join(
                (
                    str(row.get("identification") or ""),
                    str(row.get("full_name") or ""),
                    str(row.get("email") or ""),
                    str(row.get("career_name") or ""),
                    str(row.get("modality") or ""),
                )
            ).casefold()
            return q in haystack or (q_fold and q_fold in _identity_fold(row.get("full_name")))
        rows = [row for row in rows if matches(row)]

    return {
        "ok": True,
        "candidates": [
            {
                "student_id": int(row["id"]),
                "identification": audit._public_identification(row.get("identification")),
                "full_name": row.get("full_name") or "",
                "email": row.get("email") or "",
                "career_name": row.get("career_name") or "",
                "modality": row.get("modality") or "",
                "campus": row.get("campus") or "",
            }
            for row in rows[:50]
        ],
    }


def _confirm_group_project(
    period_project_id: int,
    link_id: int,
    student_id: int,
) -> dict[str, Any]:
    members = fast_read._member_reports(period_project_id)
    report_ids = {int(item["id"]) for item in members}
    with smart.sqlite_guard._WRITE_LOCK:
        with connection() as conn:
            link = conn.execute("SELECT * FROM student_source_links WHERE id=?", (link_id,)).fetchone()
            if not link or int(link["report_id"]) not in report_ids:
                raise ValueError("El caso de conciliación ya no existe en este período.")
            report_id = int(link["report_id"])
            placeholders = ",".join("?" for _ in report_ids)
            student = conn.execute(
                f"""
                SELECT id, report_id FROM period_students
                WHERE id=? AND report_id IN ({placeholders})
                  AND COALESCE(requirements_present, 1)=1
                """,
                (student_id, *sorted(report_ids)),
            ).fetchone()
            if not student:
                raise ValueError("El estudiante seleccionado no pertenece al mismo período académico.")

            source_module = str(link["source_module"])
            selected = dict(link)
            identity = smart._group_identity(selected)
            rows = rows_to_dicts(
                conn.execute(
                    """
                    SELECT * FROM student_source_links
                    WHERE report_id=? AND source_module=? AND COALESCE(source_active, 1)=1
                      AND COALESCE(match_status, 'UNMATCHED')<>'OK'
                    ORDER BY id
                    """,
                    (report_id, source_module),
                ).fetchall()
            )
            siblings = [row for row in rows if smart._group_identity(row) == identity] or [selected]
            ids = [int(row["id"]) for row in siblings]
            id_placeholders = ",".join("?" for _ in ids)
            now = utcnow()
            conn.execute(
                f"""
                UPDATE student_source_links
                SET period_student_id=?, match_status='OK', match_method='MANUAL',
                    match_confidence=100,
                    detail='Asociación confirmada manualmente dentro del período; la modalidad oficial proviene de Requisitos.',
                    updated_at=?
                WHERE id IN ({id_placeholders})
                """,
                (student_id, now, *ids),
            )
            conn.execute(
                """
                INSERT INTO student_audit_log
                (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
                VALUES (?, ?, 'CONFIRM_MATCH_GROUP', 'source_link_group', ?, ?, ?, ?)
                """,
                (
                    report_id,
                    student_id,
                    ",".join(str(item) for item in ids),
                    str(student_id),
                    f"{source_module}: se confirmaron {len(ids)} evidencias; se aceptó destino en cualquier modalidad del mismo período.",
                    now,
                ),
            )

        if source_module == "NUCLEI":
            audit.reconcile_nuclei(report_id)
        elif source_module == "COMPLEXIVE":
            audit.reconcile_complexive(report_id)
        elif source_module == "THESIS":
            audit.reconcile_thesis(report_id)

    return {
        "ok": True,
        "student_id": student_id,
        "confirmed_links": len(ids),
        "target_report_id": int(student["report_id"]),
    }


def install() -> None:
    """Hace que la identidad sea del período y la modalidad sea un atributo oficial.

    Requisitos sigue separado en Presencial/Online, pero las fuentes académicas se
    pueden haber cargado bajo el dataset equivocado. Primero se identifica a la
    persona entre todos los estudiantes del período y luego se respeta la modalidad
    oficial que tiene en Requisitos.
    """
    global _INSTALLED, _BASE_BRIDGE_GET, _BASE_CONFIRM_GROUP, _BASE_SEARCH_CANDIDATES
    if _INSTALLED:
        return

    _BASE_BRIDGE_GET = bridge.get_period_students
    _BASE_CONFIRM_GROUP = smart._confirm_group
    _BASE_SEARCH_CANDIDATES = audit.search_period_candidates

    # Matching de identidad a nivel de proyecto académico completo.
    smart._fold = _identity_fold
    smart._master_index = _project_master_index
    bridge.get_period_students = _project_students_for_bridge

    # Conserva el optimizador de decisiones manuales, pero su recuperación valida
    # contra todo el período y no solo contra el dataset fuente.
    perf._BASE_MANUAL_RECOVERY = _project_manual_recovery

    # Una evidencia físicamente cargada en Presencial puede alimentar al estudiante
    # Online correcto (y viceversa) mediante period_student_id.
    read_model._complexive_records = _complexive_records_project
    read_model._nuclei_records = _nuclei_records_project
    read_model._thesis_records = _thesis_records_project

    # La vista general cuenta por modalidad oficial de Requisitos, no por el lugar
    # donde quedó almacenada originalmente la evidencia académica.
    fast_read._distinct_complexive = _distinct_complexive_project
    fast_read._distinct_nuclei = _distinct_nuclei_project
    fast_read._distinct_thesis = _distinct_thesis_project

    # La corrección manual también puede buscar/seleccionar estudiantes de la otra
    # modalidad, siempre dentro del mismo período académico.
    audit.search_period_candidates = _search_project_candidates
    smart._confirm_group = _confirm_group_project

    _INSTALLED = True
