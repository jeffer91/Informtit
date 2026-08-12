from __future__ import annotations

import re
from typing import Any

import app as core
import report_full_detail


def install() -> None:
    if getattr(core.InformtitHandler, "_pdf_validation_installed", False):
        return

    previous_get = core.InformtitHandler._handle_api_get

    def validation_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)/validate-pdf", path)
        if match:
            result = report_full_detail.validate_pdf_report(int(match.group(1)))
            self._send_json({"ok": True, "validation": result})
            return
        previous_get(self, path, query)

    core.InformtitHandler._handle_api_get = validation_get
    core.InformtitHandler._pdf_validation_installed = True
