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
import student_domain_read_model as read_model
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
_FINAL_BASE_COMPLEXIVE_RECORDS: Callable[[int], dict[int, list[dict[str, Any]]]] | None = None
_FINAL_BASE_THESIS_RECORDS: Callable[[int], dict[int, list[dict[str, Any]]]] | None = None
_FINAL_BASE_NUCLEI_RECORDS: Callable[[int], dict[int, list[dict[str, Any]]]] | None = None
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


def _strong_identity_key(identification: Any, email: Any) -> str:
    sid = bridge._source_identification(identification)
    if sid:
        return f"id:{sid}"
    semail = bridge._source_email(email)
    if semail:
        return f"email:{semail}"
    return ""


def _weak_name_key(name: Any) -> str:
    folded = project_wide._identity_fold(name)
    tokens = tuple(sorted(token for token in folded.split() if token))
    return "name:" + "|".join(tokens) if tokens else ""


def _identity_key_values(identification: Any, email: Any, name: Any) -> str:
    """Clave descriptiva: identidad fuerte primero y nombre solo como contexto."""
    return _strong_identity_key(identification, email) or _weak_name_key(name)


def _identity_key_source(source: dict[str, Any], source_key: str = "") -> str:
    strong = _strong_identity_key(source.get("identification"), source.get("email"))
    if strong:
        return strong
    # Sin cédula/correo real no propagamos una decisión por todo el nombre:
    # dos homónimos podrían terminar enlazados en bloque. La decisión queda
    # ligada a la evidencia estable concreta.
    return f"source:{source_key}" if source_key else _weak_name_key(source.get("full_name"))


def _identity_key_link(link: dict[str, Any]) -> str:
    strong = _strong_identity_key(
        link.get("source_identification"),
        link.get("source_email"),
    )
    if strong:
        return strong
    source_key = str(link.get("source_key") or "").strip()
    if source_key:
        return f"source:{source_key}"
    return f"link:{int(link.get('id') or 0)}"


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


def _delete_decisions(
    period_project_id: int,
    source_module: str,
    identity_key: str,
    decision_type: str,
    *,
    target_student_id: int | None = None,
) -> None:
    if not identity_key:
        return
    _ensure_final_schema()
    sql = """
        DELETE FROM student_manual_decisions
        WHERE period_project_id=? AND source_module=? AND identity_key=? AND decision_type=?
    """
    args: list[Any] = [period_project_id, source_module, identity_key, decision_type]
    if target_student_id is not None:
        sql += " AND target_student_id=?"
        args.append(int(target_student_id))
    with connection() as conn:
        conn.execute(sql, tuple(args))
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


def _merge_student_decisions(conn: Any, keep_id: int, drop_id: int) -> None:
    """Mueve también las decisiones cuyo identity_key contiene el id interno."""
    prefix = f"student:{drop_id}"
    rows = rows_to_dicts(
        conn.execute(
            """
            SELECT * FROM student_manual_decisions
            WHERE target_student_id=?
               OR identity_key=?
               OR identity_key LIKE ?
            ORDER BY id
            """,
            (drop_id, prefix, prefix + ":%"),
        ).fetchall()
    )
    for row in rows:
        old_key = str(row.get("identity_key") or "")
        new_key = (
            f"student:{keep_id}" + old_key[len(prefix):]
            if old_key == prefix or old_key.startswith(prefix + ":")
            else old_key
        )
        new_target = (
            keep_id
            if row.get("target_student_id") is not None
            and int(row["target_student_id"]) == drop_id
            else row.get("target_student_id")
        )
        if new_key == old_key and new_target == row.get("target_student_id"):
            continue

        existing = conn.execute(
            """
            SELECT * FROM student_manual_decisions
            WHERE period_project_id=? AND source_module=? AND identity_key=?
              AND decision_type=? AND decision_scope=?
            """,
            (
                int(row["period_project_id"]),
                str(row["source_module"]),
                new_key,
                str(row["decision_type"]),
                str(row.get("decision_scope") or ""),
            ),
        ).fetchone()
        if existing and int(existing["id"]) != int(row["id"]):
            # Si ambos maestros tenían una decisión equivalente, conserva la más
            # reciente y elimina únicamente el duplicado lógico.
            if str(row.get("updated_at") or "") >= str(existing["updated_at"] or ""):
                conn.execute(
                    """
                    UPDATE student_manual_decisions
                    SET target_student_id=?, decision_value=?, detail=?,
                        created_at=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        new_target,
                        row.get("decision_value") or "",
                        row.get("detail") or "",
                        row.get("created_at") or utcnow(),
                        row.get("updated_at") or utcnow(),
                        int(existing["id"]),
                    ),
                )
            conn.execute(
                "DELETE FROM student_manual_decisions WHERE id=?",
                (int(row["id"]),),
            )
        else:
            conn.execute(
                """
                UPDATE student_manual_decisions
                SET identity_key=?, target_student_id=?
                WHERE id=?
                """,
                (new_key, new_target, int(row["id"])),
            )


def _migration_identity(row: dict[str, Any]) -> tuple[str, str] | None:
    sid = bridge._source_identification(row.get("identification"))
    if sid:
        return ("id", sid)
    email = bridge._source_email(row.get("email"))
    if email:
        return ("email", email)
    personal = bridge._source_email(row.get("personal_email"))
    if personal:
        return ("personal", personal)
    name = project_wide._identity_fold(row.get("full_name"))
    career = project_wide._identity_fold(row.get("career_name"))
    if name and career:
        return ("profile", f"{name}|{career}")
    return None


def _masters_for_requirement(
    conn: Any,
    report_ids: list[int],
    requirement: dict[str, Any],
) -> list[dict[str, Any]]:
    identity = _migration_identity(requirement)
    if not identity or not report_ids:
        return []
    kind, value = identity
    placeholders = ",".join("?" for _ in report_ids)
    if kind == "id":
        return rows_to_dicts(
            conn.execute(
                f"""
                SELECT * FROM period_students
                WHERE report_id IN ({placeholders}) AND identification=?
                ORDER BY id
                """,
                (*report_ids, value),
            ).fetchall()
        )
    if kind == "email":
        return rows_to_dicts(
            conn.execute(
                f"""
                SELECT * FROM period_students
                WHERE report_id IN ({placeholders}) AND lower(trim(email))=?
                ORDER BY id
                """,
                (*report_ids, value),
            ).fetchall()
        )
    if kind == "personal":
        return rows_to_dicts(
            conn.execute(
                f"""
                SELECT * FROM period_students
                WHERE report_id IN ({placeholders}) AND lower(trim(personal_email))=?
                ORDER BY id
                """,
                (*report_ids, value),
            ).fetchall()
        )

    # Último recurso: nombre+carrera exactos y únicos en Requisitos.
    rows = rows_to_dicts(
        conn.execute(
            f"""
            SELECT * FROM period_students
            WHERE report_id IN ({placeholders})
            ORDER BY id
            """,
            tuple(report_ids),
        ).fetchall()
    )
    return [
        row
        for row in rows
        if _migration_identity(row) == identity
        or (
            project_wide._identity_fold(row.get("full_name"))
            and project_wide._identity_fold(row.get("full_name"))
            == project_wide._identity_fold(requirement.get("full_name"))
            and project_wide._identity_fold(row.get("career_name"))
            == project_wide._identity_fold(requirement.get("career_name"))
        )
    ]


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
    _merge_student_decisions(conn, keep_id, drop_id)
    conn.execute("DELETE FROM period_students WHERE id=?", (drop_id,))


def _migrate_project_master(period_project_id: int) -> dict[str, int]:
    """Mantiene el mismo estudiante aunque Requisitos cambie de modalidad."""
    _ensure_final_schema()
    requirements = _requirements_rows_project(period_project_id)
    official: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in requirements:
        identity = _migration_identity(row)
        if identity:
            official[identity].append(row)

    report_ids = _project_report_ids(period_project_id)
    if not report_ids:
        return {"moved": 0, "merged": 0}

    moved = 0
    merged = 0
    with connection() as conn:
        for _identity, req_rows in official.items():
            # Cédula/correo/perfil deben identificar a una sola fila oficial. Si
            # Requisitos trae duplicados, se conserva el conflicto para revisión.
            if len(req_rows) != 1:
                continue
            target = req_rows[0]
            target_report_id = int(target["target_report_id"])
            target_modality = str(target.get("target_modality") or "")
            masters = _masters_for_requirement(conn, report_ids, target)
            if not masters:
                continue

            # Conserva la identidad interna más antigua. Si ya existe una copia en
            # el dataset destino, fusiona sus evidencias y decisiones antes de mover.
            keep = masters[0]
            keep_id = int(keep["id"])
            for row in masters:
                row_id = int(row["id"])
                if row_id != keep_id:
                    _merge_master_rows(conn, keep_id, row_id)
                    merged += 1

            current = conn.execute(
                "SELECT * FROM period_students WHERE id=?",
                (keep_id,),
            ).fetchone()
            if current and int(current["report_id"]) != target_report_id:
                old_report = int(current["report_id"])
                conn.execute(
                    """
                    UPDATE period_students
                    SET report_id=?, period_project_id=?, modality=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        target_report_id,
                        period_project_id,
                        target_modality,
                        utcnow(),
                        keep_id,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO student_audit_log
                    (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
                    VALUES (?, ?, 'MOVE_MASTER_DATASET', 'report_id', ?, ?,
                            'Requisitos cambió la modalidad oficial; se conservó la misma identidad interna y todas sus evidencias.',
                            ?)
                    """,
                    (
                        target_report_id,
                        keep_id,
                        str(old_report),
                        str(target_report_id),
                        utcnow(),
                    ),
                )
                moved += 1
    _clear_decision_cache()
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
    # La migración de identidad, la sincronización de Requisitos y su auditoría
    # forman una sola operación lógica. El candado es reentrante porque la capa
    # SQLite ya envuelve la sincronización base con el mismo RLock.
    with sqlite_guard._WRITE_LOCK:
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


def _exact_source_manual_target(report_id: int, module: str, source_key: str) -> int | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT period_student_id FROM student_source_links
            WHERE report_id=? AND source_module=? AND source_key=?
              AND match_method='MANUAL' AND period_student_id IS NOT NULL
            ORDER BY id DESC LIMIT 1
            """,
            (report_id, module, source_key),
        ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _guard_weak_manual_recovery(
    report_id: int,
    module: str,
    source_key: str,
    source: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Impide que una decisión por nombre se propague a otro homónimo."""
    if _strong_identity_key(source.get("identification"), source.get("email")):
        return result
    if str(result.get("method") or "") != "MANUAL":
        return result

    selected = int(result.get("period_student_id") or 0)
    if selected and _exact_source_manual_target(report_id, module, source_key) == selected:
        return result

    index = smart._master_index(report_id)
    folded = smart._fold(source.get("full_name"))
    exact = list(index["by_name"].get(folded, [])) if folded else []
    if len(exact) == 1 and selected == int(exact[0]["id"]):
        # El nombre es único en Requisitos; la recuperación no introduce ambigüedad.
        return result
    if len(exact) > 1:
        guarded = {
            "status": domain.MATCH_AMBIGUOUS,
            "method": "HOMONIMO",
            "confidence": 100.0,
            "period_student_id": None,
            "candidates": [smart._candidate_payload(item, 1.0) for item in exact[:3]],
            "detail": (
                "Existe una asociación manual de otra evidencia con el mismo nombre, "
                "pero hay homónimos. Informtit no la propaga automáticamente."
            ),
        }
        return _persist_final_match(report_id, module, source_key, source, guarded)

    ranked = smart._rank_candidates(source, index["masters"])
    candidates = [
        smart._candidate_payload(student, score)
        for score, student in ranked[:3]
        if score >= 0.68
    ]
    guarded = {
        "status": domain.MATCH_REVIEW,
        "method": "MANUAL_NO_PROPAGADO",
        "confidence": round(ranked[0][0] * 100, 1) if ranked else 0.0,
        "period_student_id": None,
        "candidates": candidates,
        "detail": (
            "Existe una decisión manual para otra evidencia parecida, pero esta fuente "
            "no tiene cédula ni correo real. Revise antes de reutilizar la asociación."
        ),
    }
    return _persist_final_match(report_id, module, source_key, source, guarded)


def _final_match(
    report_id: int,
    module: str,
    source_key: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    assert _FINAL_BASE_MATCH is not None
    # Mantiene el seguimiento de progreso de la capa de rendimiento.
    result = _FINAL_BASE_MATCH(report_id, module, source_key, source)
    result = _guard_weak_manual_recovery(report_id, module, source_key, source, result)
    project_id = _project_id_for_report(report_id)
    identity = _identity_key_source(source, source_key)
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


def _group_project_links(period_project_id: int, link: dict[str, Any]) -> list[dict[str, Any]]:
    report_ids = _project_report_ids(period_project_id)
    if not report_ids:
        return [link]
    placeholders = ",".join("?" for _ in report_ids)
    identity = _identity_key_link(link)
    module = str(link.get("source_module") or "")
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT * FROM student_source_links
                WHERE report_id IN ({placeholders}) AND source_module=?
                  AND COALESCE(source_active,1)=1
                ORDER BY id
                """,
                (*report_ids, module),
            ).fetchall()
        )
    siblings = [row for row in rows if _identity_key_link(row) == identity]
    return siblings or [link]


def _apply_source_rows(
    report_id: int,
    module: str,
    source_keys: set[str],
    student_id: int | None,
    *,
    manual_review: bool = False,
) -> int:
    """Actualiza solo las filas fuente afectadas; nunca re-concilia el módulo completo."""
    changed = 0
    if module == "COMPLEXIVE":
        with connection() as conn:
            rows = rows_to_dicts(
                conn.execute(
                    """
                    SELECT s.*, c.name AS career_name
                    FROM students s JOIN careers c ON c.id=s.career_id
                    WHERE c.report_id=? ORDER BY s.id
                    """,
                    (report_id,),
                ).fetchall()
            )
            for row in rows:
                if bridge._stable_source_key("COMPLEXIVE", row) not in source_keys:
                    continue
                conn.execute(
                    "UPDATE students SET period_student_id=? WHERE id=?",
                    (student_id, int(row["id"])),
                )
                changed += 1
        return changed

    if module == "THESIS":
        with connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='thesis_projects'"
            ).fetchone():
                return 0
            rows = rows_to_dicts(
                conn.execute("SELECT * FROM thesis_projects WHERE report_id=? ORDER BY id", (report_id,)).fetchall()
            )
            for row in rows:
                if bridge._stable_source_key("THESIS", row) not in source_keys:
                    continue
                conn.execute(
                    "UPDATE thesis_projects SET period_student_id=? WHERE id=?",
                    (student_id, int(row["id"])),
                )
                changed += 1
        return changed

    if module == "NUCLEI":
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
                    if manual_review:
                        conn.execute(
                            f"""
                            UPDATE {table}
                            SET period_student_id=NULL, match_status=?, match_method='MANUAL_REVIEW',
                                match_confidence=NULL
                            WHERE id=? AND course_id=?
                            """,
                            (domain.MATCH_REVIEW, int(source["id"]), course_id),
                        )
                    else:
                        conn.execute(
                            f"""
                            UPDATE {table}
                            SET period_student_id=?, match_status='OK', match_method='MANUAL',
                                match_confidence=100
                            WHERE id=? AND course_id=?
                            """,
                            (student_id, int(source["id"]), course_id),
                        )
                    changed += 1
        return changed
    return 0


def _confirm_project_case(period_project_id: int, link_id: int, student_id: int) -> dict[str, Any]:
    link = _project_link(period_project_id, link_id)
    with connection() as conn:
        student = conn.execute(
            """
            SELECT * FROM period_students
            WHERE id=? AND period_project_id=? AND COALESCE(requirements_present,1)=1
            """,
            (student_id, period_project_id),
        ).fetchone()
    if not student:
        raise ValueError("El estudiante seleccionado no pertenece a Requisitos de este período.")

    siblings = _group_project_links(period_project_id, link)
    identity = _identity_key_link(link)
    module = str(link.get("source_module") or "")
    now = utcnow()
    grouped: dict[int, set[str]] = defaultdict(set)
    ids = [int(row["id"]) for row in siblings]
    with sqlite_guard._WRITE_LOCK:
        with connection() as conn:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE student_source_links
                SET period_student_id=?, match_status='OK', match_method='MANUAL',
                    match_confidence=100,
                    detail='Asociación confirmada manualmente. Requisitos conserva nombre, carrera y modalidad oficiales.',
                    updated_at=?
                WHERE id IN ({placeholders})
                """,
                (student_id, now, *ids),
            )
            for row in siblings:
                grouped[int(row["report_id"])].add(str(row.get("source_key") or ""))
            conn.execute(
                """
                INSERT INTO student_audit_log
                (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
                VALUES (?, ?, 'CONFIRM_MATCH_PROJECT', 'source_link_group', ?, ?, ?, ?)
                """,
                (
                    int(link["report_id"]), student_id, ",".join(str(item) for item in ids),
                    str(student_id),
                    f"{module}: se confirmaron {len(ids)} evidencias agrupadas a nivel de período.",
                    now,
                ),
            )
        # Una nueva confirmación humana sustituye el descarte anterior del mismo
        # destino y cualquier asociación manual previa para esa identidad.
        _delete_decisions(period_project_id, module, identity, DECISION_MATCH)
        _delete_decisions(
            period_project_id, module, identity, DECISION_DO_NOT_MATCH,
            target_student_id=student_id,
        )
        _store_decision(
            period_project_id, module, identity, DECISION_MATCH,
            target_student_id=student_id, decision_value=str(student_id),
            detail="Asociación manual persistente; sobrevive a futuras recargas.",
        )
        for report_id, keys in grouped.items():
            _apply_source_rows(report_id, module, keys, student_id)
    return {"ok": True, "student_id": student_id, "confirmed_links": len(ids), "module": module}


def _unlink_project_case(period_project_id: int, link_id: int) -> dict[str, Any]:
    link = _project_link(period_project_id, link_id)
    siblings = _group_project_links(period_project_id, link)
    identity = _identity_key_link(link)
    module = str(link.get("source_module") or "")
    old_targets = {
        int(row["period_student_id"]) for row in siblings if row.get("period_student_id")
    }
    now = utcnow()
    grouped: dict[int, set[str]] = defaultdict(set)
    ids = [int(row["id"]) for row in siblings]
    with sqlite_guard._WRITE_LOCK:
        with connection() as conn:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE student_source_links
                SET period_student_id=NULL, match_status=?, match_method='MANUAL_REVIEW',
                    match_confidence=NULL,
                    detail='Asociación descartada manualmente. La evidencia permanece intacta y no volverá a enlazarse sola con el estudiante descartado.',
                    source_active=1, updated_at=?
                WHERE id IN ({placeholders})
                """,
                (domain.MATCH_REVIEW, now, *ids),
            )
            for row in siblings:
                grouped[int(row["report_id"])].add(str(row.get("source_key") or ""))
            conn.execute(
                """
                INSERT INTO student_audit_log
                (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
                VALUES (?, ?, 'UNLINK_SOURCE_PROJECT', 'source_link_group', ?, '', ?, ?)
                """,
                (
                    int(link["report_id"]), next(iter(old_targets), None),
                    ",".join(str(item) for item in ids),
                    f"{module}: se descartó manualmente la asociación de {len(ids)} evidencias agrupadas.",
                    now,
                ),
            )
        # Desvincular invalida una confirmación positiva previa; de otro modo el
        # siguiente Reconciliar volvería a enlazarla antes de mirar el veto.
        _delete_decisions(period_project_id, module, identity, DECISION_MATCH)
        for target_id in old_targets:
            _store_decision(
                period_project_id, module, identity, DECISION_DO_NOT_MATCH,
                decision_scope=str(target_id), target_student_id=target_id,
                detail="El usuario indicó que esta evidencia no pertenece a este estudiante.",
            )
        for report_id, keys in grouped.items():
            _apply_source_rows(report_id, module, keys, None, manual_review=True)
    return {
        "ok": True, "link_id": link_id, "module": module,
        "unlinked_links": len(ids),
        "unlinked_source_rows": sum(len(keys) for keys in grouped.values()),
    }


def _route_evidence(period_project_id: int) -> dict[int, set[str]]:
    report_ids = _project_report_ids(period_project_id)
    if not report_ids:
        return {}
    placeholders = ",".join("?" for _ in report_ids)
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT period_student_id, source_module
                FROM student_source_links
                WHERE report_id IN ({placeholders})
                  AND COALESCE(source_active,1)=1
                  AND period_student_id IS NOT NULL
                  AND source_module IN ('COMPLEXIVE','THESIS')
                  AND COALESCE(match_method,'')<>'MANUAL_REVIEW'
                """,
                tuple(report_ids),
            ).fetchall()
        )
    evidence: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        evidence[int(row["period_student_id"])].add(str(row["source_module"]))
    return evidence


def _write_route(
    conn: Any,
    row: dict[str, Any],
    route: str,
    source: str,
    detail: str,
) -> bool:
    old_route = str(row.get("route") or domain.ROUTE_COMPLEXIVE)
    old_source = str(row.get("route_source") or "")
    if old_route == route and old_source == source:
        return False
    now = utcnow()
    conn.execute(
        "UPDATE period_students SET route=?, route_source=?, updated_at=? WHERE id=?",
        (route, source, now, int(row["id"])),
    )
    conn.execute(
        """
        INSERT INTO student_audit_log
        (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
        VALUES (?, ?, ?, 'route', ?, ?, ?, ?)
        """,
        (
            int(row["report_id"]), int(row["id"]),
            "AUTO_ROUTE_EVIDENCE" if source == "AUTO_EVIDENCE" else "CHANGE_ROUTE",
            old_route, route, detail, now,
        ),
    )
    return True


def _normalize_routes(period_project_id: int) -> dict[str, int]:
    """Corrige rutas inequívocas y convierte el doble origen en un único caso manual."""
    evidence = _route_evidence(period_project_id)
    with connection() as conn:
        students = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM period_students
                WHERE period_project_id=? AND COALESCE(requirements_present,1)=1
                ORDER BY id
                """,
                (period_project_id,),
            ).fetchall()
        )
    auto_routes = 0
    conflicts = 0
    manual_resolved = 0
    with connection() as conn:
        for row in students:
            sid = int(row["id"])
            modules = evidence.get(sid, set())
            has_complexive = "COMPLEXIVE" in modules
            has_thesis = "THESIS" in modules
            manual = str(row.get("route_source") or "") == "MANUAL"

            if manual:
                selected = "THESIS" if row.get("route") == domain.ROUTE_THESIS else "COMPLEXIVE"
                opposite = "COMPLEXIVE" if selected == "THESIS" else "THESIS"
                conn.execute(
                    """
                    UPDATE student_source_links
                    SET match_status='OK',
                        match_method=CASE
                            WHEN source_module=? THEN 'MANUAL_ROUTE_INCLUDED'
                            WHEN source_module=? THEN 'ROUTE_EXCLUDED_MANUAL'
                            ELSE match_method
                        END,
                        detail=CASE
                            WHEN source_module=? THEN 'Identidad confirmada; evidencia válida para la ruta seleccionada manualmente.'
                            WHEN source_module=? THEN 'Identidad confirmada; evidencia conservada para auditoría pero excluida por la ruta seleccionada manualmente.'
                            ELSE detail
                        END,
                        updated_at=?
                    WHERE period_student_id=? AND source_module IN ('COMPLEXIVE','THESIS')
                      AND COALESCE(source_active,1)=1
                    """,
                    (selected, opposite, selected, opposite, utcnow(), sid),
                )
                if has_complexive and has_thesis:
                    manual_resolved += 1
                continue

            if has_thesis and not has_complexive:
                if _write_route(
                    conn, row, domain.ROUTE_THESIS, "AUTO_EVIDENCE",
                    "Ruta corregida automáticamente: existe Trabajo de Titulación y no existe evidencia válida de Examen Complexivo.",
                ):
                    auto_routes += 1
            elif has_complexive and not has_thesis:
                if _write_route(
                    conn, row, domain.ROUTE_COMPLEXIVE, "AUTO_EVIDENCE",
                    "Ruta corregida automáticamente: existe Examen Complexivo y no existe Trabajo de Titulación válido.",
                ):
                    auto_routes += 1
            elif has_complexive and has_thesis:
                conflicts += 1

            # La identidad no debe quedar en ROUTE_CONFLICT: la ruta se trata aparte.
            if has_complexive or has_thesis:
                conn.execute(
                    """
                    UPDATE student_source_links
                    SET match_status='OK',
                        detail=CASE
                            WHEN ?=1 AND ?=1 THEN
                                'Identidad confirmada. Existen evidencias de ambas rutas; la ruta requiere decisión humana.'
                            ELSE 'Identidad y ruta conciliadas.'
                        END,
                        updated_at=?
                    WHERE period_student_id=? AND source_module IN ('COMPLEXIVE','THESIS')
                      AND COALESCE(source_active,1)=1
                    """,
                    (int(has_complexive), int(has_thesis), utcnow(), sid),
                )
    return {
        "auto_routes": auto_routes,
        "route_conflicts": conflicts,
        "manual_route_resolved": manual_resolved,
    }


def _set_route_manual_final(period_project_id: int, student_id: int, route: str) -> dict[str, Any]:
    route = str(route or "").strip().upper()
    if route not in domain.ROUTES:
        raise ValueError("Seleccione Examen Complexivo o Trabajo de Titulación.")
    with sqlite_guard._WRITE_LOCK:
        with connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM period_students
                WHERE id=? AND period_project_id=? AND COALESCE(requirements_present,1)=1
                """,
                (student_id, period_project_id),
            ).fetchone()
            if not row:
                raise ValueError("El estudiante no pertenece al período seleccionado.")
            _write_route(
                conn, dict(row), route, "MANUAL",
                "Ruta definida manualmente desde Estudiantes; prevalece sobre futuras conciliaciones.",
            )
        _store_decision(
            period_project_id, "ROUTE", f"student:{student_id}", DECISION_ROUTE,
            decision_scope="route", target_student_id=student_id,
            decision_value=route, detail="Ruta confirmada manualmente.",
        )
        _normalize_routes(period_project_id)
    return {"ok": True, "student_id": student_id, "route": route, "route_source": "MANUAL"}


def _grade_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(str(value).replace(",", ".")), 4)
    except (TypeError, ValueError):
        return None


def _grade_resolution(period_project_id: int, module: str, identity_key: str) -> float | None:
    rows = _manual_decisions(
        period_project_id, f"GRADE_{module}", identity_key, DECISION_GRADE
    )
    return _grade_value(rows[0].get("decision_value")) if rows else None


def _grade_cases(period_project_id: int) -> list[dict[str, Any]]:
    report_ids = _project_report_ids(period_project_id)
    if not report_ids:
        return []
    placeholders = ",".join("?" for _ in report_ids)
    with connection() as conn:
        students = rows_to_dicts(
            conn.execute(
                """
                SELECT id, report_id, full_name, identification, career_name, modality, route
                FROM period_students
                WHERE period_project_id=? AND COALESCE(requirements_present,1)=1
                """,
                (period_project_id,),
            ).fetchall()
        )
        student_map = {int(row["id"]): row for row in students}
        complexive_rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT s.*, c.report_id AS source_report_id
                FROM students s JOIN careers c ON c.id=s.career_id
                WHERE c.report_id IN ({placeholders}) AND s.period_student_id IS NOT NULL
                """,
                tuple(report_ids),
            ).fetchall()
        )
        thesis_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='thesis_projects'"
        ).fetchone()
        thesis_rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT * FROM thesis_projects
                WHERE report_id IN ({placeholders}) AND period_student_id IS NOT NULL
                """,
                tuple(report_ids),
            ).fetchall()
        ) if thesis_exists else []

        nuclei_rows: list[dict[str, Any]] = []
        if (
            conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_instance_students'").fetchone()
            and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_course_instances'").fetchone()
        ):
            cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(nucleus_instance_students)").fetchall()}
            if "period_student_id" in cols:
                nuclei_rows = rows_to_dicts(
                    conn.execute(
                        f"""
                        SELECT ns.*, nc.nucleus_number, nc.report_id AS source_report_id
                        FROM nucleus_instance_students ns
                        JOIN nucleus_course_instances nc ON nc.id=ns.course_id
                        WHERE nc.report_id IN ({placeholders}) AND ns.period_student_id IS NOT NULL
                        """,
                        tuple(report_ids),
                    ).fetchall()
                )
        elif (
            conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_students'").fetchone()
            and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_courses'").fetchone()
        ):
            cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(nucleus_students)").fetchall()}
            if "period_student_id" in cols:
                nuclei_rows = rows_to_dicts(
                    conn.execute(
                        f"""
                        SELECT ns.*, nc.nucleus_number, nc.report_id AS source_report_id
                        FROM nucleus_students ns
                        JOIN nucleus_courses nc ON nc.id=ns.course_id
                        WHERE nc.report_id IN ({placeholders}) AND ns.period_student_id IS NOT NULL
                        """,
                        tuple(report_ids),
                    ).fetchall()
                )

    cases: list[dict[str, Any]] = []
    by_complexive: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in complexive_rows:
        by_complexive[int(row["period_student_id"])].append(row)
    for student_id, rows in by_complexive.items():
        student = student_map.get(student_id, {})
        if str(student.get("route") or domain.ROUTE_COMPLEXIVE) != domain.ROUTE_COMPLEXIVE:
            continue
        values = sorted({
            _grade_value(analytics.final_grade(row))
            for row in rows
            if _grade_value(analytics.final_grade(row)) is not None
        })
        if len(values) > 1 and _grade_resolution(
            period_project_id, "COMPLEXIVE", f"student:{student_id}"
        ) is None:
            cases.append({
                "case_id": f"grade:complexive:{student_id}",
                "case_type": "GRADE",
                "match_status": domain.MATCH_GRADE_CONFLICT,
                "source_module": "COMPLEXIVE",
                "student_id": student_id,
                "source_name": student.get("full_name") or "",
                "source_identification": audit._public_identification(student.get("identification")),
                "detail": "Existen notas finales distintas de Examen Complexivo para la misma persona.",
                "grade_options": values,
                "suggestion": None,
            })

    by_thesis: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in thesis_rows:
        by_thesis[int(row["period_student_id"])].append(row)
    for student_id, rows in by_thesis.items():
        student = student_map.get(student_id, {})
        if str(student.get("route") or domain.ROUTE_COMPLEXIVE) != domain.ROUTE_THESIS:
            continue
        values = sorted({
            _grade_value(row.get("final_grade"))
            for row in rows
            if _grade_value(row.get("final_grade")) is not None
        })
        if len(values) > 1 and _grade_resolution(
            period_project_id, "THESIS", f"student:{student_id}"
        ) is None:
            cases.append({
                "case_id": f"grade:thesis:{student_id}",
                "case_type": "GRADE",
                "match_status": domain.MATCH_GRADE_CONFLICT,
                "source_module": "THESIS",
                "student_id": student_id,
                "source_name": student.get("full_name") or "",
                "source_identification": audit._public_identification(student.get("identification")),
                "detail": "Existen notas finales distintas de Trabajo de Titulación para la misma persona.",
                "grade_options": values,
                "suggestion": None,
            })

    by_nucleus: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in nuclei_rows:
        sid = int(row["period_student_id"])
        number = int(row.get("nucleus_number") or 0)
        if sid and number:
            by_nucleus[(sid, number)].append(row)
    for (student_id, number), rows in by_nucleus.items():
        student = student_map.get(student_id, {})
        if str(student.get("route") or domain.ROUTE_COMPLEXIVE) != domain.ROUTE_COMPLEXIVE:
            continue
        values = sorted({
            _grade_value(row.get("final_grade"))
            for row in rows
            if _grade_value(row.get("final_grade")) is not None
        })
        key = f"student:{student_id}:nucleus:{number}"
        if len(values) > 1 and _grade_resolution(
            period_project_id, "NUCLEI", key
        ) is None:
            cases.append({
                "case_id": f"grade:nuclei:{student_id}:{number}",
                "case_type": "GRADE",
                "match_status": domain.MATCH_GRADE_CONFLICT,
                "source_module": "NUCLEI",
                "student_id": student_id,
                "nucleus_number": number,
                "source_name": student.get("full_name") or "",
                "source_identification": audit._public_identification(student.get("identification")),
                "detail": f"Existen notas distintas para el Núcleo {number}.",
                "grade_options": values,
                "suggestion": None,
            })
    return cases


def _resolve_grade_case(
    period_project_id: int,
    module: str,
    student_id: int,
    grade: Any,
    nucleus_number: int = 0,
) -> dict[str, Any]:
    module = str(module or "").strip().upper()
    if module not in {"NUCLEI", "COMPLEXIVE", "THESIS"}:
        raise ValueError("Módulo de calificación no válido.")
    selected = _grade_value(grade)
    if selected is None:
        raise ValueError("Seleccione una calificación válida.")
    with connection() as conn:
        student = conn.execute(
            """
            SELECT * FROM period_students
            WHERE id=? AND period_project_id=? AND COALESCE(requirements_present,1)=1
            """,
            (student_id, period_project_id),
        ).fetchone()
    if not student:
        raise ValueError("El estudiante no pertenece al período.")
    identity = (
        f"student:{student_id}:nucleus:{int(nucleus_number)}"
        if module == "NUCLEI" else f"student:{student_id}"
    )
    _store_decision(
        period_project_id, f"GRADE_{module}", identity, DECISION_GRADE,
        decision_scope="selected", target_student_id=student_id,
        decision_value=str(selected),
        detail="Calificación seleccionada manualmente entre evidencias contradictorias.",
    )
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO student_audit_log
            (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
            VALUES (?, ?, 'RESOLVE_GRADE_CONFLICT', ?, '', ?,
                    'Se conservan todas las evidencias originales; esta nota se usa como resolución efectiva.',
                    ?)
            """,
            (
                int(student["report_id"]), student_id, f"grade:{module.lower()}",
                str(selected), utcnow(),
            ),
        )
    return {
        "ok": True, "student_id": student_id, "module": module,
        "grade": selected, "nucleus_number": int(nucleus_number or 0),
    }



def _complexive_records_final(report_id: int) -> dict[int, list[dict[str, Any]]]:
    assert _FINAL_BASE_COMPLEXIVE_RECORDS is not None
    grouped = _FINAL_BASE_COMPLEXIVE_RECORDS(report_id)
    project_id = _project_id_for_report(report_id)
    if not project_id:
        return grouped
    result: dict[int, list[dict[str, Any]]] = {}
    for student_id, records in grouped.items():
        selected = _grade_resolution(project_id, "COMPLEXIVE", f"student:{student_id}")
        if selected is None:
            result[student_id] = records
            continue
        chosen = [
            row for row in records
            if _grade_value(analytics.final_grade(row)) == selected
        ]
        result[student_id] = chosen or records
    return result


def _thesis_records_final(report_id: int) -> dict[int, list[dict[str, Any]]]:
    assert _FINAL_BASE_THESIS_RECORDS is not None
    grouped = _FINAL_BASE_THESIS_RECORDS(report_id)
    project_id = _project_id_for_report(report_id)
    if not project_id:
        return grouped
    result: dict[int, list[dict[str, Any]]] = {}
    for student_id, records in grouped.items():
        selected = _grade_resolution(project_id, "THESIS", f"student:{student_id}")
        if selected is None:
            result[student_id] = records
            continue
        chosen = [
            row for row in records
            if _grade_value(row.get("final_grade")) == selected
        ]
        result[student_id] = chosen or records
    return result


def _nuclei_records_final(report_id: int) -> dict[int, list[dict[str, Any]]]:
    assert _FINAL_BASE_NUCLEI_RECORDS is not None
    grouped = _FINAL_BASE_NUCLEI_RECORDS(report_id)
    project_id = _project_id_for_report(report_id)
    if not project_id:
        return grouped
    result: dict[int, list[dict[str, Any]]] = {}
    for student_id, records in grouped.items():
        by_number: dict[int, list[dict[str, Any]]] = defaultdict(list)
        passthrough: list[dict[str, Any]] = []
        for row in records:
            number = int(row.get("nucleus_number") or 0)
            if number:
                by_number[number].append(row)
            else:
                passthrough.append(row)
        selected_rows = list(passthrough)
        for number, items in by_number.items():
            key = f"student:{student_id}:nucleus:{number}"
            selected = _grade_resolution(project_id, "NUCLEI", key)
            if selected is None:
                selected_rows.extend(items)
                continue
            chosen = [
                row for row in items
                if _grade_value(row.get("final_grade")) == selected
            ]
            selected_rows.extend(chosen or items)
        result[student_id] = selected_rows
    return result


def _route_cases(period_project_id: int) -> list[dict[str, Any]]:
    evidence = _route_evidence(period_project_id)
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM period_students
                WHERE period_project_id=? AND COALESCE(requirements_present,1)=1
                ORDER BY full_name
                """,
                (period_project_id,),
            ).fetchall()
        )
    cases: list[dict[str, Any]] = []
    for row in rows:
        sid = int(row["id"])
        modules = evidence.get(sid, set())
        if (
            "COMPLEXIVE" in modules and "THESIS" in modules
            and str(row.get("route_source") or "") != "MANUAL"
        ):
            cases.append({
                "case_id": f"route:{sid}",
                "case_type": "ROUTE",
                "match_status": domain.MATCH_ROUTE_CONFLICT,
                "source_module": "ROUTE",
                "student_id": sid,
                "source_name": row.get("full_name") or "",
                "source_identification": audit._public_identification(row.get("identification")),
                "career_name": row.get("career_name") or "",
                "modality": row.get("modality") or "",
                "current_route": row.get("route") or domain.ROUTE_COMPLEXIVE,
                "detail": "Existen evidencias válidas tanto de Examen Complexivo como de Trabajo de Titulación. Seleccione la ruta correcta.",
                "suggestion": None,
            })
    return cases


def _identity_cases(period_project_id: int) -> list[dict[str, Any]]:
    report_ids = _project_report_ids(period_project_id)
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
                  AND COALESCE(l.source_active,1)=1
                  AND COALESCE(l.match_status,'UNMATCHED')<>'OK'
                  AND COALESCE(l.match_status,'') NOT IN ('ROUTE_CONFLICT','GRADE_CONFLICT')
                ORDER BY l.id
                """,
                tuple(report_ids),
            ).fetchall()
        )
    priority = {
        audit.MATCH_DUPLICATE: 120,
        audit.MATCH_MODALITY_CONFLICT: 115,
        audit.MATCH_IDENTITY_CONFLICT: 110,
        domain.MATCH_AMBIGUOUS: 90,
        domain.MATCH_REVIEW: 80,
        smart.MATCH_OUTSIDE_POPULATION: 70,
        domain.MATCH_UNMATCHED: 60,
    }
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("source_module") or ""), _identity_key_link(row))].append(row)

    cases: list[dict[str, Any]] = []
    for (module, identity), items in groups.items():
        representative = max(
            items, key=lambda row: priority.get(str(row.get("match_status") or ""), 50)
        )
        item = dict(representative)
        try:
            candidates = json.loads(item.get("candidates_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            candidates = []
        blocked = _blocked_targets(period_project_id, module, identity)
        candidates = [
            candidate for candidate in candidates
            if int(candidate.get("student_id") or 0) not in blocked
        ][:3]
        item.update({
            "case_id": f"identity:{module.lower()}:{int(item['id'])}",
            "case_type": "IDENTITY",
            "occurrences": len(items),
            "group_link_ids": [int(row["id"]) for row in items],
            "candidates": candidates,
            "suggestion": candidates[0] if candidates else None,
        })
        if len(items) > 1:
            item["detail"] = (
                f"{len(items)} evidencias de la misma persona se agruparon en este caso. "
                + str(item.get("detail") or "")
            ).strip()
        cases.append(item)
    return cases


def _official_cases(period_project_id: int) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM period_students
                WHERE period_project_id=? AND COALESCE(requirements_present,1)=1
                  AND COALESCE(reconciliation_status,'OK')<>'OK'
                ORDER BY full_name
                """,
                (period_project_id,),
            ).fetchall()
        )
    return [
        {
            "case_id": f"official:{int(row['id'])}",
            "case_type": "OFFICIAL",
            "match_status": str(row.get("reconciliation_status") or domain.MATCH_REVIEW),
            "source_module": "REQUIREMENTS",
            "student_id": int(row["id"]),
            "source_name": row.get("full_name") or "",
            "source_identification": audit._public_identification(row.get("identification")),
            "detail": row.get("reconciliation_detail") or "Revise los datos oficiales de Requisitos.",
            "suggestion": None,
        }
        for row in rows
    ]


def _project_cases(period_project_id: int) -> list[dict[str, Any]]:
    cases = (
        _identity_cases(period_project_id)
        + _route_cases(period_project_id)
        + _grade_cases(period_project_id)
        + _official_cases(period_project_id)
    )
    priority = {
        audit.MATCH_IDENTITY_CONFLICT: 120,
        audit.MATCH_DUPLICATE: 115,
        audit.MATCH_MODALITY_CONFLICT: 110,
        domain.MATCH_ROUTE_CONFLICT: 100,
        domain.MATCH_GRADE_CONFLICT: 95,
        domain.MATCH_AMBIGUOUS: 90,
        domain.MATCH_REVIEW: 80,
        smart.MATCH_OUTSIDE_POPULATION: 70,
        domain.MATCH_UNMATCHED: 60,
    }
    cases.sort(
        key=lambda case: (
            -priority.get(str(case.get("match_status") or ""), 50),
            str(case.get("case_type") or ""),
            str(case.get("source_name") or "").casefold(),
        )
    )
    return cases


def _final_case_summary(period_project_id: int) -> dict[str, int]:
    cases = _project_cases(period_project_id)
    outside = sum(
        str(case.get("match_status") or "") == smart.MATCH_OUTSIDE_POPULATION
        for case in cases
    )
    identity_review = sum(
        case.get("case_type") == "IDENTITY"
        and str(case.get("match_status") or "") != smart.MATCH_OUTSIDE_POPULATION
        for case in cases
    )
    route = sum(case.get("case_type") == "ROUTE" for case in cases)
    grade = sum(case.get("case_type") == "GRADE" for case in cases)
    official = sum(case.get("case_type") == "OFFICIAL" for case in cases)

    report_ids = _project_report_ids(period_project_id)
    auto_resolved = 0
    if report_ids:
        placeholders = ",".join("?" for _ in report_ids)
        with connection() as conn:
            auto_resolved = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*) FROM student_source_links
                    WHERE report_id IN ({placeholders})
                      AND COALESCE(source_active,1)=1 AND match_status='OK'
                      AND COALESCE(match_method,'') NOT IN ('MANUAL','MANUAL_REVIEW','MANUAL_ROUTE_INCLUDED','ROUTE_EXCLUDED_MANUAL')
                    """,
                    tuple(report_ids),
                ).fetchone()[0]
            )
    return {
        "total_cases": len(cases),
        "outside_population": int(outside),
        "identity_review": int(identity_review),
        "route_conflicts": int(route),
        "grade_conflicts": int(grade),
        "official_review": int(official),
        "auto_resolved": auto_resolved,
        "raw_pending": sum(
            int(case.get("occurrences") or 1)
            for case in cases if case.get("case_type") == "IDENTITY"
        ),
    }


def _summary_from_report_ids(report_ids: list[int]) -> dict[str, int]:
    if not report_ids:
        return {
            "total_cases": 0, "outside_population": 0, "identity_review": 0,
            "route_conflicts": 0, "grade_conflicts": 0, "official_review": 0,
            "auto_resolved": 0, "raw_pending": 0,
        }
    project_id = _project_id_for_report(int(report_ids[0]))
    return _final_case_summary(project_id) if project_id else smart._case_summary(report_ids)


def _period_read_final(period_project_id: int) -> dict[str, Any]:
    assert _FINAL_BASE_PERIOD_READ is not None
    data = _FINAL_BASE_PERIOD_READ(period_project_id)
    cases = _project_cases(period_project_id)
    summary = _final_case_summary(period_project_id)
    data["cases"] = cases
    data["open_links"] = cases
    data["case_summary"] = summary
    data.setdefault("summary", {})["review"] = summary["total_cases"]
    data["summary"]["open_links"] = summary["identity_review"] + summary["outside_population"]
    data["summary"]["source_alerts"] = summary["total_cases"]

    by_student: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        if case.get("student_id"):
            by_student[int(case["student_id"])].append(case)
    priority = {
        domain.MATCH_ROUTE_CONFLICT: 100,
        domain.MATCH_GRADE_CONFLICT: 90,
        audit.MATCH_IDENTITY_CONFLICT: 85,
        domain.MATCH_AMBIGUOUS: 80,
        domain.MATCH_REVIEW: 70,
    }
    for row in data.get("students", []):
        student_cases = by_student.get(int(row["id"]), [])
        if not student_cases:
            continue
        top = max(
            student_cases,
            key=lambda case: priority.get(str(case.get("match_status") or ""), 60),
        )
        row["reconciliation_status"] = top.get("match_status") or domain.MATCH_REVIEW
        row["reconciliation_detail"] = top.get("detail") or ""
    return data


def _candidate_search(period_project_id: int, link_id: int, query: str) -> dict[str, Any]:
    result = project_wide._search_project_candidates(period_project_id, link_id, query)
    link = _project_link(period_project_id, link_id)
    blocked = _blocked_targets(
        period_project_id, str(link.get("source_module") or ""), _identity_key_link(link)
    )
    result["candidates"] = [
        row for row in list(result.get("candidates") or [])
        if int(row.get("student_id") or 0) not in blocked
    ][:20]
    return result


def _run_final_job_core(job_id: str, period_project_id: int) -> None:
    """Job final: identidad -> evidencias -> rutas -> notas -> casos."""
    try:
        members = fast_read._member_reports(period_project_id)
        if not members:
            raise ValueError("El período no tiene datasets para conciliar.")
        total_steps = len(members) * 4 + 1
        done = 0
        aggregate = {
            "matched": 0,
            "outside_population": 0,
            "identity_review": 0,
            "route_conflicts": 0,
            "grade_conflicts": 0,
            "auto_routes": 0,
            "auto_resolved": 0,
            "cases": 0,
        }
        smart._set_job(
            job_id,
            status="running",
            progress=2,
            stage="Preparando población maestra",
            detail="Verificando una sola identidad por cédula aunque Requisitos haya cambiado Presencial/Online.",
            stats=aggregate,
        )
        with sqlite_guard._WRITE_LOCK:
            migration = _migrate_project_master(period_project_id)
            smart._set_job(
                job_id,
                progress=3,
                detail=(
                    f"Identidad maestra preparada: {migration['moved']} cambios de modalidad "
                    f"y {migration['merged']} duplicados consolidados."
                ),
                stats=aggregate,
            )

            for member in members:
                report_id = int(member["id"])
                modality = str(member.get("modality") or "")
                label = "Presencial" if modality == "presencial" else "Online"
                smart._set_job(
                    job_id,
                    progress=smart._stage_progress(done, total_steps),
                    stage=f"{label} · preparando estudiantes",
                    detail="Sincronizando nombre, carrera y modalidad oficiales desde Requisitos.",
                    stats=aggregate,
                )
                sync_result = audit.sync_report_students(report_id)
                done += 1
                smart._set_job(
                    job_id,
                    progress=smart._stage_progress(done, total_steps),
                    detail=f"{int(sync_result.get('students') or 0)} estudiantes maestros verificados.",
                    stats=aggregate,
                )

                for module, module_label, callback in (
                    ("NUCLEI", "Núcleos", audit.reconcile_nuclei),
                    ("COMPLEXIVE", "Examen Complexivo", audit.reconcile_complexive),
                    ("THESIS", "Trabajo de Titulación", audit.reconcile_thesis),
                ):
                    total_records = smart._source_count(report_id, module)
                    smart._set_job(
                        job_id,
                        progress=smart._stage_progress(done, total_steps),
                        stage=f"{label} · {module_label}",
                        detail=(
                            f"Analizando {total_records} registros contra todos los "
                            "estudiantes oficiales del período."
                        ),
                        stats=aggregate,
                    )
                    result = callback(report_id)
                    counts = smart._module_status_counts(report_id, module)
                    aggregate["matched"] += int(counts.get(domain.MATCH_OK, 0))
                    aggregate["outside_population"] += int(
                        counts.get(smart.MATCH_OUTSIDE_POPULATION, 0)
                    )
                    aggregate["identity_review"] += sum(
                        int(counts.get(key, 0))
                        for key in (
                            audit.MATCH_IDENTITY_CONFLICT,
                            domain.MATCH_REVIEW,
                            domain.MATCH_AMBIGUOUS,
                            domain.MATCH_UNMATCHED,
                        )
                    )
                    done += 1
                    smart._set_job(
                        job_id,
                        progress=smart._stage_progress(done, total_steps),
                        detail=(
                            f"{module_label}: {int(result.get('matched') or 0)} vinculados; "
                            f"{int(counts.get(smart.MATCH_OUTSIDE_POPULATION, 0))} fuera de población."
                        ),
                        stats=aggregate,
                    )

            smart._set_job(
                job_id,
                progress=95,
                stage="Resolviendo rutas",
                detail="Corrigiendo automáticamente rutas inequívocas y separando los conflictos reales.",
                stats=aggregate,
            )
            route_stats = _normalize_routes(period_project_id)
            aggregate["auto_routes"] = int(route_stats["auto_routes"])

            smart._set_job(
                job_id,
                progress=97,
                stage="Verificando calificaciones",
                detail="Buscando notas contradictorias sin elegir una de ellas automáticamente.",
                stats=aggregate,
            )
            aggregate["grade_conflicts"] = len(_grade_cases(period_project_id))

            smart._set_job(
                job_id,
                progress=99,
                stage="Agrupando casos que requieren atención",
                detail="Agrupando evidencias repetidas para dejar únicamente decisiones humanas reales.",
                stats=aggregate,
            )
            summary = _final_case_summary(period_project_id)
            aggregate["auto_resolved"] = summary["auto_resolved"]
            aggregate["cases"] = summary["total_cases"]
            aggregate["outside_population"] = summary["outside_population"]
            aggregate["identity_review"] = summary["identity_review"]
            aggregate["route_conflicts"] = summary["route_conflicts"]
            aggregate["grade_conflicts"] = summary["grade_conflicts"]

        smart._set_job(
            job_id,
            progress=100,
            status="completed",
            stage="Conciliación completada",
            detail=(
                f"Informtit resolvió automáticamente {aggregate['auto_resolved']} evidencias "
                f"y dejó {aggregate['cases']} casos reales para revisión."
            ),
            stats=aggregate,
            error="",
        )
    except Exception as exc:
        smart._set_job(
            job_id,
            status="error",
            stage="No se pudo completar la conciliación",
            detail="Se conservaron los datos procesados antes del error.",
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        with smart._JOB_LOCK:
            if smart._ACTIVE_BY_PROJECT.get(period_project_id) == job_id:
                smart._ACTIVE_BY_PROJECT.pop(period_project_id, None)
        smart._cleanup_jobs()


def _install_final_contract() -> None:
    """Instala la semántica acordada después de todas las capas legacy/hotfix."""
    global _FINAL_INSTALLED, _FINAL_BASE_MATCH, _FINAL_BASE_SYNC
    global _FINAL_BASE_PERIOD_READ, _FINAL_BASE_GET, _FINAL_BASE_WRITE
    global _FINAL_BASE_COMPLEXIVE_RECORDS, _FINAL_BASE_THESIS_RECORDS, _FINAL_BASE_NUCLEI_RECORDS
    if _FINAL_INSTALLED:
        return
    _ensure_final_schema()

    _FINAL_BASE_MATCH = bridge._match
    _FINAL_BASE_SYNC = audit.sync_report_students
    _FINAL_BASE_PERIOD_READ = fast_read._period_students_read
    _FINAL_BASE_GET = core.InformtitHandler._handle_api_get
    _FINAL_BASE_WRITE = core.InformtitHandler._handle_api_write
    _FINAL_BASE_COMPLEXIVE_RECORDS = read_model._complexive_records
    _FINAL_BASE_THESIS_RECORDS = read_model._thesis_records
    _FINAL_BASE_NUCLEI_RECORDS = read_model._nuclei_records

    # Requisitos gobierna identidad/nombre/carrera/modalidad y conserva la entidad
    # aunque cambie de dataset en una carga posterior. Se actualizan también las
    # referencias capturadas por capas antiguas para que ninguna lectura salte el
    # contrato final y vuelva a usar la sincronización previa.
    audit.sync_report_students = _sync_students_final
    domain.sync_report_students = _sync_students_final
    import student_domain_runtime as domain_runtime
    import student_period_service as period_service
    domain_runtime.sync_report_students = _sync_students_final
    period_service.sync_report_students = _sync_students_final

    # Las decisiones humanas positivas y negativas sobreviven a recargas.
    bridge._match = _final_match

    # Mantiene el wrapper de rendimiento/progreso, pero sustituye su núcleo.
    perf._BASE_RUN_JOB = _run_final_job_core

    # Las decisiones de nota afectan la lectura efectiva, no la evidencia cruda.
    read_model._complexive_records = _complexive_records_final
    read_model._thesis_records = _thesis_records_final
    read_model._nuclei_records = _nuclei_records_final

    # Lectura única de casos para tabla, contadores y acciones manuales.
    fast_read._period_students_read = _period_read_final

    # Los informes deben consumir la conciliación persistida, no volver a escribir
    # miles de filas al generar una salida.
    report_integration.reconcile_all = lambda report_id: {"ok": True, "read_only": True}

    def final_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(r"/api/period-projects/(\d+)/reconciliation-summary", path)
        if match:
            pid = int(match.group(1))
            self._send_json({"ok": True, "summary": _final_case_summary(pid)})
            return

        match = re.fullmatch(
            r"/api/period-projects/(\d+)/students-domain/matches/(\d+)/candidates",
            path,
        )
        if match:
            values = query.get("q") if isinstance(query, dict) else None
            q = values[0] if isinstance(values, list) and values else str(values or "")
            try:
                self._send_json(_candidate_search(int(match.group(1)), int(match.group(2)), q))
            except ValueError as exc:
                self._send_error_json(str(exc), 400)
            return

        assert _FINAL_BASE_GET is not None
        _FINAL_BASE_GET(self, path, query)

    def final_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        match = re.fullmatch(
            r"/api/period-projects/(\d+)/students-domain/matches/(\d+)/confirm",
            path,
        )
        if match and method in {"POST", "PUT"}:
            try:
                student_id = int(payload.get("student_id") or 0)
                if not student_id:
                    raise ValueError("Seleccione un estudiante válido.")
                self._send_json(
                    _confirm_project_case(int(match.group(1)), int(match.group(2)), student_id)
                )
            except ValueError as exc:
                self._send_error_json(str(exc), 400)
            return

        match = re.fullmatch(
            r"/api/period-projects/(\d+)/students-domain/matches/(\d+)/unlink",
            path,
        )
        if match and method in {"POST", "PUT"}:
            try:
                self._send_json(_unlink_project_case(int(match.group(1)), int(match.group(2))))
            except ValueError as exc:
                self._send_error_json(str(exc), 400)
            return

        match = re.fullmatch(
            r"/api/period-projects/(\d+)/students-domain/(\d+)/route",
            path,
        )
        if match and method in {"POST", "PUT"}:
            try:
                self._send_json(
                    _set_route_manual_final(
                        int(match.group(1)), int(match.group(2)),
                        str(payload.get("route") or ""),
                    )
                )
            except ValueError as exc:
                self._send_error_json(str(exc), 400)
            return

        match = re.fullmatch(
            r"/api/period-projects/(\d+)/students-domain/grade-conflicts/resolve",
            path,
        )
        if match and method in {"POST", "PUT"}:
            try:
                self._send_json(
                    _resolve_grade_case(
                        int(match.group(1)),
                        str(payload.get("module") or ""),
                        int(payload.get("student_id") or 0),
                        payload.get("grade"),
                        int(payload.get("nucleus_number") or 0),
                    )
                )
            except ValueError as exc:
                self._send_error_json(str(exc), 400)
            return

        assert _FINAL_BASE_WRITE is not None
        _FINAL_BASE_WRITE(self, method, path, payload)

    core.InformtitHandler._handle_api_get = final_get
    core.InformtitHandler._handle_api_write = final_write
    _FINAL_INSTALLED = True
