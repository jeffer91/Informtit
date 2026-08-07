from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from coordinator_registry import normalize
from db import connection, utcnow
from nuclei_service import get_nuclei
from parser import canonical_name_key, clean_moodle_name
from process_service import get_projects
from roster_service import get_report_roster
from workflow_rules import downstream_state, prerequisite_state


PASSING_NUCLEUS_GRADE = 7.0
REQUIRED_NUCLEI = (1, 2, 3, 4)


def _career_key(value: Any) -> str:
    return normalize(value)


def _campus_key(value: Any) -> str:
    # La sede se conserva únicamente como dato del curso y del estudiante.
    # No participa en la identidad ni en la habilitación académica.
    return normalize(value)


def _email_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def _student_name_key(value: Any) -> str:
    return canonical_name_key(clean_moodle_name(str(value or "")))


def _display_name_key(value: Any) -> str:
    return normalize(clean_moodle_name(str(value or "")))


def _source_keys(nucleus_student: dict[str, Any], course: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    email = _email_key(nucleus_student.get("email"))
    if email:
        keys.append(f"email:{email}")
    name = _student_name_key(nucleus_student.get("full_name"))
    if name:
        keys.append(f"name:{_career_key(course.get('career_name'))}|{name}")
    return keys


def ensure_nucleus_matching_schema() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nucleus_manual_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                source_key TEXT NOT NULL,
                source_name TEXT DEFAULT '',
                source_email TEXT DEFAULT '',
                source_career TEXT DEFAULT '',
                student_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(report_id, source_key),
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS nucleus_grade_resolutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                nucleus_number INTEGER NOT NULL,
                chosen_grade REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(report_id, student_id, nucleus_number),
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            );
            """
        )


def _load_manual_matches(report_id: int) -> dict[str, int]:
    ensure_nucleus_matching_schema()
    with connection() as conn:
        rows = conn.execute(
            "SELECT source_key, student_id FROM nucleus_manual_matches WHERE report_id=?",
            (report_id,),
        ).fetchall()
    return {str(row["source_key"]): int(row["student_id"]) for row in rows}


def _load_grade_resolutions(report_id: int) -> dict[tuple[int, int], float]:
    ensure_nucleus_matching_schema()
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT student_id, nucleus_number, chosen_grade
            FROM nucleus_grade_resolutions WHERE report_id=?
            """,
            (report_id,),
        ).fetchall()
    return {
        (int(row["student_id"]), int(row["nucleus_number"])): float(row["chosen_grade"])
        for row in rows
    }


def _project_student_keys(report_id: int) -> tuple[set[int], set[str], set[str], set[tuple[str, str]]]:
    projects = get_projects(report_id).get("projects", [])
    student_ids: set[int] = set()
    identifications: set[str] = set()
    emails: set[str] = set()
    names: set[tuple[str, str]] = set()
    for project in projects:
        if project.get("student_id"):
            student_ids.add(int(project["student_id"]))
        identification = str(project.get("identification") or "").strip()
        if identification:
            identifications.add(identification)
        email = _email_key(project.get("email"))
        if email:
            emails.add(email)
        name = _student_name_key(project.get("full_name"))
        career = _career_key(project.get("career_name"))
        if name:
            names.add((career, name))
    return student_ids, identifications, emails, names


def _is_thesis_student(
    student: dict[str, Any],
    project_keys: tuple[set[int], set[str], set[str], set[tuple[str, str]]],
) -> bool:
    student_ids, identifications, emails, names = project_keys
    if student.get("id") and int(student["id"]) in student_ids:
        return True
    identification = str(student.get("identification") or "").strip()
    if identification and identification in identifications:
        return True
    email = _email_key(student.get("email"))
    if email and email in emails:
        return True
    name_key = (_career_key(student.get("career_name")), _student_name_key(student.get("full_name")))
    return bool(name_key[1] and name_key in names)


def _build_roster_indexes(
    students: list[dict[str, Any]],
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[tuple[str, str], list[dict[str, Any]]],
]:
    by_email: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for student in students:
        email = _email_key(student.get("email"))
        if email:
            by_email[email].append(student)
        name = _student_name_key(student.get("full_name"))
        career = _career_key(student.get("career_name"))
        if name:
            by_name[(career, name)].append(student)
    return by_email, by_name


def _eligible_nucleus_students(
    students: list[dict[str, Any]],
    project_keys: tuple[set[int], set[str], set[str], set[tuple[str, str]]],
) -> list[dict[str, Any]]:
    return [
        student
        for student in students
        if prerequisite_state(student)["complete"] and not _is_thesis_student(student, project_keys)
    ]


def _manual_target(
    nucleus_student: dict[str, Any],
    course: dict[str, Any],
    manual_matches: dict[str, int],
    eligible_by_id: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    for key in _source_keys(nucleus_student, course):
        student_id = manual_matches.get(key)
        if student_id is not None and int(student_id) in eligible_by_id:
            return eligible_by_id[int(student_id)]
    return None


def _match_nucleus_student(
    nucleus_student: dict[str, Any],
    course: dict[str, Any],
    eligible_by_email: dict[str, list[dict[str, Any]]],
    eligible_by_name: dict[tuple[str, str], list[dict[str, Any]]],
    all_by_email: dict[str, list[dict[str, Any]]],
    all_by_name: dict[tuple[str, str], list[dict[str, Any]]],
    manual_matches: dict[str, int],
    eligible_by_id: dict[int, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str, dict[str, Any] | None]:
    """Identifica por correo, luego asociación manual y finalmente nombre+carrera.

    La sede nunca bloquea una coincidencia. Solo se conserva como metadato del
    curso Moodle. Las asociaciones manuales se usan cuando no existe una
    coincidencia exacta inequívoca y se recuerdan para cargas futuras.
    """

    email = _email_key(nucleus_student.get("email"))
    if email:
        candidates = eligible_by_email.get(email, [])
        if len(candidates) == 1:
            return candidates[0], "correo", None

    manual = _manual_target(nucleus_student, course, manual_matches, eligible_by_id)
    if manual:
        return manual, "asociación manual", None

    name = _student_name_key(nucleus_student.get("full_name"))
    career = _career_key(course.get("career_name"))
    if name:
        candidates = eligible_by_name.get((career, name), [])
        if len(candidates) == 1:
            return candidates[0], "nombre y carrera", None

    # Si la identidad existe en la base pero no forma parte de la población de
    # Núcleos, se informa expresamente en vez de asignar la nota a otra persona.
    blocked: dict[str, Any] | None = None
    if email:
        all_candidates = all_by_email.get(email, [])
        if len(all_candidates) == 1 and int(all_candidates[0]["id"]) not in eligible_by_id:
            blocked = all_candidates[0]
    if blocked is None and name:
        all_candidates = all_by_name.get((career, name), [])
        if len(all_candidates) == 1 and int(all_candidates[0]["id"]) not in eligible_by_id:
            blocked = all_candidates[0]
    if blocked is not None:
        return None, "estudiante no habilitado para Núcleos", blocked

    if email and len(eligible_by_email.get(email, [])) > 1:
        return None, "correo ambiguo", None
    if name and len(eligible_by_name.get((career, name), [])) > 1:
        return None, "nombre ambiguo", None
    return None, "sin coincidencia", None


def _similarity(value_a: str, value_b: str) -> float:
    if not value_a or not value_b:
        return 0.0
    return SequenceMatcher(None, value_a, value_b).ratio()


def _suggest_candidates(
    nucleus_student: dict[str, Any],
    course: dict[str, Any],
    eligible_students: list[dict[str, Any]],
    limit: int = 8,
) -> list[dict[str, Any]]:
    source_name = _display_name_key(nucleus_student.get("full_name"))
    source_canonical = _student_name_key(nucleus_student.get("full_name"))
    source_email = _email_key(nucleus_student.get("email"))
    source_local = source_email.split("@", 1)[0] if source_email else ""
    career = _career_key(course.get("career_name"))

    same_career = [
        student for student in eligible_students
        if not career or _career_key(student.get("career_name")) == career
    ]
    pool = same_career or eligible_students
    ranked: list[tuple[float, dict[str, Any]]] = []
    for student in pool:
        candidate_name = _display_name_key(student.get("full_name"))
        candidate_canonical = _student_name_key(student.get("full_name"))
        candidate_email = _email_key(student.get("email"))
        candidate_local = candidate_email.split("@", 1)[0] if candidate_email else ""
        score = max(
            _similarity(source_name, candidate_name),
            _similarity(source_canonical, candidate_canonical),
            _similarity(source_local, candidate_local) * 0.88,
        )
        ranked.append((score, student))

    ranked.sort(key=lambda item: (-item[0], _display_name_key(item[1].get("full_name"))))
    return [
        {
            "student_id": int(student["id"]),
            "identification": student.get("identification") or "",
            "full_name": clean_moodle_name(str(student.get("full_name") or "")),
            "email": student.get("email") or "",
            "career_name": student.get("career_name") or "",
            "similarity": round(score * 100, 1),
        }
        for score, student in ranked[:limit]
    ]


def save_manual_match(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_nucleus_matching_schema()
    student_id = int(payload.get("student_id") or 0)
    if not student_id:
        raise ValueError("Seleccione el estudiante correcto.")

    roster = get_report_roster(report_id)
    students = [dict(student) for student in roster.get("students", [])]
    project_keys = _project_student_keys(report_id)
    eligible = {
        int(student["id"]): student
        for student in _eligible_nucleus_students(students, project_keys)
    }
    target = eligible.get(student_id)
    if target is None:
        raise ValueError("El estudiante seleccionado no está habilitado para Núcleos.")

    source_student = {
        "email": payload.get("source_email") or "",
        "full_name": payload.get("source_name") or "",
    }
    course = {"career_name": payload.get("career_name") or target.get("career_name") or ""}
    keys = _source_keys(source_student, course)
    if not keys:
        raise ValueError("No existe información suficiente para recordar la asociación.")

    now = utcnow()
    with connection() as conn:
        for source_key in keys:
            conn.execute(
                """
                INSERT INTO nucleus_manual_matches
                (report_id, source_key, source_name, source_email, source_career, student_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id, source_key) DO UPDATE SET
                    source_name=excluded.source_name,
                    source_email=excluded.source_email,
                    source_career=excluded.source_career,
                    student_id=excluded.student_id,
                    updated_at=excluded.updated_at
                """,
                (
                    report_id,
                    source_key,
                    clean_moodle_name(str(source_student["full_name"])),
                    _email_key(source_student["email"]),
                    str(course["career_name"]),
                    student_id,
                    now,
                    now,
                ),
            )
    return {
        "ok": True,
        "student_id": student_id,
        "student_name": clean_moodle_name(str(target.get("full_name") or "")),
        "remembered_keys": keys,
    }


def save_grade_resolution(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    student_id = int(payload.get("student_id") or 0)
    nucleus_number = int(payload.get("nucleus_number") or 0)
    try:
        chosen_grade = float(payload.get("chosen_grade"))
    except (TypeError, ValueError):
        raise ValueError("Seleccione una nota válida.")
    if not student_id or nucleus_number not in REQUIRED_NUCLEI:
        raise ValueError("El conflicto de nota no es válido.")

    current = get_eligibility(report_id)
    conflict = next(
        (
            item for item in current.get("grade_conflicts", [])
            if int(item.get("student_id") or 0) == student_id
            and int(item.get("nucleus_number") or 0) == nucleus_number
        ),
        None,
    )
    if conflict is None:
        raise ValueError("Este estudiante ya no tiene un conflicto pendiente en ese núcleo.")
    grades = [float(value) for value in conflict.get("grades", [])]
    if not any(abs(value - chosen_grade) < 0.0001 for value in grades):
        raise ValueError("La nota elegida no corresponde a ninguna de las notas encontradas.")

    ensure_nucleus_matching_schema()
    now = utcnow()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO nucleus_grade_resolutions
            (report_id, student_id, nucleus_number, chosen_grade, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_id, student_id, nucleus_number) DO UPDATE SET
                chosen_grade=excluded.chosen_grade,
                updated_at=excluded.updated_at
            """,
            (report_id, student_id, nucleus_number, chosen_grade, now, now),
        )
    return {
        "ok": True,
        "student_id": student_id,
        "nucleus_number": nucleus_number,
        "chosen_grade": chosen_grade,
    }


def _nuclei_status(grades: dict[int, float | None], has_conflict: bool = False) -> str:
    if has_conflict:
        return "Conflicto"
    values = [grades.get(number) for number in REQUIRED_NUCLEI]
    if any(value is not None and float(value) < PASSING_NUCLEUS_GRADE for value in values):
        return "No habilitado"
    if all(value is not None and float(value) >= PASSING_NUCLEUS_GRADE for value in values):
        return "Habilitado"
    return "Pendiente"


def _stage_status(thesis: bool, prerequisites_complete: bool, nuclei_status: str) -> str:
    if thesis:
        return "Trabajo de Titulación"
    if not prerequisites_complete:
        return "No habilitado para Núcleos"
    if nuclei_status == "Habilitado":
        return "Habilitado para Complexivo"
    if nuclei_status == "No habilitado":
        return "Núcleos reprobados"
    if nuclei_status == "Conflicto":
        return "Conflicto de notas de Núcleos"
    return "En Núcleos / pendiente"


def get_eligibility(report_id: int) -> dict[str, Any]:
    roster = get_report_roster(report_id)
    students = [dict(student) for student in roster.get("students", [])]
    courses = get_nuclei(report_id).get("courses", [])
    project_keys = _project_student_keys(report_id)
    eligible_students = _eligible_nucleus_students(students, project_keys)
    eligible_by_id = {int(student["id"]): student for student in eligible_students}
    eligible_by_email, eligible_by_name = _build_roster_indexes(eligible_students)
    all_by_email, all_by_name = _build_roster_indexes(students)
    manual_matches = _load_manual_matches(report_id)
    grade_resolutions = _load_grade_resolutions(report_id)

    observations: dict[int, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    match_methods: dict[int, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    unmatched: list[dict[str, Any]] = []
    course_matches: list[dict[str, Any]] = []
    prerequisite_conflicts_map: dict[int, dict[str, Any]] = {}

    for course in courses:
        nucleus_number = int(course.get("nucleus_number") or 0)
        if nucleus_number not in REQUIRED_NUCLEI:
            continue
        read_count = 0
        matched_count = 0
        unmatched_count = 0
        for nucleus_student in course.get("students", []):
            read_count += 1
            matched, method, blocked = _match_nucleus_student(
                nucleus_student,
                course,
                eligible_by_email,
                eligible_by_name,
                all_by_email,
                all_by_name,
                manual_matches,
                eligible_by_id,
            )
            if not matched:
                unmatched_count += 1
                record = {
                    "course_id": course.get("id"),
                    "career_name": course.get("career_name") or "",
                    "campus": course.get("campus") or "",
                    "nucleus_number": nucleus_number,
                    "module_code": course.get("module_code") or "",
                    "full_name": clean_moodle_name(str(nucleus_student.get("full_name") or "")),
                    "email": nucleus_student.get("email") or "",
                    "grade": nucleus_student.get("final_grade"),
                    "reason": method,
                    "source_keys": _source_keys(nucleus_student, course),
                    "suggestions": _suggest_candidates(nucleus_student, course, eligible_students),
                }
                unmatched.append(record)
                if blocked is not None:
                    blocked_id = int(blocked["id"])
                    requirements = prerequisite_state(blocked)
                    prerequisite_conflicts_map[blocked_id] = {
                        "student_id": blocked_id,
                        "identification": blocked.get("identification") or "",
                        "full_name": clean_moodle_name(str(blocked.get("full_name") or "")),
                        "career_name": blocked.get("career_name") or "Sin carrera",
                        "campus": blocked.get("campus") or "",
                        "missing_requirements": requirements["missing"],
                    }
                continue

            matched_count += 1
            student_id = int(matched["id"])
            observations[student_id][nucleus_number].append(
                {
                    "grade": nucleus_student.get("final_grade"),
                    "course_id": course.get("id"),
                    "campus": course.get("campus") or "",
                    "module_code": course.get("module_code") or "",
                    "group_code": course.get("group_code") or "",
                    "teacher_name": course.get("teacher_name") or "",
                    "course_title": course.get("course_title") or "",
                    "course_updated_at": course.get("updated_at") or "",
                    "source_email": nucleus_student.get("email") or "",
                    "source_name": clean_moodle_name(str(nucleus_student.get("full_name") or "")),
                    "match_method": method,
                }
            )
            match_methods[student_id][nucleus_number].append(method)

        course_matches.append(
            {
                "course_id": course.get("id"),
                "career_name": course.get("career_name") or "Sin carrera",
                "campus": course.get("campus") or "",
                "nucleus_number": nucleus_number,
                "module_code": course.get("module_code") or "",
                "group_code": course.get("group_code") or "",
                "teacher_name": course.get("teacher_name") or "",
                "read_students": read_count,
                "matched_students": matched_count,
                "unmatched_students": unmatched_count,
            }
        )

    grades_by_student: dict[int, dict[int, float | None]] = defaultdict(dict)
    sources_by_student: dict[int, dict[int, list[dict[str, Any]]]] = defaultdict(dict)
    conflicts_by_student: dict[int, list[dict[str, Any]]] = defaultdict(list)
    grade_conflicts: list[dict[str, Any]] = []
    resolved_grade_conflicts: list[dict[str, Any]] = []

    for student_id, nuclei in observations.items():
        for nucleus_number, source_rows in nuclei.items():
            sources_by_student[student_id][nucleus_number] = source_rows
            numeric = [float(item["grade"]) for item in source_rows if item.get("grade") is not None]
            distinct = sorted({round(value, 4) for value in numeric})
            if len(distinct) > 1:
                chosen = grade_resolutions.get((student_id, nucleus_number))
                if chosen is not None and any(abs(float(value) - float(chosen)) < 0.0001 for value in distinct):
                    grades_by_student[student_id][nucleus_number] = float(chosen)
                    resolved_grade_conflicts.append(
                        {
                            "student_id": student_id,
                            "nucleus_number": nucleus_number,
                            "grades": distinct,
                            "chosen_grade": float(chosen),
                            "sources": source_rows,
                        }
                    )
                else:
                    conflict = {
                        "student_id": student_id,
                        "nucleus_number": nucleus_number,
                        "grades": distinct,
                        "sources": source_rows,
                    }
                    conflicts_by_student[student_id].append(conflict)
                    grade_conflicts.append(conflict)
                    grades_by_student[student_id][nucleus_number] = None
            elif distinct:
                # Si la misma nota aparece varias veces, se consolida sin preguntar.
                grades_by_student[student_id][nucleus_number] = distinct[0]
            else:
                grades_by_student[student_id][nucleus_number] = None

    rows: list[dict[str, Any]] = []
    for student in students:
        student_id = int(student["id"])
        thesis = _is_thesis_student(student, project_keys)
        requirements = prerequisite_state(student)
        downstream = downstream_state(student)
        grades = grades_by_student.get(student_id, {})
        student_conflicts = conflicts_by_student.get(student_id, [])
        nuclei_status = _nuclei_status(grades, bool(student_conflicts))
        eligible_nuclei = requirements["complete"]
        eligible_complexive = bool(
            not thesis and eligible_nuclei and nuclei_status == "Habilitado"
        )
        if thesis:
            option = "Trabajo de Titulación"
        elif eligible_nuclei:
            option = "Examen Complexivo"
        else:
            option = "No habilitado para Núcleos"

        row = {
            "student_id": student_id,
            "identification": student.get("identification") or "",
            "full_name": clean_moodle_name(str(student.get("full_name") or "")),
            "email": student.get("email") or "",
            "career_name": student.get("career_name") or "Sin carrera",
            "campus": student.get("campus") or "",
            "option": option,
            "eligible_for_nuclei": eligible_nuclei,
            "eligible_for_complexive": eligible_complexive,
            "missing_requirements": requirements["missing"],
            "nucleus_1": grades.get(1),
            "nucleus_2": grades.get(2),
            "nucleus_3": grades.get(3),
            "nucleus_4": grades.get(4),
            "approved_nuclei": sum(
                grades.get(number) is not None and float(grades[number]) >= PASSING_NUCLEUS_GRADE
                for number in REQUIRED_NUCLEI
            ),
            "failed_nuclei": sum(
                grades.get(number) is not None and float(grades[number]) < PASSING_NUCLEUS_GRADE
                for number in REQUIRED_NUCLEI
            ),
            "missing_nuclei": sum(grades.get(number) is None for number in REQUIRED_NUCLEI),
            "status": "Trabajo de Titulación" if thesis else (nuclei_status if eligible_nuclei else "No habilitado"),
            "stage_status": _stage_status(thesis, eligible_nuclei, nuclei_status),
            "match_methods": {
                number: sorted(set(methods))
                for number, methods in match_methods.get(student_id, {}).items()
            },
            "nucleus_sources": sources_by_student.get(student_id, {}),
            "grade_conflicts": student_conflicts,
            "has_grade_conflict": bool(student_conflicts),
            **downstream,
        }
        rows.append(row)

    rows.sort(
        key=lambda row: (
            _career_key(row["career_name"]),
            _campus_key(row["campus"]),
            _display_name_key(row["full_name"]),
        )
    )
    nuclei_students = [row for row in rows if row["option"] == "Examen Complexivo"]
    complexive_rows = [row for row in nuclei_students if row["eligible_for_complexive"]]
    blocked_before_nuclei = [row for row in rows if row["option"] == "No habilitado para Núcleos"]
    thesis_rows = [row for row in rows if row["option"] == "Trabajo de Titulación"]

    career_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in nuclei_students:
        career_groups[row["career_name"]].append(row)
    careers: list[dict[str, Any]] = []
    for career_name, career_rows in sorted(career_groups.items(), key=lambda item: _career_key(item[0])):
        total = len(career_rows)
        habilitated = sum(row["eligible_for_complexive"] for row in career_rows)
        failed = sum(row["status"] == "No habilitado" for row in career_rows)
        conflicts = sum(row["status"] == "Conflicto" for row in career_rows)
        pending = sum(row["status"] in {"Pendiente", "Conflicto"} for row in career_rows)
        careers.append(
            {
                "career_name": career_name,
                "total": total,
                "habilitated": habilitated,
                "not_habilitated": failed,
                "pending": pending,
                "grade_conflicts": conflicts,
                "habilitation_percentage": round(habilitated / total * 100, 2) if total else 0.0,
            }
        )

    total_nuclei_students = len(nuclei_students)
    habilitated = len(complexive_rows)
    not_habilitated = sum(row["status"] == "No habilitado" for row in nuclei_students)
    pending = sum(row["status"] in {"Pendiente", "Conflicto"} for row in nuclei_students)
    non_thesis_rows = [row for row in rows if row["option"] != "Trabajo de Titulación"]
    prerequisite_conflicts = list(prerequisite_conflicts_map.values())

    return {
        "rows": rows,
        "complexive_rows": complexive_rows,
        "careers": careers,
        "course_matches": course_matches,
        "unmatched": unmatched,
        "grade_conflicts": grade_conflicts,
        "resolved_grade_conflicts": resolved_grade_conflicts,
        "prerequisite_conflicts": prerequisite_conflicts,
        "summary": {
            "registered": len(rows),
            "eligible_for_nuclei": total_nuclei_students,
            "blocked_before_nuclei": len(blocked_before_nuclei),
            "complexive_candidates": total_nuclei_students,
            "eligible_for_complexive": habilitated,
            "thesis_students": len(thesis_rows),
            "habilitated": habilitated,
            "not_habilitated": not_habilitated,
            "pending": pending,
            "grade_conflicts": len(grade_conflicts),
            "resolved_grade_conflicts": len(resolved_grade_conflicts),
            "habilitation_percentage": round(habilitated / total_nuclei_students * 100, 2) if total_nuclei_students else 0.0,
            "nucleus_without_prerequisites": len(prerequisite_conflicts),
            "titulation_marked": sum(row["titulation_marked"] for row in non_thesis_rows),
            "complexive_project_approved": sum(row["complexive_project_approved"] for row in rows),
            "titles_uploaded": sum(row["titles_uploaded"] for row in rows),
            "unmatched_nucleus_records": len(unmatched),
            "remembered_manual_matches": len(manual_matches),
        },
    }
