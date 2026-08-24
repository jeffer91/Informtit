from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable

import app as core
import completion_routes
import completion_service
import dual_modality_runtime
import nuclei_excel_import
import nuclei_routes
import period_policy_runtime
import process_routes
import process_service
import report_integrity_core as integrity
from db import connection, get_report_bundle, rows_to_dicts, utcnow
from import_service import _load_preview, clean_cell
from optional_content import set_presence


_INSTALLED = False
_BASE_PROCESS_SCHEDULE: Callable[..., dict[str, Any]] | None = None
_BASE_COMPLETION_SCHEDULE: Callable[..., dict[str, Any]] | None = None
_BASE_RESET_SCHEDULE: Callable[..., dict[str, Any]] | None = None
_BASE_NUCLEI_IMPORT: Callable[..., dict[str, Any]] | None = None


def _fold(value: Any) -> str:
    return period_policy_runtime._fold(value)


def _project_key(period: Any, report_type: str = "normal") -> str:
    canonical = period_policy_runtime.canonical_period_id(period)
    return f"{report_type}:{canonical or _fold(period)}"


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn: Any, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def ensure_schema() -> None:
    period_policy_runtime.ensure_schema()
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS period_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                period TEXT NOT NULL,
                code TEXT DEFAULT '',
                version TEXT DEFAULT '1.0',
                elaboration_date TEXT DEFAULT '',
                report_type TEXT DEFAULT 'normal',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        if "period_project_id" not in _columns(conn, "reports"):
            conn.execute("ALTER TABLE reports ADD COLUMN period_project_id INTEGER")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_period_project ON reports(period_project_id, modality)"
        )


def _requirements_count(conn: Any, report_id: int) -> int:
    if not _table_exists(conn, "requirements_students"):
        return 0
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM requirements_students WHERE report_id=?",
            (report_id,),
        ).fetchone()[0]
    )


def _complexive_count(conn: Any, report_id: int) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*) FROM students s
            JOIN careers c ON c.id=s.career_id
            WHERE c.report_id=?
            """,
            (report_id,),
        ).fetchone()[0]
    )


def _career_count(conn: Any, report_id: int) -> int:
    return int(
        conn.execute("SELECT COUNT(*) FROM careers WHERE report_id=?", (report_id,)).fetchone()[0]
    )


def _nuclei_count(conn: Any, report_id: int) -> int:
    if not _table_exists(conn, "nucleus_course_instances"):
        return 0
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM nucleus_course_instances WHERE report_id=?",
            (report_id,),
        ).fetchone()[0]
    )


def _thesis_count(conn: Any, report_id: int) -> int:
    if not _table_exists(conn, "thesis_projects"):
        return 0
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM thesis_projects WHERE report_id=?",
            (report_id,),
        ).fetchone()[0]
    )


def _row_score(conn: Any, row: Any) -> tuple[int, int, int, int, int]:
    report_id = int(row["id"])
    return (
        int(bool(row["source_import_id"])),
        _requirements_count(conn, report_id),
        _complexive_count(conn, report_id),
        _nuclei_count(conn, report_id) + _thesis_count(conn, report_id),
        report_id,
    )


def _preferred_member(conn: Any, rows: list[Any], modality: str | None = None) -> Any:
    candidates = [row for row in rows if modality is None or row["modality"] == modality]
    if not candidates:
        candidates = rows
    return max(candidates, key=lambda row: _row_score(conn, row))


def reconcile_projects() -> dict[str, Any]:
    """Convierte pares históricos Presencial/Online en un solo proyecto lógico.

    Los registros de modalidad se conservan como datasets internos para no perder
    información ya cargada, pero dejan de exponerse como informes separados.
    """
    ensure_schema()
    now = utcnow()
    linked = 0
    created = 0
    project_ids: list[int] = []

    with connection() as conn:
        reports = conn.execute("SELECT * FROM reports ORDER BY id").fetchall()
        groups: dict[str, list[Any]] = defaultdict(list)
        for row in reports:
            kind = str(row["report_type"] or period_policy_runtime.classify_period(row["period"]))
            groups[_project_key(row["period"], kind)].append(row)

        for key, rows in groups.items():
            preferred = _preferred_member(conn, rows, "presencial")
            kind = str(preferred["report_type"] or period_policy_runtime.classify_period(preferred["period"]))
            existing = conn.execute(
                "SELECT * FROM period_projects WHERE period_key=?",
                (key,),
            ).fetchone()
            if existing:
                project_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE period_projects SET
                        name=?, period=?, code=?, version=?, elaboration_date=?,
                        report_type=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        preferred["name"], preferred["period"], preferred["code"],
                        preferred["version"], preferred["elaboration_date"], kind, now, project_id,
                    ),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO period_projects
                    (period_key, name, period, code, version, elaboration_date,
                     report_type, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key, preferred["name"], preferred["period"], preferred["code"],
                        preferred["version"], preferred["elaboration_date"], kind, now, now,
                    ),
                )
                project_id = int(cursor.lastrowid)
                created += 1
            project_ids.append(project_id)

            # Los datos generales pertenecen al período, no a la modalidad.
            shared = (
                preferred["name"], preferred["period"], preferred["code"],
                preferred["version"], preferred["elaboration_date"],
                preferred["prepared_by"], preferred["prepared_role"],
                preferred["reviewed_by"], preferred["reviewed_role"],
                preferred["approved_by"], preferred["approved_role"],
            )
            for row in rows:
                conn.execute(
                    """
                    UPDATE reports SET
                        period_project_id=?, name=?, period=?, code=?, version=?, elaboration_date=?,
                        prepared_by=?, prepared_role=?, reviewed_by=?, reviewed_role=?,
                        approved_by=?, approved_role=?
                    WHERE id=?
                    """,
                    (project_id, *shared, int(row["id"])),
                )
                linked += 1

    # El cronograma es compartido. Se concilia después de cerrar la conexión
    # principal para evitar bloqueos por las marcas de presencia.
    for project_id in project_ids:
        sync_project_schedule(project_id)
    return {"ok": True, "projects_created": created, "datasets_linked": linked}


def _members(project_id: int) -> list[dict[str, Any]]:
    ensure_schema()
    with connection() as conn:
        return rows_to_dicts(
            conn.execute(
                "SELECT * FROM reports WHERE period_project_id=? ORDER BY id",
                (project_id,),
            ).fetchall()
        )


def _project_for_report(report_id: int) -> dict[str, Any] | None:
    ensure_schema()
    with connection() as conn:
        row = conn.execute(
            """
            SELECT p.* FROM period_projects p
            JOIN reports r ON r.period_project_id=p.id
            WHERE r.id=?
            """,
            (report_id,),
        ).fetchone()
    if row:
        return dict(row)
    reconcile_projects()
    with connection() as conn:
        row = conn.execute(
            """
            SELECT p.* FROM period_projects p
            JOIN reports r ON r.period_project_id=p.id
            WHERE r.id=?
            """,
            (report_id,),
        ).fetchone()
    return dict(row) if row else None


def _member_ids(project_id: int) -> dict[str, int]:
    members = _members(project_id)
    result: dict[str, int] = {}
    if not members:
        return result
    with connection() as conn:
        rows = [conn.execute("SELECT * FROM reports WHERE id=?", (int(item["id"]),)).fetchone() for item in members]
        rows = [row for row in rows if row]
        for modality in ("presencial", "en_linea"):
            candidates = [row for row in rows if row["modality"] == modality]
            if candidates:
                result[modality] = int(_preferred_member(conn, candidates)["id"])
    return result


def _counterpart_report_id(report_id: int) -> int | None:
    project = _project_for_report(report_id)
    if not project:
        return None
    ids = _member_ids(int(project["id"]))
    with connection() as conn:
        row = conn.execute("SELECT modality FROM reports WHERE id=?", (report_id,)).fetchone()
    if not row:
        return None
    other = "en_linea" if row["modality"] == "presencial" else "presencial"
    return ids.get(other)


def _project_summary(project_id: int) -> dict[str, Any]:
    ensure_schema()
    with connection() as conn:
        project = conn.execute("SELECT * FROM period_projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            raise ValueError("El período solicitado no existe.")
        members = conn.execute(
            "SELECT * FROM reports WHERE period_project_id=? ORDER BY id",
            (project_id,),
        ).fetchall()
        ids: dict[str, int] = {}
        counts: dict[str, dict[str, int]] = {}
        for modality in ("presencial", "en_linea"):
            candidates = [row for row in members if row["modality"] == modality]
            if not candidates:
                counts[modality] = {
                    "students": 0, "careers": 0, "complexive": 0, "nuclei": 0, "thesis": 0,
                }
                continue
            selected = _preferred_member(conn, candidates)
            report_id = int(selected["id"])
            ids[modality] = report_id
            counts[modality] = {
                "students": _requirements_count(conn, report_id),
                "careers": _career_count(conn, report_id),
                "complexive": _complexive_count(conn, report_id),
                "nuclei": _nuclei_count(conn, report_id),
                "thesis": _thesis_count(conn, report_id),
            }

        primary_id = ids.get("presencial") or ids.get("en_linea")
        alerts: list[str] = []
        if project["report_type"] == "normal":
            if "presencial" not in ids:
                alerts.append("Falta el dataset Presencial del período.")
            if "en_linea" not in ids:
                alerts.append("Falta el dataset Online del período.")
            if counts["presencial"]["students"] == 0:
                alerts.append("La base de Requisitos no contiene estudiantes Presencial. Revise la importación.")
            if counts["en_linea"]["students"] == 0:
                alerts.append("La base de Requisitos no contiene estudiantes Online. Revise la importación.")

        return {
            "id": primary_id,
            "period_project_id": int(project["id"]),
            "name": project["name"],
            "period": project["period"],
            "code": project["code"],
            "version": project["version"],
            "elaboration_date": project["elaboration_date"],
            "report_type": project["report_type"],
            "modality": "unified",
            "presencial_report_id": ids.get("presencial"),
            "online_report_id": ids.get("en_linea"),
            "presencial_students": counts["presencial"]["students"],
            "online_students": counts["en_linea"]["students"],
            "student_count": counts["presencial"]["students"] + counts["en_linea"]["students"],
            "presencial_careers": counts["presencial"]["careers"],
            "online_careers": counts["en_linea"]["careers"],
            "career_count": counts["presencial"]["careers"] + counts["en_linea"]["careers"],
            "presencial_complexive": counts["presencial"]["complexive"],
            "online_complexive": counts["en_linea"]["complexive"],
            "complexive_records": counts["presencial"]["complexive"] + counts["en_linea"]["complexive"],
            "presencial_nuclei": counts["presencial"]["nuclei"],
            "online_nuclei": counts["en_linea"]["nuclei"],
            "presencial_thesis": counts["presencial"]["thesis"],
            "online_thesis": counts["en_linea"]["thesis"],
            "population_error": bool(alerts),
            "alerts": alerts,
        }


def visible_projects() -> list[dict[str, Any]]:
    reconcile_projects()
    with connection() as conn:
        ids = [int(row[0]) for row in conn.execute("SELECT id FROM period_projects ORDER BY updated_at DESC, id DESC").fetchall()]
    return [_project_summary(project_id) for project_id in ids]


def _decorated_bundle(report_id: int) -> dict[str, Any] | None:
    report = get_report_bundle(report_id)
    if not report:
        return None
    project = _project_for_report(report_id)
    if not project:
        return report
    summary = _project_summary(int(project["id"]))
    report["period_project_id"] = int(project["id"])
    report["project_mode"] = True
    report["project_summary"] = summary
    report["presencial_report_id"] = summary.get("presencial_report_id")
    report["online_report_id"] = summary.get("online_report_id")
    return report


def _audit_safe(report_id: int | None) -> dict[str, Any] | None:
    if not report_id:
        return None
    try:
        return integrity.audit_report(int(report_id), resolve_resources=False)
    except Exception as exc:
        return {
            "ok": False,
            "state": "ERROR DE VALIDACIÓN",
            "can_generate_pdf": False,
            "controls": [],
            "error": str(exc),
            "metrics": {
                "requirements": {"registered": 0},
                "nuclei": {"records": 0},
                "complexive": {"registered": 0},
                "thesis": {"total": 0},
                "schedules": {"total": 0},
            },
        }


def project_overview(project_id: int) -> dict[str, Any]:
    summary = _project_summary(project_id)
    audits = {
        "presencial": _audit_safe(summary.get("presencial_report_id")),
        "en_linea": _audit_safe(summary.get("online_report_id")),
    }
    alerts = list(summary.get("alerts") or [])
    for modality, audit in audits.items():
        label = "Presencial" if modality == "presencial" else "Online"
        if not audit:
            alerts.append(f"{label}: dataset no disponible.")
            continue
        if audit.get("error"):
            alerts.append(f"{label}: {audit['error']}")
        for item in audit.get("controls", []):
            if item.get("status") in {"error", "warning"}:
                alerts.append(f"{label} · {item.get('name')}: {item.get('detail')}")

    def module_value(modality: str, module: str) -> int:
        audit = audits.get(modality) or {}
        metrics = audit.get("metrics") or {}
        row = metrics.get(module) or {}
        key = {
            "requirements": "registered",
            "nuclei": "records",
            "complexive": "registered",
            "thesis": "total",
        }[module]
        return int(row.get(key) or 0)

    modules = []
    for module, label in (
        ("requirements", "Requisitos"),
        ("nuclei", "Núcleos"),
        ("complexive", "Examen Complexivo"),
        ("thesis", "Trabajo de Titulación"),
    ):
        presencial = module_value("presencial", module)
        online = module_value("en_linea", module)
        modules.append({"module": label, "presencial": presencial, "online": online, "total": presencial + online})

    shared_schedule = 0
    for audit in audits.values():
        if audit:
            shared_schedule = max(shared_schedule, int((audit.get("metrics") or {}).get("schedules", {}).get("total") or 0))

    return {
        "ok": True,
        "project": summary,
        "audits": audits,
        "modules": modules,
        "shared_schedule": shared_schedule,
        "alerts": list(dict.fromkeys(alerts)),
    }


def _schedule_richness(row: dict[str, Any]) -> tuple[int, int]:
    score = sum(bool(clean_cell(row.get(key))) for key in ("executed_date", "execution_status", "evidence", "observation"))
    score += int(row.get("compliance_percentage") is not None)
    return score, int(row.get("id") or 0)


def sync_project_schedule(project_id: int) -> int:
    members = _members(project_id)
    report_ids = [int(row["id"]) for row in members]
    if len(report_ids) < 2:
        return 0
    with connection() as conn:
        if not _table_exists(conn, "schedule_items"):
            return 0
        columns = [str(row[1]) for row in conn.execute("PRAGMA table_info(schedule_items)").fetchall()]
        rows = rows_to_dicts(
            conn.execute(
                f"SELECT * FROM schedule_items WHERE report_id IN ({','.join('?' for _ in report_ids)}) ORDER BY sort_order, id",
                report_ids,
            ).fetchall()
        )
        if not rows:
            return 0
        merged: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in rows:
            try:
                key = (clean_cell(row.get("schedule_type")), *integrity.schedule_key(row))
            except ValueError:
                key = (clean_cell(row.get("schedule_type")), clean_cell(row.get("activity")), clean_cell(row.get("start_date")), clean_cell(row.get("end_date")))
            previous = merged.get(key)
            if previous is None or _schedule_richness(row) > _schedule_richness(previous):
                merged[key] = row

        ordered = sorted(merged.values(), key=lambda row: (clean_cell(row.get("schedule_type")), clean_cell(row.get("start_date")), clean_cell(row.get("end_date")), clean_cell(row.get("activity"))))
        insert_columns = [column for column in columns if column not in {"id", "report_id"}]
        conn.execute(
            f"DELETE FROM schedule_items WHERE report_id IN ({','.join('?' for _ in report_ids)})",
            report_ids,
        )
        for target_id in report_ids:
            order_by_type: dict[str, int] = defaultdict(int)
            for row in ordered:
                schedule_type = clean_cell(row.get("schedule_type"))
                order_by_type[schedule_type] += 1
                values = []
                for column in insert_columns:
                    if column == "sort_order":
                        values.append(order_by_type[schedule_type])
                    else:
                        values.append(row.get(column))
                conn.execute(
                    f"INSERT INTO schedule_items (report_id, {', '.join(insert_columns)}) VALUES (?, {', '.join('?' for _ in insert_columns)})",
                    (target_id, *values),
                )
    schedule_types = {clean_cell(row.get("schedule_type")) for row in ordered if clean_cell(row.get("schedule_type"))}
    for target_id in report_ids:
        for schedule_type in schedule_types:
            set_presence(target_id, f"schedule_{schedule_type}", True)
    return len(ordered)


def _mirror_schedule(base: Callable[..., dict[str, Any]], report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    result = dict(base(report_id, schedule_type, entries))
    counterpart = _counterpart_report_id(report_id)
    if counterpart:
        base(counterpart, schedule_type, entries)
        result["shared_with_report_id"] = counterpart
    return result


def replace_schedule_shared(report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    if _BASE_PROCESS_SCHEDULE is None:
        raise RuntimeError("Cronograma compartido no configurado.")
    return _mirror_schedule(_BASE_PROCESS_SCHEDULE, report_id, schedule_type, entries)


def replace_schedule_extended_shared(report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    if _BASE_COMPLETION_SCHEDULE is None:
        raise RuntimeError("Cronograma compartido no configurado.")
    return _mirror_schedule(_BASE_COMPLETION_SCHEDULE, report_id, schedule_type, entries)


def reset_schedule_shared(report_id: int, schedule_type: str) -> dict[str, Any]:
    if _BASE_RESET_SCHEDULE is None:
        raise RuntimeError("Reinicio de cronograma no configurado.")
    result = dict(_BASE_RESET_SCHEDULE(report_id, schedule_type))
    counterpart = _counterpart_report_id(report_id)
    if counterpart:
        _BASE_RESET_SCHEDULE(counterpart, schedule_type)
        result["shared_with_report_id"] = counterpart
    return result


def import_nuclei_shared(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if _BASE_NUCLEI_IMPORT is None:
        raise RuntimeError("Importación compartida de Núcleos no configurada.")
    result = dict(_BASE_NUCLEI_IMPORT(report_id, payload))
    counterpart = _counterpart_report_id(report_id)
    if counterpart:
        _BASE_NUCLEI_IMPORT(counterpart, payload)
        result["shared_with_report_id"] = counterpart
    return result


def validate_dual_preview(token: str) -> dict[str, int]:
    parsed = _load_preview(token)
    records = list(parsed.get("records") or [])
    counts = {
        "presencial": sum(row.get("modality") == "presencial" for row in records),
        "en_linea": sum(row.get("modality") == "en_linea" for row in records),
    }
    missing = ["Presencial" if key == "presencial" else "Online" for key, value in counts.items() if value == 0]
    if missing:
        raise ValueError(
            "Error de población por modalidad: el archivo no contiene registros "
            + " y ".join(missing)
            + ". Para un período regular deben existir datos Presencial y Online. Revise el archivo o la clasificación antes de importar."
        )
    return counts


def _sync_shared_general(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    project = _project_for_report(report_id)
    if not project:
        raise ValueError("El período del informe no está conciliado.")
    allowed = ["name", "period", "code", "version", "elaboration_date"]
    values = {key: payload[key] for key in allowed if key in payload}
    if not values:
        return {"ok": True}
    project_id = int(project["id"])
    now = utcnow()
    with connection() as conn:
        current = conn.execute("SELECT * FROM period_projects WHERE id=?", (project_id,)).fetchone()
        period = clean_cell(values.get("period") or current["period"])
        kind = str(current["report_type"] or period_policy_runtime.classify_period(period))
        new_key = _project_key(period, kind)
        conflict = conn.execute(
            "SELECT id FROM period_projects WHERE period_key=? AND id<>?",
            (new_key, project_id),
        ).fetchone()
        if conflict:
            raise ValueError("Ya existe otro proyecto para ese período académico.")
        assignments = []
        params: list[Any] = []
        for key in allowed:
            if key in values:
                assignments.append(f"{key}=?")
                params.append(clean_cell(values[key]))
        if "period" in values:
            assignments.extend(["period_key=?", "report_type=?"])
            params.extend([new_key, period_policy_runtime.classify_period(period)])
        assignments.append("updated_at=?")
        params.append(now)
        params.append(project_id)
        conn.execute(f"UPDATE period_projects SET {', '.join(assignments)} WHERE id=?", params)

        report_assignments = []
        report_params: list[Any] = []
        for key in allowed:
            if key in values:
                report_assignments.append(f"{key}=?")
                report_params.append(clean_cell(values[key]))
        if "period" in values:
            report_assignments.append("report_type=?")
            report_params.append(period_policy_runtime.classify_period(period))
            report_assignments.append("firebase_period_id=?")
            report_params.append(period_policy_runtime.canonical_period_id(period))
        report_assignments.append("updated_at=?")
        report_params.append(now)
        report_params.append(project_id)
        conn.execute(
            f"UPDATE reports SET {', '.join(report_assignments)} WHERE period_project_id=?",
            report_params,
        )
    return {"ok": True, "period_project_id": project_id}


def _delete_project(report_id: int) -> dict[str, Any]:
    project = _project_for_report(report_id)
    if not project:
        raise ValueError("El período no existe.")
    project_id = int(project["id"])
    filenames: list[str] = []
    with connection() as conn:
        members = [int(row[0]) for row in conn.execute("SELECT id FROM reports WHERE period_project_id=?", (project_id,)).fetchall()]
        if members and _table_exists(conn, "images"):
            filenames = [str(row[0]) for row in conn.execute(
                f"SELECT filename FROM images WHERE report_id IN ({','.join('?' for _ in members)})",
                members,
            ).fetchall()]
        for member_id in members:
            conn.execute("DELETE FROM reports WHERE id=?", (member_id,))
        conn.execute("DELETE FROM period_projects WHERE id=?", (project_id,))
    for filename in filenames:
        (core.UPLOAD_DIR / filename).unlink(missing_ok=True)
    return {"ok": True, "period_project_id": project_id}


def install() -> None:
    global _INSTALLED, _BASE_PROCESS_SCHEDULE, _BASE_COMPLETION_SCHEDULE
    global _BASE_RESET_SCHEDULE, _BASE_NUCLEI_IMPORT
    if _INSTALLED:
        return

    reconcile_projects()

    # El cronograma pertenece al período completo: cualquier edición se replica
    # a los datasets Presencial y Online y las diferencias históricas se concilian.
    _BASE_PROCESS_SCHEDULE = process_routes.replace_schedule
    _BASE_COMPLETION_SCHEDULE = completion_routes.replace_schedule_extended
    _BASE_RESET_SCHEDULE = process_routes.reset_schedule
    process_routes.replace_schedule = replace_schedule_shared
    process_service.replace_schedule = replace_schedule_shared
    completion_routes.replace_schedule_extended = replace_schedule_extended_shared
    completion_service.replace_schedule_extended = replace_schedule_extended_shared
    process_routes.reset_schedule = reset_schedule_shared
    process_service.reset_schedule = reset_schedule_shared

    # El Excel consolidado de Núcleos es una sola fuente. Se guarda en ambos
    # datasets internos y cada informe filtra después únicamente su modalidad.
    _BASE_NUCLEI_IMPORT = nuclei_routes.import_nuclei_excel
    nuclei_routes.import_nuclei_excel = import_nuclei_shared
    nuclei_excel_import.import_nuclei_excel = import_nuclei_shared

    previous_get = core.InformtitHandler._handle_api_get
    previous_write = core.InformtitHandler._handle_api_write

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/reports":
            self._send_json({"ok": True, "reports": visible_projects()})
            return

        match = re.fullmatch(r"/api/reports/(\d+)", path)
        if match:
            report = _decorated_bundle(int(match.group(1)))
            if not report:
                self._send_error_json("Informe no encontrado.", 404)
                return
            self._send_json({"ok": True, "report": report})
            return

        match = re.fullmatch(r"/api/period-projects/(\d+)/overview", path)
        if match:
            self._send_json(project_overview(int(match.group(1))))
            return

        match = re.fullmatch(r"/api/period-projects/(\d+)/export/(presencial|online)", path)
        if match:
            project_id = int(match.group(1))
            modality = "presencial" if match.group(2) == "presencial" else "en_linea"
            summary = _project_summary(project_id)
            report_id = summary.get("presencial_report_id") if modality == "presencial" else summary.get("online_report_id")
            population = summary.get("presencial_students") if modality == "presencial" else summary.get("online_students")
            label = "Presencial" if modality == "presencial" else "Online"
            if not report_id or int(population or 0) == 0:
                raise ValueError(f"No se puede generar el PDF {label}: la población de Requisitos es 0. Revise la importación.")
            output = core.build_pdf(int(report_id))
            self._serve_file(output, output.name)
            return

        previous_get(self, path, query)

    def handle_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)", path)
        if match and method == "PUT":
            self._send_json(_sync_shared_general(int(match.group(1)), payload))
            return
        if match and method == "DELETE":
            self._send_json(_delete_project(int(match.group(1))))
            return

        import_match = re.fullmatch(r"/api/reports/(\d+)/imports/([A-Za-z0-9_-]+)/commit", path)
        if import_match and method == "POST":
            with connection() as conn:
                row = conn.execute("SELECT report_type, period FROM reports WHERE id=?", (int(import_match.group(1)),)).fetchone()
            kind = str(row["report_type"] or period_policy_runtime.classify_period(row["period"])) if row else "normal"
            if kind == "normal":
                validate_dual_preview(import_match.group(2))
            previous_write(self, method, path, payload)
            reconcile_projects()
            return

        if method == "POST" and path == "/api/reports":
            previous_write(self, method, path, payload)
            reconcile_projects()
            return

        previous_write(self, method, path, payload)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
    core.InformtitHandler._period_unified_runtime_installed = True
    _INSTALLED = True
