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


def _campus_key(value: Any) -> str:
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


def _campus_candidates(candidates: list[dict[str, Any]], course: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    course_campus = _campus_key(course.get("campus"))
    if not course_campus:
        return candidates, False
    compatible = [
        student
        for student in candidates
        if not _campus_key(student.get("campus"))
        or _campus_key(student.get("campus")) == course_campus
    ]
    mismatch = bool(candidates) and not compatible
    return compatible, mismatch


def _match_nucleus_student(
    nucleus_student: dict[str, Any],
    course: dict[str, Any],
    by_email: dict[str, list[dict[str, Any]]],
    by_name: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str]:
    email = _email_key(nucleus_student.get("email"))
    if email:
        candidates, mismatch = _campus_candidates(by_email.get(email, []), course)
        if len(candidates) == 1:
            return candidates[0], "correo y sede" if _campus_key(course.get("campus")) else "correo"
        if mismatch:
            return None, "sede no coincide"

    name = _student_name_key(nucleus_student.get("full_name"))
    career = _career_key(course.get("career_name"))
    candidates = by_name.get((career, name), []) if name else []
    candidates, mismatch = _campus_candidates(candidates, course)
    if len(candidates) == 1:
        return candidates[0], "nombre, carrera y sede" if _campus_key(course.get("campus")) else "nombre y carrera"
    if mismatch:
        return None, "sede no coincide"

    return None, "sin coincidencia"


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
    by_email, by_name = _build_roster_indexes(students)

    observations: dict[int, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    match_methods: dict[int, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
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
                        "campus": course.get("campus") or "",
                        "nucleus_number": nucleus_number,
                        "module_code": course.get("module_code") or "",
                        "full_name": clean_moodle_name(str(nucleus_student.get("full_name") or "")),
                        "email": nucleus_student.get("email") or "",
                        "grade": nucleus_student.get("final_grade"),
                        "reason": method,
                    }
                )
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

    for student_id, nuclei in observations.items():
        for nucleus_number, source_rows in nuclei.items():
            sources_by_student[student_id][nucleus_number] = source_rows
            numeric = [float(item["grade"]) for item in source_rows if item.get("grade") is not None]
            distinct = sorted({round(value, 4) for value in numeric})
            if len(distinct) > 1:
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
                grades_by_student[student_id][nucleus_number] = distinct[0]
            else:
                grades_by_student[student_id][nucleus_number] = None

    rows: list[dict[str, Any]] = []
    prerequisite_conflicts: list[dict[str, Any]] = []
    for student in students:
        student_id = int(student["id"])
        thesis = _is_thesis_student(student, project_keys)
        requirements = prerequisite_state(student)
        downstream = downstream_state(student)
        grades = grades_by_student.get(student_id, {})
        student_conflicts = conflicts_by_student.get(student_id, [])
        nuclei_status = _nuclei_status(grades, bool(student_conflicts))
        has_nucleus_grade = any(
            source.get("grade") is not None
            for source_rows in observations.get(student_id, {}).values()
            for source in source_rows
        )
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

        if not thesis and has_nucleus_grade and not eligible_nuclei:
            prerequisite_conflicts.append(
                {
                    "student_id": student_id,
                    "identification": row["identification"],
                    "full_name": row["full_name"],
                    "career_name": row["career_name"],
                    "campus": row["campus"],
                    "missing_requirements": requirements["missing"],
                }
            )

    rows.sort(key=lambda row: (_career_key(row["career_name"]), _campus_key(row["campus"]), _display_name_key(row["full_name"])))
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
    return {
        "rows": rows,
        "complexive_rows": complexive_rows,
        "careers": careers,
        "course_matches": course_matches,
        "unmatched": unmatched,
        "grade_conflicts": grade_conflicts,
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
            "habilitation_percentage": round(habilitated / total_nuclei_students * 100, 2) if total_nuclei_students else 0.0,
            "nucleus_without_prerequisites": len(prerequisite_conflicts),
            "titulation_marked": sum(row["titulation_marked"] for row in non_thesis_rows),
            "complexive_project_approved": sum(row["complexive_project_approved"] for row in rows),
            "titles_uploaded": sum(row["titles_uploaded"] for row in rows),
            "unmatched_nucleus_records": len(unmatched),
        },
    }
