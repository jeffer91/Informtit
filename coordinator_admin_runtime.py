from __future__ import annotations

import re
from typing import Any

import app as core
import coordinator_registry


_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    coordinator_registry.ensure_schema()
    previous_get = core.InformtitHandler._handle_api_get
    previous_write = core.InformtitHandler._handle_api_write

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/coordinators":
            self._send_json(
                {
                    "ok": True,
                    "coordinators": coordinator_registry.list_coordinators(),
                    "careers": coordinator_registry.available_careers(),
                }
            )
            return
        previous_get(self, path, query)

    def handle_write(
        self: Any,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> None:
        match = re.fullmatch(r"/api/coordinators/(\d+)", path)
        if match and method == "PUT":
            coordinator_id = int(match.group(1))
            updated = coordinator_registry.update_coordinator(
                coordinator_id,
                name=str(payload.get("name") or "").strip(),
                telegram=str(payload.get("telegram") or "").strip(),
                careers=payload.get("careers") or [],
            )
            self._send_json({"ok": True, "coordinator": updated})
            return

        if method == "POST" and path == "/api/coordinators":
            created = coordinator_registry.create_coordinator(
                name=str(payload.get("name") or "").strip(),
                telegram=str(payload.get("telegram") or "").strip(),
                careers=payload.get("careers") or [],
            )
            self._send_json({"ok": True, "coordinator": created}, 201)
            return

        previous_write(self, method, path, payload)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
    _INSTALLED = True
