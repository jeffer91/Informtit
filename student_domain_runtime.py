from __future__ import annotations

import re
from typing import Any, Callable

import app as core
from student_domain_service import (
    confirm_source_link,
    ensure_student_domain_schema,
    get_period_students,
    get_student_audit,
    set_process_status,
    set_student_route,
    sync_report_students,
)

_INSTALLED = False
_BASE_GET: Callable[..., Any] | None = None
_BASE_WRITE: Callable[..., Any] | None = None


def install() -> None:
    global _INSTALLED, _BASE_GET, _BASE_WRITE
    if _INSTALLED:
        return
    ensure_student_domain_schema()
    _BASE_GET = core.InformtitHandler._handle_api_get
    _BASE_WRITE = core.InformtitHandler._handle_api_write

    def api_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)/students-domain", path)
        if match:
            self._send_json(get_period_students(int(match.group(1))))
            return
        match = re.fullmatch(r"/api/reports/(\d+)/students-domain/audit", path)
        if match:
            student_id = int(query.get("student_id", ["0"])[0] or 0)
            self._send_json(get_student_audit(int(match.group(1)), student_id or None))
            return
        assert _BASE_GET is not None
        _BASE_GET(self, path, query)

    def api_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)/students-domain/sync", path)
        if match and method == "POST":
            self._send_json(sync_report_students(int(match.group(1))))
            return
        match = re.fullmatch(r"/api/reports/(\d+)/students-domain/(\d+)/route", path)
        if match and method in {"PUT", "POST"}:
            self._send_json(set_student_route(int(match.group(1)), int(match.group(2)), str(payload.get("route") or "")))
            return
        match = re.fullmatch(r"/api/reports/(\d+)/students-domain/(\d+)/process-status", path)
        if match and method in {"PUT", "POST"}:
            self._send_json(set_process_status(int(match.group(1)), int(match.group(2)), str(payload.get("process_status") or "")))
            return
        match = re.fullmatch(r"/api/reports/(\d+)/students-domain/matches/confirm", path)
        if match and method in {"PUT", "POST"}:
            self._send_json(confirm_source_link(
                int(match.group(1)),
                str(payload.get("source_module") or ""),
                str(payload.get("source_key") or ""),
                int(payload.get("student_id") or 0),
            ))
            return
        assert _BASE_WRITE is not None
        _BASE_WRITE(self, method, path, payload)

    core.InformtitHandler._handle_api_get = api_get
    core.InformtitHandler._handle_api_write = api_write
    _INSTALLED = True
