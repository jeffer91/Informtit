from __future__ import annotations

from statistics import mean
from typing import Any, Iterable

PASSING_GRADE = 70.0
THEORY_WEIGHT = 0.40
PRACTICAL_WEIGHT = 0.60


def weighted(theory: float | None, practical: float | None) -> float | None:
    if theory is None or practical is None:
        return None
    return round(theory * THEORY_WEIGHT + practical * PRACTICAL_WEIGHT, 2)


def ordinary_final(student: dict[str, Any]) -> float | None:
    return weighted(student.get("ordinary_theory"), student.get("ordinary_practical"))


def final_after_supplementary(student: dict[str, Any]) -> float | None:
    theory = student.get("supplementary_theory")
    if theory is None:
        theory = student.get("ordinary_theory")
    practical = student.get("supplementary_practical")
    if practical is None:
        practical = student.get("ordinary_practical")
    return weighted(theory, practical)


def participated_in_supplementary(student: dict[str, Any]) -> bool:
    return student.get("supplementary_theory") is not None or student.get("supplementary_practical") is not None


def final_grade(student: dict[str, Any]) -> float | None:
    if participated_in_supplementary(student):
        return final_after_supplementary(student)
    return ordinary_final(student)


def status_for(grade: float | None) -> str:
    if grade is None:
        return "No evaluado"
    return "Aprobado" if grade >= PASSING_GRADE else "Reprobado"


def average(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return round(mean(clean), 2) if clean else None


def pct(value: int, total: int) -> float:
    return round((value / total * 100), 2) if total else 0.0


def enrich_student(student: dict[str, Any]) -> dict[str, Any]:
    result = dict(student)
    result["ordinary_final"] = ordinary_final(student)
    result["supplementary_final"] = final_after_supplementary(student) if participated_in_supplementary(student) else None
    result["final_grade"] = final_grade(student)
    result["ordinary_status"] = status_for(result["ordinary_final"])
    result["final_status"] = status_for(result["final_grade"])
    result["supplementary_participant"] = participated_in_supplementary(student)
    if student.get("supplementary_theory") is not None and student.get("supplementary_practical") is not None:
        result["supplementary_component"] = "Teórico y práctico"
    elif student.get("supplementary_theory") is not None:
        result["supplementary_component"] = "Teórico"
    elif student.get("supplementary_practical") is not None:
        result["supplementary_component"] = "Práctico"
    else:
        result["supplementary_component"] = "No rindió"
    source_total = student.get("source_total_course")
    calculated = result["final_grade"]
    result["source_difference"] = (
        round(calculated - source_total, 2)
        if source_total is not None and calculated is not None
        else None
    )
    return result


def summary(students: list[dict[str, Any]], phase: str = "consolidado") -> dict[str, Any]:
    enriched = [enrich_student(student) for student in students]
    total = len(enriched)

    if phase == "ordinario":
        grades = [student["ordinary_final"] for student in enriched]
        approved = [student for student in enriched if student["ordinary_final"] is not None and student["ordinary_final"] >= PASSING_GRADE]
        failed = [student for student in enriched if student["ordinary_final"] is not None and student["ordinary_final"] < PASSING_GRADE]
        not_evaluated = [student for student in enriched if student["ordinary_final"] is None]
        rows = enriched
    elif phase == "supletorio":
        rows = [student for student in enriched if student["supplementary_participant"]]
        grades = [student["supplementary_final"] for student in rows]
        approved = [student for student in rows if student["supplementary_final"] is not None and student["supplementary_final"] >= PASSING_GRADE]
        failed = [student for student in rows if student["supplementary_final"] is not None and student["supplementary_final"] < PASSING_GRADE]
        not_evaluated = [student for student in rows if student["supplementary_final"] is None]
        total = len(rows)
    else:
        grades = [student["final_grade"] for student in enriched]
        approved = [student for student in enriched if student["final_grade"] is not None and student["final_grade"] >= PASSING_GRADE]
        failed = [student for student in enriched if student["final_grade"] is not None and student["final_grade"] < PASSING_GRADE]
        not_evaluated = [student for student in enriched if student["final_grade"] is None]
        rows = enriched

    supplementary_count = sum(1 for student in enriched if student["supplementary_participant"])
    return {
        "phase": phase,
        "total": total,
        "approved": len(approved),
        "failed": len(failed),
        "not_evaluated": len(not_evaluated),
        "approved_pct": pct(len(approved), total),
        "failed_pct": pct(len(failed), total),
        "supplementary_count": supplementary_count,
        "average_theory_ordinary": average(student.get("ordinary_theory") for student in enriched),
        "average_practical_ordinary": average(student.get("ordinary_practical") for student in enriched),
        "average_final": average(grades),
        "highest": max((grade for grade in grades if grade is not None), default=None),
        "lowest": min((grade for grade in grades if grade is not None), default=None),
        "rows": rows,
    }
