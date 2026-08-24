from __future__ import annotations

from typing import Any

import completion_service
import report_integrity_core as integrity
from optional_content import is_present


def safe_course_signature(course: dict[str, Any]) -> tuple[Any, ...]:
    students = tuple(sorted(
        (
            integrity.ascii_key(student.get("full_name")),
            integrity.ascii_key(student.get("email")),
            "" if integrity.number(student.get("final_grade")) is None else f"{float(student['final_grade']):.6f}",
            integrity.ascii_key(student.get("final_status")),
        )
        for student in course.get("students", [])
    ))
    return (
        integrity.ascii_key(course.get("career_name")),
        int(course.get("nucleus_number") or 0),
        integrity.ascii_key(course.get("course_title")),
        integrity.ascii_key(course.get("teacher_name")),
        integrity.ascii_key(course.get("campus")),
        integrity.ascii_key(course.get("group_code")),
        students,
    )


def schedule_summary(report_id: int) -> dict[str, Any]:
    data = completion_service.get_schedules_extended(report_id)
    rows: list[dict[str, Any]] = []
    if is_present(report_id, "schedule_complexive"):
        rows.extend(data.get("complexive", []))
    if is_present(report_id, "schedule_thesis"):
        rows.extend(data.get("thesis", []))

    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    duplicates = 0
    for row in rows:
        try:
            key = integrity.schedule_key(row)
        except ValueError:
            unique.append(row)
            continue
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(row)

    evaluated = [
        row for row in unique
        if row.get("execution_status")
        or row.get("compliance_percentage") is not None
        or row.get("executed_date")
    ]
    incomplete = [
        row for row in evaluated
        if not row.get("executed_date")
        or not row.get("execution_status")
        or not row.get("evidence")
    ]
    return {
        "rows": unique,
        "total": len(unique),
        "evaluated": len(evaluated),
        "pending_evaluation": len(unique) - len(evaluated),
        "duplicates": duplicates,
        "incomplete_evidence": len(incomplete),
    }
