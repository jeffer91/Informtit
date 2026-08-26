from __future__ import annotations

import re
import threading
from collections import defaultdict
from typing import Any, Callable

import app as core
import dual_modality_runtime as dual
import period_unified_runtime as unified
import student_domain_bridge as bridge
import student_domain_runtime as domain_runtime
import student_domain_service as domain
import student_final_audit as audit
import student_period_service as period_service
from db import connection


_INSTALLED = False
_WRITE_LOCK = threading.RLock()
_BASE_SYNC: Callable[[int], dict[str, Any]] | None = None
_BASE_AUDIT_SAFE: Callable[[int | None], dict[str, Any] | None] | None = None
_BASE_COMMIT: Callable[..., dict[str, Any]] | None = None
_BASE_GET: Callable[..., Any] | None = None
_BASE_WRITE: Callable[..., Any] | None = None


def _current_masters(report_id: int) -> dict[int, dict[str, Any]]:
    """Usa el caché de conciliación cuando existe y evita resincronizaciones internas."""
    return {
        int(row["id"]): row
        for row in audit._matching_students(report_id)
    }


def _safe_reconcile_nuclei(report_id: int) -> dict[str, Any]:
    """Concilia Núcleos sin mantener un writer abierto mientras el matcher escribe vínculos."""
    bridge.ensure_bridge_schema()
    courses = bridge.nuclei_service.get_nuclei(report_id).get("courses", [])
    masters = _current_masters(report_id)
    matched = 0
    pending = 0
    conflicts = 0
    route_conflicts = 0
    updates: list[tuple[str, Any, str, str, Any, int, int]] = []

    for course in courses:
        course_id = int(course.get("id") or 0)
        if not course_id:
            continue
        with connection() as conn:
            table = bridge._nucleus_student_table(conn, course_id)
        context = bridge._nucleus_context(course)

        for source in course.get("students", []):
            candidate = {
                "identification": source.get("identification") or "",
                "full_name": source.get("full_name") or "",
                "email": source.get("email") or "",
                "career_name": course.get("career_name") or "",
            }
            source_key = bridge._stable_source_key("NUCLEI", candidate, context)
            result = bridge._match(report_id, "NUCLEI", source_key, candidate)
            sid = result.get("period_student_id")
            status = result.get("status") or domain.MATCH_UNMATCHED

            if status == domain.MATCH_OK and sid:
                master = masters.get(int(sid))
                if master and master.get("route") != domain.ROUTE_COMPLEXIVE:
                    status = domain.MATCH_ROUTE_CONFLICT
                    route_conflicts += 1
                    bridge.save_source_link(
                        report_id,
                        "NUCLEI",
                        source_key,
                        candidate,
                        {
                            **result,
                            "status": status,
                            "detail": "El estudiante tiene ruta Trabajo de Titulación pero aparece en Núcleos.",
                        },
                    )
                else:
                    matched += 1
                    if result.get("method") == "MANUAL":
                        bridge.save_source_link(report_id, "NUCLEI", source_key, candidate, result)
            elif status in {domain.MATCH_REVIEW, domain.MATCH_AMBIGUOUS}:
                conflicts += 1
            else:
                pending += 1

            source_id = source.get("id")
            if table and source_id:
                updates.append(
                    (
                        table,
                        sid,
                        status,
                        result.get("method") or "",
                        result.get("confidence"),
                        int(source_id),
                        course_id,
                    )
                )

    if updates:
        with connection() as conn:
            grouped: dict[str, list[tuple[Any, str, str, Any, int, int]]] = defaultdict(list)
            for table, sid, status, method, confidence, source_id, course_id in updates:
                grouped[table].append((sid, status, method, confidence, source_id, course_id))
            for table, rows in grouped.items():
                conn.executemany(
                    f"""
                    UPDATE {table}
                    SET period_student_id=?, match_status=?, match_method=?, match_confidence=?
                    WHERE id=? AND course_id=?
                    """,
                    rows,
                )

    return {
        "ok": True,
        "matched": matched,
        "pending": pending,
        "conflicts": conflicts,
        "route_conflicts": route_conflicts,
    }


def _safe_reconcile_complexive(report_id: int) -> dict[str, Any]:
    """Calcula primero todos los matches y actualiza students en una transacción final."""
    bridge.ensure_bridge_schema()
    with connection() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT s.*, c.name AS career_name
                FROM students s JOIN careers c ON c.id=s.career_id
                WHERE c.report_id=? ORDER BY c.name, s.full_name, s.id
                """,
                (report_id,),
            ).fetchall()
        ]

    masters = _current_masters(report_id)
    matched = 0
    pending = 0
    route_conflicts = 0
    updates: list[tuple[int | None, int]] = []

    for row in rows:
        source_key = bridge._stable_source_key("COMPLEXIVE", row)
        result = bridge._match(report_id, "COMPLEXIVE", source_key, row)
        sid = result.get("period_student_id")
        status = result.get("status") or domain.MATCH_UNMATCHED

        if status == domain.MATCH_OK and sid:
            master = masters.get(int(sid))
            if master and master.get("route") != domain.ROUTE_COMPLEXIVE:
                status = domain.MATCH_ROUTE_CONFLICT
                route_conflicts += 1
                bridge.save_source_link(
                    report_id,
                    "COMPLEXIVE",
                    source_key,
                    row,
                    {
                        **result,
                        "status": status,
                        "detail": "El estudiante tiene ruta Trabajo de Titulación pero existen notas de Complexivo.",
                    },
                )
            else:
                matched += 1
                if result.get("method") == "MANUAL":
                    bridge.save_source_link(report_id, "COMPLEXIVE", source_key, row, result)
        else:
            pending += 1

        updates.append((int(sid) if sid else None, int(row["id"])))

    if updates:
        with connection() as conn:
            conn.executemany(
                "UPDATE students SET period_student_id=? WHERE id=?",
                updates,
            )

    return {
        "ok": True,
        "matched": matched,
        "pending": pending,
        "route_conflicts": route_conflicts,
    }


def _safe_reconcile_thesis(report_id: int) -> dict[str, Any]:
    """Concilia tesis sin una transacción exterior que bloquee save_source_link."""
    bridge.ensure_bridge_schema()
    with connection() as conn:
        if not bridge._table_exists(conn, "thesis_projects"):
            return {"ok": True, "matched": 0, "pending": 0, "route_conflicts": 0}
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM thesis_projects WHERE report_id=? ORDER BY full_name, id",
                (report_id,),
            ).fetchall()
        ]

    masters = _current_masters(report_id)
    matched = 0
    pending = 0
    route_conflicts = 0
    updates: list[tuple[int | None, int]] = []

    for row in rows:
        source_key = bridge._stable_source_key("THESIS", row)
        result = bridge._match(report_id, "THESIS", source_key, row)
        sid = result.get("period_student_id")
        status = result.get("status") or domain.MATCH_UNMATCHED

        if status == domain.MATCH_OK and sid:
            master = masters.get(int(sid))
            if master and master.get("route") != domain.ROUTE_THESIS:
                status = domain.MATCH_ROUTE_CONFLICT
                route_conflicts += 1
                bridge.save_source_link(
                    report_id,
                    "THESIS",
                    source_key,
                    row,
                    {
                        **result,
                        "status": status,
                        "detail": "Existe Trabajo de Titulación para un estudiante cuya ruta sigue siendo Complexivo.",
                    },
                )
            else:
                matched += 1
                if result.get("method") == "MANUAL":
                    bridge.save_source_link(report_id, "THESIS", source_key, row, result)
        else:
            pending += 1

        updates.append((int(sid) if sid else None, int(row["id"])))

    if updates:
        with connection() as conn:
            conn.executemany(
                "UPDATE thesis_projects SET period_student_id=? WHERE id=?",
                updates,
            )

    return {
        "ok": True,
        "matched": matched,
        "pending": pending,
        "route_conflicts": route_conflicts,
    }


def _locked_sync(report_id: int) -> dict[str, Any]:
    if _BASE_SYNC is None:
        raise RuntimeError("La sincronización maestra todavía no está configurada.")
    with _WRITE_LOCK:
        return _BASE_SYNC(report_id)


def _requirements_count(report_id: int) -> int:
    with connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='requirements_students'"
        ).fetchone()
        if not exists:
            return 0
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM requirements_students WHERE report_id=?",
                (report_id,),
            ).fetchone()[0]
        )


def _locked_audit_safe(report_id: int | None) -> dict[str, Any] | None:
    if _BASE_AUDIT_SAFE is None:
        raise RuntimeError("La auditoría del período todavía no está configurada.")
    if not report_id:
        return None
    with _WRITE_LOCK:
        result = _BASE_AUDIT_SAFE(report_id)
        # Si otra validación falla, nunca presentar Requisitos=0 cuando la población
        # sí existe. El error se conserva, pero la vista muestra el conteo real.
        if result and result.get("error"):
            metrics = result.setdefault("metrics", {})
            requirements = metrics.setdefault("requirements", {})
            requirements["registered"] = _requirements_count(int(report_id))
        return result


def _commit_and_sync(token: str, active_report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if _BASE_COMMIT is None:
        raise RuntimeError("La importación dual todavía no está configurada.")
    with _WRITE_LOCK:
        result = _BASE_COMMIT(token, active_report_id, payload)
        report_ids = {
            int(value)
            for value in (result.get("report_ids") or {}).values()
            if value
        }
        for report_id in sorted(report_ids):
            _locked_sync(report_id)
        # Si ya existían evidencias académicas del período, quedan reconciliadas
        # contra la nueva base antes de responder al usuario.
        for report_id in sorted(report_ids):
            audit.reconcile_all(report_id)
        return result


def _install_request_serialization() -> None:
    global _BASE_GET, _BASE_WRITE
    _BASE_GET = core.InformtitHandler._handle_api_get
    _BASE_WRITE = core.InformtitHandler._handle_api_write

    writing_get = re.compile(
        r"^/api/(?:"
        r"period-projects/\d+/overview|"
        r"reports/\d+/students-domain|"
        r"period-projects/\d+/students-domain"
        r")$"
    )

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        assert _BASE_GET is not None
        if writing_get.fullmatch(path):
            with _WRITE_LOCK:
                _BASE_GET(self, path, query)
            return
        _BASE_GET(self, path, query)

    def handle_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        assert _BASE_WRITE is not None
        # Informtit es una aplicación local de un solo usuario y SQLite admite un
        # único escritor. Serializar las escrituras evita carreras entre requests.
        with _WRITE_LOCK:
            _BASE_WRITE(self, method, path, payload)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write


def install() -> None:
    """Última capa de seguridad SQLite para importación, conciliación y auditoría."""
    global _INSTALLED, _BASE_SYNC, _BASE_AUDIT_SAFE, _BASE_COMMIT
    if _INSTALLED:
        return

    _BASE_SYNC = audit.sync_report_students
    _BASE_AUDIT_SAFE = unified._audit_safe
    _BASE_COMMIT = dual.commit_preview_to_pair

    # Sustituye únicamente las implementaciones base que la auditoría final ya
    # encapsula. Los wrappers de identidad, homónimos y decisiones manuales siguen
    # intactos, pero ya no ejecutan writers SQLite anidados.
    audit._BASE_RECONCILE_NUCLEI = _safe_reconcile_nuclei
    audit._BASE_RECONCILE_COMPLEXIVE = _safe_reconcile_complexive
    audit._BASE_RECONCILE_THESIS = _safe_reconcile_thesis

    # Toda sincronización del maestro pasa por el mismo candado reentrante.
    audit.sync_report_students = _locked_sync
    domain.sync_report_students = _locked_sync
    domain_runtime.sync_report_students = _locked_sync
    period_service.sync_report_students = _locked_sync

    # Importar Requisitos deja period_students listo antes de cerrar el proceso.
    dual.commit_preview_to_pair = _commit_and_sync

    # La vista general no muestra ceros falsos ante una excepción de validación.
    unified._audit_safe = _locked_audit_safe

    # Último wrapper del servidor: un solo writer SQLite a la vez, incluyendo las
    # rutas GET históricas que todavía sincronizan o auditan al consultar.
    _install_request_serialization()
    _INSTALLED = True
