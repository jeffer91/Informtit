from __future__ import annotations

from typing import Any

from db import connection


_INSTALLED = False


def install() -> dict[str, Any]:
    """Activa WAL y valida rápidamente la base persistente.

    WAL reduce bloqueos entre lecturas de interfaz y escrituras de importación.
    El `timeout` de sqlite3 ya es de 5 segundos por defecto; WAL complementa ese
    comportamiento sin cambiar la API de conexión usada por los módulos actuales.
    """
    global _INSTALLED
    if _INSTALLED:
        return {"ok": True, "already_installed": True}

    with connection() as conn:
        journal_mode = str(conn.execute("PRAGMA journal_mode=WAL").fetchone()[0])
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        quick_check = str(conn.execute("PRAGMA quick_check").fetchone()[0])

    if quick_check.casefold() != "ok":
        raise RuntimeError(f"SQLite reportó una inconsistencia: {quick_check}")

    _INSTALLED = True
    return {
        "ok": True,
        "journal_mode": journal_mode,
        "quick_check": quick_check,
    }
