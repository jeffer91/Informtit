from __future__ import annotations

from typing import Any

from db import connection, utcnow
from import_service import clean_cell


FOLLOWUP_FIELDS = {
    "project_modality": "TEXT DEFAULT ''",
    "topic": "TEXT DEFAULT ''",
    "tutor_name": "TEXT DEFAULT ''",
    "draft_1_status": "TEXT DEFAULT ''",
    "draft_2_status": "TEXT DEFAULT ''",
    "tutor_approval": "TEXT DEFAULT ''",
    "plagiarism_result": "TEXT DEFAULT ''",
    "defense_eligible": "TEXT DEFAULT ''",
    "supplementary_defense": "TEXT DEFAULT ''",
    "process_status": "TEXT DEFAULT ''",
}


def ensure_thesis_followup_schema() -> None:
    with connection() as conn:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(thesis_projects)").fetchall()
        }
        for field, definition in FOLLOWUP_FIELDS.items():
            if field not in columns:
                conn.execute(
                    f"ALTER TABLE thesis_projects ADD COLUMN {field} {definition}"
                )


def update_project_followup(
    report_id: int,
    project_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    ensure_thesis_followup_schema()
    values = {field: clean_cell(payload.get(field)) for field in FOLLOWUP_FIELDS}
    assignments = ", ".join(f"{field}=?" for field in FOLLOWUP_FIELDS)
    parameters = [values[field] for field in FOLLOWUP_FIELDS]
    parameters.extend([utcnow(), project_id, report_id])
    with connection() as conn:
        cursor = conn.execute(
            f"UPDATE thesis_projects SET {assignments}, updated_at=? WHERE id=? AND report_id=?",
            parameters,
        )
    if not cursor.rowcount:
        raise ValueError("El registro de Trabajo de Titulación no existe.")
    return {"ok": True, "project_id": project_id, **values}
