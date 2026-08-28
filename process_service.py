from __future__ import annotations

import base64
import re
from datetime import datetime
from statistics import mean
from typing import Any

from db import connection, rows_to_dicts, utcnow
from import_service import HtmlTableParser, clean_cell


COMPLEXIVE_DEFAULTS = [
    ("", "Núcleo 1", "30/03/2026", "02/04/2026"),
    ("", "Núcleo 2", "06/04/2026", "09/04/2026"),
    ("", "Núcleo 3", "10/04/2026", "14/04/2026"),
    ("", "Núcleo 4", "15/04/2026", "18/04/2026"),
    ("", "Examen Complexivo", "20/04/2026", "24/04/2026"),
    ("", "Supletorio", "04/05/2026", "04/05/2026"),
]

THESIS_DEFAULTS = [
    ("Fase 1: Inicio y planificación", "Inducción", "16/12/2025", "16/12/2025"),
    ("Fase 1: Inicio y planificación", "Clase de redacción eficiente de tesis", "28/01/2026", "28/01/2026"),
    ("Fase 1: Inicio y planificación", "Elaboración de propuesta de temas", "01/02/2026", "01/02/2026"),
    ("Fase 1: Inicio y planificación", "Aprobación del tema", "02/02/2026", "04/02/2026"),
    ("Fase 1: Inicio y planificación", "Elaboración del plan de titulación", "08/02/2026", "08/02/2026"),
    ("Fase 1: Inicio y planificación", "Aprobación del plan", "09/02/2026", "11/02/2026"),
    ("Fase 2: Desarrollo y tutorías", "Desarrollo del trabajo (redacción)", "11/02/2026", "28/02/2026"),
    ("Fase 2: Desarrollo y tutorías", "Borrador 1", "01/03/2026", "01/03/2026"),
    ("Fase 2: Desarrollo y tutorías", "Revisión del borrador 1 con el estudiante", "02/03/2026", "05/03/2026"),
    ("Fase 2: Desarrollo y tutorías", "Borrador 2", "08/03/2026", "08/03/2026"),
    ("Fase 2: Desarrollo y tutorías", "Revisión del borrador 2 con el estudiante", "09/03/2026", "13/03/2026"),
    ("Fase 2: Desarrollo y tutorías", "Ajustes finales del trabajo", "14/03/2026", "19/03/2026"),
    ("Fase 2: Desarrollo y tutorías", "Entrega del trabajo de titulación", "22/03/2026", "22/03/2026"),
    ("Fase 2: Desarrollo y tutorías", "Aprobación del tutor e informe antiplagio", "23/03/2026", "25/03/2026"),
    ("Fase 2: Desarrollo y tutorías", "Fin de clases", "27/03/2026", "27/03/2026"),
    ("Fase 3: Defensa final", "Preparación de defensa", "25/03/2026", "08/04/2026"),
    ("Fase 3: Defensa final", "Defensa de tesis", "14/04/2026", "15/04/2026"),
    ("Fase 3: Defensa final", "Tutoría extra de supletorio", "14/04/2026", "15/04/2026"),
    ("Fase 3: Defensa final", "Supletorio de defensa", "16/04/2026", "18/04/2026"),
    ("Fase 3: Defensa final", "Cierre del proceso", "20/04/2026", "20/04/2026"),
]

PRACTICAL_CRITERIA = [
    ("Diseño", 2.5),
    ("Construcción", 2.5),
    ("Funcionamiento", 2.5),
    ("Aplicación", 2.5),
]

DEFENSE_CRITERIA = [
    ("Sustento del marco teórico", 2.0),
    ("Sustento de la propuesta", 2.0),
    ("Uso de recursos", 2.0),
    ("Solventar preguntas", 4.0),
]


def ensure_process_schema() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schedule_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                schedule_type TEXT NOT NULL CHECK(schedule_type IN ('complexive','thesis')),
                phase TEXT DEFAULT '',
                activity TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS thesis_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                student_id INTEGER,
                identification TEXT DEFAULT '',
                full_name TEXT NOT NULL,
                career_code TEXT DEFAULT '',
                career_name TEXT DEFAULT '',
                act_number TEXT DEFAULT '',
                act_date TEXT DEFAULT '',
                tutor_grade REAL,
                reader_grade REAL,
                written_average REAL,
                vocal_1 TEXT DEFAULT '',
                vocal_2 TEXT DEFAULT '',
                vocal_3 TEXT DEFAULT '',
                practical_average REAL,
                defense_average REAL,
                oral_average REAL,
                final_grade REAL,
                source_final_grade REAL,
                source_difference REAL,
                raw_text TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE SET NULL,
                UNIQUE(report_id, identification)
            );

            CREATE TABLE IF NOT EXISTS thesis_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                evaluation_type TEXT NOT NULL CHECK(evaluation_type IN ('practical','defense')),
                criterion TEXT NOT NULL,
                max_score REAL NOT NULL,
                vocal_1 REAL,
                vocal_2 REAL,
                vocal_3 REAL,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY(project_id) REFERENCES thesis_projects(id) ON DELETE CASCADE
            );
            """
        )
        report_ids = [int(row[0]) for row in conn.execute("SELECT id FROM reports").fetchall()]
        for report_id in report_ids:
            seed_schedules(conn, report_id)


def seed_schedules(conn: Any, report_id: int, force: bool = False) -> None:
    now = utcnow()
    for schedule_type, defaults in (("complexive", COMPLEXIVE_DEFAULTS), ("thesis", THESIS_DEFAULTS)):
        count = int(conn.execute(
            "SELECT COUNT(*) FROM schedule_items WHERE report_id=? AND schedule_type=?",
            (report_id, schedule_type),
        ).fetchone()[0])
        if count and not force:
            continue
        if force:
            conn.execute(
                "DELETE FROM schedule_items WHERE report_id=? AND schedule_type=?",
                (report_id, schedule_type),
            )
        for order, (phase, activity, start_date, end_date) in enumerate(defaults, start=1):
            conn.execute(
                """
                INSERT INTO schedule_items
                (report_id, schedule_type, phase, activity, start_date, end_date,
                 sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (report_id, schedule_type, phase, activity, start_date, end_date, order, now, now),
            )


def _valid_date(value: str) -> str:
    text = clean_cell(value)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            continue
    raise ValueError(f"La fecha '{text}' no tiene un formato válido.")


def get_schedules(report_id: int) -> dict[str, Any]:
    ensure_process_schema()
    with connection() as conn:
        seed_schedules(conn, report_id)
        rows = rows_to_dicts(conn.execute(
            """
            SELECT * FROM schedule_items
            WHERE report_id=? ORDER BY schedule_type, sort_order, id
            """,
            (report_id,),
        ).fetchall())
    return {
        "complexive": [row for row in rows if row["schedule_type"] == "complexive"],
        "thesis": [row for row in rows if row["schedule_type"] == "thesis"],
    }


def replace_schedule(report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    if schedule_type not in {"complexive", "thesis"}:
        raise ValueError("Tipo de cronograma no válido.")
    cleaned: list[dict[str, str]] = []
    for entry in entries:
        activity = clean_cell(entry.get("activity"))
        if not activity:
            continue
        cleaned.append({
            "phase": clean_cell(entry.get("phase")) if schedule_type == "thesis" else "",
            "activity": activity,
            "start_date": _valid_date(str(entry.get("start_date") or "")),
            "end_date": _valid_date(str(entry.get("end_date") or "")),
        })
    if not cleaned:
        raise ValueError("El cronograma no contiene actividades válidas.")
    now = utcnow()
    with connection() as conn:
        conn.execute(
            "DELETE FROM schedule_items WHERE report_id=? AND schedule_type=?",
            (report_id, schedule_type),
        )
        for order, entry in enumerate(cleaned, start=1):
            conn.execute(
                """
                INSERT INTO schedule_items
                (report_id, schedule_type, phase, activity, start_date, end_date,
                 sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (report_id, schedule_type, entry["phase"], entry["activity"],
                 entry["start_date"], entry["end_date"], order, now, now),
            )
    return {"ok": True, "count": len(cleaned)}


def reset_schedule(report_id: int, schedule_type: str) -> dict[str, Any]:
    with connection() as conn:
        seed_schedules(conn, report_id, force=True)
    return {"ok": True}


def _decode_upload(data_url: str) -> bytes:
    if "," not in data_url:
        raise ValueError("El archivo no fue enviado correctamente.")
    header, encoded = data_url.split(",", 1)
    if ";base64" not in header:
        raise ValueError("El archivo debe enviarse en base64.")
    return base64.b64decode(encoded)


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo leer el archivo.")


def parse_schedule_text(text: str, schedule_type: str) -> list[dict[str, str]]:
    current_phase = ""
    entries: list[dict[str, str]] = []
    date_re = re.compile(r"\b(?:\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})\b")
    for raw_line in text.splitlines():
        line = clean_cell(raw_line)
        if not line:
            continue
        if schedule_type == "thesis" and re.match(r"^Fase\s+\d+", line, re.IGNORECASE):
            current_phase = line
            continue
        dates = date_re.findall(line)
        if len(dates) < 2:
            continue
        activity = line[: line.find(dates[0])].strip(" \t;,-")
        activity = re.sub(r"^(Actividad|Cronograma\s+\d+\s*:?)\s*", "", activity, flags=re.IGNORECASE).strip()
        if not activity:
            continue
        entries.append({
            "phase": current_phase if schedule_type == "thesis" else "",
            "activity": activity,
            "start_date": _valid_date(dates[0]),
            "end_date": _valid_date(dates[1]),
        })
    if not entries:
        raise ValueError("No se detectaron actividades con fecha de inicio y fin.")
    return entries


def parse_schedule_upload(data_url: str, filename: str, schedule_type: str) -> list[dict[str, str]]:
    data = _decode_upload(data_url)
    text = _decode_text(data)
    if "<table" in text.lower():
        parser = HtmlTableParser()
        parser.feed(text)
        text = "\n".join("\t".join(row) for row in parser.rows)
    return parse_schedule_text(text, schedule_type)


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    text = clean_cell(value)
    if not text or text in {"-", "—"}:
        return None
    try:
        return float(text.replace(".", "").replace(",", ".") if "," in text else text)
    except ValueError:
        return None


def _field_number(text: str, label_pattern: str) -> float | None:
    match = re.search(label_pattern + r"\s*:?\s*([0-9]+(?:[.,][0-9]+)?)", text, re.IGNORECASE)
    return _number(match.group(1)) if match else None


def _field_text(text: str, label_pattern: str, next_pattern: str | None = None) -> str:
    end = f"(?={next_pattern})" if next_pattern else r"(?=\n\s*\n|$)"
    match = re.search(label_pattern + r"\s*:?\s*(.*?)" + end, text, re.IGNORECASE | re.DOTALL)
    return clean_cell(match.group(1)) if match else ""


def _score_block(text: str, start: str, end: str | None, criteria: list[tuple[str, float]]) -> list[dict[str, Any]]:
    pattern = re.escape(start) + r"(.*?)" + (r"(?=" + re.escape(end) + r")" if end else r"$")
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    block = match.group(1) if match else ""
    result: list[dict[str, Any]] = []
    for index, (criterion, default_max) in enumerate(criteria):
        next_criterion = criteria[index + 1][0] if index + 1 < len(criteria) else None
        criterion_pattern = re.escape(criterion) + r"(.*?)" + (r"(?=" + re.escape(next_criterion) + r")" if next_criterion else r"$")
        criterion_match = re.search(criterion_pattern, block, re.IGNORECASE | re.DOTALL)
        numbers = re.findall(r"\d+(?:[.,]\d+)?", criterion_match.group(1) if criterion_match else "")
        parsed = [_number(item) for item in numbers[:4]]
        while len(parsed) < 4:
            parsed.append(None)
        max_score = parsed[0] if parsed[0] is not None else default_max
        result.append({
            "criterion": criterion,
            "max_score": max_score,
            "vocal_1": parsed[1],
            "vocal_2": parsed[2],
            "vocal_3": parsed[3],
        })
    return result


def _evaluation_average(scores: list[dict[str, Any]]) -> float | None:
    totals: list[float] = []
    for vocal_key in ("vocal_1", "vocal_2", "vocal_3"):
        values = [row[vocal_key] for row in scores if row[vocal_key] is not None]
        if values:
            totals.append(sum(values))
    return round(mean(totals), 2) if totals else None


def parse_project_text(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    raw_text = str(payload.get("text") or "").strip()
    if not raw_text:
        raise ValueError("Pegue la información del proyecto de titulación.")
    student_id = int(payload.get("student_id") or 0) or None

    with connection() as conn:
        student = None
        if student_id:
            student = conn.execute(
                """
                SELECT s.*, c.name AS career_name, c.career_code
                FROM students s JOIN careers c ON c.id=s.career_id
                WHERE s.id=? AND c.report_id=?
                """,
                (student_id, report_id),
            ).fetchone()
        identification_match = re.search(r"(?:C[eé]dula|Cedula)\s*:?\s*(\d{8,13})", raw_text, re.IGNORECASE)
        identification = identification_match.group(1) if identification_match else ""
        if not student and identification:
            student = conn.execute(
                """
                SELECT s.*, c.name AS career_name, c.career_code
                FROM students s JOIN careers c ON c.id=s.career_id
                WHERE c.report_id=? AND s.identification=?
                """,
                (report_id, identification),
            ).fetchone()
        if not student:
            raise ValueError("Seleccione un estudiante de la base o incluya una cédula válida en el texto.")
        student = dict(student)

    tutor = _field_number(raw_text, r"CALIFICACI[ÓO]N\s+TUTOR")
    reader = _field_number(raw_text, r"CALIFICACI[ÓO]N\s+LECTOR")
    source_written = _field_number(raw_text, r"PROMEDIO\s+TRABAJO\s+ESCRITO")
    written = source_written if source_written is not None else round(mean([v for v in (tutor, reader) if v is not None]), 2) if tutor is not None or reader is not None else None

    act_number_match = re.search(r"N[ÚU]MERO\s+DE\s+ACTA\s+DE\s+GRADO\s*:?\s*([A-Za-z0-9-]+)", raw_text, re.IGNORECASE)
    act_date_match = re.search(r"FECHA\s+ACTA\s+DE\s+GRADO\s*:?\s*(\d{2}/\d{2}/\d{4})", raw_text, re.IGNORECASE)

    vocal_1 = _field_text(raw_text, r"PRIMER\s+VOCAL", r"SEGUNDO\s+VOCAL")
    vocal_2 = _field_text(raw_text, r"SEGUNDO\s+VOCAL", r"TERCER\s+VOCAL")
    vocal_3 = _field_text(raw_text, r"TERCER\s+VOCAL", r"EVALUACI[ÓO]N\s+PRACTICA")

    practical_scores = _score_block(raw_text, "EVALUACIÓN PRACTICA", "EVALUACIÓN DE LA DEFENSA", PRACTICAL_CRITERIA)
    defense_scores = _score_block(raw_text, "EVALUACIÓN DE LA DEFENSA", "1. PROMEDIO TRABAJO ESCRITO", DEFENSE_CRITERIA)
    practical_average = _evaluation_average(practical_scores)
    defense_average = _evaluation_average(defense_scores)
    oral_average = round((practical_average + defense_average) / 2, 2) if practical_average is not None and defense_average is not None else None
    final_grade = round(written * 0.60 + oral_average * 0.40, 2) if written is not None and oral_average is not None else None
    source_final = _field_number(raw_text, r"CALIFICACION\s+FINAL\s+DEL\s+PROYECTO\s+DE\s+TITULACION[^:]*")
    difference = round(final_grade - source_final, 2) if final_grade is not None and source_final is not None else None

    now = utcnow()
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO thesis_projects
            (report_id, student_id, identification, full_name, career_code, career_name,
             act_number, act_date, tutor_grade, reader_grade, written_average,
             vocal_1, vocal_2, vocal_3, practical_average, defense_average,
             oral_average, final_grade, source_final_grade, source_difference,
             raw_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_id, identification) DO UPDATE SET
                student_id=excluded.student_id, full_name=excluded.full_name,
                career_code=excluded.career_code, career_name=excluded.career_name,
                act_number=excluded.act_number, act_date=excluded.act_date,
                tutor_grade=excluded.tutor_grade, reader_grade=excluded.reader_grade,
                written_average=excluded.written_average, vocal_1=excluded.vocal_1,
                vocal_2=excluded.vocal_2, vocal_3=excluded.vocal_3,
                practical_average=excluded.practical_average,
                defense_average=excluded.defense_average,
                oral_average=excluded.oral_average, final_grade=excluded.final_grade,
                source_final_grade=excluded.source_final_grade,
                source_difference=excluded.source_difference, raw_text=excluded.raw_text,
                updated_at=excluded.updated_at
            """,
            (
                report_id, student["id"], student.get("identification") or identification,
                student["full_name"], student.get("career_code") or "",
                student.get("career_name") or "", act_number_match.group(1) if act_number_match else "",
                act_date_match.group(1) if act_date_match else "", tutor, reader, written,
                vocal_1, vocal_2, vocal_3, practical_average, defense_average,
                oral_average, final_grade, source_final, difference, raw_text, now, now,
            ),
        )
        if cursor.lastrowid:
            project_id = int(cursor.lastrowid)
        else:
            project_id = int(conn.execute(
                "SELECT id FROM thesis_projects WHERE report_id=? AND identification=?",
                (report_id, student.get("identification") or identification),
            ).fetchone()[0])
        conn.execute("DELETE FROM thesis_scores WHERE project_id=?", (project_id,))
        for evaluation_type, rows in (("practical", practical_scores), ("defense", defense_scores)):
            for order, row in enumerate(rows, start=1):
                conn.execute(
                    """
                    INSERT INTO thesis_scores
                    (project_id, evaluation_type, criterion, max_score, vocal_1,
                     vocal_2, vocal_3, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (project_id, evaluation_type, row["criterion"], row["max_score"],
                     row["vocal_1"], row["vocal_2"], row["vocal_3"], order),
                )
    return {"ok": True, "project_id": project_id, "final_grade": final_grade}


def get_projects(report_id: int) -> dict[str, Any]:
    ensure_process_schema()
    with connection() as conn:
        projects = rows_to_dicts(conn.execute(
            "SELECT * FROM thesis_projects WHERE report_id=? ORDER BY full_name",
            (report_id,),
        ).fetchall())
        scores_by_project: dict[int, list[dict[str, Any]]] = {
            int(project["id"]): [] for project in projects
        }
        if projects:
            project_ids = [int(project["id"]) for project in projects]
            for start in range(0, len(project_ids), 400):
                chunk = project_ids[start:start + 400]
                placeholders = ",".join("?" for _ in chunk)
                score_rows = rows_to_dicts(conn.execute(
                    f"""
                    SELECT * FROM thesis_scores
                    WHERE project_id IN ({placeholders})
                    ORDER BY project_id, evaluation_type, sort_order, id
                    """,
                    tuple(chunk),
                ).fetchall())
                for score in score_rows:
                    scores_by_project.setdefault(int(score["project_id"]), []).append(score)
        for project in projects:
            project["scores"] = scores_by_project.get(int(project["id"]), [])
    finals = [p["final_grade"] for p in projects if p["final_grade"] is not None]
    return {
        "projects": projects,
        "summary": {
            "total": len(projects),
            "average_final": round(mean(finals), 2) if finals else None,
            "approved": sum(1 for value in finals if value >= 7.0),
            "failed": sum(1 for value in finals if value < 7.0),
        },
    }


def delete_project(report_id: int, project_id: int) -> dict[str, Any]:
    with connection() as conn:
        cursor = conn.execute(
            "DELETE FROM thesis_projects WHERE id=? AND report_id=?",
            (project_id, report_id),
        )
    return {"ok": True, "deleted": cursor.rowcount}
