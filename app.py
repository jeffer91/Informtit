from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sqlite3
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ai_service import generate_analysis
from analytics import enrich_student, summary
from db import BASE_DIR, connection, create_default_sections, get_report_bundle, init_db, rows_to_dicts, utcnow
from parser import parse_moodle_text
from report_service import build_docx, build_pdf

STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
MAX_BODY_BYTES = 15 * 1024 * 1024


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")


class InformtitHandler(BaseHTTPRequestHandler):
    server_version = "Informtit/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "http://localhost:8765")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = 400, details: Any = None) -> None:
        payload: dict[str, Any] = {"ok": False, "error": message}
        if details is not None:
            payload["details"] = details
        self._send_json(payload, status)

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length > MAX_BODY_BYTES:
            raise ValueError("La solicitud supera el tamaño máximo permitido de 15 MB.")
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("El cuerpo de la solicitud no contiene JSON válido.") from exc

    def _serve_file(self, path: Path, download_name: str | None = None) -> None:
        if not path.exists() or not path.is_file():
            self._send_error_json("Archivo no encontrado.", 404)
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 256):
                self.wfile.write(chunk)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path.startswith("/api/"):
                self._handle_api_get(path, query)
                return
            if path.startswith("/uploads/"):
                filename = Path(path).name
                self._serve_file(UPLOAD_DIR / filename)
                return
            self._serve_static(path)
        except Exception as exc:
            self._send_error_json(str(exc), 500)

    def do_POST(self) -> None:
        try:
            self._handle_api_write("POST", urlparse(self.path).path, self._read_json())
        except ValueError as exc:
            self._send_error_json(str(exc), 400)
        except sqlite3.IntegrityError as exc:
            self._send_error_json("No se pudo guardar porque el registro ya existe o incumple una regla.", 409, str(exc))
        except Exception as exc:
            self._send_error_json(str(exc), 500)

    def do_PUT(self) -> None:
        try:
            self._handle_api_write("PUT", urlparse(self.path).path, self._read_json())
        except ValueError as exc:
            self._send_error_json(str(exc), 400)
        except Exception as exc:
            self._send_error_json(str(exc), 500)

    def do_DELETE(self) -> None:
        try:
            self._handle_api_write("DELETE", urlparse(self.path).path, {})
        except Exception as exc:
            self._send_error_json(str(exc), 500)

    def _serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            target = STATIC_DIR / "index.html"
        else:
            target = (STATIC_DIR / path.lstrip("/")).resolve()
            if STATIC_DIR.resolve() not in target.parents:
                self._send_error_json("Ruta inválida.", 403)
                return
            if not target.exists():
                target = STATIC_DIR / "index.html"
        self._serve_file(target)

    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/health":
            self._send_json({"ok": True, "app": "Informtit", "database": "SQLite local"})
            return

        if path == "/api/reports":
            with connection() as conn:
                reports = rows_to_dicts(conn.execute("SELECT * FROM reports ORDER BY updated_at DESC").fetchall())
                for report in reports:
                    report["career_count"] = conn.execute("SELECT COUNT(*) FROM careers WHERE report_id = ?", (report["id"],)).fetchone()[0]
                    report["student_count"] = conn.execute(
                        "SELECT COUNT(*) FROM students s JOIN careers c ON c.id=s.career_id WHERE c.report_id=?",
                        (report["id"],),
                    ).fetchone()[0]
            self._send_json({"ok": True, "reports": reports})
            return

        match = re.fullmatch(r"/api/reports/(\d+)", path)
        if match:
            report = get_report_bundle(int(match.group(1)))
            if not report:
                self._send_error_json("Informe no encontrado.", 404)
                return
            self._send_json({"ok": True, "report": report})
            return

        match = re.fullmatch(r"/api/reports/(\d+)/export/(docx|pdf)", path)
        if match:
            report_id = int(match.group(1))
            export_type = match.group(2)
            output = build_docx(report_id) if export_type == "docx" else build_pdf(report_id)
            self._serve_file(output, output.name)
            return

        match = re.fullmatch(r"/api/careers/(\d+)/students", path)
        if match:
            career_id = int(match.group(1))
            with connection() as conn:
                rows = rows_to_dicts(conn.execute("SELECT * FROM students WHERE career_id = ? ORDER BY full_name", (career_id,)).fetchall())
            self._send_json({"ok": True, "students": [enrich_student(row) for row in rows]})
            return

        match = re.fullmatch(r"/api/careers/(\d+)/summary", path)
        if match:
            phase = query.get("phase", ["consolidado"])[0]
            if phase not in {"ordinario", "supletorio", "consolidado"}:
                self._send_error_json("Fase inválida.", 400)
                return
            career_id = int(match.group(1))
            with connection() as conn:
                rows = rows_to_dicts(conn.execute("SELECT * FROM students WHERE career_id = ? ORDER BY full_name", (career_id,)).fetchall())
            self._send_json({"ok": True, "summary": summary(rows, phase)})
            return

        match = re.fullmatch(r"/api/careers/(\d+)/analyses", path)
        if match:
            with connection() as conn:
                rows = rows_to_dicts(conn.execute("SELECT * FROM analyses WHERE career_id = ?", (int(match.group(1)),)).fetchall())
            self._send_json({"ok": True, "analyses": rows})
            return

        if path == "/api/ai-providers":
            with connection() as conn:
                providers = rows_to_dicts(conn.execute("SELECT * FROM ai_providers ORDER BY priority, id").fetchall())
            for provider in providers:
                provider["has_api_key"] = bool(provider.get("api_key"))
                provider["api_key"] = "••••••••" if provider["has_api_key"] else ""
            self._send_json({"ok": True, "providers": providers})
            return

        match = re.fullmatch(r"/api/reports/(\d+)/images", path)
        if match:
            with connection() as conn:
                images = rows_to_dicts(conn.execute("SELECT * FROM images WHERE report_id = ? ORDER BY sort_order, id", (int(match.group(1)),)).fetchall())
            self._send_json({"ok": True, "images": images})
            return

        self._send_error_json("Ruta API no encontrada.", 404)

    def _handle_api_write(self, method: str, path: str, payload: dict[str, Any]) -> None:
        if method == "POST" and path == "/api/reports":
            required = ["name", "period", "modality"]
            missing = [field for field in required if not str(payload.get(field, "")).strip()]
            if missing:
                raise ValueError("Faltan campos obligatorios: " + ", ".join(missing))
            if payload["modality"] not in {"presencial", "en_linea"}:
                raise ValueError("La modalidad debe ser presencial o en línea.")
            now = utcnow()
            with connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO reports
                    (name, period, modality, code, version, elaboration_date, prepared_by, prepared_role,
                     reviewed_by, reviewed_role, approved_by, approved_role, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'borrador', ?, ?)
                    """,
                    (
                        payload["name"].strip(), payload["period"].strip(), payload["modality"],
                        payload.get("code", "").strip(), payload.get("version", "1.0").strip(),
                        payload.get("elaboration_date", "").strip(), payload.get("prepared_by", "").strip(),
                        payload.get("prepared_role", "").strip(), payload.get("reviewed_by", "").strip(),
                        payload.get("reviewed_role", "").strip(), payload.get("approved_by", "").strip(),
                        payload.get("approved_role", "").strip(), now, now,
                    ),
                )
                report_id = int(cursor.lastrowid)
                create_default_sections(conn, report_id)
            self._send_json({"ok": True, "report_id": report_id}, 201)
            return

        match = re.fullmatch(r"/api/reports/(\d+)", path)
        if match and method == "PUT":
            report_id = int(match.group(1))
            allowed = ["name", "period", "modality", "code", "version", "elaboration_date", "prepared_by", "prepared_role", "reviewed_by", "reviewed_role", "approved_by", "approved_role", "status"]
            fields = [field for field in allowed if field in payload]
            if not fields:
                raise ValueError("No se enviaron campos para actualizar.")
            assignments = ", ".join(f"{field} = ?" for field in fields) + ", updated_at = ?"
            values = [payload[field] for field in fields] + [utcnow(), report_id]
            with connection() as conn:
                cursor = conn.execute(f"UPDATE reports SET {assignments} WHERE id = ?", values)
                if cursor.rowcount == 0:
                    self._send_error_json("Informe no encontrado.", 404)
                    return
            self._send_json({"ok": True})
            return

        if match and method == "DELETE":
            report_id = int(match.group(1))
            with connection() as conn:
                filenames = [row[0] for row in conn.execute("SELECT filename FROM images WHERE report_id = ?", (report_id,)).fetchall()]
                conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
            for filename in filenames:
                (UPLOAD_DIR / filename).unlink(missing_ok=True)
            self._send_json({"ok": True})
            return

        match = re.fullmatch(r"/api/reports/(\d+)/careers", path)
        if match and method == "POST":
            report_id = int(match.group(1))
            name = str(payload.get("name", "")).strip()
            if not name:
                raise ValueError("El nombre de la carrera es obligatorio.")
            with connection() as conn:
                order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM careers WHERE report_id = ?", (report_id,)).fetchone()[0]
                cursor = conn.execute("INSERT INTO careers (report_id, name, sort_order, created_at) VALUES (?, ?, ?, ?)", (report_id, name, order, utcnow()))
                career_id = int(cursor.lastrowid)
            self._send_json({"ok": True, "career_id": career_id}, 201)
            return

        match = re.fullmatch(r"/api/careers/(\d+)", path)
        if match and method == "DELETE":
            with connection() as conn:
                cursor = conn.execute("DELETE FROM careers WHERE id = ?", (int(match.group(1)),))
            self._send_json({"ok": True, "deleted": cursor.rowcount})
            return

        match = re.fullmatch(r"/api/careers/(\d+)/parse", path)
        if match and method == "POST":
            career_id = int(match.group(1))
            raw_text = str(payload.get("text", ""))
            replace = bool(payload.get("replace", True))
            if not raw_text.strip():
                raise ValueError("Pegue el contenido de las calificaciones.")
            parsed = parse_moodle_text(raw_text)
            if not parsed["students"]:
                self._send_json({"ok": False, **parsed}, 422)
                return
            now = utcnow()
            inserted = 0
            with connection() as conn:
                if replace:
                    conn.execute("DELETE FROM students WHERE career_id = ?", (career_id,))
                for student in parsed["students"]:
                    conn.execute(
                        """
                        INSERT INTO students
                        (career_id, full_name, email, ordinary_theory, supplementary_theory, source_total_theory,
                         ordinary_practical, supplementary_practical, source_total_practical, source_total_course,
                         created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(career_id, email) DO UPDATE SET
                            full_name=excluded.full_name,
                            ordinary_theory=excluded.ordinary_theory,
                            supplementary_theory=excluded.supplementary_theory,
                            source_total_theory=excluded.source_total_theory,
                            ordinary_practical=excluded.ordinary_practical,
                            supplementary_practical=excluded.supplementary_practical,
                            source_total_practical=excluded.source_total_practical,
                            source_total_course=excluded.source_total_course,
                            updated_at=excluded.updated_at
                        """,
                        (
                            career_id, student["full_name"], student["email"], student["ordinary_theory"],
                            student["supplementary_theory"], student["source_total_theory"],
                            student["ordinary_practical"], student["supplementary_practical"],
                            student["source_total_practical"], student["source_total_course"], now, now,
                        ),
                    )
                    inserted += 1
            self._send_json({"ok": True, "inserted": inserted, "warnings": parsed["warnings"], "preview": parsed["students"][:5]})
            return

        match = re.fullmatch(r"/api/students/(\d+)", path)
        if match and method == "PUT":
            student_id = int(match.group(1))
            allowed = ["full_name", "email", "ordinary_theory", "supplementary_theory", "source_total_theory", "ordinary_practical", "supplementary_practical", "source_total_practical", "source_total_course"]
            fields = [field for field in allowed if field in payload]
            if not fields:
                raise ValueError("No se enviaron campos para actualizar.")
            for field in fields:
                if field not in {"full_name", "email"} and payload[field] not in {None, ""}:
                    payload[field] = float(payload[field])
                    if not 0 <= payload[field] <= 100:
                        raise ValueError(f"{field} debe estar entre 0 y 100.")
                elif field not in {"full_name", "email"} and payload[field] == "":
                    payload[field] = None
            assignments = ", ".join(f"{field} = ?" for field in fields) + ", updated_at = ?"
            values = [payload[field] for field in fields] + [utcnow(), student_id]
            with connection() as conn:
                conn.execute(f"UPDATE students SET {assignments} WHERE id = ?", values)
            self._send_json({"ok": True})
            return

        if match and method == "DELETE":
            with connection() as conn:
                conn.execute("DELETE FROM students WHERE id = ?", (int(match.group(1)),))
            self._send_json({"ok": True})
            return

        match = re.fullmatch(r"/api/careers/(\d+)/analysis", path)
        if match and method == "POST":
            career_id = int(match.group(1))
            phase = payload.get("phase", "consolidado")
            mode = payload.get("mode", "single")
            if phase not in {"ordinario", "supletorio", "consolidado"}:
                raise ValueError("Apartado de análisis inválido.")
            if mode not in {"single", "cascade"}:
                raise ValueError("Modo de IA inválido.")
            with connection() as conn:
                career_row = conn.execute("SELECT c.*, r.period, r.modality FROM careers c JOIN reports r ON r.id=c.report_id WHERE c.id=?", (career_id,)).fetchone()
                if not career_row:
                    raise ValueError("La carrera no existe.")
                students = rows_to_dicts(conn.execute("SELECT * FROM students WHERE career_id=?", (career_id,)).fetchall())
                providers = rows_to_dicts(conn.execute("SELECT * FROM ai_providers WHERE enabled=1 ORDER BY priority, id").fetchall())
            result, chain = generate_analysis(providers, career_row["name"], phase, students, career_row["period"], career_row["modality"], mode)
            now = utcnow()
            with connection() as conn:
                conn.execute(
                    """
                    INSERT INTO analyses (career_id, section, text_before, text_after, provider_chain, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'borrador', ?, ?)
                    ON CONFLICT(career_id, section) DO UPDATE SET
                        text_before=excluded.text_before,
                        text_after=excluded.text_after,
                        provider_chain=excluded.provider_chain,
                        status='borrador',
                        updated_at=excluded.updated_at
                    """,
                    (career_id, phase, result["texto_antes"], result["texto_despues"], " → ".join(chain), now, now),
                )
            self._send_json({"ok": True, "analysis": result, "chain": chain})
            return

        match = re.fullmatch(r"/api/careers/(\d+)/analyses/(ordinario|supletorio|consolidado)", path)
        if match and method == "PUT":
            career_id = int(match.group(1))
            phase = match.group(2)
            now = utcnow()
            with connection() as conn:
                conn.execute(
                    """
                    INSERT INTO analyses (career_id, section, text_before, text_after, provider_chain, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'Edición manual', ?, ?, ?)
                    ON CONFLICT(career_id, section) DO UPDATE SET
                      text_before=excluded.text_before, text_after=excluded.text_after,
                      status=excluded.status, updated_at=excluded.updated_at
                    """,
                    (career_id, phase, payload.get("text_before", ""), payload.get("text_after", ""), payload.get("status", "borrador"), now, now),
                )
            self._send_json({"ok": True})
            return

        match = re.fullmatch(r"/api/ai-providers/(\d+)", path)
        if match and method == "PUT":
            provider_id = int(match.group(1))
            allowed = ["endpoint", "model", "enabled", "priority", "timeout", "temperature", "max_tokens"]
            fields = [field for field in allowed if field in payload]
            if payload.get("api_key") and payload.get("api_key") != "••••••••":
                fields.append("api_key")
            if not fields:
                raise ValueError("No se enviaron campos para actualizar.")
            assignments = ", ".join(f"{field} = ?" for field in fields) + ", updated_at = ?"
            values = [payload[field] for field in fields] + [utcnow(), provider_id]
            with connection() as conn:
                conn.execute(f"UPDATE ai_providers SET {assignments} WHERE id = ?", values)
            self._send_json({"ok": True})
            return

        match = re.fullmatch(r"/api/reports/(\d+)/sections/(\d+)", path)
        if match and method == "PUT":
            report_id, section_id = map(int, match.groups())
            allowed = ["title", "content", "visible", "sort_order"]
            fields = [field for field in allowed if field in payload]
            assignments = ", ".join(f"{field} = ?" for field in fields) + ", updated_at = ?"
            values = [payload[field] for field in fields] + [utcnow(), section_id, report_id]
            with connection() as conn:
                conn.execute(f"UPDATE institutional_sections SET {assignments} WHERE id = ? AND report_id = ?", values)
            self._send_json({"ok": True})
            return

        match = re.fullmatch(r"/api/reports/(\d+)/images", path)
        if match and method == "POST":
            report_id = int(match.group(1))
            data_url = str(payload.get("data_url", ""))
            original_name = str(payload.get("original_name", "imagen"))
            if not data_url.startswith("data:image/") or "," not in data_url:
                raise ValueError("La imagen no tiene un formato válido.")
            header, encoded = data_url.split(",", 1)
            image_bytes = base64.b64decode(encoded, validate=True)
            if len(image_bytes) > 8 * 1024 * 1024:
                raise ValueError("La imagen supera 8 MB.")
            extension_match = re.match(r"data:image/([a-zA-Z0-9.+-]+);base64", header)
            extension = (extension_match.group(1) if extension_match else "png").replace("jpeg", "jpg")
            if extension not in {"png", "jpg", "webp", "gif"}:
                raise ValueError("Formato de imagen no permitido.")
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"{uuid.uuid4().hex}.{extension}"
            (UPLOAD_DIR / filename).write_bytes(image_bytes)
            with connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO images (report_id, career_id, section, filename, original_name, title, description, source, sort_order, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (report_id, payload.get("career_id"), payload.get("section", "general"), filename, original_name,
                     payload.get("title", ""), payload.get("description", ""), payload.get("source", ""),
                     int(payload.get("sort_order", 0)), utcnow()),
                )
                image_id = int(cursor.lastrowid)
            self._send_json({"ok": True, "image_id": image_id, "filename": filename}, 201)
            return

        match = re.fullmatch(r"/api/images/(\d+)", path)
        if match and method == "DELETE":
            image_id = int(match.group(1))
            with connection() as conn:
                row = conn.execute("SELECT filename FROM images WHERE id = ?", (image_id,)).fetchone()
                conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
            if row:
                (UPLOAD_DIR / row["filename"]).unlink(missing_ok=True)
            self._send_json({"ok": True})
            return

        self._send_error_json("Ruta API no encontrada.", 404)


def main() -> None:
    parser = argparse.ArgumentParser(description="Informtit - informe de titulación con base local")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    init_db()
    server = ThreadingHTTPServer((args.host, args.port), InformtitHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"Informtit iniciado en {url}")
    print("La información se guarda localmente en data/informtit.db")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nInformtit detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
