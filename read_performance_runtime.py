from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Callable

import app as core
import period_unified_runtime as unified
import sqlite_concurrency_runtime as sqlite_guard
import student_domain_read_model as read_model
import student_domain_service as domain
import student_final_audit as audit
from db import connection, rows_to_dicts


_INSTALLED = False
_BASE_GET: Callable[..., Any] | None = None
_BASE_WRITE: Callable[..., Any] | None = None


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


def _member_reports(period_project_id: int) -> list[dict[str, Any]]:
    with connection() as conn:
        project = conn.execute(
            "SELECT id FROM period_projects WHERE id=?",
            (period_project_id,),
        ).fetchone()
        if not project:
            raise ValueError("El período solicitado no existe.")
        return rows_to_dicts(
            conn.execute(
                """
                SELECT id, modality, period, name
                FROM reports
                WHERE period_project_id=?
                ORDER BY CASE modality WHEN 'presencial' THEN 0 ELSE 1 END, id
                """,
                (period_project_id,),
            ).fetchall()
        )


def _read_master_students(report_id: int) -> dict[str, Any]:
    """Lee el maestro actual sin ejecutar sync_report_students ni conciliaciones."""
    with connection() as conn:
        if not _table_exists(conn, "period_students"):
            return {"ok": True, "summary": {"students": 0}, "students": []}
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM period_students
                WHERE report_id=? AND COALESCE(requirements_present, 1)=1
                ORDER BY career_name, full_name, id
                """,
                (report_id,),
            ).fetchall()
        )
        links = (
            rows_to_dicts(
                conn.execute(
                    """
                    SELECT * FROM student_source_links
                    WHERE report_id=? AND COALESCE(source_active, 1)=1
                    ORDER BY source_module, id
                    """,
                    (report_id,),
                ).fetchall()
            )
            if _table_exists(conn, "student_source_links")
            else []
        )

    by_student: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for link in links:
        sid = int(link["period_student_id"]) if link.get("period_student_id") else 0
        if sid:
            try:
                link["candidates"] = json.loads(link.get("candidates_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                link["candidates"] = []
            by_student[sid].append(link)

    for row in rows:
        try:
            row["missing_requirements"] = json.loads(row.get("missing_requirements_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            row["missing_requirements"] = []
        row["source_links"] = by_student.get(int(row["id"]), [])
        raw_identification = str(row.get("identification") or "")
        row["identity_key"] = raw_identification
        row["identification"] = audit._public_identification(raw_identification)
        row["requirements_present"] = int(row.get("requirements_present", 1) or 0)
        row["modality_conflict"] = int(row.get("modality_conflict", 0) or 0)

    return {
        "ok": True,
        "summary": {
            "students": len(rows),
            "complexive": sum(row.get("route") == domain.ROUTE_COMPLEXIVE for row in rows),
            "thesis": sum(row.get("route") == domain.ROUTE_THESIS for row in rows),
            "graduated": sum(bool(row.get("official_graduated")) for row in rows),
            "retired": sum(row.get("process_status") == domain.PROCESS_RETIRED for row in rows),
            "one_missing": sum(row.get("process_status") == domain.PROCESS_WITH_ONE_MISSING for row in rows),
        },
        "students": rows,
    }


def _consolidated_read(report_id: int) -> dict[str, Any]:
    """Enriquece el maestro usando únicamente SELECT sobre las evidencias ya conciliadas."""
    students = _read_master_students(report_id)
    complexive = read_model._complexive_records(report_id)
    thesis = read_model._thesis_records(report_id)
    nuclei = read_model._nuclei_records(report_id)
    rows: list[dict[str, Any]] = []

    for student in students.get("students", []):
        sid = int(student["id"])
        row = dict(student)
        row["nuclei_records"] = nuclei.get(sid, [])
        row["complexive_records"] = complexive.get(sid, [])
        row["thesis_records"] = thesis.get(sid, [])
        row["has_nuclei"] = bool(row["nuclei_records"])
        row["has_complexive"] = bool(row["complexive_records"])
        row["has_thesis"] = bool(row["thesis_records"])
        effective_status, effective_detail = audit._effective_reconciliation(row)
        row["reconciliation_status"] = effective_status
        row["reconciliation_detail"] = effective_detail
        rows.append(row)

    summary = dict(students.get("summary") or {})
    summary["review"] = sum(
        str(row.get("reconciliation_status") or domain.MATCH_OK) != domain.MATCH_OK
        for row in rows
    )
    summary["with_nuclei"] = sum(bool(row.get("has_nuclei")) for row in rows)
    summary["with_complexive"] = sum(bool(row.get("has_complexive")) for row in rows)
    summary["with_thesis_data"] = sum(bool(row.get("has_thesis")) for row in rows)
    return {"ok": True, "summary": summary, "students": rows}


def _period_students_read(period_project_id: int) -> dict[str, Any]:
    members = _member_reports(period_project_id)
    rows: list[dict[str, Any]] = []
    report_ids: list[int] = []

    for member in members:
        report_id = int(member["id"])
        report_ids.append(report_id)
        modality = str(member.get("modality") or "")
        data = _consolidated_read(report_id)
        for source in data.get("students", []):
            item = dict(source)
            item["dataset_report_id"] = report_id
            item["dataset_modality"] = modality
            item["modality"] = modality
            rows.append(item)

    # Detecta el conflicto entre modalidades en memoria. No hace UPDATE durante GET.
    identities: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        identification = audit._official_identification(row.get("identity_key") or row.get("identification"))
        if identification:
            identities[identification].append(row)
    for items in identities.values():
        datasets = {int(item.get("dataset_report_id") or 0) for item in items}
        if len(datasets) <= 1:
            continue
        for item in items:
            item["modality_conflict"] = 1
            item["reconciliation_status"] = audit.MATCH_MODALITY_CONFLICT
            item["reconciliation_detail"] = (
                "La misma cédula aparece simultáneamente en los datasets Presencial y Online del período."
            )

    rows.sort(
        key=lambda row: (
            str(row.get("career_name") or "").casefold(),
            str(row.get("full_name") or "").casefold(),
            int(row.get("id") or 0),
        )
    )
    open_links = audit._open_links(report_ids)
    review_students = sum(
        str(row.get("reconciliation_status") or domain.MATCH_OK) != domain.MATCH_OK
        for row in rows
    )
    return {
        "ok": True,
        "period_project_id": period_project_id,
        "summary": {
            "students": len(rows),
            "complexive": sum(row.get("route") == domain.ROUTE_COMPLEXIVE for row in rows),
            "thesis": sum(row.get("route") == domain.ROUTE_THESIS for row in rows),
            "graduated": sum(bool(row.get("official_graduated")) for row in rows),
            "retired": sum(row.get("process_status") == domain.PROCESS_RETIRED for row in rows),
            "one_missing": sum(row.get("process_status") == domain.PROCESS_WITH_ONE_MISSING for row in rows),
            "review": review_students,
            "review_students": review_students,
            "open_links": len(open_links),
            "source_alerts": len(open_links),
            "presencial": sum(row.get("modality") == "presencial" for row in rows),
            "online": sum(row.get("modality") == "en_linea" for row in rows),
        },
        "students": rows,
        "open_links": open_links,
        "members": members,
        "reconciliations": {},
        "read_only": True,
    }


def _distinct_complexive(conn: Any, report_id: int) -> int:
    if not _table_exists(conn, "students") or "period_student_id" not in _columns(conn, "students"):
        return 0
    if not _table_exists(conn, "period_students"):
        return 0
    return int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT s.period_student_id)
            FROM students s
            JOIN careers c ON c.id=s.career_id
            JOIN period_students ps ON ps.id=s.period_student_id
            WHERE c.report_id=? AND s.period_student_id IS NOT NULL
              AND ps.report_id=? AND COALESCE(ps.requirements_present, 1)=1
              AND ps.route='COMPLEXIVO' AND ps.process_status<>'RETIRADO'
            """,
            (report_id, report_id),
        ).fetchone()[0]
    )


def _distinct_thesis(conn: Any, report_id: int) -> int:
    if not _table_exists(conn, "thesis_projects") or "period_student_id" not in _columns(conn, "thesis_projects"):
        return 0
    if not _table_exists(conn, "period_students"):
        return 0
    return int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT tp.period_student_id)
            FROM thesis_projects tp
            JOIN period_students ps ON ps.id=tp.period_student_id
            WHERE tp.report_id=? AND tp.period_student_id IS NOT NULL
              AND ps.report_id=? AND COALESCE(ps.requirements_present, 1)=1
              AND ps.route='TRABAJO_TITULACION' AND ps.process_status<>'RETIRADO'
            """,
            (report_id, report_id),
        ).fetchone()[0]
    )


def _distinct_nuclei(conn: Any, report_id: int) -> int:
    if not _table_exists(conn, "period_students"):
        return 0
    if _table_exists(conn, "nucleus_instance_students") and _table_exists(conn, "nucleus_course_instances") and "period_student_id" in _columns(conn, "nucleus_instance_students"):
        return int(
            conn.execute(
                """
                SELECT COUNT(DISTINCT ns.period_student_id)
                FROM nucleus_instance_students ns
                JOIN nucleus_course_instances nc ON nc.id=ns.course_id
                JOIN period_students ps ON ps.id=ns.period_student_id
                WHERE nc.report_id=? AND ns.period_student_id IS NOT NULL
                  AND ps.report_id=? AND COALESCE(ps.requirements_present, 1)=1
                  AND ps.route='COMPLEXIVO' AND ps.process_status<>'RETIRADO'
                """,
                (report_id, report_id),
            ).fetchone()[0]
        )
    if _table_exists(conn, "nucleus_students") and _table_exists(conn, "nucleus_courses") and "period_student_id" in _columns(conn, "nucleus_students"):
        return int(
            conn.execute(
                """
                SELECT COUNT(DISTINCT ns.period_student_id)
                FROM nucleus_students ns
                JOIN nucleus_courses nc ON nc.id=ns.course_id
                JOIN period_students ps ON ps.id=ns.period_student_id
                WHERE nc.report_id=? AND ns.period_student_id IS NOT NULL
                  AND ps.report_id=? AND COALESCE(ps.requirements_present, 1)=1
                  AND ps.route='COMPLEXIVO' AND ps.process_status<>'RETIRADO'
                """,
                (report_id, report_id),
            ).fetchone()[0]
        )
    return 0


def _schedule_count(conn: Any, report_id: int) -> int:
    if not _table_exists(conn, "schedule_items"):
        return 0
    return int(conn.execute("SELECT COUNT(*) FROM schedule_items WHERE report_id=?", (report_id,)).fetchone()[0])


def _fast_audit(report_id: int | None) -> dict[str, Any] | None:
    if not report_id:
        return None
    with connection() as conn:
        requirements = (
            int(conn.execute("SELECT COUNT(*) FROM requirements_students WHERE report_id=?", (report_id,)).fetchone()[0])
            if _table_exists(conn, "requirements_students")
            else 0
        )
        nuclei = _distinct_nuclei(conn, report_id)
        complexive = _distinct_complexive(conn, report_id)
        thesis = _distinct_thesis(conn, report_id)
        schedules = _schedule_count(conn, report_id)
        open_links = (
            int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM student_source_links
                    WHERE report_id=? AND COALESCE(source_active, 1)=1
                      AND COALESCE(match_status, 'UNMATCHED')<>'OK'
                    """,
                    (report_id,),
                ).fetchone()[0]
            )
            if _table_exists(conn, "student_source_links")
            else 0
        )

    controls: list[dict[str, Any]] = []
    if requirements == 0:
        controls.append({"name": "Población de Requisitos", "status": "error", "detail": "No existen estudiantes cargados en Requisitos."})
    if open_links:
        controls.append({"name": "Conciliación", "status": "warning", "detail": f"Existen {open_links} discrepancias académicas pendientes de subsanar."})
    state = "ERROR DE VALIDACIÓN" if requirements == 0 else "BORRADOR"
    return {
        "ok": requirements > 0,
        "state": state,
        "can_generate_pdf": requirements > 0,
        "controls": controls,
        "metrics": {
            "requirements": {"registered": requirements},
            "nuclei": {"records": nuclei},
            "complexive": {"registered": complexive},
            "thesis": {"total": thesis},
            "schedules": {"total": schedules},
        },
        "read_only": True,
    }


def _fast_overview(period_project_id: int) -> dict[str, Any]:
    summary = unified._project_summary(period_project_id)
    audits = {
        "presencial": _fast_audit(summary.get("presencial_report_id")),
        "en_linea": _fast_audit(summary.get("online_report_id")),
    }
    alerts = list(summary.get("alerts") or [])
    for modality, audit_result in audits.items():
        label = "Presencial" if modality == "presencial" else "Online"
        if not audit_result:
            alerts.append(f"{label}: dataset no disponible.")
            continue
        for item in audit_result.get("controls", []):
            if item.get("status") in {"error", "warning"}:
                alerts.append(f"{label} · {item.get('name')}: {item.get('detail')}")

    def value(modality: str, module: str, key: str) -> int:
        metrics = (audits.get(modality) or {}).get("metrics") or {}
        return int((metrics.get(module) or {}).get(key) or 0)

    modules: list[dict[str, Any]] = []
    for module, label, key in (
        ("requirements", "Requisitos", "registered"),
        ("nuclei", "Núcleos", "records"),
        ("complexive", "Examen Complexivo", "registered"),
        ("thesis", "Trabajo de Titulación", "total"),
    ):
        presencial = value("presencial", module, key)
        online = value("en_linea", module, key)
        modules.append({"module": label, "presencial": presencial, "online": online, "total": presencial + online})

    shared_schedule = max(
        value("presencial", "schedules", "total"),
        value("en_linea", "schedules", "total"),
    )
    return {
        "ok": True,
        "project": summary,
        "audits": audits,
        "modules": modules,
        "shared_schedule": shared_schedule,
        "alerts": list(dict.fromkeys(alerts)),
        "read_only": True,
    }


def _reconcile_period(period_project_id: int) -> dict[str, Any]:
    """La operación pesada queda explícitamente detrás del botón Reconciliar."""
    members = _member_reports(period_project_id)
    results: dict[str, Any] = {}
    with sqlite_guard._WRITE_LOCK:
        for member in members:
            report_id = int(member["id"])
            audit.sync_report_students(report_id)
            results[str(member.get("modality") or report_id)] = audit.reconcile_all(report_id)
    data = _period_students_read(period_project_id)
    data["reconciliations"] = results
    return data


def install() -> None:
    global _INSTALLED, _BASE_GET, _BASE_WRITE
    if _INSTALLED:
        return

    _BASE_GET = core.InformtitHandler._handle_api_get
    _BASE_WRITE = core.InformtitHandler._handle_api_write

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(r"/api/period-projects/(\d+)/overview", path)
        if match:
            self._send_json(_fast_overview(int(match.group(1))))
            return
        match = re.fullmatch(r"/api/period-projects/(\d+)/students-domain", path)
        if match:
            self._send_json(_period_students_read(int(match.group(1))))
            return
        match = re.fullmatch(r"/api/reports/(\d+)/students-domain", path)
        if match:
            self._send_json(_consolidated_read(int(match.group(1))))
            return
        assert _BASE_GET is not None
        _BASE_GET(self, path, query)

    def handle_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        match = re.fullmatch(r"/api/period-projects/(\d+)/students-domain/reconcile", path)
        if match and method == "POST":
            self._send_json(_reconcile_period(int(match.group(1))))
            return
        assert _BASE_WRITE is not None
        _BASE_WRITE(self, method, path, payload)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
    _INSTALLED = True
