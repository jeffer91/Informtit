from __future__ import annotations

import re
import unicodedata
from typing import Any


# Catálogo inicial. Se usa únicamente para sembrar una instalación nueva.
# Después del primer arranque, los cambios se leen desde SQLite y ya no desde
# esta constante, de modo que editar un coordinador sea realmente persistente.
COORDINATORS: tuple[dict[str, str], ...] = (
    {"career": "Enfermería", "coordinator": "Ana Emilia Guzman", "program": "Técnico Superior", "telegram": "@emiliaguzmant"},
    {"career": "Mecánica Automotriz", "coordinator": "Dario Torres", "program": "Tecnología Superior", "telegram": "@INGEDARIOTORRES"},
    {"career": "Mecánica de Motos", "coordinator": "Dario Torres", "program": "Tecnología Superior", "telegram": "@INGEDARIOTORRES"},
    {"career": "Diseño Multimedia", "coordinator": "Javier Tapia", "program": "Tecnología Superior", "telegram": "@JAVIERTAPIA28"},
    {"career": "Marketing Digital y Comercio Electrónico", "coordinator": "Javier Tapia", "program": "Tecnología Superior", "telegram": "@JAVIERTAPIA28"},
    {"career": "Marketing Digital y Comercio Electrónico TSU", "coordinator": "Javier Tapia", "program": "Tecnología Universitaria", "telegram": "@JAVIERTAPIA28"},
    {"career": "Ventas", "coordinator": "Javier Tapia", "program": "Tecnología Superior", "telegram": "@JAVIERTAPIA28"},
    {"career": "Desarrollo de Software", "coordinator": "Juan Carlos Pazmiño", "program": "Tecnología Superior", "telegram": "@JUANPAZMINO"},
    {"career": "Desarrollo de Software y Ciberseguridad", "coordinator": "Juan Carlos Pazmiño", "program": "Tecnología Universitaria", "telegram": "@JUANPAZMINO"},
    {"career": "Redes y Telecomunicaciones", "coordinator": "Juan Carlos Pazmiño", "program": "Tecnología Superior", "telegram": "@JUANPAZMINO"},
    {"career": "Redes y Telecomunicaciones TSU", "coordinator": "Juan Carlos Pazmiño", "program": "Tecnología Universitaria", "telegram": "@JUANPAZMINO"},
    {"career": "Estética Integral", "coordinator": "Katherine Chamba", "program": "Tecnología Superior", "telegram": "@Katherine_Chamba_21"},
    {"career": "Educación Básica", "coordinator": "Maria Eugenia Barre", "program": "Tecnología Superior", "telegram": "@MBARREAVILA"},
    {"career": "Educación Inicial", "coordinator": "Maria Eugenia Barre", "program": "Tecnología Superior", "telegram": "@MBARREAVILA"},
    {"career": "Educación Inicial TSU", "coordinator": "Maria Eugenia Barre", "program": "Tecnología Universitaria", "telegram": "@MBARREAVILA"},
    {"career": "Pedagogía", "coordinator": "Maria Eugenia Barre", "program": "Tecnología Universitaria", "telegram": "@MBARREAVILA"},
    {"career": "Procesamiento de Alimentos", "coordinator": "Mayra Molina", "program": "Tecnología Superior", "telegram": "0"},
    {"career": "Administración", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Superior", "telegram": "@RODRIGOESPINOZAITSQMET"},
    {"career": "Administración de Empresas e inteligencia de negocios", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Universitaria", "telegram": "@RODRIGOESPINOZAITSQMET"},
    {"career": "Administración del Talento Humano", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Universitaria", "telegram": ""},
    {"career": "Contabilidad", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Superior", "telegram": "@RODRIGOESPINOZAITSQMET"},
    {"career": "Contabilidad y Tributación TSU", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Universitaria", "telegram": "@RODRIGOESPINOZAITSQMET"},
    {"career": "Gestión del Talento Humano", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Superior", "telegram": ""},
    {"career": "Seguridad y Prevención de Riesgos Laborales", "coordinator": "Rodrigo Espinoza", "program": "Tecnología Superior", "telegram": "@RODRIGOESPINOZAITSQMET"},
    {"career": "Rehabilitación Física", "coordinator": "Andrea Moreano", "program": "Tecnología Superior", "telegram": ""},
    {"career": "Seguridad Ciudadana y Orden Publico", "coordinator": "Sonia Moreno", "program": "Tecnología Superior", "telegram": "@Smoreno1"},
    {"career": "Gastronomia", "coordinator": "Amado Chiluisa", "program": "Tecnología Superior", "telegram": ""},
)


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "")).casefold()
    text = "".join(character for character in text if unicodedata.category(character) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _table_exists(conn: Any, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def _columns(conn: Any, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema() -> None:
    from db import connection, utcnow

    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS coordinator_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                name_key TEXT NOT NULL UNIQUE,
                telegram TEXT DEFAULT '',
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS coordinator_careers (
                career_key TEXT PRIMARY KEY,
                career TEXT NOT NULL,
                program TEXT DEFAULT '',
                coordinator_id INTEGER NOT NULL,
                sort_order INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(coordinator_id) REFERENCES coordinator_profiles(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_coordinator_careers_profile
                ON coordinator_careers(coordinator_id, sort_order, career);
            """
        )

        count = int(conn.execute("SELECT COUNT(*) FROM coordinator_profiles").fetchone()[0])
        if count:
            return

        now = utcnow()
        ids: dict[str, int] = {}
        orders: dict[int, int] = {}
        for item in COORDINATORS:
            coordinator_name = str(item.get("coordinator") or "").strip()
            if not coordinator_name:
                continue
            name_key = normalize(coordinator_name)
            coordinator_id = ids.get(name_key)
            if coordinator_id is None:
                cursor = conn.execute(
                    """
                    INSERT INTO coordinator_profiles
                    (name, name_key, telegram, active, created_at, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (
                        coordinator_name,
                        name_key,
                        str(item.get("telegram") or "").strip(),
                        now,
                        now,
                    ),
                )
                coordinator_id = int(cursor.lastrowid)
                ids[name_key] = coordinator_id
                orders[coordinator_id] = 0

            career = str(item.get("career") or "").strip()
            if not career:
                continue
            orders[coordinator_id] += 1
            conn.execute(
                """
                INSERT OR REPLACE INTO coordinator_careers
                (career_key, career, program, coordinator_id, sort_order, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalize(career),
                    career,
                    str(item.get("program") or "").strip(),
                    coordinator_id,
                    orders[coordinator_id],
                    now,
                ),
            )


def list_coordinators() -> list[dict[str, Any]]:
    from db import connection

    ensure_schema()
    with connection() as conn:
        profiles = conn.execute(
            """
            SELECT id, name, telegram, active
            FROM coordinator_profiles
            ORDER BY active DESC, name COLLATE NOCASE, id
            """
        ).fetchall()
        output: list[dict[str, Any]] = []
        for profile in profiles:
            careers = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT career_key, career, program, sort_order
                    FROM coordinator_careers
                    WHERE coordinator_id=?
                    ORDER BY sort_order, career COLLATE NOCASE
                    """,
                    (int(profile["id"]),),
                ).fetchall()
            ]
            output.append(
                {
                    "id": int(profile["id"]),
                    "name": str(profile["name"] or ""),
                    "telegram": str(profile["telegram"] or ""),
                    "active": bool(profile["active"]),
                    "careers": careers,
                }
            )
    return output


def available_careers() -> list[dict[str, str]]:
    """Devuelve carreras configuradas y carreras observadas en los datos locales."""
    from db import connection

    ensure_schema()
    catalog: dict[str, dict[str, str]] = {}

    def add(career: Any, program: Any = "") -> None:
        name = str(career or "").strip()
        if not name:
            return
        key = normalize(name)
        current = catalog.get(key)
        program_text = str(program or "").strip()
        if current is None:
            catalog[key] = {"career_key": key, "career": name, "program": program_text}
        elif not current.get("program") and program_text:
            current["program"] = program_text

    for item in COORDINATORS:
        add(item.get("career"), item.get("program"))

    with connection() as conn:
        for row in conn.execute(
            "SELECT career_key, career, program FROM coordinator_careers"
        ).fetchall():
            add(row["career"], row["program"])

        local_sources = (
            ("requirements_students", "career_name"),
            ("careers", "name"),
            ("nucleus_courses", "career_name"),
            ("thesis_projects", "career_name"),
        )
        for table, column in local_sources:
            if column not in _columns(conn, table):
                continue
            rows = conn.execute(
                f"SELECT DISTINCT {column} AS career FROM {table} "
                f"WHERE TRIM(COALESCE({column}, '')) <> ''"
            ).fetchall()
            for row in rows:
                add(row["career"])

    return sorted(catalog.values(), key=lambda item: normalize(item["career"]))


def _clean_careers(careers: Any) -> list[dict[str, str]]:
    available = {item["career_key"]: item for item in available_careers()}
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in careers if isinstance(careers, list) else []:
        if isinstance(item, dict):
            career = str(item.get("career") or item.get("name") or "").strip()
            program = str(item.get("program") or "").strip()
        else:
            career = str(item or "").strip()
            program = ""
        if not career:
            continue
        key = normalize(career)
        if not key or key in seen:
            continue
        seen.add(key)
        known = available.get(key, {})
        output.append(
            {
                "career_key": key,
                "career": str(known.get("career") or career),
                "program": program or str(known.get("program") or ""),
            }
        )
    return output


def _profile_by_id(coordinator_id: int) -> dict[str, Any]:
    for item in list_coordinators():
        if int(item["id"]) == int(coordinator_id):
            return item
    raise ValueError("El coordinador no existe.")


def update_coordinator(
    coordinator_id: int,
    *,
    name: str,
    telegram: str = "",
    careers: Any = None,
) -> dict[str, Any]:
    from db import connection, utcnow

    ensure_schema()
    clean_name = " ".join(str(name or "").split())
    if not clean_name:
        raise ValueError("El nombre del coordinador es obligatorio.")
    name_key = normalize(clean_name)
    assignments = _clean_careers(careers or [])
    now = utcnow()

    with connection() as conn:
        current = conn.execute(
            "SELECT id FROM coordinator_profiles WHERE id=?",
            (int(coordinator_id),),
        ).fetchone()
        if not current:
            raise ValueError("El coordinador no existe.")
        duplicate = conn.execute(
            "SELECT id FROM coordinator_profiles WHERE name_key=? AND id<>?",
            (name_key, int(coordinator_id)),
        ).fetchone()
        if duplicate:
            raise ValueError("Ya existe otro coordinador con ese nombre.")

        conn.execute(
            """
            UPDATE coordinator_profiles
            SET name=?, name_key=?, telegram=?, updated_at=?
            WHERE id=?
            """,
            (clean_name, name_key, str(telegram or "").strip(), now, int(coordinator_id)),
        )
        conn.execute(
            "DELETE FROM coordinator_careers WHERE coordinator_id=?",
            (int(coordinator_id),),
        )
        for order, item in enumerate(assignments, start=1):
            conn.execute(
                """
                INSERT INTO coordinator_careers
                    (career_key, career, program, coordinator_id, sort_order, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(career_key) DO UPDATE SET
                    career=excluded.career,
                    program=excluded.program,
                    coordinator_id=excluded.coordinator_id,
                    sort_order=excluded.sort_order,
                    updated_at=excluded.updated_at
                """,
                (
                    item["career_key"],
                    item["career"],
                    item["program"],
                    int(coordinator_id),
                    order,
                    now,
                ),
            )

    return _profile_by_id(int(coordinator_id))


def create_coordinator(
    *,
    name: str,
    telegram: str = "",
    careers: Any = None,
) -> dict[str, Any]:
    from db import connection, utcnow

    ensure_schema()
    clean_name = " ".join(str(name or "").split())
    if not clean_name:
        raise ValueError("El nombre del coordinador es obligatorio.")
    name_key = normalize(clean_name)
    now = utcnow()
    with connection() as conn:
        if conn.execute(
            "SELECT 1 FROM coordinator_profiles WHERE name_key=?",
            (name_key,),
        ).fetchone():
            raise ValueError("Ya existe un coordinador con ese nombre.")
        cursor = conn.execute(
            """
            INSERT INTO coordinator_profiles
            (name, name_key, telegram, active, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (clean_name, name_key, str(telegram or "").strip(), now, now),
        )
        coordinator_id = int(cursor.lastrowid)

    return update_coordinator(
        coordinator_id,
        name=clean_name,
        telegram=telegram,
        careers=careers or [],
    )


def _configured_rows() -> list[dict[str, str]]:
    from db import connection

    ensure_schema()
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT cc.career, cc.program, cp.name AS coordinator, cp.telegram
            FROM coordinator_careers cc
            JOIN coordinator_profiles cp ON cp.id=cc.coordinator_id
            WHERE cp.active=1
            ORDER BY cc.career COLLATE NOCASE
            """
        ).fetchall()
    return [
        {
            "career": str(row["career"] or ""),
            "coordinator": str(row["coordinator"] or ""),
            "program": str(row["program"] or ""),
            "telegram": str(row["telegram"] or ""),
        }
        for row in rows
    ]


def find_coordinator(career_name: str) -> dict[str, str]:
    target = normalize(career_name)
    try:
        rows = _configured_rows()
    except Exception:
        # Respaldo para utilidades que puedan usar este módulo antes de que la
        # base esté disponible. En el escritorio normal se usa siempre SQLite.
        rows = [dict(item) for item in COORDINATORS]

    exact = next((item for item in rows if normalize(item["career"]) == target), None)
    if exact:
        return dict(exact)

    target_tokens = set(target.split())
    best: tuple[int, dict[str, str] | None] = (0, None)
    for item in rows:
        tokens = set(normalize(item["career"]).split())
        score = len(target_tokens & tokens)
        if score > best[0]:
            best = (score, item)
    return dict(best[1]) if best[1] and best[0] >= 2 else {
        "career": career_name,
        "coordinator": "",
        "program": "",
        "telegram": "",
    }
