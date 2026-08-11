from __future__ import annotations

import re
from typing import Any

import app as core
from nuclei_excel_import import get_excel_import_summary, import_nuclei_excel
from nuclei_service import analyze_nucleus, delete_nucleus, ensure_nuclei_schema, get_nuclei, save_nucleus


def install() -> None:
    ensure_nuclei_schema()
    original_get = core.InformtitHandler._handle_api_get
    original_write = core.InformtitHandler._handle_api_write

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)/nuclei", path)
        if match:
            report_id = int(match.group(1))
            self._send_json(
                {
                    "ok": True,
                    **get_nuclei(report_id),
                    "excel_import": get_excel_import_summary(report_id),
                }
            )
            return
        original_get(self, path, query)

    def handle_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)/nuclei/import-excel", path)
        if match and method == "POST":
            self._send_json(import_nuclei_excel(int(match.group(1)), payload), 201)
            return

        # Se conservan las rutas anteriores por compatibilidad con instalaciones
        # previas, aunque la interfaz actual de Núcleos utiliza únicamente Excel.
        match = re.fullmatch(r"/api/reports/(\d+)/nuclei/analyze", path)
        if match and method == "POST":
            self._send_json({"ok": True, "analysis": analyze_nucleus(payload)})
            return

        match = re.fullmatch(r"/api/reports/(\d+)/nuclei", path)
        if match and method == "POST":
            self._send_json(save_nucleus(int(match.group(1)), payload), 201)
            return

        match = re.fullmatch(r"/api/reports/(\d+)/nuclei/(\d+)", path)
        if match and method == "DELETE":
            self._send_json(delete_nucleus(int(match.group(1)), int(match.group(2))))
            return

        original_write(self, method, path, payload)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
