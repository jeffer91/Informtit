from __future__ import annotations

import time
import traceback
from typing import Any

import app as core
import import_service


_INSTALLED = False


def install() -> None:
    """Atiende la previsualización de Requisitos en una ruta final y observable.

    La ruta se instala de último para no depender de la cadena de wrappers. Además
    registra inicio, duración, resultado y errores en la terminal que ejecuta
    ``npm start`` para distinguir un análisis activo de un bloqueo real.
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

            started = time.perf_counter()
            approx_kb = round((len(data_url) * 3 / 4) / 1024, 1)
            print(
                f"[ImportPreview] INICIO archivo={original_name!r} carga≈{approx_kb} KB",
                flush=True,
            )
            try:
                preview = import_service.create_preview(data_url, original_name)
            except Exception as exc:
                elapsed = time.perf_counter() - started
                print(
                    f"[ImportPreview] ERROR después de {elapsed:.3f}s: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                traceback.print_exc()
                raise

            elapsed = time.perf_counter() - started
            print(
                "[ImportPreview] OK "
                f"{elapsed:.3f}s · total={preview.get('total', 0)} · "
                f"presencial={preview.get('presencial', 0)} · "
                f"online={preview.get('en_linea', 0)}",
                flush=True,
            )
            self._send_json({"ok": True, "preview": preview}, 200)
            return

        previous_write(self, method, path, payload)

    core.InformtitHandler._handle_api_write = handle_write
    core.InformtitHandler._import_preview_runtime_installed = True
    _INSTALLED = True
