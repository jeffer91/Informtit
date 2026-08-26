from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from section_templates import (
    LEGACY_PLACEHOLDERS,
    SECTION_TEMPLATES,
    resolve_template,
    template_by_key,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "informtit.db"


def utcnow() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    columns = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_section_schema(conn: sqlite3.Connection) -> None:
    _ensure_column(
        conn, "institutional_sections", "section_mode", "TEXT DEFAULT 'fixed'"
    )
    _ensure_column(
        conn, "institutional_sections", "template_content", "TEXT DEFAULT ''"
    )
    _ensure_column(
        conn, "institutional_sections", "help_text", "TEXT DEFAULT ''"
    )
    _ensure_column(
        conn, "institutional_sections", "customized", "INTEGER DEFAULT 0"
    )


def init_db() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                period TEXT NOT NULL,
                modality TEXT NOT NULL CHECK(modality IN ('presencial', 'en_linea')),
                code TEXT DEFAULT '',
                version TEXT DEFAULT '1.0',
                elaboration_date TEXT DEFAULT '',
                prepared_by TEXT DEFAULT '',
                prepared_role TEXT DEFAULT '',
                reviewed_by TEXT DEFAULT '',
                reviewed_role TEXT DEFAULT '',
                approved_by TEXT DEFAULT '',
                approved_role TEXT DEFAULT '',
                status TEXT DEFAULT 'borrador',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS careers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
                UNIQUE(report_id, name)
            );

            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                career_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT DEFAULT '',
                ordinary_theory REAL,
                supplementary_theory REAL,
                source_total_theory REAL,
                ordinary_practical REAL,
                supplementary_practical REAL,
                source_total_practical REAL,
                source_total_course REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(career_id) REFERENCES careers(id) ON DELETE CASCADE,
                UNIQUE(career_id, email)
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                career_id INTEGER NOT NULL,
                section TEXT NOT NULL CHECK(section IN ('ordinario', 'supletorio', 'consolidado')),
                text_before TEXT DEFAULT '',
                text_after TEXT DEFAULT '',
                provider_chain TEXT DEFAULT '',
                status TEXT DEFAULT 'borrador',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(career_id) REFERENCES careers(id) ON DELETE CASCADE,
                UNIQUE(career_id, section)
            );

            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                career_id INTEGER,
                section TEXT DEFAULT 'general',
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                source TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
                FOREIGN KEY(career_id) REFERENCES careers(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS institutional_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                section_key TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT DEFAULT '',
                visible INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL,
                section_mode TEXT DEFAULT 'fixed',
                template_content TEXT DEFAULT '',
                help_text TEXT DEFAULT '',
                customized INTEGER DEFAULT 0,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
                UNIQUE(report_id, section_key)
            );

            CREATE TABLE IF NOT EXISTS ai_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                provider_type TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                model TEXT DEFAULT '',
                api_key TEXT DEFAULT '',
                enabled INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 1,
                timeout INTEGER DEFAULT 45,
                temperature REAL DEFAULT 0.2,
                max_tokens INTEGER DEFAULT 1400,
                updated_at TEXT NOT NULL
            );
            """
        )
        ensure_section_schema(conn)
        seed_ai_providers(conn)
        sync_section_templates(conn)


def seed_ai_providers(conn: sqlite3.Connection) -> None:
    defaults = [
        (
            "Gemini",
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            "",
            1,
        ),
        (
            "Groq",
            "openai_compatible",
            "https://api.groq.com/openai/v1/chat/completions",
            "",
            2,
        ),
        (
            "OpenRouter",
            "openai_compatible",
            "https://openrouter.ai/api/v1/chat/completions",
            "",
            3,
        ),
    ]
    for name, provider_type, endpoint, model, priority in defaults:
        conn.execute(
            """
            INSERT INTO ai_providers
                (name, provider_type, endpoint, model, enabled, priority, timeout, temperature, max_tokens, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, 45, 0.2, 1400, ?)
            ON CONFLICT(name) DO NOTHING
            """,
            (name, provider_type, endpoint, model, priority, utcnow()),
        )


def _report_dict(conn: sqlite3.Connection, report_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if not row:
        raise ValueError("El informe no existe.")
    return dict(row)


def create_default_sections(conn: sqlite3.Connection, report_id: int) -> None:
    ensure_section_schema(conn)
    report = _report_dict(conn, report_id)
    now = utcnow()
    for template in SECTION_TEMPLATES:
        resolved = resolve_template(template.content, report)
        conn.execute(
            """
            INSERT INTO institutional_sections
                (report_id, section_key, title, content, visible, sort_order,
                 updated_at, section_mode, template_content, help_text, customized)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(report_id, section_key) DO NOTHING
            """,
            (
                report_id,
                template.key,
                template.title,
                resolved,
                template.order,
                now,
                template.mode,
                template.content,
                template.help_text,
            ),
        )


def refresh_report_sections(
    conn: sqlite3.Connection, report_id: int, *, force: bool = False
) -> None:
    """Actualiza periodo/modalidad en secciones no personalizadas."""

    ensure_section_schema(conn)
    report = _report_dict(conn, report_id)
    now = utcnow()
    for template in SECTION_TEMPLATES:
        row = conn.execute(
            """
            SELECT * FROM institutional_sections
            WHERE report_id = ? AND section_key = ?
            """,
            (report_id, template.key),
        ).fetchone()
        resolved = resolve_template(template.content, report)
        if not row:
            conn.execute(
                """
                INSERT INTO institutional_sections
                    (report_id, section_key, title, content, visible, sort_order,
                     updated_at, section_mode, template_content, help_text, customized)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, 0)
                """,
                (
                    report_id,
                    template.key,
                    template.title,
                    resolved,
                    template.order,
                    now,
                    template.mode,
                    template.content,
                    template.help_text,
                ),
            )
            continue

        content = str(row["content"] or "").strip()
        customized = bool(row["customized"])

        # Las versiones anteriores guardaban instrucciones de una sola línea.
        # Se sustituyen por contenido institucional listo para el informe.
        if content in LEGACY_PLACEHOLDERS or not content:
            customized = False
        elif not row["template_content"] and not row["help_text"]:
            # Columna recién migrada: conservar como personalizado cualquier texto
            # que no corresponda a los antiguos marcadores de posición.
            customized = True

        new_content = resolved if force or not customized else row["content"]
        conn.execute(
            """
            UPDATE institutional_sections
            SET title = ?, content = ?, sort_order = ?, updated_at = ?,
                section_mode = ?, template_content = ?, help_text = ?, customized = ?
            WHERE id = ?
            """,
            (
                template.title,
                new_content,
                template.order,
                now,
                template.mode,
                template.content,
                template.help_text,
                0 if force or not customized else 1,
                row["id"],
            ),
        )


def restore_section_template(
    conn: sqlite3.Connection, report_id: int, section_id: int
) -> None:
    row = conn.execute(
        """
        SELECT section_key FROM institutional_sections
        WHERE id = ? AND report_id = ?
        """,
        (section_id, report_id),
    ).fetchone()
    if not row:
        raise ValueError("La sección no existe.")
    template = template_by_key(row["section_key"])
    if not template:
        raise ValueError("La sección no tiene una plantilla institucional.")
    report = _report_dict(conn, report_id)
    conn.execute(
        """
        UPDATE institutional_sections
        SET title = ?, content = ?, section_mode = ?, template_content = ?,
            help_text = ?, customized = 0, updated_at = ?
        WHERE id = ? AND report_id = ?
        """,
        (
            template.title,
            resolve_template(template.content, report),
            template.mode,
            template.content,
            template.help_text,
            utcnow(),
            section_id,
            report_id,
        ),
    )


def sync_section_templates(conn: sqlite3.Connection) -> None:
    ensure_section_schema(conn)
    report_ids = [
        row["id"] for row in conn.execute("SELECT id FROM reports").fetchall()
    ]
    for report_id in report_ids:
        refresh_report_sections(conn, int(report_id))


def get_report_bundle(report_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        report = conn.execute(
            "SELECT * FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        if not report:
            return None
        careers = rows_to_dicts(
            conn.execute(
                "SELECT * FROM careers WHERE report_id = ? ORDER BY sort_order, name",
                (report_id,),
            ).fetchall()
        )
        sections = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM institutional_sections
                WHERE report_id = ? ORDER BY sort_order, id
                """,
                (report_id,),
            ).fetchall()
        )
        images = rows_to_dicts(
            conn.execute(
                "SELECT * FROM images WHERE report_id = ? ORDER BY sort_order, id",
                (report_id,),
            ).fetchall()
        )
        bundle = dict(report)
        bundle["careers"] = careers
        bundle["sections"] = sections
        bundle["images"] = images
        return bundle


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
