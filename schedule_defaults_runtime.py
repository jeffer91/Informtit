from __future__ import annotations

from typing import Any, Callable

import process_routes
import process_service
from db import connection, utcnow


_INSTALLED = False
_BASE_SEED: Callable[..., None] | None = None


def _table_exists(conn: Any, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _matches_defaults(rows: list[Any], defaults: list[tuple[str, str, str, str]]) -> bool:
    current = [
        (
            str(row["phase"] or ""),
            str(row["activity"] or ""),
            str(row["start_date"] or ""),
            str(row["end_date"] or ""),
        )
        for row in rows
    ]
    return current == list(defaults)


def _has_execution(rows: list[Any], columns: set[str]) -> bool:
    execution_fields = {
        "executed_date",
        "execution_status",
        "compliance_percentage",
        "evidence",
        "observation",
    }
    if not execution_fields.issubset(columns):
        return False
    return any(
        str(row["executed_date"] or "").strip()
        or str(row["execution_status"] or "").strip()
        or row["compliance_percentage"] is not None
        or str(row["evidence"] or "").strip()
        or str(row["observation"] or "").strip()
        for row in rows
    )


def cleanup_untouched_defaults() -> int:
    """Elimina solo semillas históricas idénticas y nunca trabajo del usuario."""
    deleted = 0
    with connection() as conn:
        if not _table_exists(conn, "schedule_items"):
            return 0
        columns = _columns(conn, "schedule_items")
        select_columns = [
            "phase",
            "activity",
            "start_date",
            "end_date",
        ]
        for optional in (
            "executed_date",
            "execution_status",
            "compliance_percentage",
            "evidence",
            "observation",
        ):
            if optional in columns:
                select_columns.append(optional)

        report_ids = [
            int(row[0])
            for row in conn.execute("SELECT id FROM reports ORDER BY id").fetchall()
        ]
        defaults_by_type = {
            "complexive": process_service.COMPLEXIVE_DEFAULTS,
            "thesis": process_service.THESIS_DEFAULTS,
        }
        for report_id in report_ids:
            for schedule_type, defaults in defaults_by_type.items():
                rows = conn.execute(
                    f"""
                    SELECT {', '.join(select_columns)} FROM schedule_items
                    WHERE report_id=? AND schedule_type=?
                    ORDER BY sort_order, id
                    """,
                    (report_id, schedule_type),
                ).fetchall()
                if not rows:
                    continue
                if not _matches_defaults(rows, defaults) or _has_execution(rows, columns):
                    continue
                cursor = conn.execute(
                    "DELETE FROM schedule_items WHERE report_id=? AND schedule_type=?",
                    (report_id, schedule_type),
                )
                deleted += int(cursor.rowcount or 0)
                if _table_exists(conn, "content_presence"):
                    conn.execute(
                        """
                        INSERT INTO content_presence
                        (report_id, content_key, included, updated_at)
                        VALUES (?, ?, 0, ?)
                        ON CONFLICT(report_id, content_key) DO UPDATE SET
                            included=0, updated_at=excluded.updated_at
                        """,
                        (report_id, f"schedule_{schedule_type}", utcnow()),
                    )
    return deleted


def seed_schedules_without_legacy_defaults(
    conn: Any,
    report_id: int,
    force: bool = False,
) -> None:
    """Los períodos nuevos nacen sin fechas heredadas de 2025/2026."""
    # La creación/lectura normal ya no inserta fechas históricas. Los reinicios
    # se gestionan por tipo en reset_schedule_empty().
    return


def reset_schedule_empty(report_id: int, schedule_type: str) -> dict[str, Any]:
    if schedule_type not in {"complexive", "thesis"}:
        raise ValueError("Tipo de cronograma no válido.")
    with connection() as conn:
        conn.execute(
            "DELETE FROM schedule_items WHERE report_id=? AND schedule_type=?",
            (int(report_id), schedule_type),
        )
    return {"ok": True, "count": 0}


def install() -> None:
    global _INSTALLED, _BASE_SEED
    if _INSTALLED:
        return

    _BASE_SEED = process_service.seed_schedules
    cleanup_untouched_defaults()
    process_service.seed_schedules = seed_schedules_without_legacy_defaults
    process_service.reset_schedule = reset_schedule_empty
    process_routes.reset_schedule = reset_schedule_empty
    process_service._legacy_schedule_defaults_disabled = True
    _INSTALLED = True
