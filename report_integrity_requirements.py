from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import report_integrity_core as integrity
from roster_service import REQUIREMENTS, get_report_roster


SATISFIED_STATES = {"CUMPLE", "NO APLICA"}
NONCOMPLIANT_STATES = {"NO CUMPLE", "REQUIERE CORRECCIÓN"}
INCOMPLETE_STATES = {
    "SIN INFORMACIÓN",
    "NO EVALUADO",
    "EN REVISIÓN",
    "RETIRADO",
    "AUSENTE",
    "PENDIENTE DE CLASIFICAR",
}

# En registros repetidos se conserva el estado que exige mayor atención.
_STATE_PRIORITY = {
    "NO CUMPLE": 100,
    "REQUIERE CORRECCIÓN": 90,
    "PENDIENTE DE CLASIFICAR": 80,
    "EN REVISIÓN": 70,
    "NO EVALUADO": 60,
    "AUSENTE": 50,
    "RETIRADO": 40,
    "SIN INFORMACIÓN": 30,
    "CUMPLE": 20,
    "NO APLICA": 10,
}


def _identity_key(student: dict[str, Any]) -> str:
    identification = integrity.ascii_key(student.get("identification"))
    if identification:
        return "id:" + identification
    email = integrity.norm(student.get("email")).casefold()
    if email:
        return "email:" + email
    career = integrity.ascii_key(student.get("career_name"))
    name = integrity.ascii_key(student.get("full_name"))
    return f"name:{career}|{name}"


def _dedupe(students: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for student in students:
        groups[_identity_key(student)].append(dict(student))

    result: list[dict[str, Any]] = []
    requirement_keys = [key for key, _ in REQUIREMENTS]
    for items in groups.values():
        selected = max(
            items,
            key=lambda item: sum(bool(integrity.norm(value)) for value in item.values()),
        )
        merged = dict(selected)
        for key in requirement_keys:
            candidates = [integrity.canonical_state(item.get(key)) for item in items if integrity.norm(item.get(key))]
            if not candidates:
                merged[key] = ""
                continue
            merged[key] = max(candidates, key=lambda state: _STATE_PRIORITY.get(state, 80))
        result.append(merged)
    return result


def _raw(student: dict[str, Any], key: str) -> str:
    return integrity.norm(student.get(key))


def _state(student: dict[str, Any], key: str) -> str:
    return integrity.canonical_state(_raw(student, key))


def corrected_requirement_analysis(report_id: int) -> dict[str, Any] | None:
    students = _dedupe(list(get_report_roster(report_id).get("students", [])))
    if not students:
        return None

    active = [
        (key, label)
        for key, label in REQUIREMENTS
        if any(_raw(student, key) for student in students)
    ]
    if not active:
        return None

    def classify(student: dict[str, Any]) -> str:
        states = [_state(student, key) for key, _ in active]
        if any(state in NONCOMPLIANT_STATES for state in states):
            return "pending"
        if all(state in SATISFIED_STATES for state in states):
            return "complete"
        return "incomplete"

    total = len(students)
    states = [classify(student) for student in students]
    complete = states.count("complete")
    pending = states.count("pending")
    incomplete = states.count("incomplete")

    requirement_rows: list[dict[str, Any]] = []
    for key, label in active:
        values = [_state(student, key) for student in students]
        counts = Counter(values)
        applicable = total - counts["NO APLICA"]
        complies = counts["CUMPLE"]
        percentage = round(complies / applicable * 100, 2) if applicable else 100.0
        requirement_rows.append(
            {
                "key": key,
                "label": label,
                "complies": complies,
                "does_not_comply": counts["NO CUMPLE"],
                "blank": counts["SIN INFORMACIÓN"],
                "percentage": percentage,
                "denominator": applicable,
                "denominator_type": "APLICABLES",
                "not_applicable": counts["NO APLICA"],
                "not_evaluated": counts["NO EVALUADO"],
                "in_review": counts["EN REVISIÓN"],
                "requires_correction": counts["REQUIERE CORRECCIÓN"],
                "withdrawn": counts["RETIRADO"],
                "absent": counts["AUSENTE"],
                "pending_classification": counts["PENDIENTE DE CLASIFICAR"],
            }
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for student in students:
        grouped[str(student.get("career_name") or "Sin carrera")].append(student)
    career_rows: list[dict[str, Any]] = []
    for career_name, career_students in sorted(grouped.items()):
        career_states = [classify(student) for student in career_students]
        registered = len(career_students)
        career_complete = career_states.count("complete")
        career_rows.append(
            {
                "career": career_name,
                "registered": registered,
                "complete": career_complete,
                "pending": career_states.count("pending"),
                "incomplete": career_states.count("incomplete"),
                "percentage": round(career_complete / registered * 100, 2) if registered else 0.0,
            }
        )

    lowest = min(float(row["percentage"]) for row in requirement_rows)
    lowest_rows = [row for row in requirement_rows if float(row["percentage"]) == lowest]
    labels = [str(row["label"]) for row in lowest_rows]
    if len(labels) == 1:
        requirement_text = labels[0]
    elif len(labels) == 2:
        requirement_text = f"{labels[0]} y {labels[1]}"
    else:
        requirement_text = ", ".join(labels[:-1]) + f" y {labels[-1]}"

    narrative = (
        f"De los {total} estudiantes únicos registrados, {complete} cumplieron integralmente los requisitos, "
        f"{pending} presentan incumplimientos o requieren corrección y {incomplete} mantienen estados todavía no cerrados. "
        f"El menor nivel de cumplimiento entre registros aplicables corresponde a {requirement_text}, con {str(f'{lowest:.2f}').replace('.', ',')} %."
    )
    return {
        "total": total,
        "complete": complete,
        "pending": pending,
        "incomplete": incomplete,
        "percentage": round(complete / total * 100, 2) if total else 0.0,
        "requirements": requirement_rows,
        "careers": career_rows,
        "narrative": narrative,
        "state_catalog": sorted(integrity.VALID_STATES),
    }
