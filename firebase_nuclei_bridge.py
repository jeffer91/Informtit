from __future__ import annotations

import hashlib
import json
from statistics import mean
from typing import Any, Callable

import firebase_sync_runtime as firebase_sync
import nuclei_multicampus
from coordinator_registry import find_coordinator, normalize
from db import connection, rows_to_dicts, utcnow
from import_service import clean_cell


_INSTALLED = False
_BASE_REPORT_HAS_LOCAL_DATA: Callable[[int, str], bool] | None = None


def _document_id(period_id: str, group: str, course: dict[str, Any]) -> str:
    career_key = firebase_sync._slug(course.get("career_name"))
    nucleus = int(course.get("nucleus_number") or 1)
    identity = clean_cell(course.get("course_key")) or "|".join(
        (
            clean_cell(course.get("career_name")),
            str(nucleus),
            clean_cell(course.get("course_title")),
            clean_cell(course.get("teacher_name")),
            clean_cell(course.get("campus")),
            clean_cell(course.get("group_code")),
        )
    )
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12].upper()
    return f"{period_id}__{clean_cell(group).upper()}__{career_key}__N{nucleus}__{digest}"


def _requirement_indexes(report_id: int) -> tuple[dict[str, str], dict[str, str]]:
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT identification, email, career_name, career_code
                FROM requirements_students WHERE report_id=?
                """,
                (report_id,),
            ).fetchall()
        )
    cedula_by_email = {
        clean_cell(row.get("email")).lower(): clean_cell(row.get("identification"))
        for row in rows
        if clean_cell(row.get("email")) and clean_cell(row.get("identification"))
    }
    code_by_career: dict[str, str] = {}
    for row in rows:
        key = normalize(row.get("career_name"))
        code = clean_cell(row.get("career_code"))
        if key and code and key not in code_by_career:
            code_by_career[key] = code
    return cedula_by_email, code_by_career


def local_nuclei(
    report_id: int,
    period_id: str,
    group: str,
) -> list[tuple[str, dict[str, Any]]]:
    """Serializa únicamente el modelo canónico multicampus de Núcleos."""
    courses = list(nuclei_multicampus.get_nuclei(report_id).get("courses", []))
    cedula_by_email, code_by_career = _requirement_indexes(report_id)
    output: list[tuple[str, dict[str, Any]]] = []

    for course in courses:
        results: list[dict[str, Any]] = []
        for student in course.get("students", []):
            email = clean_cell(student.get("email")).lower()
            results.append(
                {
                    "cedula": cedula_by_email.get(email, ""),
                    "correo": email,
                    "nombre": clean_cell(student.get("full_name")),
                    "notaFinal": student.get("final_grade"),
                    "estado": clean_cell(student.get("final_status")),
                }
            )

        activities = [
            {
                "nombre": clean_cell(item.get("name")),
                "promedio": item.get("average"),
            }
            for item in course.get("assessments", [])
        ]
        career_name = clean_cell(course.get("career_name"))
        doc_id = _document_id(period_id, group, course)
        output.append(
            (
                doc_id,
                {
                    "periodoId": period_id,
                    "carreraId": code_by_career.get(normalize(career_name), ""),
                    "carrera": career_name,
                    "nucleo": int(course.get("nucleus_number") or 1),
                    "curso": clean_cell(course.get("course_title")),
                    "docente": clean_cell(course.get("teacher_name")),
                    "grupoInforme": group,
                    "sede": clean_cell(course.get("campus")),
                    "modulo": clean_cell(course.get("module_code")),
                    "periodoCurso": clean_cell(course.get("period_label")),
                    "paralelo": clean_cell(course.get("group_code")),
                    "jornada": clean_cell(course.get("schedule")),
                    "courseKey": clean_cell(course.get("course_key")),
                    "resultados": results,
                    "actividades": activities,
                    "version": 2,
                    "updatedAt": utcnow(),
                },
            )
        )
    return output


def report_has_local_data(report_id: int, module: str) -> bool:
    if module != "nucleos":
        if _BASE_REPORT_HAS_LOCAL_DATA is None:
            return False
        return bool(_BASE_REPORT_HAS_LOCAL_DATA(report_id, module))

    nuclei_multicampus.ensure_multicampus_schema()
    with connection() as conn:
        return bool(
            conn.execute(
                "SELECT 1 FROM nucleus_course_instances WHERE report_id=? LIMIT 1",
                (report_id,),
            ).fetchone()
        )


def _remote_course_key(item: dict[str, Any]) -> str:
    explicit = clean_cell(item.get("courseKey"))
    if explicit:
        return explicit
    return "firebase|" + "|".join(
        (
            normalize(item.get("carrera")),
            str(int(item.get("nucleo") or 1)),
            normalize(item.get("curso")),
            normalize(item.get("docente")),
            normalize(item.get("sede")),
            normalize(item.get("paralelo")),
            normalize(item.get("jornada")),
        )
    )


def _dedupe_remote(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for item in rows:
        key = _remote_course_key(item)
        previous = selected.get(key)
        if previous is None:
            selected[key] = item
            continue
        previous_version = int(previous.get("version") or 0)
        current_version = int(item.get("version") or 0)
        if current_version >= previous_version:
            selected[key] = item
    return list(selected.values())


def restore_nuclei(
    report_id: int,
    rows: list[dict[str, Any]],
    students: dict[str, dict[str, Any]],
) -> int:
    """Restaura Firebase directamente en nucleus_course_instances."""
    nuclei_multicampus.ensure_multicampus_schema()
    restored = 0
    now = utcnow()

    with connection() as conn:
        for item in _dedupe_remote(rows):
            career = clean_cell(item.get("carrera")) or "Sin carrera"
            nucleus = int(item.get("nucleo") or 1)
            course_key = _remote_course_key(item)
            results = item.get("resultados") if isinstance(item.get("resultados"), list) else []
            activities = item.get("actividades") if isinstance(item.get("actividades"), list) else []

            numeric_grades = [
                float(result["notaFinal"])
                for result in results
                if result.get("notaFinal") is not None
            ]
            approved = sum(
                clean_cell(result.get("estado")).upper() in {"APROBADO", "APROBADA", "APR"}
                for result in results
            )
            failed = sum(
                clean_cell(result.get("estado")).upper()
                in {"REPROBADO", "REPROBADA", "REP", "SUSPENSO"}
                for result in results
            )
            unevaluated = max(len(results) - approved - failed, 0)
            coordinator = find_coordinator(career)
            activity_averages = [
                {
                    "name": clean_cell(activity.get("nombre")),
                    "calculated_average": activity.get("promedio"),
                }
                for activity in activities
            ]

            existing = conn.execute(
                "SELECT id FROM nucleus_course_instances WHERE report_id=? AND course_key=?",
                (report_id, course_key),
            ).fetchone()
            if existing:
                course_id = int(existing["id"])
                conn.execute(
                    "DELETE FROM nucleus_instance_assessments WHERE course_id=?",
                    (course_id,),
                )
                conn.execute(
                    "DELETE FROM nucleus_instance_students WHERE course_id=?",
                    (course_id,),
                )
                conn.execute(
                    """
                    UPDATE nucleus_course_instances SET
                        career_name=?, nucleus_number=?, campus=?, module_code=?,
                        period_label=?, group_code=?, schedule=?, course_title=?,
                        teacher_name=?, teacher_candidates='[]', coordinator_name=?,
                        coordinator_program=?, coordinator_telegram=?, participant_students=?,
                        graded_students=?, matched_students=?, missing_grades=?, extra_grades=0,
                        course_average=?, approved_count=?, failed_count=?, unevaluated_count=?,
                        activity_averages=?, raw_grades='', raw_participants='', updated_at=?
                    WHERE id=?
                    """,
                    (
                        career,
                        nucleus,
                        clean_cell(item.get("sede")),
                        clean_cell(item.get("modulo")),
                        clean_cell(item.get("periodoCurso")),
                        clean_cell(item.get("paralelo")),
                        clean_cell(item.get("jornada")),
                        clean_cell(item.get("curso")),
                        clean_cell(item.get("docente")),
                        coordinator.get("coordinator", ""),
                        coordinator.get("program", ""),
                        coordinator.get("telegram", ""),
                        len(results),
                        len(numeric_grades),
                        len(results),
                        unevaluated,
                        round(mean(numeric_grades), 2) if numeric_grades else None,
                        approved,
                        failed,
                        unevaluated,
                        json.dumps(activity_averages, ensure_ascii=False),
                        now,
                        course_id,
                    ),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO nucleus_course_instances
                    (report_id, career_name, nucleus_number, campus, module_code, period_label,
                     group_code, schedule, course_key, course_title, teacher_name, teacher_candidates,
                     coordinator_name, coordinator_program, coordinator_telegram, participant_students,
                     graded_students, matched_students, missing_grades, extra_grades, course_average,
                     approved_count, failed_count, unevaluated_count, activity_averages, raw_grades,
                     raw_participants, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, '', '', ?, ?)
                    """,
                    (
                        report_id,
                        career,
                        nucleus,
                        clean_cell(item.get("sede")),
                        clean_cell(item.get("modulo")),
                        clean_cell(item.get("periodoCurso")),
                        clean_cell(item.get("paralelo")),
                        clean_cell(item.get("jornada")),
                        course_key,
                        clean_cell(item.get("curso")),
                        clean_cell(item.get("docente")),
                        coordinator.get("coordinator", ""),
                        coordinator.get("program", ""),
                        coordinator.get("telegram", ""),
                        len(results),
                        len(numeric_grades),
                        len(results),
                        unevaluated,
                        round(mean(numeric_grades), 2) if numeric_grades else None,
                        approved,
                        failed,
                        unevaluated,
                        json.dumps(activity_averages, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                course_id = int(cursor.lastrowid)

            for order, activity in enumerate(activities, start=1):
                conn.execute(
                    """
                    INSERT INTO nucleus_instance_assessments
                    (course_id, name, sort_order, average)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        course_id,
                        clean_cell(activity.get("nombre")) or f"Actividad {order}",
                        order,
                        activity.get("promedio"),
                    ),
                )

            for index, result in enumerate(results, start=1):
                cedula = clean_cell(result.get("cedula"))
                profile = students.get(cedula, {})
                email = clean_cell(result.get("correo")).lower()
                if not email:
                    email = f"firebase-{cedula or course_id}-{index}@local.invalid"
                full_name = (
                    clean_cell(result.get("nombre"))
                    or clean_cell(profile.get("nombres"))
                    or cedula
                    or f"Estudiante {index}"
                )
                conn.execute(
                    """
                    INSERT INTO nucleus_instance_students
                    (course_id, full_name, email, final_grade, final_status, participant_found)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (
                        course_id,
                        full_name,
                        email,
                        result.get("notaFinal"),
                        clean_cell(result.get("estado")) or "No evaluado",
                    ),
                )
            restored += 1

    return restored


def install() -> None:
    global _INSTALLED, _BASE_REPORT_HAS_LOCAL_DATA
    if _INSTALLED:
        return

    _BASE_REPORT_HAS_LOCAL_DATA = firebase_sync._report_has_local_data
    firebase_sync._local_nuclei = local_nuclei
    firebase_sync._report_has_local_data = report_has_local_data
    firebase_sync._restore_nuclei = restore_nuclei
    firebase_sync._modern_nuclei_bridge_installed = True
    _INSTALLED = True
