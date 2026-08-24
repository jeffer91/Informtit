from __future__ import annotations

from typing import Any

import app as core
import import_service


_INSTALLED = False


def install() -> None:
    """Atiende la previsualización de Requisitos en una ruta final y simple.

    Varias capas de la aplicación envuelven ``_handle_api_write``. Esta guarda se
    instala al final para que ``/api/imports/preview`` no dependa de esos
    envoltorios y responda directamente con el parser oficial del .xls HTML.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    previous_write = core.InformtitHandler._handle_api_write

    def handle_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        if method == "POST" and path == "/api/imports/preview":
            data_url = str(payload.get("data_url") or "")
            original_name = str(payload.get("original_name") or "").strip()
            if not data_url:
                raise ValueError("Seleccione primero el archivo de Requisitos.")
            if not original_name:
                raise ValueError("No se recibió el nombre del archivo.")

            preview = import_service.create_preview(data_url, original_name)
            self._send_json({"ok": True, "preview": preview}, 200)
            return

        previous_write(self, method, path, payload)

    core.InformtitHandler._handle_api_write = handle_write
    core.InformtitHandler._import_preview_runtime_installed = True
    _INSTALLED = True
