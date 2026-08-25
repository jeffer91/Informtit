from __future__ import annotations

import re
from typing import Any, Callable

import app as core
from student_period_service import (
    confirm_period_source_link,
    get_period_student_domain,
    set_period_student_process_status,
    set_period_student_route,
)

_INSTALLED = False
_BASE_GET: Callable[..., Any] | None = None
_BASE_WRITE: Callable[..., Any] | None = None


def install() -> None:
    global _INSTALLED, _BASE_GET, _BASE_WRITE
    if _INSTALLED:
        return
    _BASE_GET = core.InformtitHandler._handle_api_get
    _BASE_WRITE = core.InformtitHandler._handle_api_write

    def api_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(r"/api/period-projects/(\d+)/students-domain", path)
        if match:
            self._send_json(get_period_student_domain(int(match.group(1))))
            return
        assert _BASE_GET is not None
        _BASE_GET(self, path, query)

    def api_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        match = re.fullmatch(r"/api/period-projects/(\d+)/students-domain/(\d+)/route", path)
        if match and method in {"POST", "PUT"}:
            self._send_json(set_period_student_route(
                int(match.group(1)), int(match.group(2)), str(payload.get("route") or "")
            ))
            return
        match = re.fullmatch(r"/api/period-projects/(\d+)/students-domain/(\d+)/process-status", path)
        if match and method in {"POST", "PUT"}:
            self._send_json(set_period_student_process_status(
                int(match.group(1)), int(match.group(2)), str(payload.get("process_status") or "")
            ))
            return
        match = re.fullmatch(r"/api/period-projects/(\d+)/students-domain/matches/(\d+)/confirm", path)
        if match and method in {"POST", "PUT"}:
            self._send_json(confirm_period_source_link(
                int(match.group(1)),
                int(match.group(2)),
                int(payload.get("student_id") or 0),
            ))
            return
        assert _BASE_WRITE is not None
        _BASE_WRITE(self, method, path, payload)

    core.InformtitHandler._handle_api_get = api_get
    core.InformtitHandler._handle_api_write = api_write
    _INSTALLED = True
