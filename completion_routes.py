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
from eligibility_service import get_eligibility


def install() -> None:
    ensure_completion_schema()
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

        match = re.fullmatch(r"/api/reports/(\d+)/nuclei/eligibility", path)
        if match:
            self._send_json({"ok": True, **get_eligibility(int(match.group(1)))})
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
            entries = payload.get("entries")
            if not isinstance(entries, list):
                raise ValueError("Envíe las actividades del cronograma como una lista.")
            self._send_json(
                replace_schedule_extended(
                    int(match.group(1)), match.group(2), entries
                )
            )
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

        original_write(self, method, path, payload)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
