from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "informtit.db"


def utcnow() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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
        seed_ai_providers(conn)


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


def create_default_sections(conn: sqlite3.Connection, report_id: int) -> None:
    sections = [
        (
            "marco_legal",
            "Marco legal",
            "El presente apartado consolida la normativa institucional y nacional que sustenta el proceso de titulación.",
            10,
        ),
        (
            "reglamento",
            "Reglamento del examen complexivo",
            "Este apartado describe los lineamientos aplicables al componente teórico, práctico, ordinario y supletorio.",
            20,
        ),
        (
            "metodologia",
            "Metodología de núcleos estructurantes",
            "La metodología integra conocimientos teóricos y prácticos de acuerdo con el perfil de egreso de cada carrera.",
            30,
        ),
        (
            "cronograma",
            "Cronograma del proceso",
            "Registre aquí las actividades, responsables, fechas y estado de ejecución del proceso de titulación.",
            40,
        ),
        (
            "analisis_estrategico",
            "Análisis estratégico",
            "El análisis estratégico se completará con base en los resultados consolidados de la cohorte.",
            90,
        ),
        (
            "conclusiones",
            "Conclusiones",
            "Las conclusiones deberán ser revisadas y aprobadas antes de exportar el informe final.",
            100,
        ),
        (
            "recomendaciones",
            "Recomendaciones",
            "Las recomendaciones deberán corresponder a los hallazgos cuantitativos y cualitativos del informe.",
            110,
        ),
    ]
    now = utcnow()
    for key, title, content, order in sections:
        conn.execute(
            """
            INSERT INTO institutional_sections
                (report_id, section_key, title, content, visible, sort_order, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(report_id, section_key) DO NOTHING
            """,
            (report_id, key, title, content, order, now),
        )


def get_report_bundle(report_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        report = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not report:
            return None
        careers = rows_to_dicts(
            conn.execute(
                "SELECT * FROM careers WHERE report_id = ? ORDER BY sort_order, name", (report_id,)
            ).fetchall()
        )
        sections = rows_to_dicts(
            conn.execute(
                "SELECT * FROM institutional_sections WHERE report_id = ? ORDER BY sort_order, id",
                (report_id,),
            ).fetchall()
        )
        images = rows_to_dicts(
            conn.execute(
                "SELECT * FROM images WHERE report_id = ? ORDER BY sort_order, id", (report_id,)
            ).fetchall()
        )
        bundle = dict(report)
        bundle["careers"] = careers
        bundle["sections"] = sections
        bundle["images"] = images
        return bundle


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
