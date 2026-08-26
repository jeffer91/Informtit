from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import Counter, defaultdict
from typing import Any, Callable

import analytics
import app as core
import project_wide_reconciliation_runtime as project_wide
import smart_reconciliation_performance_runtime as perf
import student_report_integration as report_integration
import read_performance_runtime as fast_read
import smart_reconciliation_runtime as smart
import sqlite_concurrency_runtime as sqlite_guard
import student_domain_bridge as bridge
import student_domain_service as domain
import student_final_audit as audit
from db import connection, rows_to_dicts, utcnow


_INSTALLED = False
_BASE_GET: Callable[..., Any] | None = None
_BASE_WRITE: Callable[..., Any] | None = None
_BASE_MEMBER_REPORTS: Callable[[int], list[dict[str, Any]]] | None = None


def _error_job(period_project_id: int, message: str) -> dict[str, Any]:
    """Crea una respuesta de job válida aun si no fue posible iniciar un hilo."""
    now = time.time()
    return {
        "id": uuid.uuid4().hex,
        "period_project_id": period_project_id,
        "status": "error",
        "progress": 0,
        "stage": "No se pudo iniciar la conciliación",
        "detail": "El backend continúa disponible; revise el detalle del error.",
        "error": message,
        "stats": {},
        "created_at": now,
        "updated_at": now,
    }


def _member_reports_safe(period_project_id: int) -> list[dict[str, Any]]:
    """Obtiene los datasets incluso en bases persistentes creadas por versiones antiguas.

    Algunas instalaciones ya tienen ``reports.period_project_id`` pero no conservan
    la tabla auxiliar ``period_projects`` que usa la lectura rápida. El fallo previo
    podía escapar durante el POST de Reconciliar y Electron mostraba únicamente
    ``Failed to fetch``. Primero intentamos la lectura normal y, si el catálogo del
    proyecto no existe o está incompleto, reconstruimos los miembros directamente
    desde ``reports`` sin crear ni modificar datos.
    """
    if _BASE_MEMBER_REPORTS is not None:
        try:
            rows = _BASE_MEMBER_REPORTS(period_project_id)
            if rows:
                return list(rows)
        except Exception:
            pass

    with connection() as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reports'"
        ).fetchone()
        if not table:
            return []
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
        if "period_project_id" not in columns:
            return []
        selected = [name for name in ("id", "name", "period", "modality", "period_project_id") if name in columns]
        if "id" not in selected or "modality" not in selected:
            return []
        sql = (
            f"SELECT {', '.join(selected)} FROM reports "
            "WHERE period_project_id=? ORDER BY "
            + ("CASE modality WHEN 'presencial' THEN 0 WHEN 'en_linea' THEN 1 ELSE 2 END, " if "modality" in columns else "")
            + "id"
        )
        return rows_to_dicts(conn.execute(sql, (period_project_id,)).fetchall())


def _safe_job_worker(job_id: str, period_project_id: int) -> None:
    """Impide que un error del worker rompa la comunicación HTTP del escritorio."""
    try:
        smart._run_reconciliation_job(job_id, period_project_id)
    except BaseException as exc:  # protección final del proceso de escritorio
        smart._set_job(
            job_id,
            status="error",
            stage="No se pudo completar la conciliación",
            detail="Los datos procesados antes del error se conservaron.",
            error=f"{type(exc).__name__}: {exc}",
        )
        with smart._JOB_LOCK:
            if smart._ACTIVE_BY_PROJECT.get(period_project_id) == job_id:
                smart._ACTIVE_BY_PROJECT.pop(period_project_id, None)


def _safe_start_job(period_project_id: int) -> dict[str, Any]:
    """Versión tolerante a fallos del arranque del job.

    La petición POST siempre recibe JSON. Antes, una excepción al crear/iniciar el
    hilo podía cerrar la conexión y el frontend solo veía ``Failed to fetch``.
    """
    try:
        members = _member_reports_safe(period_project_id)
        if not members:
            return _error_job(period_project_id, "El período no tiene datasets para conciliar.")

        smart._cleanup_jobs()
        with smart._JOB_LOCK:
            active_id = smart._ACTIVE_BY_PROJECT.get(period_project_id)
            if active_id:
                active = smart._JOBS.get(active_id)
                if active and active.get("status") in {"queued", "running"}:
                    return smart._public_job(active)

            job_id = uuid.uuid4().hex
            now = time.time()
            job = {
                "id": job_id,
                "period_project_id": period_project_id,
                "status": "queued",
                "progress": 1,
                "stage": "Preparando conciliación",
                "detail": "Iniciando el análisis inteligente de identidad y evidencias académicas.",
                "error": "",
                "stats": {},
                "created_at": now,
                "updated_at": now,
            }
            smart._JOBS[job_id] = job
            smart._ACTIVE_BY_PROJECT[period_project_id] = job_id

        try:
            thread = threading.Thread(
                target=_safe_job_worker,
                args=(job_id, period_project_id),
                daemon=True,
                name=f"reconcile-safe-{job_id[:8]}",
            )
            thread.start()
        except BaseException as exc:
            smart._set_job(
                job_id,
                status="error",
                progress=0,
                stage="No se pudo iniciar la conciliación",
                detail="El backend permanece operativo.",
                error=f"{type(exc).__name__}: {exc}",
            )
            with smart._JOB_LOCK:
                smart._ACTIVE_BY_PROJECT.pop(period_project_id, None)
        return smart._get_job(job_id) or _error_job(period_project_id, "No se pudo crear el proceso de conciliación.")
    except BaseException as exc:
        return _error_job(period_project_id, f"{type(exc).__name__}: {exc}")


def _project_link(period_project_id: int, link_id: int) -> dict[str, Any]:
    members = _member_reports_safe(period_project_id)
    report_ids = {int(item["id"]) for item in members}
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM student_source_links WHERE id=? AND COALESCE(source_active,1)=1",
            (link_id,),
        ).fetchone()
    if not row or int(row["report_id"]) not in report_ids:
        raise ValueError("El vínculo ya no existe en este período.")
    return dict(row)


def _group_links(link: dict[str, Any]) -> list[dict[str, Any]]:
    """Agrupa las evidencias que representan la misma persona dentro del módulo."""
    report_id = int(link["report_id"])
    module = str(link.get("source_module") or "")
    identity = smart._group_identity(link)
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM student_source_links
                WHERE report_id=? AND source_module=? AND COALESCE(source_active,1)=1
                ORDER BY id
                """,
                (report_id, module),
            ).fetchall()
        )
    siblings = [row for row in rows if smart._group_identity(row) == identity]
    return siblings or [link]


def _clear_complexive_sources(report_id: int, source_keys: set[str]) -> int:
    changed = 0
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT s.*, c.name AS career_name
                FROM students s JOIN careers c ON c.id=s.career_id
                WHERE c.report_id=?
                ORDER BY s.id
                """,
                (report_id,),
            ).fetchall()
        )
        for row in rows:
            key = bridge._stable_source_key("COMPLEXIVE", row)
            if key not in source_keys:
                continue
            conn.execute("UPDATE students SET period_student_id=NULL WHERE id=?", (int(row["id"]),))
            changed += 1
    return changed


def _clear_thesis_sources(report_id: int, source_keys: set[str]) -> int:
    changed = 0
    with connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='thesis_projects'"
        ).fetchone()
        if not exists:
            return 0
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM thesis_projects WHERE report_id=? ORDER BY id",
                (report_id,),
            ).fetchall()
        )
        for row in rows:
            key = bridge._stable_source_key("THESIS", row)
            if key not in source_keys:
                continue
            conn.execute("UPDATE thesis_projects SET period_student_id=NULL WHERE id=?", (int(row["id"]),))
            changed += 1
    return changed


def _clear_nuclei_sources(report_id: int, source_keys: set[str]) -> int:
    changed = 0
    courses = bridge.nuclei_service.get_nuclei(report_id).get("courses", [])
    with connection() as conn:
        for course in courses:
            course_id = int(course.get("id") or 0)
            if not course_id:
                continue
            table = bridge._nucleus_student_table(conn, course_id)
            if not table:
                continue
            context = bridge._nucleus_context(course)
            for source in course.get("students", []):
                candidate = {
                    "identification": source.get("identification") or "",
                    "full_name": source.get("full_name") or "",
                    "email": source.get("email") or "",
                    "career_name": course.get("career_name") or "",
                }
                key = bridge._stable_source_key("NUCLEI", candidate, context)
                if key not in source_keys or not source.get("id"):
                    continue
                conn.execute(
                    f"""
                    UPDATE {table}
                    SET period_student_id=NULL,
                        match_status=?, match_method='MANUAL_REVIEW', match_confidence=NULL
                    WHERE id=? AND course_id=?
                    """,
                    (domain.MATCH_REVIEW, int(source["id"]), course_id),
                )
                changed += 1
    return changed


def unlink_period_source(period_project_id: int, link_id: int) -> dict[str, Any]:
    """Desvincula de verdad una evidencia y bloquea su re-vinculación automática.

    No borra la nota ni el registro académico. El registro crudo permanece en su
    módulo, pero deja de apuntar al estudiante hasta que el usuario lo confirme de
    nuevo. Todas las evidencias agrupadas de la misma persona reciben MANUAL_REVIEW.
    """
    link = _project_link(period_project_id, link_id)
    siblings = _group_links(link)
    report_id = int(link["report_id"])
    module = str(link.get("source_module") or "")
    old_student_id = int(link["period_student_id"]) if link.get("period_student_id") else None
    source_keys = {str(row.get("source_key") or "") for row in siblings if row.get("source_key")}
    ids = [int(row["id"]) for row in siblings]
    now = utcnow()

    with sqlite_guard._WRITE_LOCK:
        with connection() as conn:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE student_source_links
                SET period_student_id=NULL,
                    match_status=?,
                    match_method='MANUAL_REVIEW',
                    match_confidence=NULL,
                    detail='Vínculo desasociado manualmente. La evidencia se conserva, pero no volverá a asociarse automáticamente hasta una nueva decisión.',
                    source_active=1,
                    updated_at=?
                WHERE id IN ({placeholders})
                """,
                (domain.MATCH_REVIEW, now, *ids),
            )

            conn.execute(
                """
                INSERT INTO student_audit_log
                (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
                VALUES (?, ?, 'UNLINK_SOURCE_GROUP', 'source_link_group', ?, '', ?, ?)
                """,
                (
                    report_id,
                    old_student_id,
                    ",".join(str(item) for item in ids),
                    f"{module}: se desvincularon {len(ids)} evidencias y quedaron en revisión manual.",
                    now,
                ),
            )

        if module == "COMPLEXIVE":
            cleared = _clear_complexive_sources(report_id, source_keys)
        elif module == "THESIS":
            cleared = _clear_thesis_sources(report_id, source_keys)
        elif module == "NUCLEI":
            cleared = _clear_nuclei_sources(report_id, source_keys)
        else:
            cleared = 0

        # Se reafirma MANUAL_REVIEW después de tocar las tablas fuente. No se llama
        # reconcile_all aquí: desvincular es una decisión humana y no debe ser
        # deshecha inmediatamente por el matcher automático.
        with connection() as conn:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE student_source_links
                SET period_student_id=NULL, match_status=?, match_method='MANUAL_REVIEW',
                    match_confidence=NULL, source_active=1, updated_at=?
                WHERE id IN ({placeholders})
                """,
                (domain.MATCH_REVIEW, utcnow(), *ids),
            )

    return {
        "ok": True,
        "link_id": link_id,
        "report_id": report_id,
        "unlinked_links": len(ids),
        "unlinked_source_rows": cleared,
        "module": module,
    }


def install() -> None:
    """Última barrera de fiabilidad para conciliación y acciones manuales."""
    global _INSTALLED, _BASE_GET, _BASE_WRITE, _BASE_MEMBER_REPORTS
    if _INSTALLED:
        return

    # Instalar el fallback a nivel del lector compartido también protege el worker
    # original de smart_reconciliation_runtime, que vuelve a consultar los miembros
    # una vez iniciado el hilo.
    _BASE_MEMBER_REPORTS = fast_read._member_reports
    fast_read._member_reports = _member_reports_safe

    # Mantiene disponible la función también para cualquier wrapper antiguo que la
    # consulte por nombre dentro de student_final_audit.
    audit.unlink_period_source = unlink_period_source
    smart._start_job = _safe_start_job

    _BASE_GET = core.InformtitHandler._handle_api_get
    _BASE_WRITE = core.InformtitHandler._handle_api_write

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(r"/api/reconciliation-jobs/([a-f0-9]{32})", path)
        if match:
            job = smart._get_job(match.group(1))
            if not job:
                self._send_error_json("Proceso de conciliación no encontrado.", 404)
                return
            self._send_json({"ok": True, "job": job})
            return
        assert _BASE_GET is not None
        try:
            _BASE_GET(self, path, query)
        except Exception as exc:
            self._send_error_json(f"Error del backend: {type(exc).__name__}: {exc}", 500)

    def handle_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        match = re.fullmatch(r"/api/period-projects/(\d+)/students-domain/reconcile-jobs", path)
        if match and method == "POST":
            job = _safe_start_job(int(match.group(1)))
            # Aun si el worker no pudo arrancar, la respuesta es JSON y la interfaz
            # puede mostrar el error real en vez de ``Failed to fetch``.
            self._send_json({"ok": True, "job": job}, 202)
            return

        match = re.fullmatch(r"/api/period-projects/(\d+)/students-domain/matches/(\d+)/unlink", path)
        if match and method in {"POST", "PUT"}:
            try:
                result = unlink_period_source(int(match.group(1)), int(match.group(2)))
            except ValueError as exc:
                self._send_error_json(str(exc), 400)
                return
            except Exception as exc:
                self._send_error_json(f"No se pudo desvincular: {type(exc).__name__}: {exc}", 500)
                return
            self._send_json(result)
            return

        assert _BASE_WRITE is not None
        try:
            _BASE_WRITE(self, method, path, payload)
        except Exception as exc:
            self._send_error_json(f"Error del backend: {type(exc).__name__}: {exc}", 500)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
    _install_final_contract()
    _INSTALLED = True


# ---------------------------------------------------------------------------
# Contrato final del dominio de estudiantes
# ---------------------------------------------------------------------------

_FINAL_INSTALLED = False
_FINAL_BASE_MATCH: Callable[..., dict[str, Any]] | None = None
_FINAL_BASE_SYNC: Callable[[int], dict[str, Any]] | None = None
_FINAL_BASE_PERIOD_READ: Callable[[int], dict[str, Any]] | None = None
_FINAL_BASE_GET: Callable[..., Any] | None = None
_FINAL_BASE_WRITE: Callable[..., Any] | None = None
_DECISION_LOCAL = threading.local()

DECISION_MATCH = "MATCH"
DECISION_DO_NOT_MATCH = "DO_NOT_MATCH"
DECISION_ROUTE = "ROUTE"
DECISION_GRADE = "GRADE"


def _ensure_final_schema() -> None:
    audit.ensure_schema()
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS student_manual_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_project_id INTEGER NOT NULL,
                source_module TEXT NOT NULL,
                identity_key TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                decision_scope TEXT NOT NULL DEFAULT '',
                target_student_id INTEGER,
                decision_value TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(period_project_id, source_module, identity_key, decision_type, decision_scope)
            );
            CREATE INDEX IF NOT EXISTS idx_student_manual_decisions_lookup
                ON student_manual_decisions(period_project_id, source_module, identity_key, decision_type);
            """
        )


def _project_id_for_report(report_id: int) -> int | None:
    with connection() as conn:
        cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
        if "period_project_id" not in cols:
            return None
        row = conn.execute("SELECT period_project_id FROM reports WHERE id=?", (report_id,)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _project_report_ids(period_project_id: int) -> list[int]:
    return [int(item["id"]) for item in _member_reports_safe(period_project_id)]


def _identity_key_values(identification: Any, email: Any, name: Any) -> str:
    sid = bridge._source_identification(identification)
    if sid:
        return f"id:{sid}"
    semail = bridge._source_email(email)
    if semail:
        return f"email:{semail}"
    folded = project_wide._identity_fold(name)
    tokens = tuple(sorted(token for token in folded.split() if token))
    return "name:" + "|".join(tokens) if tokens else ""


def _identity_key_source(source: dict[str, Any]) -> str:
    return _identity_key_values(
        source.get("identification"),
        source.get("email"),
        source.get("full_name"),
    )


def _identity_key_link(link: dict[str, Any]) -> str:
    return _identity_key_values(
        link.get("source_identification"),
        link.get("source_email"),
        link.get("source_name"),
    ) or f"link:{int(link.get('id') or 0)}"


def _decision_cache() -> dict[Any, Any]:
    cache = getattr(_DECISION_LOCAL, "cache", None)
    if cache is None:
        cache = {}
        _DECISION_LOCAL.cache = cache
    return cache


def _clear_decision_cache() -> None:
    _DECISION_LOCAL.cache = {}


def _manual_decisions(
    period_project_id: int,
    source_module: str,
    identity_key: str,
    decision_type: str | None = None,
) -> list[dict[str, Any]]:
    if not identity_key:
        return []
    key = (period_project_id, source_module, identity_key, decision_type or "*")
    cache = _decision_cache()
    if key in cache:
        return [dict(row) for row in cache[key]]
    _ensure_final_schema()
    sql = """
        SELECT * FROM student_manual_decisions
        WHERE period_project_id=? AND source_module=? AND identity_key=?
    """
    args: list[Any] = [period_project_id, source_module, identity_key]
    if decision_type:
        sql += " AND decision_type=?"
        args.append(decision_type)
    sql += " ORDER BY id DESC"
    with connection() as conn:
        rows = rows_to_dicts(conn.execute(sql, tuple(args)).fetchall())
    cache[key] = [dict(row) for row in rows]
    return rows


def _store_decision(
    period_project_id: int,
    source_module: str,
    identity_key: str,
    decision_type: str,
    *,
    decision_scope: str = "",
    target_student_id: int | None = None,
    decision_value: str = "",
    detail: str = "",
) -> None:
    if not identity_key:
        return
    _ensure_final_schema()
    now = utcnow()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO student_manual_decisions
            (period_project_id, source_module, identity_key, decision_type, decision_scope,
             target_student_id, decision_value, detail, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(period_project_id, source_module, identity_key, decision_type, decision_scope)
            DO UPDATE SET target_student_id=excluded.target_student_id,
                          decision_value=excluded.decision_value,
                          detail=excluded.detail,
                          updated_at=excluded.updated_at
            """,
            (
                period_project_id, source_module, identity_key, decision_type,
                decision_scope, target_student_id, decision_value, detail, now, now,
            ),
        )
    _clear_decision_cache()


def _requirements_rows_project(period_project_id: int) -> list[dict[str, Any]]:
    report_ids = _project_report_ids(period_project_id)
    if not report_ids:
        return []
    placeholders = ",".join("?" for _ in report_ids)
    with connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='requirements_students'"
        ).fetchone():
            return []
        return rows_to_dicts(
            conn.execute(
                f"""
                SELECT rs.*, rs.report_id AS target_report_id, r.modality AS target_modality
                FROM requirements_students rs
                JOIN reports r ON r.id=rs.report_id
                WHERE rs.report_id IN ({placeholders})
                ORDER BY rs.id
                """,
                tuple(report_ids),
            ).fetchall()
        )


def _merge_master_rows(conn: Any, keep_id: int, drop_id: int) -> None:
    if keep_id == drop_id:
        return
    keep = conn.execute("SELECT * FROM period_students WHERE id=?", (keep_id,)).fetchone()
    drop = conn.execute("SELECT * FROM period_students WHERE id=?", (drop_id,)).fetchone()
    if not keep or not drop:
        return
    if str(drop["route_source"] or "") == "MANUAL" and str(keep["route_source"] or "") != "MANUAL":
        conn.execute(
            "UPDATE period_students SET route=?, route_source='MANUAL', updated_at=? WHERE id=?",
            (drop["route"], utcnow(), keep_id),
        )
    if (
        str(drop["process_status_source"] or "") == "MANUAL"
        and str(keep["process_status_source"] or "") != "MANUAL"
    ):
        conn.execute(
            """
            UPDATE period_students SET process_status=?, process_status_source='MANUAL', updated_at=?
            WHERE id=?
            """,
            (drop["process_status"], utcnow(), keep_id),
        )
    for table in (
        "student_source_links", "students", "thesis_projects",
        "nucleus_students", "nucleus_instance_students",
    ):
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone():
            continue
        cols = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "period_student_id" in cols:
            conn.execute(
                f"UPDATE {table} SET period_student_id=? WHERE period_student_id=?",
                (keep_id, drop_id),
            )
    conn.execute(
        "UPDATE student_audit_log SET period_student_id=? WHERE period_student_id=?",
        (keep_id, drop_id),
    )
    conn.execute(
        "UPDATE student_manual_decisions SET target_student_id=? WHERE target_student_id=?",
        (keep_id, drop_id),
    )
    conn.execute("DELETE FROM period_students WHERE id=?", (drop_id,))


def _migrate_project_master(period_project_id: int) -> dict[str, int]:
    """Mantiene un solo period_student_id aunque Requisitos cambie Presencial/Online."""
    _ensure_final_schema()
    requirements = _requirements_rows_project(period_project_id)
    official: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in requirements:
        sid = bridge._source_identification(row.get("identification"))
        if sid:
            official[sid].append(row)
    report_ids = _project_report_ids(period_project_id)
    if not report_ids:
        return {"moved": 0, "merged": 0}
    placeholders = ",".join("?" for _ in report_ids)
    moved = 0
    merged = 0
    with connection() as conn:
        for sid, req_rows in official.items():
            if len(req_rows) != 1:
                continue
            target = req_rows[0]
            target_report_id = int(target["target_report_id"])
            target_modality = str(target.get("target_modality") or "")
            masters = rows_to_dicts(
                conn.execute(
                    f"""
                    SELECT * FROM period_students
                    WHERE report_id IN ({placeholders}) AND identification=?
                    ORDER BY id
                    """,
                    (*report_ids, sid),
                ).fetchall()
            )
            if not masters:
                continue
            keep = next(
                (row for row in masters if int(row["report_id"]) == target_report_id),
                masters[0],
            )
            keep_id = int(keep["id"])
            for row in masters:
                row_id = int(row["id"])
                if row_id != keep_id:
                    _merge_master_rows(conn, keep_id, row_id)
                    merged += 1
            current = conn.execute("SELECT * FROM period_students WHERE id=?", (keep_id,)).fetchone()
            if current and int(current["report_id"]) != target_report_id:
                old_report = int(current["report_id"])
                conn.execute(
                    """
                    UPDATE period_students
                    SET report_id=?, period_project_id=?, modality=?, updated_at=?
                    WHERE id=?
                    """,
                    (target_report_id, period_project_id, target_modality, utcnow(), keep_id),
                )
                conn.execute(
                    """
                    INSERT INTO student_audit_log
                    (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
                    VALUES (?, ?, 'MOVE_MASTER_DATASET', 'report_id', ?, ?,
                            'Requisitos cambió la modalidad oficial; se conservó la misma identidad interna y todas sus evidencias.',
                            ?)
                    """,
                    (target_report_id, keep_id, str(old_report), str(target_report_id), utcnow()),
                )
                moved += 1
    return {"moved": moved, "merged": merged}


def _official_snapshot(report_id: int) -> dict[int, dict[str, Any]]:
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT id, identification, full_name, email, career_code, career_name,
                       modality, campus, schedule
                FROM period_students WHERE report_id=?
                """,
                (report_id,),
            ).fetchall()
        )
    return {int(row["id"]): row for row in rows}


def _audit_official_changes(report_id: int, before: dict[int, dict[str, Any]]) -> None:
    fields = (
        "identification", "full_name", "email", "career_code",
        "career_name", "modality", "campus", "schedule",
    )
    after = _official_snapshot(report_id)
    now = utcnow()
    with connection() as conn:
        for student_id, old in before.items():
            current = after.get(student_id)
            if not current:
                continue
            for field in fields:
                old_value = str(old.get(field) or "")
                new_value = str(current.get(field) or "")
                if old_value == new_value:
                    continue
                conn.execute(
                    """
                    INSERT INTO student_audit_log
                    (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
                    VALUES (?, ?, 'SYNC_REQUIREMENTS_OFFICIAL', ?, ?, ?,
                            'Requisitos actualizó el dato oficial; las fuentes académicas se conservan intactas.',
                            ?)
                    """,
                    (report_id, student_id, field, old_value, new_value, now),
                )


def _sync_students_final(report_id: int) -> dict[str, Any]:
    assert _FINAL_BASE_SYNC is not None
    project_id = _project_id_for_report(report_id)
    if project_id:
        _migrate_project_master(project_id)
    before = _official_snapshot(report_id)
    result = _FINAL_BASE_SYNC(report_id)
    _audit_official_changes(report_id, before)
    return result


def _manual_match_target(period_project_id: int, module: str, identity: str) -> int | None:
    rows = _manual_decisions(period_project_id, module, identity, DECISION_MATCH)
    if not rows or not rows[0].get("target_student_id"):
        return None
    target = int(rows[0]["target_student_id"])
    with connection() as conn:
        valid = conn.execute(
            """
            SELECT 1 FROM period_students
            WHERE id=? AND period_project_id=? AND COALESCE(requirements_present,1)=1
            """,
            (target, period_project_id),
        ).fetchone()
    return target if valid else None


def _blocked_targets(period_project_id: int, module: str, identity: str) -> set[int]:
    return {
        int(row["target_student_id"])
        for row in _manual_decisions(period_project_id, module, identity, DECISION_DO_NOT_MATCH)
        if row.get("target_student_id")
    }


def _persist_final_match(
    report_id: int,
    module: str,
    source_key: str,
    source: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    bridge.save_source_link(report_id, module, source_key, source, result)
    return result


def _final_match(
    report_id: int,
    module: str,
    source_key: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    assert _FINAL_BASE_MATCH is not None
    # Mantiene el seguimiento de progreso de la capa de rendimiento.
    result = _FINAL_BASE_MATCH(report_id, module, source_key, source)
    project_id = _project_id_for_report(report_id)
    identity = _identity_key_source(source)
    if not project_id or not identity:
        return result

    manual_target = _manual_match_target(project_id, module, identity)
    if manual_target:
        return _persist_final_match(
            report_id, module, source_key, source,
            {
                "status": domain.MATCH_OK,
                "method": "MANUAL",
                "confidence": 100.0,
                "period_student_id": manual_target,
                "candidates": list(result.get("candidates") or [])[:3],
                "detail": "Asociación manual persistente; prevalece sobre futuras conciliaciones y recargas.",
            },
        )

    blocked = _blocked_targets(project_id, module, identity)
    selected = int(result.get("period_student_id") or 0)
    if selected and selected in blocked:
        candidates = [
            item for item in list(result.get("candidates") or [])
            if int(item.get("student_id") or 0) not in blocked
        ][:3]
        return _persist_final_match(
            report_id, module, source_key, source,
            {
                "status": domain.MATCH_REVIEW,
                "method": "MANUAL_REVIEW",
                "confidence": candidates[0].get("similarity") if candidates else None,
                "period_student_id": None,
                "candidates": candidates,
                "detail": "La asociación propuesta fue descartada manualmente y no volverá a aplicarse sola.",
            },
        )

    # Carrera es contexto, no evidencia suficiente para escoger entre homónimos.
    if str(result.get("method") or "") == "NOMBRE_EXACTO_CONTEXTO":
        index = smart._master_index(report_id)
        folded = smart._fold(source.get("full_name"))
        exact = list(index["by_name"].get(folded, [])) if folded else []
        if len(exact) > 1:
            return _persist_final_match(
                report_id, module, source_key, source,
                {
                    "status": domain.MATCH_AMBIGUOUS,
                    "method": "HOMONIMO",
                    "confidence": 100.0,
                    "period_student_id": None,
                    "candidates": [smart._candidate_payload(item, 1.0) for item in exact[:3]],
                    "detail": "Existen homónimos. La carrera de la fuente no decide la identidad; seleccione la persona correcta.",
                },
            )

    # La similitud fuzzy queda como sugerencia salvo confianza excepcional.
    if (
        str(result.get("method") or "") == "NOMBRE_ALTA_CONFIANZA"
        and float(result.get("confidence") or 0) < 98.5
    ):
        downgraded = dict(result)
        downgraded.update(
            {
                "status": domain.MATCH_REVIEW,
                "method": "NOMBRE_SUGERIDO",
                "period_student_id": None,
                "candidates": list(result.get("candidates") or [])[:3],
                "detail": "Informtit encontró una coincidencia probable, pero la deja como sugerencia porque no alcanza el umbral final de identidad segura.",
            }
        )
        return _persist_final_match(report_id, module, source_key, source, downgraded)
    return result
