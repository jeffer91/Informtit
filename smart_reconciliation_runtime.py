from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any, Callable

import app as core
import read_performance_runtime as fast_read
import sqlite_concurrency_runtime as sqlite_guard
import student_domain_bridge as bridge
import student_domain_service as domain
import student_final_audit as audit
from db import connection, rows_to_dicts, utcnow
from parser import canonical_name_key, clean_moodle_name


MATCH_OUTSIDE_POPULATION = "OUT_OF_POPULATION"

_INSTALLED = False
_BASE_MATCH: Callable[..., dict[str, Any]] | None = None
_BASE_OPEN_LINKS: Callable[[list[int]], list[dict[str, Any]]] | None = None
_BASE_FAST_AUDIT: Callable[[int | None], dict[str, Any] | None] | None = None
_BASE_PERIOD_READ: Callable[[int], dict[str, Any]] | None = None
_BASE_GET: Callable[..., Any] | None = None
_BASE_WRITE: Callable[..., Any] | None = None

_JOB_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}
_ACTIVE_BY_PROJECT: dict[int, str] = {}
_INDEX_LOCAL = threading.local()


def _fold(value: Any) -> str:
    return canonical_name_key(clean_moodle_name(str(value or "")))


def _email(value: Any) -> str:
    return bridge._source_email(value)


def _identification(value: Any) -> str:
    return bridge._source_identification(value)


def _token_signature(value: Any) -> tuple[str, ...]:
    return tuple(sorted(token for token in _fold(value).split() if token))


def _career(value: Any) -> str:
    return bridge.normalize(value)


def _candidate_payload(student: dict[str, Any], similarity: float) -> dict[str, Any]:
    return {
        "student_id": int(student["id"]),
        "identification": audit._public_identification(student.get("identification")),
        "full_name": student.get("full_name") or "",
        "email": student.get("email") or "",
        "career_name": student.get("career_name") or "",
        "similarity": round(similarity * 100, 1),
    }


def _master_index(report_id: int) -> dict[str, Any]:
    masters = [
        row
        for row in audit._matching_students(report_id)
        if int(row.get("requirements_present", 1) or 0) == 1
    ]
    cache = getattr(_INDEX_LOCAL, "value", None)
    cache_key = (report_id, id(masters))
    if cache and cache.get("key") == cache_key:
        return cache["index"]

    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_email: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_tokens: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    prepared: list[dict[str, Any]] = []
    for master in masters:
        item = dict(master)
        item["_fold_name"] = _fold(item.get("full_name"))
        item["_tokens"] = _token_signature(item.get("full_name"))
        item["_career"] = _career(item.get("career_name"))
        prepared.append(item)
        sid = _identification(item.get("identification"))
        semail = _email(item.get("email"))
        if sid:
            by_id[sid].append(item)
        if semail:
            by_email[semail].append(item)
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
    _INDEX_LOCAL.value = {"key": cache_key, "index": index}
    return index


def _name_similarity(source_name: str, student: dict[str, Any]) -> float:
    target_name = str(student.get("_fold_name") or _fold(student.get("full_name")))
    if not source_name or not target_name:
        return 0.0
    direct = SequenceMatcher(None, source_name, target_name).ratio()
    source_tokens = " ".join(sorted(source_name.split()))
    target_tokens = " ".join(sorted(target_name.split()))
    reordered = SequenceMatcher(None, source_tokens, target_tokens).ratio()
    return max(direct, reordered)


def _rank_candidates(source: dict[str, Any], masters: list[dict[str, Any]]) -> list[tuple[float, dict[str, Any]]]:
    source_name = _fold(source.get("full_name"))
    source_career = _career(source.get("career_name"))
    ranked: list[tuple[float, dict[str, Any]]] = []
    for master in masters:
        score = _name_similarity(source_name, master)
        if source_career and master.get("_career") == source_career:
            score = min(1.0, score + 0.015)
        ranked.append((score, master))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("full_name") or "")))
    return ranked


def _persist_match(
    report_id: int,
    source_module: str,
    source_key: str,
    source: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    bridge.save_source_link(report_id, source_module, source_key, source, result)
    return result


def _ambiguous_result(matches: list[dict[str, Any]], detail: str) -> dict[str, Any]:
    return {
        "status": domain.MATCH_AMBIGUOUS,
        "method": "IDENTIDAD_AMBIGUA",
        "confidence": 100.0,
        "period_student_id": None,
        "candidates": [_candidate_payload(item, 1.0) for item in matches[:8]],
        "detail": detail,
    }


def _identity_conflict_result(matches: list[dict[str, Any]], detail: str) -> dict[str, Any]:
    return {
        "status": audit.MATCH_IDENTITY_CONFLICT,
        "method": "IDENTIDAD_CONFLICTIVA",
        "confidence": 100.0,
        "period_student_id": None,
        "candidates": [_candidate_payload(item, 1.0) for item in matches[:8]],
        "detail": detail,
    }


def _smart_match(report_id: int, source_module: str, source_key: str, source: dict[str, Any]) -> dict[str, Any]:
    """Resuelve identidad fuerte primero y usa similitud solo como apoyo.

    La carrera valida contexto, pero nunca reduce una coincidencia exacta de identidad.
    Los correos técnicos @excel.local se consideran ausencia de correo.
    """
    manual_review = audit._manual_review_decision(report_id, source_module, source_key, source)
    if manual_review:
        return manual_review

    manual = bridge._manual_match(report_id, source_module, source_key)
    if manual:
        return manual

    recovered = bridge._manual_match_by_identity(report_id, source_module, source)
    if recovered:
        return _persist_match(report_id, source_module, source_key, source, recovered)

    if source_module == "NUCLEI":
        legacy = bridge._legacy_nucleus_manual_match(report_id, source)
        if legacy:
            return _persist_match(report_id, source_module, source_key, source, legacy)

    index = _master_index(report_id)
    masters: list[dict[str, Any]] = index["masters"]
    source_id = _identification(source.get("identification"))
    source_email = _email(source.get("email"))
    source_name = _fold(source.get("full_name"))
    source_tokens = _token_signature(source.get("full_name"))
    source_career = _career(source.get("career_name"))

    if not masters:
        return _persist_match(
            report_id,
            source_module,
            source_key,
            source,
            {
                "status": MATCH_OUTSIDE_POPULATION,
                "method": "SIN_POBLACION",
                "confidence": 0.0,
                "period_student_id": None,
                "candidates": [],
                "detail": "No existe población maestra de Requisitos para comparar este registro.",
            },
        )

    id_matches = list(index["by_id"].get(source_id, [])) if source_id else []
    email_matches = list(index["by_email"].get(source_email, [])) if source_email else []
    name_matches = list(index["by_name"].get(source_name, [])) if source_name else []
    token_matches = list(index["by_tokens"].get(source_tokens, [])) if source_tokens else []

    if len(id_matches) > 1:
        return _persist_match(
            report_id,
            source_module,
            source_key,
            source,
            _ambiguous_result(id_matches, "La misma cédula apunta a más de un estudiante maestro. Revise Requisitos."),
        )

    if len(id_matches) == 1:
        target = id_matches[0]
        detail = "Coincidencia exacta por cédula."
        if source_name and _name_similarity(source_name, target) < 0.75:
            detail += " El nombre de la fuente difiere del nombre oficial y debe revisarse como dato de origen."
        return _persist_match(
            report_id,
            source_module,
            source_key,
            source,
            {
                "status": domain.MATCH_OK,
                "method": "CEDULA",
                "confidence": 100.0,
                "period_student_id": int(target["id"]),
                "candidates": [_candidate_payload(target, 1.0)],
                "detail": detail,
            },
        )

    # Si la fuente trae una cédula explícita que no existe, no se fuerza un vínculo
    # por nombre/correo: se muestra el posible conflicto para decisión humana.
    if source_id:
        strong = email_matches if len(email_matches) == 1 else name_matches if len(name_matches) == 1 else []
        if strong:
            return _persist_match(
                report_id,
                source_module,
                source_key,
                source,
                _identity_conflict_result(
                    strong,
                    f"La cédula {source_id} de la fuente no existe en Requisitos, pero otros datos apuntan a un estudiante. Revise antes de asociar.",
                ),
            )
        return _persist_match(
            report_id,
            source_module,
            source_key,
            source,
            {
                "status": MATCH_OUTSIDE_POPULATION,
                "method": "CEDULA_FUERA_POBLACION",
                "confidence": 0.0,
                "period_student_id": None,
                "candidates": [],
                "detail": f"La cédula {source_id} no aparece en la población actual de Requisitos.",
            },
        )

    if len(email_matches) > 1:
        return _persist_match(
            report_id,
            source_module,
            source_key,
            source,
            _ambiguous_result(email_matches, "El mismo correo coincide con más de un estudiante maestro."),
        )

    if len(email_matches) == 1:
        target = email_matches[0]
        if len(name_matches) == 1 and int(name_matches[0]["id"]) != int(target["id"]):
            return _persist_match(
                report_id,
                source_module,
                source_key,
                source,
                _identity_conflict_result(
                    [target, name_matches[0]],
                    "El correo y el nombre exacto apuntan a estudiantes diferentes. Se requiere revisión manual.",
                ),
            )
        return _persist_match(
            report_id,
            source_module,
            source_key,
            source,
            {
                "status": domain.MATCH_OK,
                "method": "CORREO",
                "confidence": 99.5,
                "period_student_id": int(target["id"]),
                "candidates": [_candidate_payload(target, 0.995)],
                "detail": "Coincidencia exacta por correo institucional.",
            },
        )

    if len(name_matches) == 1:
        target = name_matches[0]
        context_detail = "Coincidencia exacta por nombre completo único en el período."
        if source_career and target.get("_career") and source_career != target.get("_career"):
            context_detail += " La carrera de la fuente difiere de Requisitos; se conserva la identidad y solo se registra la diferencia de contexto."
        return _persist_match(
            report_id,
            source_module,
            source_key,
            source,
            {
                "status": domain.MATCH_OK,
                "method": "NOMBRE_EXACTO",
                "confidence": 99.0,
                "period_student_id": int(target["id"]),
                "candidates": [_candidate_payload(target, 1.0)],
                "detail": context_detail,
            },
        )

    if len(name_matches) > 1:
        same_career = [item for item in name_matches if source_career and item.get("_career") == source_career]
        if len(same_career) == 1:
            target = same_career[0]
            return _persist_match(
                report_id,
                source_module,
                source_key,
                source,
                {
                    "status": domain.MATCH_OK,
                    "method": "NOMBRE_EXACTO_CONTEXTO",
                    "confidence": 98.5,
                    "period_student_id": int(target["id"]),
                    "candidates": [_candidate_payload(target, 1.0)],
                    "detail": "Nombre exacto repetido, resuelto de forma única por la carrera del registro.",
                },
            )
        return _persist_match(
            report_id,
            source_module,
            source_key,
            source,
            _ambiguous_result(name_matches, "Existen homónimos con el mismo nombre completo. Se requiere una identificación adicional."),
        )

    if len(token_matches) == 1 and len(source_tokens) >= 3:
        target = token_matches[0]
        return _persist_match(
            report_id,
            source_module,
            source_key,
            source,
            {
                "status": domain.MATCH_OK,
                "method": "NOMBRE_REORDENADO",
                "confidence": 97.5,
                "period_student_id": int(target["id"]),
                "candidates": [_candidate_payload(target, 0.975)],
                "detail": "Los mismos componentes del nombre aparecen en distinto orden.",
            },
        )

    ranked = _rank_candidates(source, masters)
    top_score, top_student = ranked[0] if ranked else (0.0, None)
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    gap = top_score - second_score
    candidates = [
        _candidate_payload(student, score)
        for score, student in ranked[:8]
        if score >= 0.68
    ]

    if top_student and top_score >= 0.965 and gap >= 0.06:
        result = {
            "status": domain.MATCH_OK,
            "method": "NOMBRE_ALTA_CONFIANZA",
            "confidence": round(top_score * 100, 1),
            "period_student_id": int(top_student["id"]),
            "candidates": candidates[:5],
            "detail": "Coincidencia de nombre de muy alta confianza y sin candidato cercano.",
        }
    elif top_score >= 0.90 and gap >= 0.05:
        result = {
            "status": domain.MATCH_REVIEW,
            "method": "NOMBRE_POSIBLE",
            "confidence": round(top_score * 100, 1),
            "period_student_id": None,
            "candidates": candidates[:5],
            "detail": "Existe una coincidencia probable, pero no es suficientemente fuerte para asociarla automáticamente.",
        }
    elif top_score >= 0.78 and gap < 0.04:
        result = {
            "status": domain.MATCH_AMBIGUOUS,
            "method": "NOMBRE_AMBIGUO",
            "confidence": round(top_score * 100, 1),
            "period_student_id": None,
            "candidates": candidates[:5],
            "detail": "Hay varios candidatos con similitud comparable. Se requiere decisión humana.",
        }
    elif top_score >= 0.72:
        result = {
            "status": domain.MATCH_REVIEW,
            "method": "NOMBRE_POSIBLE",
            "confidence": round(top_score * 100, 1),
            "period_student_id": None,
            "candidates": candidates[:5],
            "detail": "La similitud es insuficiente para una asociación automática. Revise los candidatos sugeridos.",
        }
    else:
        result = {
            "status": MATCH_OUTSIDE_POPULATION,
            "method": "FUERA_POBLACION",
            "confidence": round(top_score * 100, 1) if top_score else 0.0,
            "period_student_id": None,
            "candidates": [],
            "detail": "No se encontró un estudiante compatible en la población actual de Requisitos. Verifique período, modalidad o carga de origen.",
        }
    return _persist_match(report_id, source_module, source_key, source, result)


def _group_identity(row: dict[str, Any]) -> str:
    sid = _identification(row.get("source_identification"))
    if sid:
        return f"id:{sid}"
    email = _email(row.get("source_email"))
    if email:
        return f"email:{email}"
    name = _fold(row.get("source_name"))
    if name:
        return f"name:{name}"
    return f"link:{int(row.get('id') or 0)}"


def _group_open_links(report_ids: list[int]) -> list[dict[str, Any]]:
    if _BASE_OPEN_LINKS is None:
        return []
    raw = _BASE_OPEN_LINKS(report_ids)
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in raw:
        status = str(row.get("match_status") or domain.MATCH_UNMATCHED)
        if status == domain.MATCH_OK:
            continue
        key = (
            int(row.get("report_id") or 0),
            str(row.get("source_module") or ""),
            status,
            _group_identity(row),
        )
        grouped[key].append(row)

    priority = {
        audit.MATCH_DUPLICATE: 120,
        audit.MATCH_MODALITY_CONFLICT: 115,
        audit.MATCH_IDENTITY_CONFLICT: 110,
        domain.MATCH_ROUTE_CONFLICT: 100,
        domain.MATCH_GRADE_CONFLICT: 90,
        domain.MATCH_OFFICIAL_CONFLICT: 85,
        domain.MATCH_AMBIGUOUS: 80,
        domain.MATCH_REVIEW: 70,
        MATCH_OUTSIDE_POPULATION: 60,
        domain.MATCH_UNMATCHED: 55,
    }
    result: list[dict[str, Any]] = []
    for items in grouped.values():
        def top_similarity(item: dict[str, Any]) -> float:
            candidates = item.get("candidates") or []
            if not candidates:
                return 0.0
            try:
                return float(candidates[0].get("similarity") or 0.0)
            except (TypeError, ValueError):
                return 0.0

        representative = dict(max(items, key=top_similarity))
        representative["occurrences"] = len(items)
        representative["group_link_ids"] = [int(item["id"]) for item in items]
        if len(items) > 1:
            base_detail = str(representative.get("detail") or "").strip()
            prefix = f"{len(items)} evidencias del mismo estudiante se agruparon en un solo caso."
            representative["detail"] = f"{prefix} {base_detail}".strip()
        result.append(representative)

    result.sort(
        key=lambda row: (
            -priority.get(str(row.get("match_status") or ""), 50),
            str(row.get("source_module") or ""),
            str(row.get("source_name") or "").casefold(),
            int(row.get("id") or 0),
        )
    )
    return result


def _case_summary(report_ids: list[int]) -> dict[str, int]:
    cases = _group_open_links(report_ids)
    counts = Counter(str(row.get("match_status") or domain.MATCH_UNMATCHED) for row in cases)
    raw_pending = sum(int(row.get("occurrences") or 1) for row in cases)
    outside = counts[MATCH_OUTSIDE_POPULATION]
    route = counts[domain.MATCH_ROUTE_CONFLICT]
    identity_review = sum(
        counts[key]
        for key in (
            audit.MATCH_IDENTITY_CONFLICT,
            domain.MATCH_AMBIGUOUS,
            domain.MATCH_REVIEW,
            domain.MATCH_UNMATCHED,
        )
    )
    other = max(0, len(cases) - outside - route - identity_review)

    auto_resolved = 0
    if report_ids:
        placeholders = ",".join("?" for _ in report_ids)
        with connection() as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='student_source_links'"
            ).fetchone()
            if table:
                auto_resolved = int(
                    conn.execute(
                        f"""
                        SELECT COUNT(*) FROM student_source_links
                        WHERE report_id IN ({placeholders})
                          AND COALESCE(source_active, 1)=1
                          AND match_status='OK'
                          AND match_method IN ('NOMBRE_EXACTO','NOMBRE_EXACTO_CONTEXTO','NOMBRE_REORDENADO','NOMBRE_ALTA_CONFIANZA')
                        """,
                        tuple(report_ids),
                    ).fetchone()[0]
                )
    return {
        "total_cases": len(cases),
        "raw_pending": raw_pending,
        "outside_population": outside,
        "identity_review": identity_review,
        "route_conflicts": route,
        "other": other,
        "auto_resolved": auto_resolved,
    }


def _smart_fast_audit(report_id: int | None) -> dict[str, Any] | None:
    if _BASE_FAST_AUDIT is None:
        return None
    data = _BASE_FAST_AUDIT(report_id)
    if not data or not report_id:
        return data
    summary = _case_summary([int(report_id)])
    controls = [item for item in data.get("controls", []) if item.get("name") != "Conciliación"]
    if summary["total_cases"]:
        parts: list[str] = []
        if summary["outside_population"]:
            parts.append(f"{summary['outside_population']} fuera de población")
        if summary["identity_review"]:
            parts.append(f"{summary['identity_review']} de identidad")
        if summary["route_conflicts"]:
            parts.append(f"{summary['route_conflicts']} de ruta")
        if summary["other"]:
            parts.append(f"{summary['other']} otros")
        detail = f"Existen {summary['total_cases']} casos únicos que requieren atención"
        if summary["raw_pending"] != summary["total_cases"]:
            detail += f" ({summary['raw_pending']} evidencias técnicas agrupadas)"
        if parts:
            detail += ": " + ", ".join(parts)
        detail += "."
        controls.append({"name": "Conciliación", "status": "warning", "detail": detail})
    data["controls"] = controls
    data["case_summary"] = summary
    return data


def _smart_period_read(period_project_id: int) -> dict[str, Any]:
    if _BASE_PERIOD_READ is None:
        raise RuntimeError("La lectura del período no está disponible.")
    data = _BASE_PERIOD_READ(period_project_id)
    report_ids = [int(item["id"]) for item in data.get("members", [])]
    summary = _case_summary(report_ids)
    data["case_summary"] = summary
    data.setdefault("summary", {})["open_links"] = summary["total_cases"]
    data["summary"]["source_alerts"] = summary["total_cases"]
    return data


def _source_count(report_id: int, module: str) -> int:
    with connection() as conn:
        if module == "COMPLEXIVE":
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM students s JOIN careers c ON c.id=s.career_id WHERE c.report_id=?",
                    (report_id,),
                ).fetchone()[0]
            )
        if module == "THESIS":
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='thesis_projects'"
            ).fetchone()
            if not exists:
                return 0
            return int(conn.execute("SELECT COUNT(*) FROM thesis_projects WHERE report_id=?", (report_id,)).fetchone()[0])
        if module == "NUCLEI":
            instance = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_instance_students'"
            ).fetchone()
            courses = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_course_instances'"
            ).fetchone()
            if instance and courses:
                return int(
                    conn.execute(
                        """
                        SELECT COUNT(*) FROM nucleus_instance_students ns
                        JOIN nucleus_course_instances nc ON nc.id=ns.course_id
                        WHERE nc.report_id=?
                        """,
                        (report_id,),
                    ).fetchone()[0]
                )
            legacy_students = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_students'"
            ).fetchone()
            legacy_courses = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='nucleus_courses'"
            ).fetchone()
            if legacy_students and legacy_courses:
                return int(
                    conn.execute(
                        """
                        SELECT COUNT(*) FROM nucleus_students ns
                        JOIN nucleus_courses nc ON nc.id=ns.course_id
                        WHERE nc.report_id=?
                        """,
                        (report_id,),
                    ).fetchone()[0]
                )
    return 0


def _module_status_counts(report_id: int, module: str) -> dict[str, int]:
    with connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='student_source_links'"
        ).fetchone()
        if not exists:
            return {}
        rows = conn.execute(
            """
            SELECT match_status, COUNT(*) AS total
            FROM student_source_links
            WHERE report_id=? AND source_module=? AND COALESCE(source_active, 1)=1
            GROUP BY match_status
            """,
            (report_id, module),
        ).fetchall()
    return {str(row["match_status"] or domain.MATCH_UNMATCHED): int(row["total"] or 0) for row in rows}


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["id"],
        "period_project_id": job["period_project_id"],
        "status": job["status"],
        "progress": job["progress"],
        "stage": job["stage"],
        "detail": job.get("detail", ""),
        "error": job.get("error", ""),
        "stats": dict(job.get("stats") or {}),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }


def _set_job(job_id: str, *, progress: int | None = None, stage: str | None = None,
             detail: str | None = None, status: str | None = None,
             stats: dict[str, Any] | None = None, error: str | None = None) -> None:
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        if progress is not None:
            job["progress"] = max(int(job.get("progress", 0)), min(100, int(progress)))
        if stage is not None:
            job["stage"] = stage
        if detail is not None:
            job["detail"] = detail
        if status is not None:
            job["status"] = status
        if stats is not None:
            job["stats"] = dict(stats)
        if error is not None:
            job["error"] = error
        job["updated_at"] = time.time()


def _cleanup_jobs() -> None:
    with _JOB_LOCK:
        completed = sorted(
            (job for job in _JOBS.values() if job["status"] in {"completed", "error"}),
            key=lambda item: float(item.get("updated_at", 0)),
        )
        while len(_JOBS) > 25 and completed:
            old = completed.pop(0)
            _JOBS.pop(old["id"], None)
            if _ACTIVE_BY_PROJECT.get(int(old["period_project_id"])) == old["id"]:
                _ACTIVE_BY_PROJECT.pop(int(old["period_project_id"]), None)


def _stage_progress(done: int, total: int) -> int:
    if total <= 0:
        return 95
    return min(95, 5 + int(round((done / total) * 90)))


def _run_reconciliation_job(job_id: str, period_project_id: int) -> None:
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
            "auto_resolved": 0,
            "cases": 0,
        }
        _set_job(
            job_id,
            status="running",
            progress=3,
            stage="Preparando conciliación",
            detail="Identificando datasets Presencial y Online y la población maestra de Requisitos.",
            stats=aggregate,
        )

        with sqlite_guard._WRITE_LOCK:
            for member in members:
                report_id = int(member["id"])
                modality = str(member.get("modality") or "")
                label = "Presencial" if modality == "presencial" else "Online"

                _set_job(
                    job_id,
                    progress=_stage_progress(done, total_steps),
                    stage=f"{label} · preparando estudiantes",
                    detail="Sincronizando la identidad maestra desde Requisitos sin modificar decisiones manuales.",
                    stats=aggregate,
                )
                sync_result = audit.sync_report_students(report_id)
                done += 1
                _set_job(
                    job_id,
                    progress=_stage_progress(done, total_steps),
                    detail=f"{int(sync_result.get('students') or 0)} estudiantes maestros verificados.",
                    stats=aggregate,
                )

                for module, module_label, callback in (
                    ("NUCLEI", "Núcleos", audit.reconcile_nuclei),
                    ("COMPLEXIVE", "Examen Complexivo", audit.reconcile_complexive),
                    ("THESIS", "Trabajo de Titulación", audit.reconcile_thesis),
                ):
                    total_records = _source_count(report_id, module)
                    _set_job(
                        job_id,
                        progress=_stage_progress(done, total_steps),
                        stage=f"{label} · {module_label}",
                        detail=f"Analizando {total_records} registros contra la población oficial de Requisitos.",
                        stats=aggregate,
                    )
                    result = callback(report_id)
                    status_counts = _module_status_counts(report_id, module)
                    aggregate["matched"] += int(status_counts.get(domain.MATCH_OK, 0))
                    aggregate["outside_population"] += int(status_counts.get(MATCH_OUTSIDE_POPULATION, 0))
                    aggregate["identity_review"] += sum(
                        int(status_counts.get(key, 0))
                        for key in (audit.MATCH_IDENTITY_CONFLICT, domain.MATCH_REVIEW, domain.MATCH_AMBIGUOUS, domain.MATCH_UNMATCHED)
                    )
                    aggregate["route_conflicts"] += int(status_counts.get(domain.MATCH_ROUTE_CONFLICT, 0))
                    done += 1
                    _set_job(
                        job_id,
                        progress=_stage_progress(done, total_steps),
                        detail=(
                            f"{module_label}: {int(result.get('matched') or 0)} vinculados, "
                            f"{int(status_counts.get(MATCH_OUTSIDE_POPULATION, 0))} fuera de población, "
                            f"{int(result.get('route_conflicts') or 0)} conflictos de ruta."
                        ),
                        stats=aggregate,
                    )

            _set_job(
                job_id,
                progress=_stage_progress(done, total_steps),
                stage="Agrupando casos que requieren atención",
                detail="Consolidando evidencias repetidas del mismo estudiante para evitar alertas duplicadas.",
                stats=aggregate,
            )
            report_ids = [int(item["id"]) for item in members]
            case_summary = _case_summary(report_ids)
            aggregate["auto_resolved"] = case_summary["auto_resolved"]
            aggregate["cases"] = case_summary["total_cases"]
            aggregate["outside_population"] = case_summary["outside_population"]
            aggregate["identity_review"] = case_summary["identity_review"]
            aggregate["route_conflicts"] = case_summary["route_conflicts"]
            done += 1

        _set_job(
            job_id,
            progress=100,
            status="completed",
            stage="Conciliación completada",
            detail=(
                f"Quedaron {aggregate['cases']} casos únicos que requieren atención. "
                f"{aggregate['auto_resolved']} evidencias se resolvieron automáticamente por identidad fuerte."
            ),
            stats=aggregate,
            error="",
        )
    except Exception as exc:
        _set_job(
            job_id,
            status="error",
            stage="No se pudo completar la conciliación",
            detail="Se conservaron los datos ya procesados. Revise el error antes de volver a intentar.",
            error=str(exc),
        )
    finally:
        with _JOB_LOCK:
            if _ACTIVE_BY_PROJECT.get(period_project_id) == job_id:
                _ACTIVE_BY_PROJECT.pop(period_project_id, None)
        _cleanup_jobs()


def _start_job(period_project_id: int) -> dict[str, Any]:
    _cleanup_jobs()
    with _JOB_LOCK:
        active_id = _ACTIVE_BY_PROJECT.get(period_project_id)
        if active_id:
            active = _JOBS.get(active_id)
            if active and active["status"] in {"queued", "running"}:
                return _public_job(active)

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
        _JOBS[job_id] = job
        _ACTIVE_BY_PROJECT[period_project_id] = job_id

    thread = threading.Thread(
        target=_run_reconciliation_job,
        args=(job_id, period_project_id),
        daemon=True,
        name=f"reconcile-{job_id[:8]}",
    )
    thread.start()
    return _public_job(job)


def _get_job(job_id: str) -> dict[str, Any] | None:
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        return _public_job(job) if job else None


def _confirm_group(period_project_id: int, link_id: int, student_id: int) -> dict[str, Any]:
    members = fast_read._member_reports(period_project_id)
    report_ids = {int(item["id"]) for item in members}
    with sqlite_guard._WRITE_LOCK:
        with connection() as conn:
            link = conn.execute("SELECT * FROM student_source_links WHERE id=?", (link_id,)).fetchone()
            if not link or int(link["report_id"]) not in report_ids:
                raise ValueError("El caso de conciliación ya no existe en este período.")
            report_id = int(link["report_id"])
            student = conn.execute(
                "SELECT id FROM period_students WHERE id=? AND report_id=? AND period_project_id=?",
                (student_id, report_id, period_project_id),
            ).fetchone()
            if not student:
                raise ValueError("El estudiante seleccionado no pertenece al mismo dataset del caso.")
            source_module = str(link["source_module"])
            selected = dict(link)
            identity = _group_identity(selected)
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
            siblings = [row for row in rows if _group_identity(row) == identity]
            if not siblings:
                siblings = [selected]
            now = utcnow()
            ids = [int(row["id"]) for row in siblings]
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE student_source_links
                SET period_student_id=?, match_status='OK', match_method='MANUAL',
                    match_confidence=100,
                    detail='Asociación confirmada manualmente para todas las evidencias agrupadas del mismo estudiante.',
                    updated_at=?
                WHERE id IN ({placeholders})
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
                    f"{source_module}: se confirmaron {len(ids)} evidencias agrupadas.",
                    now,
                ),
            )

        # Actualiza las tablas fuente para que la evidencia aparezca de inmediato.
        if source_module == "NUCLEI":
            audit.reconcile_nuclei(report_id)
        elif source_module == "COMPLEXIVE":
            audit.reconcile_complexive(report_id)
        elif source_module == "THESIS":
            audit.reconcile_thesis(report_id)

    return {"ok": True, "student_id": student_id, "confirmed_links": len(ids)}


def install() -> None:
    global _INSTALLED, _BASE_MATCH, _BASE_OPEN_LINKS, _BASE_FAST_AUDIT
    global _BASE_PERIOD_READ, _BASE_GET, _BASE_WRITE
    if _INSTALLED:
        return

    _BASE_MATCH = bridge._match
    _BASE_OPEN_LINKS = audit._open_links
    _BASE_FAST_AUDIT = fast_read._fast_audit
    _BASE_PERIOD_READ = fast_read._period_students_read

    # El matcher final prioriza cédula/correo/nombre exacto. Carrera y sede son
    # contexto, no penalizaciones capaces de destruir una identidad fuerte.
    bridge._match = _smart_match

    # Las discrepancias se presentan como casos únicos por estudiante/fuente, no
    # como una tarjeta independiente por cada Núcleo o evidencia repetida.
    audit._open_links = _group_open_links
    fast_read._fast_audit = _smart_fast_audit
    fast_read._period_students_read = _smart_period_read

    _BASE_GET = core.InformtitHandler._handle_api_get
    _BASE_WRITE = core.InformtitHandler._handle_api_write

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(r"/api/reconciliation-jobs/([a-f0-9]{32})", path)
        if match:
            job = _get_job(match.group(1))
            if not job:
                self._send_error_json("Proceso de conciliación no encontrado.", 404)
                return
            self._send_json({"ok": True, "job": job})
            return

        match = re.fullmatch(r"/api/period-projects/(\d+)/reconciliation-summary", path)
        if match:
            project_id = int(match.group(1))
            members = fast_read._member_reports(project_id)
            report_ids = [int(item["id"]) for item in members]
            self._send_json({"ok": True, "summary": _case_summary(report_ids)})
            return

        assert _BASE_GET is not None
        _BASE_GET(self, path, query)

    def handle_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        match = re.fullmatch(r"/api/period-projects/(\d+)/students-domain/reconcile-jobs", path)
        if match and method == "POST":
            job = _start_job(int(match.group(1)))
            self._send_json({"ok": True, "job": job}, 202)
            return

        match = re.fullmatch(r"/api/period-projects/(\d+)/students-domain/matches/(\d+)/confirm", path)
        if match and method == "POST":
            student_id = int(payload.get("student_id") or 0)
            if not student_id:
                self._send_error_json("Seleccione un estudiante válido.", 400)
                return
            try:
                result = _confirm_group(int(match.group(1)), int(match.group(2)), student_id)
            except ValueError as exc:
                self._send_error_json(str(exc), 400)
                return
            self._send_json(result)
            return

        assert _BASE_WRITE is not None
        _BASE_WRITE(self, method, path, payload)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
    _INSTALLED = True
