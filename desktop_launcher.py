from __future__ import annotations

import re
from typing import Any

import app as core
from db import connection, rows_to_dicts
from import_service import (
    commit_preview,
    create_preview,
    ensure_schema,
    get_settings,
    merge_moodle_notes,
    settings_for_report,
    update_settings,
)


core.MAX_BODY_BYTES = 25 * 1024 * 1024

_original_get = core.InformtitHandler._handle_api_get
_original_write = core.InformtitHandler._handle_api_write


def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
    if path == "/api/institutional-settings":
        self._send_json({"ok": True, "settings": get_settings()})
        return

    if path == "/api/import-history":
        ensure_schema()
        with connection() as conn:
            rows = rows_to_dicts(
                conn.execute(
                    "SELECT * FROM import_history ORDER BY id DESC LIMIT 20"
                ).fetchall()
            )
        self._send_json({"ok": True, "imports": rows})
        return

    _original_get(self, path, query)


def _handle_api_write(
    self, method: str, path: str, payload: dict[str, Any]
) -> None:
    if method == "POST" and path == "/api/imports/preview":
        filename = str(payload.get("original_name", "")).strip()
        data_url = str(payload.get("data_url", ""))
        if not filename:
            raise ValueError("Seleccione el archivo de reporte.")
        result = create_preview(data_url, filename)
        self._send_json({"ok": True, "preview": result}, 201)
        return

    match = re.fullmatch(r"/api/imports/([A-Za-z0-9_-]{10,80})/commit", path)
    if method == "POST" and match:
        result = commit_preview(match.group(1), payload)
        self._send_json(result, 201)
        return

    if path == "/api/institutional-settings" and method == "PUT":
        settings = update_settings(payload)
        self._send_json({"ok": True, "settings": settings})
        return

    if method == "POST" and path == "/api/reports":
        payload = {**settings_for_report(), **payload}
        _original_write(self, method, path, payload)
        return

    match = re.fullmatch(r"/api/careers/(\d+)/parse", path)
    if method == "POST" and match:
        raw_text = str(payload.get("text", ""))
        if not raw_text.strip():
            raise ValueError("Pegue el contenido de las calificaciones.")
        result = merge_moodle_notes(
            int(match.group(1)), raw_text, bool(payload.get("replace", True))
        )
        status = 200 if result.get("ok") else 422
        self._send_json(result, status)
        return

    _original_write(self, method, path, payload)


core.InformtitHandler._handle_api_get = _handle_api_get
core.InformtitHandler._handle_api_write = _handle_api_write


def main() -> None:
    # En una instalación nueva primero se crean las tablas base y luego se
    # aplican las ampliaciones para importación y configuración institucional.
    core.init_db()
    ensure_schema()
    core.main()


if __name__ == "__main__":
    main()
