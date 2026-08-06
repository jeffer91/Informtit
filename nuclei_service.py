from __future__ import annotations

import json
import re
from statistics import mean
from typing import Any

from coordinator_registry import find_coordinator, normalize
from db import connection, rows_to_dicts, utcnow


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
NUMBER_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")
STATUS_GRADE_RE = re.compile(r"^(Aprobado|Suspenso)\s+(-?\d+(?:[.,]\d+)?)$", re.IGNORECASE)
NOISE = {
    "retroalimentacion proporcionada",
    "matriculacion de usuarios suspendida",
    "suspendido base de datos externa dar de baja",
    "no hay grupos",
}


def ensure_nuclei_schema() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nucleus_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                career_name TEXT NOT NULL,
                nucleus_number INTEGER NOT NULL,
                course_title TEXT DEFAULT '',
                teacher_name TEXT DEFAULT '',
                teacher_candidates TEXT DEFAULT '[]',
                coordinator_name TEXT DEFAULT '',
                coordinator_program TEXT DEFAULT '',
                coordinator_telegram TEXT DEFAULT '',
                participant_students INTEGER DEFAULT 0,
                graded_students INTEGER DEFAULT 0,
                matched_students INTEGER DEFAULT 0,
                missing_grades INTEGER DEFAULT 0,
                extra_grades INTEGER DEFAULT 0,
                course_average REAL,
                approved_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                unevaluated_count INTEGER DEFAULT 0,
                activity_averages TEXT DEFAULT '[]',
                raw_grades TEXT DEFAULT '',
                raw_participants TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
                UNIQUE(report_id, career_name, nucleus_number)
            );

            CREATE TABLE IF NOT EXISTS nucleus_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                average REAL,
                FOREIGN KEY(course_id) REFERENCES nucleus_courses(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS nucleus_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT DEFAULT '',
                final_grade REAL,
                final_status TEXT DEFAULT 'No evaluado',
                participant_found INTEGER DEFAULT 0,
                FOREIGN KEY(course_id) REFERENCES nucleus_courses(id) ON DELETE CASCADE,
                UNIQUE(course_id, email)
            );

            CREATE TABLE IF NOT EXISTS nucleus_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nucleus_student_id INTEGER NOT NULL,
                assessment_id INTEGER NOT NULL,
                grade REAL,
                source_status TEXT DEFAULT '',
                FOREIGN KEY(nucleus_student_id) REFERENCES nucleus_students(id) ON DELETE CASCADE,
                FOREIGN KEY(assessment_id) REFERENCES nucleus_assessments(id) ON DELETE CASCADE,
                UNIQUE(nucleus_student_id, assessment_id)
            );
            """
        )


def _line(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").strip().split())


def _number(value: str | None) -> float | None:
    text = _line(value)
    if not text or text in {"-", "—", "–"}:
        return None
    try:
        return float(text.replace(".", "").replace(",", ".") if "," in text else text)
    except ValueError:
        return None


def _clean_name(value: str) -> str:
    text = re.sub(
        r"Matriculaci[oó]n de usuarios suspendida.*$",
        "",
        _line(value),
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(r"^[A-ZÁÉÍÓÚÑ]{1,3}(?=[A-ZÁÉÍÓÚÑ]{4,})", "", text)
    return text.strip()


def _find_name(lines: list[str], email_index: int) -> str:
    for index in range(email_index - 1, -1, -1):
        candidate = _clean_name(lines[index])
        folded = normalize(candidate)
        if not candidate or folded in NOISE or EMAIL_RE.search(candidate):
            continue
        if re.fullmatch(r"[A-ZÁÉÍÓÚÑ]{1,3}", candidate):
            continue
        if candidate.lower().startswith(("cuestionario", "tarea", "media de calificaciones")):
            continue
        return candidate
    return "ESTUDIANTE SIN NOMBRE"


def _course_metadata(title: str, career_hint: str = "", nucleus_hint: Any = None) -> tuple[str, int]:
    nucleus_match = re.search(r"N[ÚU]CLEO\s*(\d+)", title, re.IGNORECASE)
    nucleus_number = int(nucleus_hint or (nucleus_match.group(1) if nucleus_match else 1))
    career = _line(career_hint)
    if not career and nucleus_match:
        remainder = title[nucleus_match.end() :]
        career = re.split(r"\[|\(|\{|Mod\s*\d+", remainder, maxsplit=1, flags=re.IGNORECASE)[0]
        career = _line(re.sub(r"^[\-:]+", "", career))
    coordinator = find_coordinator(career)
    official = coordinator.get("career") or career
    return official, nucleus_number


def _assessment_headers(lines: list[str], first_email: int) -> list[str]:
    headers: list[str] = []
    for line in lines[:first_email]:
        match = re.match(r"^(?:Cuestionario|Tarea)\s*(.+)$", line, re.IGNORECASE)
        if match:
            name = _line(match.group(1))
            if name and name not in headers:
                headers.append(name)
    return headers


def _grade_token(value: str) -> tuple[float | None, str] | None:
    text = _line(value)
    match = STATUS_GRADE_RE.fullmatch(text)
    if match:
        return _number(match.group(2)), match.group(1).capitalize()
    if text in {"-", "—", "–"}:
        return None, ""
    if NUMBER_RE.fullmatch(text):
        return _number(text), ""
    return None


def parse_grades_text(raw_text: str, career_hint: str = "", nucleus_hint: Any = None) -> dict[str, Any]:
    lines = [_line(line) for line in raw_text.splitlines() if _line(line)]
    email_positions = [index for index, line in enumerate(lines) if EMAIL_RE.fullmatch(line)]
    if not email_positions:
        raise ValueError("No se detectaron correos institucionales en las calificaciones del núcleo.")

    title = lines[0]
    career_name, nucleus_number = _course_metadata(title, career_hint, nucleus_hint)
    assessments = _assessment_headers(lines, email_positions[0])
    if not assessments:
        raise ValueError("No se detectaron las actividades de evaluación del núcleo.")

    average_index = next(
        (index for index, line in enumerate(lines) if normalize(line) == "promedio general"),
        len(lines),
    )
    students: list[dict[str, Any]] = []
    for position, email_index in enumerate(email_positions):
        email = lines[email_index].lower()
        end = email_positions[position + 1] if position + 1 < len(email_positions) else average_index
        segment = lines[email_index + 1 : min(end, average_index)]
        tokens = [token for item in segment if (token := _grade_token(item)) is not None]
        while len(tokens) < len(assessments) + 1:
            tokens.append((None, ""))
        activity_tokens = tokens[: len(assessments)]
        final_grade = tokens[len(assessments)][0]
        final_status = (
            "Aprobado" if final_grade is not None and final_grade >= 7
            else "Reprobado" if final_grade is not None
            else "No evaluado"
        )
        students.append(
            {
                "full_name": _find_name(lines, email_index),
                "email": email,
                "scores": [
                    {"assessment": assessments[index], "grade": token[0], "source_status": token[1]}
                    for index, token in enumerate(activity_tokens)
                ],
                "final_grade": final_grade,
                "final_status": final_status,
            }
        )

    average_values: list[float | None] = []
    if average_index < len(lines):
        for item in lines[average_index + 1 :]:
            token = _grade_token(item)
            if token is not None:
                average_values.append(token[0])
    while len(average_values) < len(assessments) + 1:
        average_values.append(None)

    calculated_averages: list[float | None] = []
    for index in range(len(assessments)):
        values = [student["scores"][index]["grade"] for student in students if student["scores"][index]["grade"] is not None]
        calculated_averages.append(round(mean(values), 2) if values else None)
    final_values = [student["final_grade"] for student in students if student["final_grade"] is not None]
    calculated_course_average = round(mean(final_values), 2) if final_values else None

    return {
        "course_title": title,
        "career_name": career_name,
        "nucleus_number": nucleus_number,
        "assessments": assessments,
        "students": students,
        "activity_averages": [
            {
                "name": name,
                "source_average": average_values[index],
                "calculated_average": calculated_averages[index],
            }
            for index, name in enumerate(assessments)
        ],
        "source_course_average": average_values[len(assessments)],
        "calculated_course_average": calculated_course_average,
    }


def parse_participants_text(raw_text: str, grade_students: list[dict[str, Any]]) -> list[dict[str, str]]:
    grade_names = {student["email"].lower(): student["full_name"] for student in grade_students}
    raw_lines = [line.rstrip() for line in raw_text.splitlines() if line.strip()]
    participants: list[dict[str, str]] = []

    for index, raw_line in enumerate(raw_lines):
        email_match = EMAIL_RE.search(raw_line)
        if not email_match:
            continue
        email = email_match.group(0).lower()
        cells = [_line(cell) for cell in re.split(r"\t+", raw_line) if _line(cell)]
        name = grade_names.get(email, "")
        role = ""
        if cells:
            email_cell = next((i for i, cell in enumerate(cells) if email in cell.lower()), -1)
            if email_cell >= 0:
                if not name and email_cell > 0:
                    name = _clean_name(cells[email_cell - 1])
                role = next((cell for cell in cells[email_cell + 1 :] if normalize(cell) in {"estudiante", "profesor"}), "")
        if not name:
            name = _find_name([_line(line) for line in raw_lines], index)
        if not role:
            following = " ".join(_line(line) for line in raw_lines[index : index + 4])
            role_match = re.search(r"\b(Estudiante|Profesor)\b", following, re.IGNORECASE)
            role = role_match.group(1).capitalize() if role_match else ""
        participants.append({"full_name": name, "email": email, "role": role})

    unique: dict[str, dict[str, str]] = {}
    for participant in participants:
        unique[participant["email"]] = participant
    return list(unique.values())


def _teacher_resolution(career_name: str, participants: list[dict[str, str]]) -> dict[str, Any]:
    coordinator = find_coordinator(career_name)
    teachers = [participant["full_name"] for participant in participants if normalize(participant.get("role")) == "profesor"]
    coordinator_name = coordinator.get("coordinator", "")
    non_coordinators = [teacher for teacher in teachers if normalize(teacher) != normalize(coordinator_name)]
    if len(non_coordinators) == 1:
        teacher = non_coordinators[0]
    elif not non_coordinators and len(teachers) == 1:
        teacher = teachers[0]
    elif len(teachers) == 1:
        teacher = teachers[0]
    else:
        teacher = ""
    return {
        "teacher_name": teacher,
        "teacher_candidates": non_coordinators or teachers,
        "coordinator": coordinator,
    }


def analyze_nucleus(payload: dict[str, Any]) -> dict[str, Any]:
    grades_text = str(payload.get("grades_text") or "")
    participants_text = str(payload.get("participants_text") or "")
    grades = parse_grades_text(grades_text, str(payload.get("career_name") or ""), payload.get("nucleus_number"))
    participants = parse_participants_text(participants_text, grades["students"]) if participants_text.strip() else []
    resolution = _teacher_resolution(grades["career_name"], participants)

    participant_students = {participant["email"] for participant in participants if normalize(participant.get("role")) == "estudiante"}
    graded_students = {student["email"] for student in grades["students"]}
    for student in grades["students"]:
        student["participant_found"] = student["email"] in participant_students if participants else False

    approved = sum(student["final_status"] == "Aprobado" for student in grades["students"])
    failed = sum(student["final_status"] == "Reprobado" for student in grades["students"])
    unevaluated = sum(student["final_status"] == "No evaluado" for student in grades["students"])
    return {
        **grades,
        **resolution,
        "participants": participants,
        "participant_students": len(participant_students),
        "graded_students": len(graded_students),
        "matched_students": len(participant_students & graded_students),
        "missing_grades": len(participant_students - graded_students),
        "extra_grades": len(graded_students - participant_students) if participants else 0,
        "approved_count": approved,
        "failed_count": failed,
        "unevaluated_count": unevaluated,
        "grades_text": grades_text,
        "participants_text": participants_text,
    }


def save_nucleus(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_nuclei_schema()
    data = analyze_nucleus(payload)
    teacher_name = _line(payload.get("teacher_name")) or data["teacher_name"]
    now = utcnow()
    coordinator = data["coordinator"]
    with connection() as conn:
        existing = conn.execute(
            "SELECT id FROM nucleus_courses WHERE report_id=? AND career_name=? AND nucleus_number=?",
            (report_id, data["career_name"], data["nucleus_number"]),
        ).fetchone()
        if existing:
            course_id = int(existing["id"])
            conn.execute("DELETE FROM nucleus_assessments WHERE course_id=?", (course_id,))
            conn.execute("DELETE FROM nucleus_students WHERE course_id=?", (course_id,))
            conn.execute(
                """
                UPDATE nucleus_courses SET course_title=?, teacher_name=?, teacher_candidates=?,
                    coordinator_name=?, coordinator_program=?, coordinator_telegram=?,
                    participant_students=?, graded_students=?, matched_students=?, missing_grades=?,
                    extra_grades=?, course_average=?, approved_count=?, failed_count=?,
                    unevaluated_count=?, activity_averages=?, raw_grades=?, raw_participants=?, updated_at=?
                WHERE id=?
                """,
                (
                    data["course_title"], teacher_name, json.dumps(data["teacher_candidates"], ensure_ascii=False),
                    coordinator.get("coordinator", ""), coordinator.get("program", ""), coordinator.get("telegram", ""),
                    data["participant_students"], data["graded_students"], data["matched_students"], data["missing_grades"],
                    data["extra_grades"], data["calculated_course_average"], data["approved_count"], data["failed_count"],
                    data["unevaluated_count"], json.dumps(data["activity_averages"], ensure_ascii=False),
                    data["grades_text"], data["participants_text"], now, course_id,
                ),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO nucleus_courses
                (report_id, career_name, nucleus_number, course_title, teacher_name, teacher_candidates,
                 coordinator_name, coordinator_program, coordinator_telegram, participant_students,
                 graded_students, matched_students, missing_grades, extra_grades, course_average,
                 approved_count, failed_count, unevaluated_count, activity_averages, raw_grades,
                 raw_participants, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id, data["career_name"], data["nucleus_number"], data["course_title"], teacher_name,
                    json.dumps(data["teacher_candidates"], ensure_ascii=False), coordinator.get("coordinator", ""),
                    coordinator.get("program", ""), coordinator.get("telegram", ""), data["participant_students"],
                    data["graded_students"], data["matched_students"], data["missing_grades"], data["extra_grades"],
                    data["calculated_course_average"], data["approved_count"], data["failed_count"],
                    data["unevaluated_count"], json.dumps(data["activity_averages"], ensure_ascii=False),
                    data["grades_text"], data["participants_text"], now, now,
                ),
            )
            course_id = int(cursor.lastrowid)

        assessment_ids: list[int] = []
        for order, assessment in enumerate(data["assessments"], start=1):
            average = data["activity_averages"][order - 1]["calculated_average"]
            cursor = conn.execute(
                "INSERT INTO nucleus_assessments (course_id, name, sort_order, average) VALUES (?, ?, ?, ?)",
                (course_id, assessment, order, average),
            )
            assessment_ids.append(int(cursor.lastrowid))

        for student in data["students"]:
            cursor = conn.execute(
                """
                INSERT INTO nucleus_students
                (course_id, full_name, email, final_grade, final_status, participant_found)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (course_id, student["full_name"], student["email"], student["final_grade"], student["final_status"], 1 if student["participant_found"] else 0),
            )
            nucleus_student_id = int(cursor.lastrowid)
            for index, score in enumerate(student["scores"]):
                conn.execute(
                    """
                    INSERT INTO nucleus_scores
                    (nucleus_student_id, assessment_id, grade, source_status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (nucleus_student_id, assessment_ids[index], score["grade"], score["source_status"]),
                )
    return {"ok": True, "course_id": course_id, "analysis": data}


def get_nuclei(report_id: int) -> dict[str, Any]:
    ensure_nuclei_schema()
    with connection() as conn:
        courses = rows_to_dicts(conn.execute(
            "SELECT * FROM nucleus_courses WHERE report_id=? ORDER BY career_name, nucleus_number",
            (report_id,),
        ).fetchall())
        for course in courses:
            course["teacher_candidates"] = json.loads(course.get("teacher_candidates") or "[]")
            course["activity_averages"] = json.loads(course.get("activity_averages") or "[]")
            assessments = rows_to_dicts(conn.execute(
                "SELECT * FROM nucleus_assessments WHERE course_id=? ORDER BY sort_order, id",
                (course["id"],),
            ).fetchall())
            students = rows_to_dicts(conn.execute(
                "SELECT * FROM nucleus_students WHERE course_id=? ORDER BY full_name",
                (course["id"],),
            ).fetchall())
            for student in students:
                scores = rows_to_dicts(conn.execute(
                    """
                    SELECT s.*, a.name AS assessment_name, a.sort_order
                    FROM nucleus_scores s JOIN nucleus_assessments a ON a.id=s.assessment_id
                    WHERE s.nucleus_student_id=? ORDER BY a.sort_order, a.id
                    """,
                    (student["id"],),
                ).fetchall())
                student["scores"] = scores
            course["assessments"] = assessments
            course["students"] = students
    return {"courses": courses}


def delete_nucleus(report_id: int, course_id: int) -> dict[str, Any]:
    ensure_nuclei_schema()
    with connection() as conn:
        cursor = conn.execute(
            "DELETE FROM nucleus_courses WHERE id=? AND report_id=?",
            (course_id, report_id),
        )
    if not cursor.rowcount:
        raise ValueError("El curso de núcleo no existe.")
    return {"ok": True}
