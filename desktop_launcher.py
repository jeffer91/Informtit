from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Any

import app as core
from db import (
    connection,
    refresh_report_sections,
    restore_section_template,
    rows_to_dicts,
    utcnow,
)
from import_service import (
    commit_preview,
    create_preview,
    ensure_schema,
    get_settings,
    merge_moodle_notes,
    settings_for_report,
    update_settings,
)
from roster_service import commit_preview_to_report, get_report_roster


core.MAX_BODY_BYTES = 25 * 1024 * 1024

_original_get = core.InformtitHandler._handle_api_get
_original_write = core.InformtitHandler._handle_api_write


def _serve_file_no_cache(
    self, path: Path, download_name: str | None = None
) -> None:
    """Sirve la interfaz sin caché para que Electron muestre cada actualización."""
    if not path.exists() or not path.is_file():
        self._send_error_json("Archivo no encontrado.", 404)
        return

    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    size = path.stat().st_size
    self.send_response(200)
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(size))
    self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
    self.send_header("Pragma", "no-cache")
    self.send_header("Expires", "0")
    self.send_header("X-Informtit-Frontend", "0.6")
    if download_name:
        self.send_header(
            "Content-Disposition", f'attachment; filename="{download_name}"'
        )
    self.end_headers()

    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 256):
            self.wfile.write(chunk)


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

    match = re.fullmatch(r"/api/reports/(\d+)/roster", path)
    if match:
        self._send_json(get_report_roster(int(match.group(1))))
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

    match = re.fullmatch(
        r"/api/reports/(\d+)/imports/([A-Za-z0-9_-]{10,80})/commit", path
    )
    if method == "POST" and match:
        result = commit_preview_to_report(
            match.group(2), int(match.group(1)), payload
        )
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

    report_match = re.fullmatch(r"/api/reports/(\d+)", path)
    if method == "PUT" and report_match:
        report_id = int(report_match.group(1))
        _original_write(self, method, path, payload)
        if any(key in payload for key in ("period", "modality", "name")):
            with connection() as conn:
                refresh_report_sections(conn, report_id)
        return

    section_match = re.fullmatch(r"/api/reports/(\d+)/sections/(\d+)", path)
    if method == "PUT" and section_match:
        report_id, section_id = map(int, section_match.groups())
        with connection() as conn:
            if payload.get("restore_template"):
                restore_section_template(conn, report_id, section_id)
            else:
                fields: list[str] = []
                values: list[Any] = []
                if "content" in payload:
                    fields.extend(["content = ?", "customized = 1"])
                    values.append(str(payload.get("content") or ""))
                if "visible" in payload:
                    fields.append("visible = ?")
                    values.append(1 if payload.get("visible") else 0)
                if "sort_order" in payload:
                    fields.append("sort_order = ?")
                    values.append(int(payload.get("sort_order") or 0))
                if not fields:
                    raise ValueError("No se enviaron cambios para la sección.")
                fields.append("updated_at = ?")
                values.extend([utcnow(), section_id, report_id])
                conn.execute(
                    f"""
                    UPDATE institutional_sections SET {', '.join(fields)}
                    WHERE id = ? AND report_id = ?
                    """,
                    values,
                )
        self._send_json({"ok": True})
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


core.InformtitHandler._serve_file = _serve_file_no_cache
core.InformtitHandler._handle_api_get = _handle_api_get
core.InformtitHandler._handle_api_write = _handle_api_write


def main() -> None:
    core.init_db()
    ensure_schema()
    core.main()


if __name__ == "__main__":
    main()
