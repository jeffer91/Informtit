from __future__ import annotations

import os
from typing import Any

import app as core
import desktop_entry


def _allowed_origins() -> set[str]:
    configured = os.environ.get(
        "INFORMTIT_ALLOWED_ORIGINS",
        "https://jeffer91.github.io,http://localhost:8765,http://127.0.0.1:8765",
    )
    return {
        origin.strip().rstrip("/")
        for origin in configured.split(",")
        if origin.strip()
    }


class InformtitWebHandler(core.InformtitHandler):
    """Servidor HTTP de Informtit preparado para un frontend en otro origen."""

    def _cors_headers(self) -> None:
        # La clase base llama este método al responder JSON. La cabecera se añade
        # una sola vez desde end_headers para cubrir también PDFs, imágenes y DOCX.
        return

    def end_headers(self) -> None:
        origin = str(self.headers.get("Origin") or "").rstrip("/")
        if origin and origin in _allowed_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header(
                "Access-Control-Allow-Methods",
                "GET, POST, PUT, DELETE, OPTIONS",
            )
        super().end_headers()


def main() -> None:
    os.environ.setdefault("INFORMTIT_DESKTOP_MODE", "web")
    desktop_entry.prepare()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8765"))
    server = core.ThreadingHTTPServer((host, port), InformtitWebHandler)
    print(f"Informtit web API iniciada en http://{host}:{port}")
    print("Orígenes permitidos:", ", ".join(sorted(_allowed_origins())))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
