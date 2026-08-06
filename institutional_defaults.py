from __future__ import annotations

from typing import Any

from db import utcnow


DEFAULT_RESPONSIBLES: dict[str, str] = {
    "prepared_by": "Mgs. Jefferson Villarreal",
    "prepared_role": "COORDINADOR DE TITULACIÓN",
    "reviewed_by": "Ing. Martha Tomalá",
    "reviewed_role": "COORDINADORA GENERAL DE CARRERAS",
    "approved_by": "Dr. Alex León T.",
    "approved_role": "VICERRECTOR",
}

LEGACY_DEFAULTS: dict[str, str] = {
    "prepared_role": "COORDINADOR DE CARRERAS",
}


def value(report: dict[str, Any], key: str) -> str:
    current = str(report.get(key) or "").strip()
    return current or DEFAULT_RESPONSIBLES[key]


def apply_defaults(conn: Any) -> None:
    """Completa responsables vacíos y migra únicamente valores predeterminados anteriores."""

    settings = conn.execute(
        "SELECT * FROM institutional_settings WHERE id = 1"
    ).fetchone()
    if settings:
        assignments: list[str] = []
        values: list[str] = []
        for key, default in DEFAULT_RESPONSIBLES.items():
            current = str(settings[key] or "").strip()
            legacy = LEGACY_DEFAULTS.get(key)
            if not current or (legacy and current == legacy):
                assignments.append(f"{key} = ?")
                values.append(default)
        if assignments:
            assignments.append("updated_at = ?")
            values.extend([utcnow(), 1])
            conn.execute(
                f"UPDATE institutional_settings SET {', '.join(assignments)} WHERE id = ?",
                values,
            )

    for key, default in DEFAULT_RESPONSIBLES.items():
        legacy = LEGACY_DEFAULTS.get(key)
        if legacy:
            conn.execute(
                f"UPDATE reports SET {key} = ?, updated_at = ? "
                f"WHERE TRIM(COALESCE({key}, '')) = '' OR TRIM({key}) = ?",
                (default, utcnow(), legacy),
            )
        else:
            conn.execute(
                f"UPDATE reports SET {key} = ?, updated_at = ? "
                f"WHERE TRIM(COALESCE({key}, '')) = ''",
                (default, utcnow()),
            )
