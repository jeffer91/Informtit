from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

import app as core
import db
from db import connection


_INSTALLED = False
BUILD_ID = "0.3.4-stability"


def _serve_static_no_cache(self: Any, path: str) -> None:
    static_dir = Path(core.STATIC_DIR).resolve()
    if path in {"", "/"}:
        target = static_dir / "index.html"
    else:
        target = (static_dir / path.lstrip("/")).resolve()
        if static_dir not in target.parents:
            self._send_error_json("Ruta inválida.", 403)
            return
        if not target.exists():
            target = static_dir / "index.html"

    if not target.exists() or not target.is_file():
        self._send_error_json("Archivo no encontrado.", 404)
        return

    body = target.read_bytes()
    content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    self.send_response(200)
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(len(body)))
    self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
    self.send_header("Pragma", "no-cache")
    self.send_header("Expires", "0")
    self.send_header("X-Informtit-Build", BUILD_ID)
    self.end_headers()
    self.wfile.write(body)


def _runtime_info() -> dict[str, Any]:
    database = Path(db.DB_PATH).resolve()
    reports = 0
    projects = 0
    requirements = 0
    try:
        with connection() as conn:
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "reports" in tables:
                reports = int(conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0])
            if "period_projects" in tables:
                projects = int(conn.execute("SELECT COUNT(*) FROM period_projects").fetchone()[0])
            if "requirements_students" in tables:
                requirements = int(
                    conn.execute("SELECT COUNT(*) FROM requirements_students").fetchone()[0]
                )
    except Exception:
        pass

    return {
        "ok": True,
        "build": BUILD_ID,
        "desktop_mode": os.environ.get("INFORMTIT_DESKTOP_MODE", "python"),
        "database": str(database),
        "database_exists": database.exists(),
        "reports": reports,
        "period_projects": projects,
        "requirements_students": requirements,
        "static_dir": str(Path(core.STATIC_DIR).resolve()),
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    core.InformtitHandler._serve_static = _serve_static_no_cache

    previous_get = core.InformtitHandler._handle_api_get

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/runtime-info":
            self._send_json(_runtime_info())
            return
        previous_get(self, path, query)

    core.InformtitHandler._handle_api_get = handle_get
    _INSTALLED = True
