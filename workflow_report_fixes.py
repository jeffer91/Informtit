from __future__ import annotations

from collections import defaultdict
from typing import Any

import eligibility_service
import report_completion
import report_structure
import workflow_report_runtime
from parser import canonical_name_key, clean_moodle_name
from roster_service import get_report_roster as _raw_get_report_roster
from workflow_rules import (
    POST_NUCLEUS_FIELDS,
    PRE_NUCLEUS_REQUIREMENTS,
    downstream_state,
    prerequisite_state,
    status,
)


def _identity_key(student: dict[str, Any]) -> str:
    identification = str(student.get("identification") or "").strip()
    if identification:
        return f"id:{identification}"
    email = str(student.get("email") or "").strip().casefold()
    if email:
        return f"email:{email}"
    career = canonical_name_key(str(student.get("career_name") or ""))
    name = canonical_name_key(clean_moodle_name(str(student.get("full_name") or "")))
    return f"name:{career}|{name}"


def _status_merge(values: list[Any], *, downstream: bool = False) -> str:
    normalized = [status(value) for value in values if status(value)]
    if not normalized:
        return ""
    if downstream:
        if "CUMPLE" in normalized:
            return "CUMPLE"
        if "NO CUMPLE" in normalized:
            return "NO CUMPLE"
    else:
        if "NO CUMPLE" in normalized:
            return "NO CUMPLE"
        if "CUMPLE" in normalized:
            return "CUMPLE"
    return normalized[0]


def dedupe_workflow_students(students: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Consolida duplicados sin mezclar la semántica de etapas del proceso."""

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for student in students:
        groups[_identity_key(student)].append(dict(student))

    pre_keys = {key for key, _label in PRE_NUCLEUS_REQUIREMENTS}
    post_keys = {key for key, _label in POST_NUCLEUS_FIELDS}
    merged_rows: list[dict[str, Any]] = []
    for items in groups.values():
        representative = max(
            items,
            key=lambda item: sum(
                bool(str(value or "").strip()) for value in item.values()
            ),
        )
        merged = dict(representative)

        for key in pre_keys:
            merged[key] = _status_merge([item.get(key) for item in items])
        for key in post_keys:
            merged[key] = _status_merge(
                [item.get(key) for item in items], downstream=True
            )

        for item in items:
            for key, value in item.items():
                if (merged.get(key) is None or str(merged.get(key) or "").strip() == "") and value not in (None, ""):
                    merged[key] = value
        merged_rows.append(merged)

    return merged_rows


def get_workflow_roster(report_id: int) -> dict[str, Any]:
    data = _raw_get_report_roster(report_id)
    result = dict(data)
    result["students"] = dedupe_workflow_students(
        [dict(student) for student in data.get("students", [])]
    )
    summary = dict(data.get("summary", {}))
    summary["students"] = len(result["students"])
    result["summary"] = summary
    return result


def prerequisite_requirement_analysis(report_id: int) -> dict[str, Any] | None:
    students = get_workflow_roster(report_id).get("students", [])
    if not students:
        return None

    classifications: list[str] = []
    for student in students:
        state = prerequisite_state(student)
        if state["complete"]:
            classifications.append("complete")
        elif state["pending"]:
            classifications.append("pending")
        else:
            classifications.append("incomplete")

    total = len(students)
    complete = classifications.count("complete")
    pending = classifications.count("pending")
    incomplete = classifications.count("incomplete")

    requirement_rows: list[dict[str, Any]] = []
    for key, label in PRE_NUCLEUS_REQUIREMENTS:
        values = [status(student.get(key)) for student in students]
        complies = values.count("CUMPLE")
        does_not_comply = values.count("NO CUMPLE")
        requirement_rows.append(
            {
                "key": key,
                "label": label,
                "complies": complies,
                "does_not_comply": does_not_comply,
                "blank": total - complies - does_not_comply,
                "percentage": round(complies / total * 100, 2),
            }
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for student in students:
        grouped[str(student.get("career_name") or "Sin carrera")].append(student)

    career_rows: list[dict[str, Any]] = []
    for career_name, career_students in sorted(grouped.items()):
        states = [prerequisite_state(student) for student in career_students]
        registered = len(career_students)
        career_complete = sum(item["complete"] for item in states)
        career_pending = sum(bool(item["pending"]) for item in states)
        career_incomplete = registered - career_complete - career_pending
        career_rows.append(
            {
                "career": career_name,
                "registered": registered,
                "complete": career_complete,
                "pending": career_pending,
                "incomplete": career_incomplete,
                "percentage": round(career_complete / registered * 100, 2)
                if registered
                else 0.0,
            }
        )

    lowest_percentage = min(row["percentage"] for row in requirement_rows)
    lowest_requirements = [
        row for row in requirement_rows if row["percentage"] == lowest_percentage
    ]
    highest_issue_count = max(
        row["pending"] + row["incomplete"] for row in career_rows
    )
    highest_issue_careers = [
        row
        for row in career_rows
        if row["pending"] + row["incomplete"] == highest_issue_count
    ]
    requirement_names = ", ".join(row["label"] for row in lowest_requirements)
    career_names = " y ".join(row["career"] for row in highest_issue_careers)
    percentage = round(complete / total * 100, 2)
    narrative = (
        f"De los {total} estudiantes únicos registrados, {complete} cumplieron integralmente "
        f"los ocho requisitos previos para ingresar a Núcleos, equivalente al "
        f"{report_completion.report_quality._pct(percentage)}. Se identificaron {pending} "
        f"estudiantes con al menos un requisito marcado como NO CUMPLE y {incomplete} con "
        f"información incompleta. El menor nivel de cumplimiento se registró en "
        f"{requirement_names}, con {report_completion.report_quality._pct(lowest_percentage)}. "
        f"La mayor cantidad de casos pendientes o incompletos se presentó en {career_names}, "
        f"con {highest_issue_count} casos por carrera."
    )

    return {
        "total": total,
        "complete": complete,
        "pending": pending,
        "incomplete": incomplete,
        "percentage": percentage,
        "requirements": requirement_rows,
        "careers": career_rows,
        "narrative": narrative,
    }


def process_funnel(report_id: int) -> dict[str, Any]:
    requirements = prerequisite_requirement_analysis(report_id)
    eligibility = eligibility_service.get_eligibility(report_id)
    summary = eligibility["summary"]
    return {
        "registered": requirements["total"] if requirements else 0,
        "eligible_for_nuclei": summary["eligible_for_nuclei"],
        "blocked_before_nuclei": summary["blocked_before_nuclei"],
        "eligible_for_complexive": summary["eligible_for_complexive"],
        "titulation_marked": summary["titulation_marked"],
        "complexive_project_approved": summary["complexive_project_approved"],
        "titles_uploaded": summary["titles_uploaded"],
    }


def install() -> None:
    if getattr(report_completion, "_workflow_report_fixes_installed", False):
        return

    # Eligibility trabaja con la misma población única que utiliza el informe.
    eligibility_service.get_report_roster = get_workflow_roster

    # El análisis de requisitos debe contener exclusivamente los ocho campos
    # que habilitan el ingreso a Núcleos. Los tres campos posteriores quedan
    # fuera de esta sección y se presentan únicamente en la trazabilidad.
    report_completion.corrected_requirement_analysis = prerequisite_requirement_analysis
    report_structure.requirement_analysis = prerequisite_requirement_analysis
    workflow_report_runtime.process_funnel = process_funnel

    report_completion._workflow_report_fixes_installed = True
