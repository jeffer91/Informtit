from __future__ import annotations

import re
import threading
import time
import uuid
from typing import Any, Callable

import app as core
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
        members = fast_read._member_reports(period_project_id)
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
    members = fast_read._member_reports(period_project_id)
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
    global _INSTALLED, _BASE_GET, _BASE_WRITE
    if _INSTALLED:
        return

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
    _INSTALLED = True
