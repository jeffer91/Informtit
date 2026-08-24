from __future__ import annotations

from typing import Any, Callable

import completion_routes
import completion_service
import process_routes
import process_service
import report_integrity_final_fixes as final_fixes
from db import connection
from optional_content import is_present, set_presence
from process_service import COMPLEXIVE_DEFAULTS, THESIS_DEFAULTS


_INSTALLED = False


def _with_presence(function: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def wrapped(report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
        result = dict(function(report_id, schedule_type, entries))
        set_presence(report_id, f"schedule_{schedule_type}", True)
        return result

    return wrapped


def repair_schedule_presence() -> int:
    """Recupera cronogramas reales que pudieron quedar ocultos por una capa anterior.

    Los cronogramas por defecto siguen marcados como ausentes; únicamente se
    reactiva la presencia cuando existen filas distintas de la plantilla base.
    """
    defaults = {
        "complexive": list(COMPLEXIVE_DEFAULTS),
        "thesis": list(THESIS_DEFAULTS),
    }
    candidates: list[tuple[int, str]] = []

    # Primero se identifican los cronogramas reales y se cierra la conexión.
    # Las funciones is_present/set_presence abren su propia conexión, por lo que
    # no se ejecutan dentro de este bloque para evitar bloqueos de SQLite.
    with connection() as conn:
        report_ids = [
            int(row[0])
            for row in conn.execute("SELECT DISTINCT report_id FROM schedule_items").fetchall()
        ]
        for report_id in report_ids:
            for schedule_type in ("complexive", "thesis"):
                rows = conn.execute(
                    """
                    SELECT phase, activity, start_date, end_date
                    FROM schedule_items
                    WHERE report_id=? AND schedule_type=?
                    ORDER BY sort_order, id
                    """,
                    (report_id, schedule_type),
                ).fetchall()
                current = [tuple(row) for row in rows]
                if current and current != defaults[schedule_type]:
                    candidates.append((report_id, schedule_type))

    repaired = 0
    for report_id, schedule_type in candidates:
        key = f"schedule_{schedule_type}"
        if not is_present(report_id, key):
            set_presence(report_id, key, True)
            repaired += 1
    return repaired


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # La capa de integridad reemplaza las funciones de guardado para deduplicar.
    # Se vuelve a añadir explícitamente la marca de presencia para que el
    # cronograma guardado no desaparezca del análisis ni de la auditoría.
    process_routes.replace_schedule = _with_presence(process_routes.replace_schedule)
    completion_routes.replace_schedule_extended = _with_presence(
        completion_routes.replace_schedule_extended
    )

    # También se protegen llamadas directas a los servicios.
    process_service.replace_schedule = _with_presence(process_service.replace_schedule)
    completion_service.replace_schedule_extended = _with_presence(
        completion_service.replace_schedule_extended
    )

    repair_schedule_presence()

    # Activa realmente las correcciones finales de empates y conteo de ceros.
    final_fixes.install()
    _INSTALLED = True
