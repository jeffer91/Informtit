from __future__ import annotations

from collections import defaultdict
from typing import Any

from coordinator_registry import normalize
from nuclei_service import get_nuclei
from parser import canonical_name_key, clean_moodle_name
from process_service import get_projects
from roster_service import get_report_roster
from workflow_rules import downstream_state, prerequisite_state


PASSING_NUCLEUS_GRADE = 7.0
REQUIRED_NUCLEI = (1, 2, 3, 4)


def _career_key(value: Any) -> str:
    return normalize(value)


def _email_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def _student_name_key(value: Any) -> str:
    return canonical_name_key(clean_moodle_name(str(value or "")))


def _display_name_key(value: Any) -> str:
    """Orden alfabético visible, sin reordenar nombres y apellidos."""

    return normalize(clean_moodle_name(str(value or "")))


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


def _is_thesis_student(student: dict[str, Any], project_keys: tuple[set[int], set[str], set[str], set[tuple[str, str]]]) -> bool:
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


def _build_roster_indexes(students: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], dict[tuple[str, str], list[dict[str, Any]]]]:
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


def _match_nucleus_student(
    nucleus_student: dict[str, Any],
    course: dict[str, Any],
    by_email: dict[str, list[dict[str, Any]]],
    by_name: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str]:
    email = _email_key(nucleus_student.get("email"))
    if email and len(by_email.get(email, [])) == 1:
        return by_email[email][0], "correo"

    name = _student_name_key(nucleus_student.get("full_name"))
    career = _career_key(course.get("career_name"))
    candidates = by_name.get((career, name), []) if name else []
    if len(candidates) == 1:
        return candidates[0], "nombre y carrera"

    return None, "sin coincidencia"


def _nuclei_status(grades: dict[int, float | None]) -> str:
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
    return "En Núcleos / pendiente"


def get_eligibility(report_id: int) -> dict[str, Any]:
    roster = get_report_roster(report_id)
    students = [dict(student) for student in roster.get("students", [])]
    courses = get_nuclei(report_id).get("courses", [])
    project_keys = _project_student_keys(report_id)
    by_email, by_name = _build_roster_indexes(students)

    grades_by_student: dict[int, dict[int, float | None]] = defaultdict(dict)
    match_methods: dict[int, dict[int, str]] = defaultdict(dict)
    unmatched: list[dict[str, Any]] = []
    course_matches: list[dict[str, Any]] = []

    for course in courses:
        nucleus_number = int(course.get("nucleus_number") or 0)
        if nucleus_number not in REQUIRED_NUCLEI:
            continue
        read_count = 0
        matched_count = 0
        unmatched_count = 0
        for nucleus_student in course.get("students", []):
            read_count += 1
            matched, method = _match_nucleus_student(nucleus_student, course, by_email, by_name)
            if not matched:
                unmatched_count += 1
                unmatched.append(
                    {
                        "course_id": course.get("id"),
                        "career_name": course.get("career_name") or "",
                        "nucleus_number": nucleus_number,
                        "full_name": clean_moodle_name(str(nucleus_student.get("full_name") or "")),
                        "email": nucleus_student.get("email") or "",
                        "grade": nucleus_student.get("final_grade"),
                    }
                )
                continue
            matched_count += 1
            student_id = int(matched["id"])
            grades_by_student[student_id][nucleus_number] = nucleus_student.get("final_grade")
            match_methods[student_id][nucleus_number] = method
        course_matches.append(
            {
                "course_id": course.get("id"),
                "career_name": course.get("career_name") or "Sin carrera",
                "nucleus_number": nucleus_number,
                "teacher_name": course.get("teacher_name") or "",
                "read_students": read_count,
                "matched_students": matched_count,
                "unmatched_students": unmatched_count,
            }
        )

    rows: list[dict[str, Any]] = []
    prerequisite_conflicts: list[dict[str, Any]] = []
    for student in students:
        student_id = int(student["id"])
        thesis = _is_thesis_student(student, project_keys)
        requirements = prerequisite_state(student)
        downstream = downstream_state(student)
        grades = grades_by_student.get(student_id, {})
        nuclei_status = _nuclei_status(grades)
        has_nucleus_grade = any(grades.get(number) is not None for number in REQUIRED_NUCLEI)
        eligible_nuclei = requirements["complete"]
        eligible_complexive = bool(
            not thesis
            and eligible_nuclei
            and nuclei_status == "Habilitado"
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
            "match_methods": match_methods.get(student_id, {}),
            **downstream,
        }
        rows.append(row)

        if not thesis and has_nucleus_grade and not eligible_nuclei:
            prerequisite_conflicts.append(
                {
                    "student_id": student_id,
                    "identification": row["identification"],
                    "full_name": row["full_name"],
                    "career_name": row["career_name"],
                    "missing_requirements": requirements["missing"],
                }
            )

    rows.sort(key=lambda row: (_career_key(row["career_name"]), _display_name_key(row["full_name"])))
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
        pending = sum(row["status"] == "Pendiente" for row in career_rows)
        careers.append(
            {
                "career_name": career_name,
                "total": total,
                "habilitated": habilitated,
                "not_habilitated": failed,
                "pending": pending,
                "habilitation_percentage": round(habilitated / total * 100, 2) if total else 0.0,
            }
        )

    total_nuclei_students = len(nuclei_students)
    habilitated = len(complexive_rows)
    not_habilitated = sum(row["status"] == "No habilitado" for row in nuclei_students)
    pending = sum(row["status"] == "Pendiente" for row in nuclei_students)

    non_thesis_rows = [row for row in rows if row["option"] != "Trabajo de Titulación"]
    return {
        "rows": rows,
        "complexive_rows": complexive_rows,
        "careers": careers,
        "course_matches": course_matches,
        "unmatched": unmatched,
        "prerequisite_conflicts": prerequisite_conflicts,
        "summary": {
            "registered": len(rows),
            "eligible_for_nuclei": total_nuclei_students,
            "blocked_before_nuclei": len(blocked_before_nuclei),
            # Se conserva por compatibilidad con la interfaz existente. Este
            # valor representa a quienes ingresaron a Núcleos, no la lista
            # final de estudiantes que pueden rendir el Complexivo.
            "complexive_candidates": total_nuclei_students,
            "eligible_for_complexive": habilitated,
            "thesis_students": len(thesis_rows),
            "habilitated": habilitated,
            "not_habilitated": not_habilitated,
            "pending": pending,
            "habilitation_percentage": round(habilitated / total_nuclei_students * 100, 2) if total_nuclei_students else 0.0,
            "nucleus_without_prerequisites": len(prerequisite_conflicts),
            "titulation_marked": sum(row["titulation_marked"] for row in non_thesis_rows),
            "complexive_project_approved": sum(row["complexive_project_approved"] for row in rows),
            "titles_uploaded": sum(row["titles_uploaded"] for row in rows),
            "unmatched_nucleus_records": len(unmatched),
        },
    }
