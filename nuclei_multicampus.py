from __future__ import annotations

import json
import re
from typing import Any

import nuclei_service as legacy
from coordinator_registry import normalize
from db import connection, rows_to_dicts, utcnow


_ORIGINAL_ANALYZE = legacy.analyze_nucleus
_ORIGINAL_ENSURE = legacy.ensure_nuclei_schema


def _line(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").strip().split())


def _metadata_from_title(title: str, payload: dict[str, Any] | None = None) -> dict[str, str]:
    payload = payload or {}
    text = _line(title)

    campus = _line(payload.get("campus"))
    if not campus:
        match = re.search(r"-\s*([A-Za-zÁÉÍÓÚÑáéíóúñ ]+)\]\s*$", text)
        campus = _line(match.group(1)) if match else ""

    module_code = _line(payload.get("module_code"))
    if not module_code:
        match = re.search(r"\bMod\s*(\d+)\b", text, re.IGNORECASE)
        module_code = match.group(1) if match else ""

    period_label = _line(payload.get("period_label"))
    if not period_label:
        match = re.search(r"\bMod\s*\d+\s*,\s*([^,\]\s]+)", text, re.IGNORECASE)
        period_label = _line(match.group(1)) if match else ""

    group_code = _line(payload.get("group_code"))
    if not group_code:
        match = re.search(r"\bEsp\.\s*([A-Za-z0-9_-]+)", text, re.IGNORECASE)
        group_code = _line(match.group(1)) if match else ""

    schedule = _line(payload.get("schedule"))
    if not schedule:
        match = re.search(r"(\d{1,2}h\d{2}\s*-\s*\d{1,2}h\d{2})", text, re.IGNORECASE)
        schedule = _line(match.group(1)) if match else ""

    return {
        "campus": campus,
        "module_code": module_code,
        "period_label": period_label,
        "group_code": group_code,
        "schedule": schedule,
    }


def _course_key(data: dict[str, Any]) -> str:
    career = normalize(data.get("career_name"))
    nucleus = int(data.get("nucleus_number") or 0)
    campus = normalize(data.get("campus"))
    module_code = normalize(data.get("module_code"))
    period_label = normalize(data.get("period_label"))
    group_code = normalize(data.get("group_code"))
    schedule = normalize(data.get("schedule"))
    structured = "|".join(
        [career, str(nucleus), campus, module_code, period_label, group_code, schedule]
    )
    if any((campus, module_code, period_label, group_code, schedule)):
        return structured
    return f"{career}|{nucleus}|title:{normalize(data.get('course_title'))}"


def analyze_nucleus(payload: dict[str, Any]) -> dict[str, Any]:
    data = _ORIGINAL_ANALYZE(payload)
    metadata = _metadata_from_title(data.get("course_title") or "", payload)
    data.update(metadata)
    data["course_key"] = _course_key(data)
    return data


def _table_exists(conn: Any, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def ensure_multicampus_schema() -> None:
    # Se conserva el esquema anterior para poder migrar instalaciones existentes.
    _ORIGINAL_ENSURE()
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nucleus_multicampus_meta (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS nucleus_course_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                career_name TEXT NOT NULL,
                nucleus_number INTEGER NOT NULL,
                campus TEXT DEFAULT '',
                module_code TEXT DEFAULT '',
                period_label TEXT DEFAULT '',
                group_code TEXT DEFAULT '',
                schedule TEXT DEFAULT '',
                course_key TEXT NOT NULL,
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
                UNIQUE(report_id, course_key)
            );

            CREATE TABLE IF NOT EXISTS nucleus_instance_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                average REAL,
                FOREIGN KEY(course_id) REFERENCES nucleus_course_instances(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS nucleus_instance_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT DEFAULT '',
                final_grade REAL,
                final_status TEXT DEFAULT 'No evaluado',
                participant_found INTEGER DEFAULT 0,
                FOREIGN KEY(course_id) REFERENCES nucleus_course_instances(id) ON DELETE CASCADE,
                UNIQUE(course_id, email)
            );

            CREATE TABLE IF NOT EXISTS nucleus_instance_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nucleus_student_id INTEGER NOT NULL,
                assessment_id INTEGER NOT NULL,
                grade REAL,
                source_status TEXT DEFAULT '',
                FOREIGN KEY(nucleus_student_id) REFERENCES nucleus_instance_students(id) ON DELETE CASCADE,
                FOREIGN KEY(assessment_id) REFERENCES nucleus_instance_assessments(id) ON DELETE CASCADE,
                UNIQUE(nucleus_student_id, assessment_id)
            );
            """
        )

        migrated = conn.execute(
            "SELECT value FROM nucleus_multicampus_meta WHERE key='legacy_migrated'"
        ).fetchone()
        if migrated:
            return

        if _table_exists(conn, "nucleus_courses"):
            legacy_courses = rows_to_dicts(
                conn.execute("SELECT * FROM nucleus_courses ORDER BY id").fetchall()
            )
            for old_course in legacy_courses:
                metadata = _metadata_from_title(old_course.get("course_title") or "")
                course_data = {**old_course, **metadata}
                course_data["course_key"] = _course_key(course_data)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO nucleus_course_instances
                    (report_id, career_name, nucleus_number, campus, module_code, period_label,
                     group_code, schedule, course_key, course_title, teacher_name, teacher_candidates,
                     coordinator_name, coordinator_program, coordinator_telegram, participant_students,
                     graded_students, matched_students, missing_grades, extra_grades, course_average,
                     approved_count, failed_count, unevaluated_count, activity_averages, raw_grades,
                     raw_participants, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        old_course["report_id"], old_course["career_name"], old_course["nucleus_number"],
                        metadata["campus"], metadata["module_code"], metadata["period_label"],
                        metadata["group_code"], metadata["schedule"], course_data["course_key"],
                        old_course.get("course_title") or "", old_course.get("teacher_name") or "",
                        old_course.get("teacher_candidates") or "[]", old_course.get("coordinator_name") or "",
                        old_course.get("coordinator_program") or "", old_course.get("coordinator_telegram") or "",
                        old_course.get("participant_students") or 0, old_course.get("graded_students") or 0,
                        old_course.get("matched_students") or 0, old_course.get("missing_grades") or 0,
                        old_course.get("extra_grades") or 0, old_course.get("course_average"),
                        old_course.get("approved_count") or 0, old_course.get("failed_count") or 0,
                        old_course.get("unevaluated_count") or 0, old_course.get("activity_averages") or "[]",
                        old_course.get("raw_grades") or "", old_course.get("raw_participants") or "",
                        old_course.get("created_at") or utcnow(), old_course.get("updated_at") or utcnow(),
                    ),
                )
                new_course = conn.execute(
                    "SELECT id FROM nucleus_course_instances WHERE report_id=? AND course_key=?",
                    (old_course["report_id"], course_data["course_key"]),
                ).fetchone()
                if not new_course:
                    continue
                new_course_id = int(new_course["id"])
                assessment_map: dict[int, int] = {}
                for assessment in rows_to_dicts(
                    conn.execute(
                        "SELECT * FROM nucleus_assessments WHERE course_id=? ORDER BY id",
                        (old_course["id"],),
                    ).fetchall()
                ):
                    new_assessment = conn.execute(
                        "INSERT INTO nucleus_instance_assessments (course_id, name, sort_order, average) VALUES (?, ?, ?, ?)",
                        (new_course_id, assessment["name"], assessment.get("sort_order") or 0, assessment.get("average")),
                    )
                    assessment_map[int(assessment["id"])] = int(new_assessment.lastrowid)

                for student in rows_to_dicts(
                    conn.execute(
                        "SELECT * FROM nucleus_students WHERE course_id=? ORDER BY id",
                        (old_course["id"],),
                    ).fetchall()
                ):
                    new_student = conn.execute(
                        """
                        INSERT INTO nucleus_instance_students
                        (course_id, full_name, email, final_grade, final_status, participant_found)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            new_course_id, student["full_name"], student.get("email") or "",
                            student.get("final_grade"), student.get("final_status") or "No evaluado",
                            student.get("participant_found") or 0,
                        ),
                    )
                    new_student_id = int(new_student.lastrowid)
                    scores = rows_to_dicts(
                        conn.execute(
                            "SELECT * FROM nucleus_scores WHERE nucleus_student_id=? ORDER BY id",
                            (student["id"],),
                        ).fetchall()
                    )
                    for score in scores:
                        assessment_id = assessment_map.get(int(score["assessment_id"]))
                        if assessment_id is None:
                            continue
                        conn.execute(
                            """
                            INSERT INTO nucleus_instance_scores
                            (nucleus_student_id, assessment_id, grade, source_status)
                            VALUES (?, ?, ?, ?)
                            """,
                            (new_student_id, assessment_id, score.get("grade"), score.get("source_status") or ""),
                        )

        conn.execute(
            "INSERT OR REPLACE INTO nucleus_multicampus_meta (key, value) VALUES ('legacy_migrated', '1')"
        )


def save_nucleus(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_multicampus_schema()
    data = analyze_nucleus(payload)
    teacher_name = _line(payload.get("teacher_name")) or data["teacher_name"]
    now = utcnow()
    coordinator = data["coordinator"]

    with connection() as conn:
        existing = conn.execute(
            "SELECT id FROM nucleus_course_instances WHERE report_id=? AND course_key=?",
            (report_id, data["course_key"]),
        ).fetchone()
        if existing:
            course_id = int(existing["id"])
            conn.execute("DELETE FROM nucleus_instance_assessments WHERE course_id=?", (course_id,))
            conn.execute("DELETE FROM nucleus_instance_students WHERE course_id=?", (course_id,))
            conn.execute(
                """
                UPDATE nucleus_course_instances SET career_name=?, nucleus_number=?, campus=?, module_code=?,
                    period_label=?, group_code=?, schedule=?, course_title=?, teacher_name=?, teacher_candidates=?,
                    coordinator_name=?, coordinator_program=?, coordinator_telegram=?, participant_students=?,
                    graded_students=?, matched_students=?, missing_grades=?, extra_grades=?, course_average=?,
                    approved_count=?, failed_count=?, unevaluated_count=?, activity_averages=?, raw_grades=?,
                    raw_participants=?, updated_at=? WHERE id=?
                """,
                (
                    data["career_name"], data["nucleus_number"], data["campus"], data["module_code"],
                    data["period_label"], data["group_code"], data["schedule"], data["course_title"],
                    teacher_name, json.dumps(data["teacher_candidates"], ensure_ascii=False),
                    coordinator.get("coordinator", ""), coordinator.get("program", ""), coordinator.get("telegram", ""),
                    data["participant_students"], data["graded_students"], data["matched_students"],
                    data["missing_grades"], data["extra_grades"], data["calculated_course_average"],
                    data["approved_count"], data["failed_count"], data["unevaluated_count"],
                    json.dumps(data["activity_averages"], ensure_ascii=False), data["grades_text"],
                    data["participants_text"], now, course_id,
                ),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO nucleus_course_instances
                (report_id, career_name, nucleus_number, campus, module_code, period_label, group_code,
                 schedule, course_key, course_title, teacher_name, teacher_candidates, coordinator_name,
                 coordinator_program, coordinator_telegram, participant_students, graded_students,
                 matched_students, missing_grades, extra_grades, course_average, approved_count,
                 failed_count, unevaluated_count, activity_averages, raw_grades, raw_participants,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id, data["career_name"], data["nucleus_number"], data["campus"], data["module_code"],
                    data["period_label"], data["group_code"], data["schedule"], data["course_key"],
                    data["course_title"], teacher_name, json.dumps(data["teacher_candidates"], ensure_ascii=False),
                    coordinator.get("coordinator", ""), coordinator.get("program", ""), coordinator.get("telegram", ""),
                    data["participant_students"], data["graded_students"], data["matched_students"],
                    data["missing_grades"], data["extra_grades"], data["calculated_course_average"],
                    data["approved_count"], data["failed_count"], data["unevaluated_count"],
                    json.dumps(data["activity_averages"], ensure_ascii=False), data["grades_text"],
                    data["participants_text"], now, now,
                ),
            )
            course_id = int(cursor.lastrowid)

        assessment_ids: list[int] = []
        for order, assessment in enumerate(data["assessments"], start=1):
            average = data["activity_averages"][order - 1]["calculated_average"]
            cursor = conn.execute(
                "INSERT INTO nucleus_instance_assessments (course_id, name, sort_order, average) VALUES (?, ?, ?, ?)",
                (course_id, assessment, order, average),
            )
            assessment_ids.append(int(cursor.lastrowid))

        for student in data["students"]:
            cursor = conn.execute(
                """
                INSERT INTO nucleus_instance_students
                (course_id, full_name, email, final_grade, final_status, participant_found)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    course_id, student["full_name"], student["email"], student["final_grade"],
                    student["final_status"], 1 if student["participant_found"] else 0,
                ),
            )
            nucleus_student_id = int(cursor.lastrowid)
            for index, score in enumerate(student["scores"]):
                conn.execute(
                    """
                    INSERT INTO nucleus_instance_scores
                    (nucleus_student_id, assessment_id, grade, source_status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (nucleus_student_id, assessment_ids[index], score["grade"], score["source_status"]),
                )

    return {"ok": True, "course_id": course_id, "analysis": data}


def _id_chunks(values: list[int], size: int = 400):
    """Divide ids para respetar el límite de parámetros de SQLite."""
    for start in range(0, len(values), size):
        yield values[start:start + size]


def get_nuclei(report_id: int) -> dict[str, Any]:
    """Carga Núcleos en lotes, evitando consultas por curso y por estudiante."""
    ensure_multicampus_schema()
    with connection() as conn:
        courses = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM nucleus_course_instances
                WHERE report_id=?
                ORDER BY career_name, campus, nucleus_number, module_code, group_code, id
                """,
                (report_id,),
            ).fetchall()
        )
        if not courses:
            return {"courses": []}

        for course in courses:
            course["teacher_candidates"] = json.loads(course.get("teacher_candidates") or "[]")
            course["activity_averages"] = json.loads(course.get("activity_averages") or "[]")

        course_ids = [int(course["id"]) for course in courses]
        assessments_by_course: dict[int, list[dict[str, Any]]] = {
            course_id: [] for course_id in course_ids
        }
        students_by_course: dict[int, list[dict[str, Any]]] = {
            course_id: [] for course_id in course_ids
        }

        for chunk in _id_chunks(course_ids):
            placeholders = ",".join("?" for _ in chunk)
            assessments = rows_to_dicts(
                conn.execute(
                    f"""
                    SELECT * FROM nucleus_instance_assessments
                    WHERE course_id IN ({placeholders})
                    ORDER BY course_id, sort_order, id
                    """,
                    tuple(chunk),
                ).fetchall()
            )
            for assessment in assessments:
                assessments_by_course.setdefault(int(assessment["course_id"]), []).append(assessment)

            students = rows_to_dicts(
                conn.execute(
                    f"""
                    SELECT * FROM nucleus_instance_students
                    WHERE course_id IN ({placeholders})
                    ORDER BY course_id, full_name, id
                    """,
                    tuple(chunk),
                ).fetchall()
            )
            for student in students:
                students_by_course.setdefault(int(student["course_id"]), []).append(student)

        all_students = [
            student
            for course_students in students_by_course.values()
            for student in course_students
        ]
        scores_by_student: dict[int, list[dict[str, Any]]] = {
            int(student["id"]): [] for student in all_students
        }
        student_ids = list(scores_by_student)

        for chunk in _id_chunks(student_ids):
            placeholders = ",".join("?" for _ in chunk)
            scores = rows_to_dicts(
                conn.execute(
                    f"""
                    SELECT s.*, a.name AS assessment_name, a.sort_order
                    FROM nucleus_instance_scores s
                    JOIN nucleus_instance_assessments a ON a.id=s.assessment_id
                    WHERE s.nucleus_student_id IN ({placeholders})
                    ORDER BY s.nucleus_student_id, a.sort_order, a.id
                    """,
                    tuple(chunk),
                ).fetchall()
            )
            for score in scores:
                scores_by_student.setdefault(int(score["nucleus_student_id"]), []).append(score)

        for course in courses:
            course_id = int(course["id"])
            students = students_by_course.get(course_id, [])
            for student in students:
                student["scores"] = scores_by_student.get(int(student["id"]), [])
            course["assessments"] = assessments_by_course.get(course_id, [])
            course["students"] = students

    return {"courses": courses}


def get_nuclei_career_names(report_id: int) -> list[str]:
    """Obtiene solo las carreras de Núcleos sin cargar estudiantes ni calificaciones."""
    ensure_multicampus_schema()
    with connection() as conn:
        report_ids = [int(report_id)]
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
        if "period_project_id" in columns:
            project = conn.execute(
                "SELECT period_project_id FROM reports WHERE id=?",
                (report_id,),
            ).fetchone()
            if project and project[0] is not None:
                report_ids = [
                    int(row[0])
                    for row in conn.execute(
                        "SELECT id FROM reports WHERE period_project_id=? ORDER BY id",
                        (int(project[0]),),
                    ).fetchall()
                ] or report_ids

        placeholders = ",".join("?" for _ in report_ids)
        rows = conn.execute(
            f"""
            SELECT DISTINCT career_name
            FROM nucleus_course_instances
            WHERE report_id IN ({placeholders})
              AND TRIM(COALESCE(career_name, '')) <> ''
            ORDER BY career_name
            """,
            tuple(report_ids),
        ).fetchall()
    return [str(row[0]) for row in rows]


def delete_nucleus(report_id: int, course_id: int) -> dict[str, Any]:
    ensure_multicampus_schema()
    with connection() as conn:
        cursor = conn.execute(
            "DELETE FROM nucleus_course_instances WHERE id=? AND report_id=?",
            (course_id, report_id),
        )
    if not cursor.rowcount:
        raise ValueError("El curso de núcleo no existe.")
    return {"ok": True}


def install() -> None:
    ensure_multicampus_schema()

    # El servicio y las rutas deben utilizar la entidad curso Moodle, no solo
    # carrera+número de núcleo. Esto permite Quito, Manta y paralelos distintos.
    legacy.analyze_nucleus = analyze_nucleus
    legacy.save_nucleus = save_nucleus
    legacy.get_nuclei = get_nuclei
    legacy.delete_nucleus = delete_nucleus
    legacy.ensure_nuclei_schema = ensure_multicampus_schema

    import eligibility_service
    import nuclei_export
    import nuclei_routes
    import report_quality

    eligibility_service.get_nuclei = get_nuclei
    nuclei_export.get_nuclei = get_nuclei
    nuclei_routes.analyze_nucleus = analyze_nucleus
    nuclei_routes.save_nucleus = save_nucleus
    nuclei_routes.get_nuclei = get_nuclei
    nuclei_routes.delete_nucleus = delete_nucleus
    nuclei_routes.ensure_nuclei_schema = ensure_multicampus_schema
    report_quality.get_nuclei = get_nuclei
