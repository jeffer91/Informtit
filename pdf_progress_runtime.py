from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
import uuid
from contextlib import nullcontext
from copy import deepcopy
from functools import wraps
from pathlib import Path
from typing import Any, Callable

import app as core
import db
import report_full_detail
import report_quality


_LOCK = threading.RLock()
_BUILD_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_ACTIVE_BY_REPORT: dict[int, str] = {}
_PREFLIGHTS: dict[str, dict[str, Any]] = {}
_LOCAL = threading.local()

_PREFLIGHT_TTL_SECONDS = 300.0
_STALL_WARNING_SECONDS = 300.0
_GENERATOR_REVISION: str | None = None


def _cache_dir() -> Path:
    path = db.DATA_DIR / "generated_pdfs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_pdf_path(report_id: int) -> Path:
    return _cache_dir() / f"report_{int(report_id)}.pdf"


def _cache_meta_path(report_id: int) -> Path:
    return _cache_dir() / f"report_{int(report_id)}.json"


def _generator_revision() -> str:
    """Firma barata del código que puede afectar el PDF.

    Se calcula una vez por ejecución. Al actualizar Informtit, los archivos Python
    cambian y los PDF guardados dejan de considerarse vigentes automáticamente.
    """
    global _GENERATOR_REVISION
    if _GENERATOR_REVISION is not None:
        return _GENERATOR_REVISION
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    excluded = {".git", "data", "node_modules", "out", "tests", "__pycache__"}
    files = []
    for candidate in root.rglob("*.py"):
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        if any(part in excluded for part in relative.parts):
            continue
        files.append((str(relative).replace("\\", "/"), candidate))
    for relative, candidate in sorted(files, key=lambda item: item[0]):
        try:
            stat = candidate.stat()
        except OSError:
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
    _GENERATOR_REVISION = digest.hexdigest()
    return _GENERATOR_REVISION


def _valid_pdf(path: Path) -> bool:
    try:
        if not path.exists() or not path.is_file() or path.stat().st_size < 5:
            return False
        with path.open("rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False


def _read_cache_meta(report_id: int) -> dict[str, Any]:
    path = _cache_meta_path(report_id)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _saved_pdf(report_id: int) -> tuple[Path, dict[str, Any]] | None:
    pdf_path = _cache_pdf_path(report_id)
    meta = _read_cache_meta(report_id)
    if not meta or not _valid_pdf(pdf_path):
        return None
    return pdf_path, meta


def cached_pdf(report_id: int) -> tuple[Path, dict[str, Any]] | None:
    saved = _saved_pdf(report_id)
    if not saved:
        return None
    pdf_path, meta = saved
    if bool(meta.get("stale")):
        return None
    if str(meta.get("generator_revision") or "") != _generator_revision():
        return None
    return pdf_path, meta


def cache_status(report_id: int) -> dict[str, Any]:
    saved = _saved_pdf(report_id)
    if not saved:
        return {
            "available": False,
            "saved": False,
            "stale": False,
            "report_id": int(report_id),
        }
    path, meta = saved
    generator_changed = str(meta.get("generator_revision") or "") != _generator_revision()
    stale = bool(meta.get("stale")) or generator_changed
    return {
        "available": not stale,
        "saved": True,
        "stale": stale,
        "stale_reason": (
            "La aplicación cambió desde la última generación."
            if generator_changed
            else str(meta.get("stale_reason") or "")
        ),
        "report_id": int(report_id),
        "filename": str(meta.get("filename") or path.name),
        "generated_at": meta.get("generated_at"),
        "size": path.stat().st_size,
    }


def invalidate_cached_pdf(report_id: int, reason: str = "La información del informe cambió.") -> None:
    saved = _saved_pdf(report_id)
    if not saved:
        return
    _path, meta = saved
    meta["stale"] = True
    meta["stale_reason"] = str(reason or "La información del informe cambió.")
    meta["invalidated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        _cache_meta_path(report_id).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _related_report_ids(report_id: int) -> list[int]:
    ids = {int(report_id)}
    try:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT period_project_id FROM reports WHERE id=?",
                (int(report_id),),
            ).fetchone()
            project_id = int(row[0] or 0) if row else 0
            if project_id:
                for item in conn.execute(
                    "SELECT id FROM reports WHERE period_project_id=?",
                    (project_id,),
                ).fetchall():
                    ids.add(int(item[0]))
    except Exception:
        pass
    return sorted(ids)


def invalidate_report_cache(report_id: int, reason: str = "La información del informe cambió.") -> None:
    for related_id in _related_report_ids(report_id):
        invalidate_cached_pdf(related_id, reason)


def _store_cached_pdf(report_id: int, source: Path) -> Path:
    target = _cache_pdf_path(report_id)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    if not _valid_pdf(target):
        raise ValueError("No se pudo guardar una copia persistente válida del PDF.")
    meta = {
        "report_id": int(report_id),
        "filename": source.name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator_revision": _generator_revision(),
        "stale": False,
        "stale_reason": "",
    }
    _cache_meta_path(report_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def _now() -> float:
    return time.time()


def _cleanup_preflights() -> None:
    now = _now()
    with _LOCK:
        expired = [
            token
            for token, item in _PREFLIGHTS.items()
            if now - float(item.get("created_at") or 0) > _PREFLIGHT_TTL_SECONDS
        ]
        for token in expired:
            _PREFLIGHTS.pop(token, None)
        if len(_PREFLIGHTS) > 30:
            ordered = sorted(
                _PREFLIGHTS.items(),
                key=lambda pair: float(pair[1].get("created_at") or 0),
            )
            for token, _item in ordered[:-30]:
                _PREFLIGHTS.pop(token, None)


def store_preflight(report_id: int, kind: str, payload: dict[str, Any]) -> str:
    """Guarda temporalmente el preflight que el usuario acaba de revisar."""
    _cleanup_preflights()
    token = uuid.uuid4().hex
    with _LOCK:
        _PREFLIGHTS[token] = {
            "report_id": int(report_id),
            "kind": str(kind),
            "payload": deepcopy(payload),
            "created_at": _now(),
        }
    return token


def consume_preflight(report_id: int, kind: str) -> dict[str, Any] | None:
    """Consume una sola vez el preflight asociado al job PDF actual."""
    token = str(getattr(_LOCAL, "preflight_token", "") or "")
    if not token:
        return None
    _cleanup_preflights()
    with _LOCK:
        item = _PREFLIGHTS.pop(token, None)
    if not item:
        return None
    if int(item.get("report_id") or 0) != int(report_id):
        return None
    if str(item.get("kind") or "") != str(kind):
        return None
    return deepcopy(item.get("payload") or {})


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    finished = job.get("duration_seconds")
    elapsed = float(finished) if finished is not None else max(0.0, _now() - float(job.get("created_at") or _now()))
    last_progress = float(
        job.get("last_progress_at")
        or job.get("updated_at")
        or job.get("created_at")
        or _now()
    )
    without_progress = 0.0 if finished is not None else max(0.0, _now() - last_progress)
    stalled = job.get("status") == "running" and without_progress >= _STALL_WARNING_SECONDS
    return {
        "id": job["id"],
        "report_id": job["report_id"],
        "status": job["status"],
        "progress": job["progress"],
        "stage": job["stage"],
        "detail": job.get("detail", ""),
        "error": job.get("error", ""),
        "download_ready": bool(job.get("path")) and job["status"] == "completed",
        "cached": bool(job.get("cached")),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "elapsed_seconds": round(elapsed, 1),
        "duration_seconds": round(float(finished), 1) if finished is not None else None,
        "stalled": bool(stalled),
        "seconds_without_progress": round(without_progress, 1),
        "steps": [dict(item) for item in list(job.get("steps") or [])[-16:]],
    }


def _set_progress(percent: int | float, stage: str, detail: str = "") -> None:
    job_id = getattr(_LOCAL, "job_id", None)
    if not job_id:
        return
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job["progress"] = max(int(job.get("progress", 0)), min(100, int(round(percent))))
        job["stage"] = stage
        if detail:
            job["detail"] = detail
        now = _now()
        steps = job.setdefault("steps", [])
        if not steps or str(steps[-1].get("stage") or "") != str(stage):
            steps.append({
                "stage": stage,
                "progress": int(job["progress"]),
                "detail": detail or job.get("detail", ""),
                "at": now,
            })
            if len(steps) > 24:
                del steps[:-24]
        else:
            steps[-1]["progress"] = int(job["progress"])
            if detail:
                steps[-1]["detail"] = detail
            steps[-1]["at"] = now
        job["updated_at"] = now
        job["last_progress_at"] = now


def _wrap_stage(
    original: Callable[..., Any],
    before: int,
    before_stage: str,
    after: int,
    after_stage: str,
) -> Callable[..., Any]:
    @wraps(original)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        started = _now()
        _set_progress(before, before_stage)
        result = original(*args, **kwargs)
        elapsed = max(0.0, _now() - started)
        _set_progress(after, after_stage, f"Etapa completada en {elapsed:.1f} s.")
        return result

    return wrapped


def _cleanup_jobs() -> None:
    with _LOCK:
        completed = sorted(
            (
                job for job in _JOBS.values()
                if job["status"] in {"completed", "error"}
            ),
            key=lambda item: float(item.get("updated_at", 0)),
        )
        while len(_JOBS) > 25 and completed:
            old = completed.pop(0)
            _JOBS.pop(old["id"], None)
            if _ACTIVE_BY_REPORT.get(int(old["report_id"])) == old["id"]:
                _ACTIVE_BY_REPORT.pop(int(old["report_id"]), None)


def _run_job(job_id: str, report_id: int) -> None:
    _LOCAL.job_id = job_id
    with _LOCK:
        job_info = dict(_JOBS.get(job_id) or {})
    _LOCAL.preflight_token = str(job_info.get("preflight_token") or "")
    try:
        _set_progress(
            2,
            "Esperando turno de generación",
            "Informtit genera un PDF a la vez para evitar colisiones entre Presencial y Online.",
        )
        with _BUILD_LOCK:
            # La validación completa ya forma parte de core.build_pdf. Antes se
            # ejecutaba también aquí y luego otra vez dentro del generador, lo que
            # repetía consultas y cálculos costosos sin aportar seguridad adicional.
            _set_progress(
                5,
                "Preparando datos del informe",
                "Usando la conciliación ya guardada y preparando las secciones del documento.",
            )
            snapshot = nullcontext()
            try:
                import student_report_integration as report_integration
                snapshot = report_integration.report_read_snapshot()
            except (ImportError, AttributeError):
                pass
            with snapshot:
                output = core.build_pdf(report_id)
            _set_progress(96, "Verificando archivo generado", "Comprobando integridad y tamaño del PDF.")
            path = Path(output)
            if not _valid_pdf(path):
                raise ValueError("El generador no produjo un archivo PDF válido.")
            _set_progress(98, "Guardando PDF generado", "Conservando una copia para futuras descargas sin regenerar el informe.")
            path = _store_cached_pdf(report_id, path)
            _set_progress(99, "Preparando descarga", "El PDF está listo; preparando la descarga automática.")

        _set_progress(100, "PDF listo", "El informe fue generado correctamente y está listo para descargar.")
        with _LOCK:
            job = _JOBS[job_id]
            duration = max(0.0, _now() - float(job.get("created_at") or _now()))
            job.update(
                status="completed",
                progress=100,
                stage="PDF listo",
                detail="El informe fue generado correctamente y está listo para descargar.",
                path=str(path),
                cached=False,
                error="",
                duration_seconds=duration,
                updated_at=_now(),
            )
    except Exception as exc:
        with _LOCK:
            job = _JOBS.get(job_id)
            if job:
                duration = max(0.0, _now() - float(job.get("created_at") or _now()))
                job.update(
                    status="error",
                    stage="No se pudo generar el PDF",
                    detail="La generación se detuvo en la etapa indicada. Revise el detalle y vuelva a intentarlo.",
                    error=str(exc),
                    duration_seconds=duration,
                    updated_at=_now(),
                )
    finally:
        with _LOCK:
            if _ACTIVE_BY_REPORT.get(report_id) == job_id:
                _ACTIVE_BY_REPORT.pop(report_id, None)
        _LOCAL.job_id = None
        _LOCAL.preflight_token = ""
        _cleanup_jobs()
        _cleanup_preflights()


def start_job(report_id: int, preflight_token: str = "") -> dict[str, Any]:
    _cleanup_jobs()
    _cleanup_preflights()

    saved = cached_pdf(report_id)
    if saved:
        path, _meta = saved
        job_id = uuid.uuid4().hex
        now = _now()
        job = {
            "id": job_id,
            "report_id": int(report_id),
            "status": "completed",
            "progress": 100,
            "stage": "PDF guardado",
            "detail": "Se reutilizó el último PDF porque la información del sistema no ha cambiado.",
            "error": "",
            "path": str(path),
            "cached": True,
            "preflight_token": "",
            "last_progress_at": now,
            "steps": [{
                "stage": "PDF guardado",
                "progress": 100,
                "detail": "Se reutilizó el último PDF porque la información del sistema no ha cambiado.",
                "at": now,
            }],
            "duration_seconds": 0.0,
            "created_at": now,
            "updated_at": now,
        }
        with _LOCK:
            _JOBS[job_id] = job
        return _public_job(job)
    with _LOCK:
        active_id = _ACTIVE_BY_REPORT.get(report_id)
        if active_id:
            active = _JOBS.get(active_id)
            if active and active["status"] in {"queued", "running"}:
                return _public_job(active)

        job_id = uuid.uuid4().hex
        now = _now()
        job = {
            "id": job_id,
            "report_id": report_id,
            "status": "queued",
            "progress": 1,
            "stage": "Preparando generación",
            "detail": "Se está preparando el proceso de exportación.",
            "error": "",
            "path": "",
            "cached": False,
            "preflight_token": str(preflight_token or ""),
            "last_progress_at": now,
            "steps": [{
                "stage": "Preparando generación",
                "progress": 1,
                "detail": "Se está preparando el proceso de exportación.",
                "at": now,
            }],
            "created_at": now,
            "updated_at": now,
        }
        _JOBS[job_id] = job
        _ACTIVE_BY_REPORT[report_id] = job_id

    thread = threading.Thread(target=_run_job, args=(job_id, report_id), daemon=True, name=f"pdf-{job_id[:8]}")
    with _LOCK:
        _JOBS[job_id]["status"] = "running"
        _JOBS[job_id]["updated_at"] = _now()
    thread.start()
    return _public_job(job)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return _public_job(job) if job else None


def get_job_path(job_id: str) -> Path | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job.get("status") != "completed" or not job.get("path"):
            return None
        path = Path(str(job["path"]))
    return path if path.exists() else None


def install_cache_invalidation() -> None:
    """Instala al final del backend la invalidación persistente por escrituras.

    A diferencia de usar la fecha del archivo SQLite, esto no invalida los PDF por
    mantenimiento interno o por reiniciar Informtit. Solo una operación de escritura
    solicitada por la aplicación marca como desactualizado el PDF relacionado.
    """
    if getattr(core.InformtitHandler, "_pdf_cache_invalidation_installed", False):
        return

    previous_write = core.InformtitHandler._handle_api_write

    def cache_aware_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        import re

        report_match = re.match(r"/api/reports/(\d+)(?:/|$)", path)
        if report_match and method in {"POST", "PUT", "PATCH", "DELETE"}:
            invalidate_report_cache(
                int(report_match.group(1)),
                "Los datos del informe cambiaron; se requiere una nueva generación.",
            )
        previous_write(self, method, path, payload)

    core.InformtitHandler._handle_api_write = cache_aware_write
    core.InformtitHandler._pdf_cache_invalidation_installed = True


def install() -> None:
    if getattr(core.InformtitHandler, "_pdf_progress_runtime_installed", False):
        return

    # Estas etapas corresponden a bloques reales del generador. El porcentaje
    # expresa avance por fase, no una estimación basada únicamente en tiempo.
    report_quality._pdf_methodology = _wrap_stage(
        report_quality._pdf_methodology,
        10,
        "Preparando contenido académico",
        18,
        "Metodología y contenido académico listos",
    )
    report_quality._pdf_requirements = _wrap_stage(
        report_quality._pdf_requirements,
        20,
        "Procesando requisitos",
        27,
        "Resultados de requisitos listos",
    )
    report_quality._pdf_schedules = _wrap_stage(
        report_quality._pdf_schedules,
        28,
        "Procesando cronogramas",
        33,
        "Cronogramas listos",
    )
    report_quality._pdf_nucleus_results = _wrap_stage(
        report_quality._pdf_nucleus_results,
        34,
        "Generando resultados de Núcleos",
        58,
        "Resultados de Núcleos listos",
    )
    report_quality._pdf_complexive = _wrap_stage(
        report_quality._pdf_complexive,
        60,
        "Generando Examen Complexivo",
        76,
        "Examen Complexivo listo",
    )
    report_quality._pdf_projects = _wrap_stage(
        report_quality._pdf_projects,
        78,
        "Generando Trabajo de Titulación",
        85,
        "Trabajo de Titulación listo",
    )
    report_quality._pdf_post_sections = _wrap_stage(
        report_quality._pdf_post_sections,
        86,
        "Generando análisis final",
        92,
        "Maquetando el PDF final",
    )

    previous_get = core.InformtitHandler._handle_api_get
    previous_write = core.InformtitHandler._handle_api_write

    def progress_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        import re

        direct = re.fullmatch(r"/api/reports/(\d+)/export/pdf", path)
        if direct:
            self._send_error_json(
                "La exportación PDF directa está deshabilitada por seguridad. Use el botón PDF para iniciar un proceso controlado.",
                409,
            )
            return

        cache_match = re.fullmatch(r"/api/reports/(\d+)/pdf-cache", path)
        if cache_match:
            self._send_json({"ok": True, "cache": cache_status(int(cache_match.group(1)))})
            return

        cache_download = re.fullmatch(r"/api/reports/(\d+)/pdf-cache/download", path)
        if cache_download:
            report_id = int(cache_download.group(1))
            saved = cached_pdf(report_id)
            if not saved:
                self._send_error_json("No existe un PDF guardado vigente para este informe.", 409)
                return
            pdf_path, meta = saved
            self._serve_file(pdf_path, str(meta.get("filename") or pdf_path.name))
            return

        match = re.fullmatch(r"/api/pdf-jobs/([a-f0-9]{32})", path)
        if match:
            job = get_job(match.group(1))
            if not job:
                self._send_error_json("Proceso de PDF no encontrado.", 404)
                return
            self._send_json({"ok": True, "job": job})
            return

        match = re.fullmatch(r"/api/pdf-jobs/([a-f0-9]{32})/download", path)
        if match:
            pdf_path = get_job_path(match.group(1))
            if not pdf_path:
                self._send_error_json("El PDF todavía no está disponible.", 409)
                return
            self._serve_file(pdf_path, pdf_path.name)
            return

        previous_get(self, path, query)

    def progress_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        import re

        match = re.fullmatch(r"/api/reports/(\d+)/pdf-jobs", path)
        if method == "POST" and match:
            job = start_job(
                int(match.group(1)),
                str(payload.get("preflight_token") or ""),
            )
            self._send_json({"ok": True, "job": job}, 202)
            return
        previous_write(self, method, path, payload)

    core.InformtitHandler._handle_api_get = progress_get
    core.InformtitHandler._handle_api_write = progress_write
    core.InformtitHandler._pdf_progress_runtime_installed = True
