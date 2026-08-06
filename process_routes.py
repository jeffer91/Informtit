from __future__ import annotations

import re
from typing import Any

import app as core
from process_service import (
    delete_project,
    ensure_process_schema,
    get_projects,
    get_schedules,
    parse_project_text,
    parse_schedule_text,
    parse_schedule_upload,
    replace_schedule,
    reset_schedule,
)


BACKEND_VERSION = "1.1"
CAPABILITIES = ["roster", "complexive", "schedules", "thesis_projects"]


def install() -> None:
    """Instala las rutas adicionales sobre el manejador ya configurado.

    Debe ejecutarse después de importar ``desktop_launcher`` para envolver el
    manejador definitivo utilizado por Electron.
    """

    ensure_process_schema()
    original_get = core.InformtitHandler._handle_api_get
    original_write = core.InformtitHandler._handle_api_write

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "app": "Informtit",
                    "version": BACKEND_VERSION,
                    "database": "SQLite local",
                    "capabilities": CAPABILITIES,
                }
            )
            return

        match = re.fullmatch(r"/api/reports/(\d+)/schedules", path)
        if match:
            self._send_json(
                {
                    "ok": True,
                    "schedules": get_schedules(int(match.group(1))),
                }
            )
            return

        match = re.fullmatch(r"/api/reports/(\d+)/projects", path)
        if match:
            self._send_json(
                {"ok": True, **get_projects(int(match.group(1)))}
            )
            return

        original_get(self, path, query)

    def handle_write(
        self: Any,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> None:
        match = re.fullmatch(
            r"/api/reports/(\d+)/schedules/(complexive|thesis)", path
        )
        if match and method == "PUT":
            report_id = int(match.group(1))
            schedule_type = match.group(2)
            entries = payload.get("entries")
            if not isinstance(entries, list):
                raise ValueError(
                    "Envíe las actividades del cronograma como una lista."
                )
            self._send_json(
                replace_schedule(report_id, schedule_type, entries)
            )
            return

        match = re.fullmatch(
            r"/api/reports/(\d+)/schedules/(complexive|thesis)/reset",
            path,
        )
        if match and method == "POST":
            self._send_json(
                reset_schedule(int(match.group(1)), match.group(2))
            )
            return

        match = re.fullmatch(
            r"/api/reports/(\d+)/schedules/(complexive|thesis)/parse",
            path,
        )
        if match and method == "POST":
            schedule_type = match.group(2)
            if payload.get("data_url"):
                entries = parse_schedule_upload(
                    str(payload.get("data_url")),
                    str(payload.get("filename") or "cronograma.xls"),
                    schedule_type,
                )
            else:
                entries = parse_schedule_text(
                    str(payload.get("text") or ""), schedule_type
                )
            if not entries:
                raise ValueError(
                    "No se detectaron actividades con fecha de inicio y fin."
                )
            self._send_json({"ok": True, "entries": entries})
            return

        match = re.fullmatch(r"/api/reports/(\d+)/projects/parse", path)
        if match and method == "POST":
            self._send_json(
                parse_project_text(int(match.group(1)), payload), 201
            )
            return

        match = re.fullmatch(r"/api/reports/(\d+)/projects/(\d+)", path)
        if match and method == "DELETE":
            self._send_json(
                delete_project(int(match.group(1)), int(match.group(2)))
            )
            return

        original_write(self, method, path, payload)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
