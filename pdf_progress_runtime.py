from __future__ import annotations

import threading
import time
import uuid
from contextlib import nullcontext
from functools import wraps
from pathlib import Path
from typing import Any, Callable

import app as core
import report_full_detail
import report_quality


_LOCK = threading.RLock()
_BUILD_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_ACTIVE_BY_REPORT: dict[int, str] = {}
_LOCAL = threading.local()


def _now() -> float:
    return time.time()


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    finished = job.get("duration_seconds")
    elapsed = float(finished) if finished is not None else max(0.0, _now() - float(job.get("created_at") or _now()))
    return {
        "id": job["id"],
        "report_id": job["report_id"],
        "status": job["status"],
        "progress": job["progress"],
        "stage": job["stage"],
        "detail": job.get("detail", ""),
        "error": job.get("error", ""),
        "download_ready": bool(job.get("path")) and job["status"] == "completed",
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "elapsed_seconds": round(elapsed, 1),
        "duration_seconds": round(float(finished), 1) if finished is not None else None,
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
            if not path.exists() or not path.is_file() or path.stat().st_size < 5:
                raise ValueError("El generador no produjo un archivo PDF válido.")
            with path.open("rb") as handle:
                if handle.read(5) != b"%PDF-":
                    raise ValueError("El archivo generado no contiene una cabecera PDF válida.")
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
        _cleanup_jobs()


def start_job(report_id: int) -> dict[str, Any]:
    _cleanup_jobs()
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
            job = start_job(int(match.group(1)))
            self._send_json({"ok": True, "job": job}, 202)
            return
        previous_write(self, method, path, payload)

    core.InformtitHandler._handle_api_get = progress_get
    core.InformtitHandler._handle_api_write = progress_write
    core.InformtitHandler._pdf_progress_runtime_installed = True
