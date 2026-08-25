from __future__ import annotations

from collections import defaultdict
from typing import Any

import analytics
from db import connection, rows_to_dicts
from student_domain_service import MATCH_OK, get_period_students


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()} if _table_exists(conn, table) else set()


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _complexive_records(report_id: int) -> dict[int, list[dict[str, Any]]]:
    with connection() as conn:
        if "period_student_id" not in _columns(conn, "students"):
            return {}
        rows = rows_to_dicts(conn.execute(
            """
            SELECT s.*, c.name AS source_career
            FROM students s JOIN careers c ON c.id=s.career_id
            WHERE c.report_id=? AND s.period_student_id IS NOT NULL
            ORDER BY s.id
            """,
            (report_id,),
        ).fetchall())
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["period_student_id"]), []).append(row)
    return grouped


def _thesis_records(report_id: int) -> dict[int, list[dict[str, Any]]]:
    with connection() as conn:
        if "period_student_id" not in _columns(conn, "thesis_projects"):
            return {}
        rows = rows_to_dicts(conn.execute(
            "SELECT * FROM thesis_projects WHERE report_id=? AND period_student_id IS NOT NULL ORDER BY id",
            (report_id,),
        ).fetchall())
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["period_student_id"]), []).append(row)
    return grouped


def _nuclei_records(report_id: int) -> dict[int, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    with connection() as conn:
        if "period_student_id" in _columns(conn, "nucleus_instance_students") and _table_exists(conn, "nucleus_course_instances"):
            rows = rows_to_dicts(conn.execute(
                """
                SELECT ns.*, nc.nucleus_number, nc.career_name AS source_career,
                       nc.id AS course_id, nc.campus, nc.group_code, nc.module_code
                FROM nucleus_instance_students ns
                JOIN nucleus_course_instances nc ON nc.id=ns.course_id
                WHERE nc.report_id=? AND ns.period_student_id IS NOT NULL
                ORDER BY nc.nucleus_number, ns.id
                """,
                (report_id,),
            ).fetchall())
        elif "period_student_id" in _columns(conn, "nucleus_students") and _table_exists(conn, "nucleus_courses"):
            rows = rows_to_dicts(conn.execute(
                """
                SELECT ns.*, nc.nucleus_number, nc.career_name AS source_career, nc.id AS course_id
                FROM nucleus_students ns JOIN nucleus_courses nc ON nc.id=ns.course_id
                WHERE nc.report_id=? AND ns.period_student_id IS NOT NULL
                ORDER BY nc.nucleus_number, ns.id
                """,
                (report_id,),
            ).fetchall())
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["period_student_id"]), []).append(row)
    return grouped


def _nucleus_grade_conflicts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, set[float]] = defaultdict(set)
    for record in records:
        number = int(record.get("nucleus_number") or 0)
        grade = _number(record.get("final_grade"))
        if number and grade is not None:
            grouped[number].add(round(grade, 4))
    return [
        {"nucleus_number": number, "grades": sorted(grades)}
        for number, grades in sorted(grouped.items())
        if len(grades) > 1
    ]


def _has_complexive_grade(records: list[dict[str, Any]]) -> bool:
    return any(analytics.final_grade(record) is not None for record in records)


def _complexive_approved(records: list[dict[str, Any]]) -> bool:
    return any(analytics.enrich_student(record).get("final_status") == "Aprobado" for record in records)


def _has_thesis_grade(records: list[dict[str, Any]]) -> bool:
    return any(_number(record.get("final_grade")) is not None for record in records)


def _thesis_approved(records: list[dict[str, Any]]) -> bool:
    for record in records:
        status = str(record.get("final_status") or "").strip().upper()
        grade = _number(record.get("final_grade"))
        if status == "APROBADO" or (grade is not None and grade >= 7):
            return True
    return False


def _academic_consistency(row: dict[str, Any]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    nucleus_conflicts = _nucleus_grade_conflicts(row.get("nuclei_records", []))
    row["nucleus_grade_conflicts"] = nucleus_conflicts
    if nucleus_conflicts:
        detail = "; ".join(
            f"Núcleo {item['nucleus_number']}: {', '.join(str(value) for value in item['grades'])}"
            for item in nucleus_conflicts
        )
        issues.append(("GRADE_CONFLICT", f"Se encontraron notas distintas para el mismo núcleo. {detail}."))

    route = str(row.get("route") or "COMPLEXIVO")
    official_graduated = bool(row.get("official_graduated"))
    titulation_completed = bool(row.get("official_titulation_completed"))
    if route == "COMPLEXIVO":
        has_grade = _has_complexive_grade(row.get("complexive_records", []))
        approved = _complexive_approved(row.get("complexive_records", []))
        if official_graduated and not has_grade:
            issues.append(("REVIEW_REQUIRED", "Requisitos confirma que el estudiante se graduó, pero no se encontró su nota final de Examen Complexivo."))
        elif not official_graduated and approved:
            issues.append(("OFFICIAL_DATA_CONFLICT", "Existe una nota aprobatoria de Examen Complexivo, pero Requisitos todavía no confirma la graduación oficial."))
        if titulation_completed and not row.get("has_nuclei"):
            issues.append(("REVIEW_REQUIRED", "Titulación consta CUMPLE en Requisitos, pero no se encontró evidencia de Núcleos para completar la trazabilidad."))
    else:
        has_grade = _has_thesis_grade(row.get("thesis_records", []))
        approved = _thesis_approved(row.get("thesis_records", []))
        if official_graduated and not has_grade:
            issues.append(("REVIEW_REQUIRED", "Requisitos confirma que el estudiante se graduó, pero no se encontró su nota final de Trabajo de Titulación."))
        elif not official_graduated and approved:
            issues.append(("OFFICIAL_DATA_CONFLICT", "Existe una nota aprobatoria de Trabajo de Titulación, pero Requisitos todavía no confirma la graduación oficial."))
        if titulation_completed and not row.get("has_thesis"):
            issues.append(("REVIEW_REQUIRED", "Titulación consta CUMPLE en Requisitos, pero no se encontró el Trabajo de Titulación para completar la trazabilidad."))
    return issues


def _effective_reconciliation(row: dict[str, Any]) -> tuple[str, str]:
    current = str(row.get("reconciliation_status") or MATCH_OK)
    detail = str(row.get("reconciliation_detail") or "")
    candidates: list[tuple[int, str, str]] = []
    priority = {
        "ROUTE_CONFLICT": 100,
        "GRADE_CONFLICT": 90,
        "OFFICIAL_DATA_CONFLICT": 85,
        "AMBIGUOUS": 80,
        "REVIEW_REQUIRED": 70,
        "UNMATCHED": 60,
    }
    if current != MATCH_OK:
        candidates.append((priority.get(current, 75), current, detail))
    for link in row.get("source_links", []):
        status = str(link.get("match_status") or MATCH_OK)
        if status == MATCH_OK:
            continue
        link_detail = str(link.get("detail") or "") or f"Revise la conciliación del módulo {link.get('source_module') or 'académico'}."
        candidates.append((priority.get(status, 50), status, link_detail))
    for status, academic_detail in _academic_consistency(row):
        candidates.append((priority.get(status, 50), status, academic_detail))
    if not candidates:
        return MATCH_OK, detail
    _, selected_status, selected_detail = max(candidates, key=lambda item: item[0])
    return selected_status, selected_detail


def consolidated_students(report_id: int) -> dict[str, Any]:
    students = get_period_students(report_id)
    complexive = _complexive_records(report_id)
    thesis = _thesis_records(report_id)
    nuclei = _nuclei_records(report_id)
    rows: list[dict[str, Any]] = []
    for student in students.get("students", []):
        sid = int(student["id"])
        row = dict(student)
        row["nuclei_records"] = nuclei.get(sid, [])
        row["complexive_records"] = complexive.get(sid, [])
        row["thesis_records"] = thesis.get(sid, [])
        row["has_nuclei"] = bool(row["nuclei_records"])
        row["has_complexive"] = bool(row["complexive_records"])
        row["has_thesis"] = bool(row["thesis_records"])
        effective_status, effective_detail = _effective_reconciliation(row)
        row["reconciliation_status"] = effective_status
        row["reconciliation_detail"] = effective_detail
        rows.append(row)

    summary = dict(students.get("summary", {}))
    summary["review"] = sum(row.get("reconciliation_status") != MATCH_OK for row in rows)
    summary["with_nuclei"] = sum(bool(row.get("has_nuclei")) for row in rows)
    summary["with_complexive"] = sum(bool(row.get("has_complexive")) for row in rows)
    summary["with_thesis_data"] = sum(bool(row.get("has_thesis")) for row in rows)
    summary["grade_conflicts"] = sum(bool(row.get("nucleus_grade_conflicts")) for row in rows)
    return {"ok": True, "summary": summary, "students": rows}
