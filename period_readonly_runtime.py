from __future__ import annotations

from typing import Any

import period_unified_runtime as unified
from db import connection


_INSTALLED = False


def _project_for_report_read_only(report_id: int) -> dict[str, Any] | None:
    """Obtiene el proyecto del informe sin reconciliar ni modificar la base."""
    unified.ensure_schema()
    with connection() as conn:
        row = conn.execute(
            """
            SELECT p.* FROM period_projects p
            JOIN reports r ON r.period_project_id=p.id
            WHERE r.id=?
            """,
            (int(report_id),),
        ).fetchone()
    return dict(row) if row else None


def visible_projects_read_only() -> list[dict[str, Any]]:
    """Lista los proyectos existentes; un GET nunca debe reescribir datos."""
    unified.ensure_schema()
    with connection() as conn:
        ids = [
            int(row[0])
            for row in conn.execute(
                "SELECT id FROM period_projects ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        ]
    return [unified._project_summary(project_id) for project_id in ids]


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # period_unified_runtime ya ejecuta la conciliación una vez durante el arranque
    # y después de las operaciones de escritura que crean/importan períodos. Desde
    # este punto, las rutas GET quedan estrictamente de lectura.
    unified._project_for_report = _project_for_report_read_only
    unified.visible_projects = visible_projects_read_only
    _INSTALLED = True
