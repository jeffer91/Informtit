from __future__ import annotations

from typing import Any

from db import connection, rows_to_dicts, utcnow
from import_service import clean_cell
from process_service import _valid_date, seed_schedules


EXECUTION_STATUSES = {
    "",
    "Cumplido",
    "Cumplido con retraso",
    "Cumplido parcialmente",
    "No cumplido",
    "Reprogramado",
}

INCIDENT_STATUSES = {"Abierto", "En seguimiento", "Resuelto"}
ACTION_STATUSES = {"Pendiente", "En ejecución", "Cumplida"}


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_completion_schema() -> None:
    with connection() as conn:
        schedule_columns = _columns(conn, "schedule_items")
        additions = {
            "executed_date": "TEXT DEFAULT ''",
            "execution_status": "TEXT DEFAULT ''",
            "compliance_percentage": "REAL",
            "evidence": "TEXT DEFAULT ''",
            "observation": "TEXT DEFAULT ''",
        }
        for column, definition in additions.items():
            if column not in schedule_columns:
                conn.execute(f"ALTER TABLE schedule_items ADD COLUMN {column} {definition}")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS report_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                category TEXT DEFAULT '',
                description TEXT NOT NULL,
                responsible TEXT DEFAULT '',
                treatment TEXT DEFAULT '',
                status TEXT DEFAULT 'Abierto',
                evidence TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS improvement_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                finding TEXT NOT NULL,
                action TEXT NOT NULL,
                responsible TEXT DEFAULT '',
                due_date TEXT DEFAULT '',
                indicator TEXT DEFAULT '',
                evidence TEXT DEFAULT '',
                status TEXT DEFAULT 'Pendiente',
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            );
            """
        )


def _optional_date(value: Any) -> str:
    text = clean_cell(value)
    return _valid_date(text) if text else ""


def _optional_percentage(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", "."))
    except ValueError as exc:
        raise ValueError("El porcentaje de cumplimiento no es válido.") from exc
    if not 0 <= number <= 100:
        raise ValueError("El porcentaje de cumplimiento debe estar entre 0 y 100.")
    return round(number, 2)


def get_schedules_extended(report_id: int) -> dict[str, Any]:
    ensure_completion_schema()
    with connection() as conn:
        seed_schedules(conn, report_id)
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM schedule_items
                WHERE report_id=? ORDER BY schedule_type, sort_order, id
                """,
                (report_id,),
            ).fetchall()
        )
    return {
        "complexive": [row for row in rows if row["schedule_type"] == "complexive"],
        "thesis": [row for row in rows if row["schedule_type"] == "thesis"],
    }


def replace_schedule_extended(report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_completion_schema()
    if schedule_type not in {"complexive", "thesis"}:
        raise ValueError("Tipo de cronograma no válido.")

    cleaned: list[dict[str, Any]] = []
    for entry in entries:
        activity = clean_cell(entry.get("activity"))
        if not activity:
            continue
        status = clean_cell(entry.get("execution_status"))
        if status not in EXECUTION_STATUSES:
            raise ValueError(f"El estado de ejecución '{status}' no es válido.")
        percentage = _optional_percentage(entry.get("compliance_percentage"))
        if percentage is None and status:
            percentage = {
                "Cumplido": 100.0,
                "Cumplido con retraso": 100.0,
                "Cumplido parcialmente": 50.0,
                "No cumplido": 0.0,
            }.get(status)
        cleaned.append(
            {
                "phase": clean_cell(entry.get("phase")) if schedule_type == "thesis" else "",
                "activity": activity,
                "start_date": _valid_date(str(entry.get("start_date") or "")),
                "end_date": _valid_date(str(entry.get("end_date") or "")),
                "executed_date": _optional_date(entry.get("executed_date")),
                "execution_status": status,
                "compliance_percentage": percentage,
                "evidence": clean_cell(entry.get("evidence")),
                "observation": clean_cell(entry.get("observation")),
            }
        )

    if not cleaned:
        raise ValueError("El cronograma no contiene actividades válidas.")

    now = utcnow()
    with connection() as conn:
        conn.execute(
            "DELETE FROM schedule_items WHERE report_id=? AND schedule_type=?",
            (report_id, schedule_type),
        )
        for order, entry in enumerate(cleaned, start=1):
            conn.execute(
                """
                INSERT INTO schedule_items
                (report_id, schedule_type, phase, activity, start_date, end_date,
                 executed_date, execution_status, compliance_percentage, evidence,
                 observation, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    schedule_type,
                    entry["phase"],
                    entry["activity"],
                    entry["start_date"],
                    entry["end_date"],
                    entry["executed_date"],
                    entry["execution_status"],
                    entry["compliance_percentage"],
                    entry["evidence"],
                    entry["observation"],
                    order,
                    now,
                    now,
                ),
            )
    return {"ok": True, "count": len(cleaned)}


def _clean_incident(item: dict[str, Any]) -> dict[str, Any] | None:
    description = clean_cell(item.get("description"))
    if not description:
        return None
    status = clean_cell(item.get("status")) or "Abierto"
    if status not in INCIDENT_STATUSES:
        raise ValueError(f"El estado de incidencia '{status}' no es válido.")
    return {
        "category": clean_cell(item.get("category")),
        "description": description,
        "responsible": clean_cell(item.get("responsible")),
        "treatment": clean_cell(item.get("treatment")),
        "status": status,
        "evidence": clean_cell(item.get("evidence")),
    }


def _clean_action(item: dict[str, Any]) -> dict[str, Any] | None:
    finding = clean_cell(item.get("finding"))
    action = clean_cell(item.get("action"))
    if not finding and not action:
        return None
    if not finding or not action:
        raise ValueError("Cada acción de mejora debe incluir el hallazgo y la acción propuesta.")
    status = clean_cell(item.get("status")) or "Pendiente"
    if status not in ACTION_STATUSES:
        raise ValueError(f"El estado de la acción '{status}' no es válido.")
    return {
        "finding": finding,
        "action": action,
        "responsible": clean_cell(item.get("responsible")),
        "due_date": _optional_date(item.get("due_date")),
        "indicator": clean_cell(item.get("indicator")),
        "evidence": clean_cell(item.get("evidence")),
        "status": status,
    }


def get_completion_data(report_id: int) -> dict[str, Any]:
    ensure_completion_schema()
    with connection() as conn:
        incidents = rows_to_dicts(
            conn.execute(
                "SELECT * FROM report_incidents WHERE report_id=? ORDER BY sort_order, id",
                (report_id,),
            ).fetchall()
        )
        actions = rows_to_dicts(
            conn.execute(
                "SELECT * FROM improvement_actions WHERE report_id=? ORDER BY sort_order, id",
                (report_id,),
            ).fetchall()
        )
    return {"incidents": incidents, "actions": actions}


def replace_completion_data(report_id: int, incidents: list[dict[str, Any]], actions: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_completion_schema()
    cleaned_incidents = [cleaned for item in incidents if (cleaned := _clean_incident(item))]
    cleaned_actions = [cleaned for item in actions if (cleaned := _clean_action(item))]
    now = utcnow()
    with connection() as conn:
        conn.execute("DELETE FROM report_incidents WHERE report_id=?", (report_id,))
        conn.execute("DELETE FROM improvement_actions WHERE report_id=?", (report_id,))
        for order, item in enumerate(cleaned_incidents, start=1):
            conn.execute(
                """
                INSERT INTO report_incidents
                (report_id, category, description, responsible, treatment, status,
                 evidence, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    item["category"],
                    item["description"],
                    item["responsible"],
                    item["treatment"],
                    item["status"],
                    item["evidence"],
                    order,
                    now,
                    now,
                ),
            )
        for order, item in enumerate(cleaned_actions, start=1):
            conn.execute(
                """
                INSERT INTO improvement_actions
                (report_id, finding, action, responsible, due_date, indicator,
                 evidence, status, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    item["finding"],
                    item["action"],
                    item["responsible"],
                    item["due_date"],
                    item["indicator"],
                    item["evidence"],
                    item["status"],
                    order,
                    now,
                    now,
                ),
            )
    return {
        "ok": True,
        "incident_count": len(cleaned_incidents),
        "action_count": len(cleaned_actions),
    }
