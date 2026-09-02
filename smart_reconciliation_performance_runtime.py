from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from typing import Any, Callable

import smart_reconciliation_runtime as smart
import student_domain_bridge as bridge
import student_domain_service as domain
import student_final_audit as audit
from db import connection, utcnow


_INSTALLED = False
_LOCAL = threading.local()

_BASE_RUN_JOB: Callable[..., Any] | None = None
_BASE_SET_JOB: Callable[..., Any] | None = None
_BASE_MATCH: Callable[..., Any] | None = None
_BASE_SAVE_SOURCE_LINK: Callable[..., Any] | None = None
_BASE_MANUAL_REVIEW: Callable[..., Any] | None = None
_BASE_MANUAL_MATCH: Callable[..., Any] | None = None
_BASE_MANUAL_RECOVERY: Callable[..., Any] | None = None
_BASE_LEGACY_MANUAL: Callable[..., Any] | None = None


def _active_job() -> bool:
    return bool(getattr(_LOCAL, "active", False))


def _thread_cache(name: str) -> dict[Any, Any]:
    cache = getattr(_LOCAL, name, None)
    if cache is None:
        cache = {}
        setattr(_LOCAL, name, cache)
    return cache


def _fast_master_index(report_id: int) -> dict[str, Any]:
    """Construye el índice una sola vez por caché maestra de conciliación.

    La implementación anterior usaba ``id(masters)`` después de crear una lista
    nueva en cada registro. Eso hacía imposible acertar el caché y reconstruía
    cientos de nombres por cada fila de Núcleos.
    """
    cached_students = audit._MATCH_CACHE.get()
    if cached_students is not None:
        masters = cached_students
        cache_key: Any = (report_id, id(cached_students))
    else:
        masters = [
            row
            for row in audit._matching_students(report_id)
            if int(row.get("requirements_present", 1) or 0) == 1
        ]
        cache_key = (
            report_id,
            tuple(
                (int(row.get("id") or 0), str(row.get("updated_at") or ""))
                for row in masters
            ),
        )

    cache = getattr(smart._INDEX_LOCAL, "value", None)
    if cache and cache.get("key") == cache_key:
        return cache["index"]

    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_email: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_tokens: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    prepared: list[dict[str, Any]] = []

    for master in masters:
        item = dict(master)
        item["_fold_name"] = smart._fold(item.get("full_name"))
        item["_tokens"] = smart._token_signature(item.get("full_name"))
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
    smart._INDEX_LOCAL.value = {"key": cache_key, "index": index}
    return index


def _has_manual_rows(report_id: int, source_module: str, method: str) -> bool:
    if not _active_job():
        return True
    cache = _thread_cache("manual_presence")
    key = (report_id, source_module, method)
    if key in cache:
        return bool(cache[key])
    with connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='student_source_links'"
        ).fetchone()
        found = bool(
            exists
            and conn.execute(
                """
                SELECT 1 FROM student_source_links
                WHERE report_id=? AND source_module=? AND match_method=?
                LIMIT 1
                """,
                (report_id, source_module, method),
            ).fetchone()
        )
    cache[key] = found
    return found


def _has_legacy_manual_rows(report_id: int) -> bool:
    if not _active_job():
        return True
    cache = _thread_cache("legacy_presence")
    if report_id in cache:
        return bool(cache[report_id])
    with connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_manual_matches'"
        ).fetchone()
        found = bool(
            exists
            and conn.execute(
                "SELECT 1 FROM nucleus_manual_matches WHERE report_id=? LIMIT 1",
                (report_id,),
            ).fetchone()
        )
    cache[report_id] = found
    return found


def _cached_manual_review(
    report_id: int,
    source_module: str,
    source_key: str,
    source: dict[str, Any],
) -> dict[str, Any] | None:
    assert _BASE_MANUAL_REVIEW is not None
    if _active_job() and not _has_manual_rows(report_id, source_module, "MANUAL_REVIEW"):
        return None
    return _BASE_MANUAL_REVIEW(report_id, source_module, source_key, source)


def _cached_manual_match(
    report_id: int,
    source_module: str,
    source_key: str,
) -> dict[str, Any] | None:
    assert _BASE_MANUAL_MATCH is not None
    if _active_job() and not _has_manual_rows(report_id, source_module, "MANUAL"):
        return None
    return _BASE_MANUAL_MATCH(report_id, source_module, source_key)


def _cached_manual_recovery(
    report_id: int,
    source_module: str,
    source: dict[str, Any],
) -> dict[str, Any] | None:
    assert _BASE_MANUAL_RECOVERY is not None
    if _active_job() and not _has_manual_rows(report_id, source_module, "MANUAL"):
        return None
    return _BASE_MANUAL_RECOVERY(report_id, source_module, source)


def _cached_legacy_manual(
    report_id: int,
    source: dict[str, Any],
) -> dict[str, Any] | None:
    assert _BASE_LEGACY_MANUAL is not None
    if _active_job() and not _has_legacy_manual_rows(report_id):
        return None
    return _BASE_LEGACY_MANUAL(report_id, source)


def _fast_save_source_link(
    report_id: int,
    source_module: str,
    source_key: str,
    source: dict[str, Any],
    match: dict[str, Any],
) -> None:
    """Persiste un match en una sola transacción durante la conciliación masiva.

    El camino normal ejecuta comprobaciones de esquema y dos capas de guardado,
    algo correcto para operaciones aisladas pero muy costoso para 1.000+ filas.
    El esquema ya fue validado al iniciar Informtit, por lo que el job masivo puede
    hacer el mismo UPSERT y activar la fuente en una única escritura.
    """
    assert _BASE_SAVE_SOURCE_LINK is not None
    if not _active_job():
        _BASE_SAVE_SOURCE_LINK(report_id, source_module, source_key, source, match)
        return

    now = utcnow()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO student_source_links
            (report_id, period_student_id, source_module, source_key, source_name,
             source_email, source_identification, source_career, match_status,
             match_method, match_confidence, candidates_json, detail,
             source_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(report_id, source_module, source_key) DO UPDATE SET
                period_student_id=excluded.period_student_id,
                source_name=excluded.source_name,
                source_email=excluded.source_email,
                source_identification=excluded.source_identification,
                source_career=excluded.source_career,
                match_status=excluded.match_status,
                match_method=excluded.match_method,
                match_confidence=excluded.match_confidence,
                candidates_json=excluded.candidates_json,
                detail=excluded.detail,
                source_active=1,
                updated_at=excluded.updated_at
            """,
            (
                report_id,
                match.get("period_student_id"),
                source_module,
                source_key,
                source.get("full_name") or "",
                bridge._source_email(source.get("email")),
                bridge._source_identification(source.get("identification")),
                source.get("career_name") or "",
                match.get("status") or domain.MATCH_UNMATCHED,
                match.get("method") or "",
                match.get("confidence"),
                json.dumps(match.get("candidates") or [], ensure_ascii=False),
                match.get("detail") or "",
                now,
                now,
            ),
        )


def _job_snapshot(job_id: str) -> dict[str, Any] | None:
    with smart._JOB_LOCK:
        job = smart._JOBS.get(job_id)
        return dict(job) if job else None


def _start_module_tracking(job_id: str, stage: str, detail: str) -> None:
    match = re.search(r"Analizando\s+(\d+)\s+registros", detail or "", re.IGNORECASE)
    if not match:
        return
    total = int(match.group(1))
    snapshot = _job_snapshot(job_id)
    if not snapshot:
        return
    project_id = int(snapshot.get("period_project_id") or 0)
    try:
        members = smart.fast_read._member_reports(project_id)
        total_steps = len(members) * 4 + 1
    except Exception:
        total_steps = 9
    span = 90.0 / max(1, total_steps)
    module_label = stage.split(" · ", 1)[1] if " · " in stage else stage
    _LOCAL.progress = {
        "job_id": job_id,
        "module": module_label,
        "total": total,
        "processed": 0,
        "start_progress": int(snapshot.get("progress") or 0),
        "span": span,
        "last_reported": 0,
        "base_stats": dict(snapshot.get("stats") or {}),
        "auto": 0,
        "cases": 0,
        "outside": 0,
        "route": 0,
    }


def _tracked_set_job(job_id: str, **kwargs: Any) -> None:
    assert _BASE_SET_JOB is not None
    _BASE_SET_JOB(job_id, **kwargs)
    if not _active_job():
        return
    stage = str(kwargs.get("stage") or "")
    detail = str(kwargs.get("detail") or "")
    if stage and " · " in stage and detail.lower().startswith("analizando "):
        _start_module_tracking(job_id, stage, detail)
    elif stage and (
        "preparando estudiantes" in stage.lower()
        or stage.lower().startswith("agrupando casos")
        or stage.lower().startswith("conciliación completada")
    ):
        _LOCAL.progress = None


def _advance_progress(result: dict[str, Any]) -> None:
    progress = getattr(_LOCAL, "progress", None)
    if not progress:
        return
    total = int(progress.get("total") or 0)
    if total <= 0:
        return
    progress["processed"] = min(total, int(progress.get("processed") or 0) + 1)
    processed = int(progress["processed"])

    status = str(result.get("status") or domain.MATCH_UNMATCHED)
    method = str(result.get("method") or "")
    if status == domain.MATCH_OK and method not in {"MANUAL", "MANUAL_REVIEW"}:
        progress["auto"] = int(progress.get("auto") or 0) + 1
    elif status != domain.MATCH_OK:
        progress["cases"] = int(progress.get("cases") or 0) + 1
    if status == smart.MATCH_OUTSIDE_POPULATION:
        progress["outside"] = int(progress.get("outside") or 0) + 1
    if status == domain.MATCH_ROUTE_CONFLICT:
        progress["route"] = int(progress.get("route") or 0) + 1

    # Aproximadamente 50 actualizaciones visuales como máximo por módulo. Así la
    # barra es fluida sin convertir el progreso en otra fuente de lentitud.
    batch = max(1, total // 50)
    if processed != total and processed - int(progress.get("last_reported") or 0) < batch:
        return
    progress["last_reported"] = processed

    fraction = processed / total
    visible_progress = int(
        round(float(progress.get("start_progress") or 0) + float(progress.get("span") or 1.0) * fraction)
    )
    base_stats = dict(progress.get("base_stats") or {})
    base_stats["auto_resolved"] = int(base_stats.get("auto_resolved") or 0) + int(progress.get("auto") or 0)
    base_stats["cases"] = int(base_stats.get("cases") or 0) + int(progress.get("cases") or 0)
    base_stats["outside_population"] = int(base_stats.get("outside_population") or 0) + int(progress.get("outside") or 0)
    base_stats["route_conflicts"] = int(base_stats.get("route_conflicts") or 0) + int(progress.get("route") or 0)

    smart._set_job(
        str(progress["job_id"]),
        progress=min(94, visible_progress),
        detail=f"{progress.get('module')}: {processed} de {total} registros analizados.",
        stats=base_stats,
    )


def _tracked_match(
    report_id: int,
    source_module: str,
    source_key: str,
    source: dict[str, Any],
    **context: Any,
) -> dict[str, Any]:
    assert _BASE_MATCH is not None
    result = _BASE_MATCH(report_id, source_module, source_key, source, **context)
    if _active_job():
        _advance_progress(result)
    return result


def _run_job(job_id: str, period_project_id: int) -> None:
    assert _BASE_RUN_JOB is not None
    _LOCAL.active = True
    _LOCAL.job_id = job_id
    _LOCAL.manual_presence = {}
    _LOCAL.legacy_presence = {}
    _LOCAL.progress = None
    smart._INDEX_LOCAL.value = None
    try:
        _BASE_RUN_JOB(job_id, period_project_id)
    finally:
        smart._INDEX_LOCAL.value = None
        for name in ("active", "job_id", "manual_presence", "legacy_presence", "progress"):
            if hasattr(_LOCAL, name):
                delattr(_LOCAL, name)


def install() -> None:
    """Hotfix final para conciliaciones masivas de cientos o miles de evidencias."""
    global _INSTALLED, _BASE_RUN_JOB, _BASE_SET_JOB, _BASE_MATCH
    global _BASE_SAVE_SOURCE_LINK, _BASE_MANUAL_REVIEW, _BASE_MANUAL_MATCH
    global _BASE_MANUAL_RECOVERY, _BASE_LEGACY_MANUAL
    if _INSTALLED:
        return

    _BASE_RUN_JOB = smart._run_reconciliation_job
    _BASE_SET_JOB = smart._set_job
    _BASE_MATCH = bridge._match
    _BASE_SAVE_SOURCE_LINK = bridge.save_source_link
    _BASE_MANUAL_REVIEW = audit._manual_review_decision
    _BASE_MANUAL_MATCH = bridge._manual_match
    _BASE_MANUAL_RECOVERY = bridge._manual_match_by_identity
    _BASE_LEGACY_MANUAL = bridge._legacy_nucleus_manual_match

    # Corrige el caché roto del índice maestro.
    smart._master_index = _fast_master_index

    # Evita miles de SELECT redundantes cuando no existen decisiones manuales.
    audit._manual_review_decision = _cached_manual_review
    bridge._manual_match = _cached_manual_match
    bridge._manual_match_by_identity = _cached_manual_recovery
    bridge._legacy_nucleus_manual_match = _cached_legacy_manual

    # Durante el job masivo cada evidencia se guarda con un único UPSERT.
    bridge.save_source_link = _fast_save_source_link

    # El matcher reporta avance real dentro de Núcleos/Complexivo/Trabajo.
    bridge._match = _tracked_match
    smart._set_job = _tracked_set_job
    smart._run_reconciliation_job = _run_job

    _INSTALLED = True
