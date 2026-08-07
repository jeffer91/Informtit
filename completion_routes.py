from __future__ import annotations

import re
from typing import Any

import app as core
from completion_service import (
    ensure_completion_schema,
    get_completion_data,
    get_schedules_extended,
    replace_completion_data,
    replace_schedule_extended,
)
from optional_content import set_presence
from thesis_followup import ensure_thesis_followup_schema, update_project_followup


def install() -> None:
    ensure_completion_schema()
    ensure_thesis_followup_schema()
    original_get = core.InformtitHandler._handle_api_get
    original_write = core.InformtitHandler._handle_api_write

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)/schedules", path)
        if match:
            self._send_json(
                {
                    "ok": True,
                    "schedules": get_schedules_extended(int(match.group(1))),
                }
            )
            return

        match = re.fullmatch(r"/api/reports/(\d+)/completion", path)
        if match:
            self._send_json({"ok": True, **get_completion_data(int(match.group(1)))})
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
                raise ValueError("Envíe las actividades del cronograma como una lista.")
            result = replace_schedule_extended(report_id, schedule_type, entries)
            set_presence(report_id, f"schedule_{schedule_type}", True)
            self._send_json(result)
            return

        match = re.fullmatch(r"/api/reports/(\d+)/completion", path)
        if match and method == "PUT":
            incidents = payload.get("incidents")
            actions = payload.get("actions")
            if not isinstance(incidents, list) or not isinstance(actions, list):
                raise ValueError("Las incidencias y acciones deben enviarse como listas.")
            self._send_json(
                replace_completion_data(int(match.group(1)), incidents, actions)
            )
            return

        match = re.fullmatch(r"/api/reports/(\d+)/projects/(\d+)/followup", path)
        if match and method == "PUT":
            self._send_json(
                update_project_followup(
                    int(match.group(1)), int(match.group(2)), payload
                )
            )
            return

        original_write(self, method, path, payload)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
