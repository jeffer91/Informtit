from __future__ import annotations

import base64
import json
import re
import secrets
import unicodedata
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from db import DATA_DIR, connection, create_default_sections, rows_to_dicts, utcnow
from parser import parse_moodle_text


REQUIRED_HEADERS = {
    "numeroidentificacion",
    "nombres",
    "codigocarrera",
    "nombrecarrera",
    "correoinstitucional",
}

STUDENT_COLUMNS = {
    "identification": "TEXT",
    "career_code": "TEXT DEFAULT ''",
    "schedule": "TEXT DEFAULT ''",
    "academic_status": "TEXT DEFAULT ''",
    "documentation_status": "TEXT DEFAULT ''",
    "financial_status": "TEXT DEFAULT ''",
    "titulation_status": "TEXT DEFAULT ''",
    "practices_linkage_status": "TEXT DEFAULT ''",
    "linkage_status": "TEXT DEFAULT ''",
    "graduate_followup_status": "TEXT DEFAULT ''",
    "english_status": "TEXT DEFAULT ''",
    "data_update_status": "TEXT DEFAULT ''",
    "personal_email": "TEXT DEFAULT ''",
    "phone": "TEXT DEFAULT ''",
    "campus": "TEXT DEFAULT ''",
    "titulation_approval": "TEXT DEFAULT ''",
    "complexive_approval": "TEXT DEFAULT ''",
    "imported_from_roster": "INTEGER DEFAULT 0",
    "notes_matched": "INTEGER DEFAULT 0",
    "match_method": "TEXT DEFAULT ''",
}

CAREER_COLUMNS = {
    "career_code": "TEXT DEFAULT ''",
}

REPORT_COLUMNS = {
    "source_import_id": "INTEGER",
}


def normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]+", " ", text)).strip().upper()


def clean_cell(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


class HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(clean_cell("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(cell for cell in self._row):
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def _decode_html(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
            if "<table" in text.lower():
                return text
        except UnicodeDecodeError:
            continue
    raise ValueError("El archivo no contiene una tabla HTML compatible con Excel.")


def _extract_period(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ")
    months = (
        "ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|"
        "SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE"
    )
    match = re.search(
        rf"({months})\s+(\d{{4}})\s*(?:-|A|AL)\s*({months})\s+(\d{{4}})",
        stem,
        re.IGNORECASE,
    )
    if not match:
        return ""
    first_month, first_year, second_month, second_year = match.groups()
    return f"{first_month.title()} {first_year} - {second_month.title()} {second_year}"


def _record_value(record: dict[str, str], *aliases: str) -> str:
    lookup = {normalize_key(key): clean_cell(value) for key, value in record.items()}
    for alias in aliases:
        value = lookup.get(normalize_key(alias), "")
        if value:
            return value
    return ""


def _modality(career_name: str, career_code: str) -> str:
    name = normalize_name(career_name)
    code = career_code.upper()
    return "en_linea" if "ONLINE" in name or "-L-" in code else "presencial"


def parse_roster_html(data: bytes, filename: str) -> dict[str, Any]:
    if len(data) > 12 * 1024 * 1024:
        raise ValueError("El archivo supera el límite permitido de 12 MB.")

    text = _decode_html(data)
    parser = HtmlTableParser()
    parser.feed(text)
    rows = parser.rows
    if not rows:
        raise ValueError("No se encontró ninguna tabla en el archivo.")

    header_index = -1
    headers: list[str] = []
    for index, row in enumerate(rows[:20]):
        normalized = {normalize_key(cell) for cell in row}
        if REQUIRED_HEADERS.issubset(normalized):
            header_index = index
            headers = row
            break
    if header_index < 0:
        raise ValueError(
            "No se reconocieron las columnas obligatorias del reporte de titulación."
        )

    records: list[dict[str, str]] = []
    for row in rows[header_index + 1 :]:
        padded = row + [""] * max(0, len(headers) - len(row))
        record = {
            clean_cell(headers[index]): clean_cell(padded[index])
            for index in range(len(headers))
            if clean_cell(headers[index]) and normalize_key(headers[index]) != "column1"
        }
        identification = _record_value(record, "numeroIdentificacion")
        full_name = _record_value(record, "Nombres")
        career_name = _record_value(record, "NombreCarrera")
        if not identification and not full_name:
            continue
        if not full_name or not career_name:
            continue
        records.append(record)

    if not records:
        raise ValueError("El reporte no contiene estudiantes válidos.")

    enriched: list[dict[str, Any]] = []
    for record in records:
        career_name = _record_value(record, "NombreCarrera")
        career_code = _record_value(record, "CodigoCarrera")
        enriched.append(
            {
                "identification": _record_value(record, "numeroIdentificacion"),
                "full_name": _record_value(record, "Nombres"),
                "career_code": career_code,
                "career_name": career_name,
                "modality": _modality(career_name, career_code),
                "schedule": _record_value(record, "HorarioComplexivo"),
                "academic_status": _record_value(record, "Academico"),
                "documentation_status": _record_value(record, "Documentacion"),
                "financial_status": _record_value(record, "Financiero"),
                "titulation_status": _record_value(record, "Titulacion"),
                "practices_linkage_status": _record_value(
                    record, "PrácticasVinculacion", "PracticasVinculacion"
                ),
                "linkage_status": _record_value(record, "Vinculacion"),
                "graduate_followup_status": _record_value(record, "SeguimientoGraduados"),
                "english_status": _record_value(record, "Ingles"),
                "data_update_status": _record_value(
                    record, "ActualizaciónDatos", "ActualizacionDatos"
                ),
                "personal_email": _record_value(record, "CorreoPersonal"),
                "email": _record_value(record, "CorreoInstitucional").lower(),
                "phone": _record_value(record, "Celular"),
                "campus": _record_value(record, "Sede"),
                "titulation_approval": _record_value(record, "AprobacionTitulacion"),
                "complexive_approval": _record_value(
                    record, "AprobacionComplexivoProyecto"
                ),
            }
        )

    identification_counts = Counter(
        row["identification"] for row in enriched if row["identification"]
    )
    email_counts = Counter(row["email"] for row in enriched if row["email"])
    career_counts: dict[str, Counter[str]] = {
        "presencial": Counter(),
        "en_linea": Counter(),
    }
    for row in enriched:
        career_counts[row["modality"]][row["career_name"]] += 1

    preview = {
        "filename": filename,
        "file_type": "HTML antiguo compatible con Excel (.xls)",
        "period": _extract_period(filename),
        "total": len(enriched),
        "presencial": sum(row["modality"] == "presencial" for row in enriched),
        "en_linea": sum(row["modality"] == "en_linea" for row in enriched),
        "careers_total": len({row["career_name"] for row in enriched}),
        "careers": {
            modality: [
                {"name": name, "students": count}
                for name, count in sorted(career_counts[modality].items())
            ]
            for modality in ("presencial", "en_linea")
        },
        "campuses": dict(sorted(Counter(row["campus"] for row in enriched if row["campus"]).items())),
        "schedules": dict(
            sorted(Counter(row["schedule"] for row in enriched if row["schedule"]).items())
        ),
        "duplicate_identifications": [
            key for key, count in identification_counts.items() if count > 1
        ],
        "duplicate_emails": [key for key, count in email_counts.items() if count > 1],
        "missing_institutional_email": sum(not row["email"] for row in enriched),
    }
    return {"records": enriched, "preview": preview}


def decode_data_url(data_url: str) -> bytes:
    if "," not in data_url:
        raise ValueError("El archivo no fue enviado correctamente.")
    header, encoded = data_url.split(",", 1)
    if ";base64" not in header:
        raise ValueError("El archivo debe enviarse codificado en base64.")
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("El contenido base64 del archivo no es válido.") from exc


def _import_dir() -> Path:
    path = DATA_DIR / "imports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_preview(data_url: str, filename: str) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".xls", ".html", ".htm"}:
        raise ValueError("Seleccione el reporte antiguo en formato .xls, .html o .htm.")
    data = decode_data_url(data_url)
    parsed = parse_roster_html(data, filename)
    token = secrets.token_urlsafe(18)
    base = _import_dir() / token
    (base.with_suffix(".json")).write_text(
        json.dumps(parsed, ensure_ascii=False), encoding="utf-8"
    )
    (base.with_suffix(suffix or ".xls")).write_bytes(data)
    return {"token": token, **parsed["preview"]}


def _load_preview(token: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,80}", token):
        raise ValueError("El identificador de importación no es válido.")
    path = _import_dir() / f"{token}.json"
    if not path.exists():
        raise ValueError("La previsualización expiró o no existe.")
    return json.loads(path.read_text(encoding="utf-8"))


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS institutional_settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                prepared_by TEXT DEFAULT '',
                prepared_role TEXT DEFAULT '',
                reviewed_by TEXT DEFAULT '',
                reviewed_role TEXT DEFAULT '',
                approved_by TEXT DEFAULT '',
                approved_role TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS import_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_name TEXT NOT NULL,
                period TEXT DEFAULT '',
                total_students INTEGER DEFAULT 0,
                presencial_students INTEGER DEFAULT 0,
                online_students INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO institutional_settings
            (id, prepared_by, prepared_role, reviewed_by, reviewed_role,
             approved_by, approved_role, updated_at)
            VALUES (1, '', '', '', '', '', '', ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (utcnow(),),
        )

        report_columns = _columns(conn, "reports")
        for name, definition in REPORT_COLUMNS.items():
            if name not in report_columns:
                conn.execute(f"ALTER TABLE reports ADD COLUMN {name} {definition}")

        career_columns = _columns(conn, "careers")
        for name, definition in CAREER_COLUMNS.items():
            if name not in career_columns:
                conn.execute(f"ALTER TABLE careers ADD COLUMN {name} {definition}")

        student_columns = _columns(conn, "students")
        for name, definition in STUDENT_COLUMNS.items():
            if name not in student_columns:
                conn.execute(f"ALTER TABLE students ADD COLUMN {name} {definition}")

        settings = conn.execute(
            "SELECT * FROM institutional_settings WHERE id = 1"
        ).fetchone()
        if settings and not any(
            settings[key]
            for key in (
                "prepared_by",
                "prepared_role",
                "reviewed_by",
                "reviewed_role",
                "approved_by",
                "approved_role",
            )
        ):
            previous = conn.execute(
                """
                SELECT prepared_by, prepared_role, reviewed_by, reviewed_role,
                       approved_by, approved_role
                FROM reports
                WHERE prepared_by <> '' OR reviewed_by <> '' OR approved_by <> ''
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            if previous:
                conn.execute(
                    """
                    UPDATE institutional_settings SET
                        prepared_by=?, prepared_role=?, reviewed_by=?, reviewed_role=?,
                        approved_by=?, approved_role=?, updated_at=?
                    WHERE id=1
                    """,
                    (*previous, utcnow()),
                )


def get_settings() -> dict[str, Any]:
    ensure_schema()
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM institutional_settings WHERE id = 1"
        ).fetchone()
    return dict(row) if row else {}


def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_schema()
    fields = (
        "prepared_by",
        "prepared_role",
        "reviewed_by",
        "reviewed_role",
        "approved_by",
        "approved_role",
    )
    values = [clean_cell(payload.get(field, "")) for field in fields]
    with connection() as conn:
        conn.execute(
            """
            UPDATE institutional_settings SET
                prepared_by=?, prepared_role=?, reviewed_by=?, reviewed_role=?,
                approved_by=?, approved_role=?, updated_at=?
            WHERE id=1
            """,
            (*values, utcnow()),
        )
        conn.execute(
            """
            UPDATE reports SET
                prepared_by=?, prepared_role=?, reviewed_by=?, reviewed_role=?,
                approved_by=?, approved_role=?, updated_at=?
            """,
            (*values, utcnow()),
        )
    return get_settings()


def settings_for_report() -> dict[str, str]:
    row = get_settings()
    return {
        key: clean_cell(row.get(key, ""))
        for key in (
            "prepared_by",
            "prepared_role",
            "reviewed_by",
            "reviewed_role",
            "approved_by",
            "approved_role",
        )
    }


def commit_preview(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_schema()
    parsed = _load_preview(token)
    preview = parsed["preview"]
    records = parsed["records"]

    period = clean_cell(payload.get("period") or preview.get("period"))
    if not period:
        raise ValueError("Confirme el periodo académico antes de importar.")
    report_name = clean_cell(
        payload.get("report_name") or "Informe Final del Proceso de Titulación"
    )
    version = clean_cell(payload.get("version") or "1.0")
    elaboration_date = clean_cell(payload.get("elaboration_date"))
    settings = settings_for_report()
    now = utcnow()

    report_ids: dict[str, int] = {}
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO import_history
            (original_name, period, total_students, presencial_students,
             online_students, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                preview["filename"],
                period,
                preview["total"],
                preview["presencial"],
                preview["en_linea"],
                now,
            ),
        )
        import_id = int(cursor.lastrowid)

        for modality in ("presencial", "en_linea"):
            modality_records = [
                record for record in records if record["modality"] == modality
            ]
            if not modality_records:
                continue
            code_key = "code_online" if modality == "en_linea" else "code_presencial"
            code = clean_cell(payload.get(code_key, ""))
            cursor = conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, code, version, elaboration_date,
                 prepared_by, prepared_role, reviewed_by, reviewed_role,
                 approved_by, approved_role, status, source_import_id,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'borrador', ?, ?, ?)
                """,
                (
                    report_name,
                    period,
                    modality,
                    code,
                    version,
                    elaboration_date,
                    settings["prepared_by"],
                    settings["prepared_role"],
                    settings["reviewed_by"],
                    settings["reviewed_role"],
                    settings["approved_by"],
                    settings["approved_role"],
                    import_id,
                    now,
                    now,
                ),
            )
            report_id = int(cursor.lastrowid)
            report_ids[modality] = report_id
            create_default_sections(conn, report_id)

            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for record in modality_records:
                grouped[record["career_name"]].append(record)

            for sort_order, career_name in enumerate(sorted(grouped), start=1):
                career_records = grouped[career_name]
                codes = sorted(
                    {record["career_code"] for record in career_records if record["career_code"]}
                )
                career_code = " / ".join(codes)
                cursor = conn.execute(
                    """
                    INSERT INTO careers
                    (report_id, name, sort_order, created_at, career_code)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (report_id, career_name, sort_order, now, career_code),
                )
                career_id = int(cursor.lastrowid)

                for record in career_records:
                    email = record["email"] or None
                    conn.execute(
                        """
                        INSERT INTO students
                        (career_id, full_name, email, created_at, updated_at,
                         identification, career_code, schedule, academic_status,
                         documentation_status, financial_status, titulation_status,
                         practices_linkage_status, linkage_status,
                         graduate_followup_status, english_status,
                         data_update_status, personal_email, phone, campus,
                         titulation_approval, complexive_approval,
                         imported_from_roster, notes_matched, match_method)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, 1, 0, '')
                        """,
                        (
                            career_id,
                            record["full_name"],
                            email,
                            now,
                            now,
                            record["identification"],
                            record["career_code"],
                            record["schedule"],
                            record["academic_status"],
                            record["documentation_status"],
                            record["financial_status"],
                            record["titulation_status"],
                            record["practices_linkage_status"],
                            record["linkage_status"],
                            record["graduate_followup_status"],
                            record["english_status"],
                            record["data_update_status"],
                            record["personal_email"],
                            record["phone"],
                            record["campus"],
                            record["titulation_approval"],
                            record["complexive_approval"],
                        ),
                    )

    return {
        "ok": True,
        "report_ids": report_ids,
        "period": period,
        "total": preview["total"],
        "presencial": preview["presencial"],
        "en_linea": preview["en_linea"],
    }


def merge_moodle_notes(career_id: int, raw_text: str, replace: bool = True) -> dict[str, Any]:
    ensure_schema()
    parsed = parse_moodle_text(raw_text)
    if not parsed["students"]:
        return {"ok": False, **parsed}

    now = utcnow()
    matched_email = 0
    matched_name = 0
    inserted = 0

    with connection() as conn:
        current = rows_to_dicts(
            conn.execute(
                "SELECT * FROM students WHERE career_id = ? ORDER BY id", (career_id,)
            ).fetchall()
        )
        by_email = {
            str(row.get("email") or "").strip().lower(): row
            for row in current
            if str(row.get("email") or "").strip()
        }
        by_name = {
            normalize_name(row.get("full_name")): row
            for row in current
            if normalize_name(row.get("full_name"))
        }

        if replace:
            conn.execute(
                """
                UPDATE students SET
                    ordinary_theory=NULL, supplementary_theory=NULL,
                    source_total_theory=NULL, ordinary_practical=NULL,
                    supplementary_practical=NULL, source_total_practical=NULL,
                    source_total_course=NULL, notes_matched=0,
                    match_method='', updated_at=?
                WHERE career_id=?
                """,
                (now, career_id),
            )

        for student in parsed["students"]:
            email = str(student.get("email") or "").strip().lower()
            target = by_email.get(email) if email else None
            method = "correo"
            if target is None:
                target = by_name.get(normalize_name(student.get("full_name")))
                method = "nombre"

            grade_values = (
                student["ordinary_theory"],
                student["supplementary_theory"],
                student["source_total_theory"],
                student["ordinary_practical"],
                student["supplementary_practical"],
                student["source_total_practical"],
                student["source_total_course"],
            )

            if target:
                if method == "correo":
                    matched_email += 1
                else:
                    matched_name += 1
                new_email = target.get("email") or email or None
                conn.execute(
                    """
                    UPDATE students SET
                        full_name=?, email=?, ordinary_theory=?,
                        supplementary_theory=?, source_total_theory=?,
                        ordinary_practical=?, supplementary_practical=?,
                        source_total_practical=?, source_total_course=?,
                        notes_matched=1, match_method=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        student["full_name"],
                        new_email,
                        *grade_values,
                        method,
                        now,
                        target["id"],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO students
                    (career_id, full_name, email, ordinary_theory,
                     supplementary_theory, source_total_theory,
                     ordinary_practical, supplementary_practical,
                     source_total_practical, source_total_course,
                     created_at, updated_at, imported_from_roster,
                     notes_matched, match_method)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, 'nuevo')
                    """,
                    (
                        career_id,
                        student["full_name"],
                        email or None,
                        *grade_values,
                        now,
                        now,
                    ),
                )
                inserted += 1

    warnings = list(parsed.get("warnings") or [])
    if inserted:
        warnings.append(
            f"{inserted} registro(s) de Moodle no constaban en el reporte general."
        )
    return {
        "ok": True,
        "inserted": len(parsed["students"]),
        "matched_by_email": matched_email,
        "matched_by_name": matched_name,
        "new_students": inserted,
        "warnings": warnings,
        "preview": parsed["students"][:5],
    }
