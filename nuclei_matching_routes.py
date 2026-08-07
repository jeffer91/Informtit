from __future__ import annotations

import re
from typing import Any

import app as core
from eligibility_service import (
    ensure_nucleus_matching_schema,
    save_grade_resolution,
    save_manual_match,
)


def install() -> None:
    ensure_nucleus_matching_schema()
    original_write = core.InformtitHandler._handle_api_write

    def handle_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)/nuclei/manual-match", path)
        if match and method == "POST":
            self._send_json(save_manual_match(int(match.group(1)), payload))
            return

        match = re.fullmatch(r"/api/reports/(\d+)/nuclei/grade-resolution", path)
        if match and method == "POST":
            self._send_json(save_grade_resolution(int(match.group(1)), payload))
            return

        original_write(self, method, path, payload)

    core.InformtitHandler._handle_api_write = handle_write
