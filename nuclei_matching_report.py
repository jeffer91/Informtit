from __future__ import annotations

from collections import defaultdict

import nuclei_multicampus_report as report
from eligibility_service import get_eligibility
from parser import canonical_name_key, clean_moodle_name


def _email(value: object) -> str:
    return str(value or "").strip().casefold()


def _name(value: object) -> str:
    return canonical_name_key(clean_moodle_name(str(value or "")))


def _eligible_members_by_course(report_id: int) -> dict[int, dict[str, set[str]]]:
    """Usa la identidad original de Moodle que fue vinculada al estudiante.

    Esto es importante cuando una coincidencia se resolvió manualmente: el correo
    o el nombre de Moodle puede ser distinto del registro de la base, pero la
    nota ya quedó asociada explícitamente al estudiante correcto.
    """

    eligibility = get_eligibility(report_id)
    members: dict[int, dict[str, set[str]]] = defaultdict(
        lambda: {"emails": set(), "names": set()}
    )
    for row in eligibility.get("rows", []):
        if row.get("option") != "Examen Complexivo" or not row.get("eligible_for_nuclei"):
            continue
        for sources in (row.get("nucleus_sources") or {}).values():
            for source in sources or []:
                course_id = int(source.get("course_id") or 0)
                if not course_id:
                    continue
                source_email = _email(source.get("source_email")) or _email(row.get("email"))
                source_name = _name(source.get("source_name")) or _name(row.get("full_name"))
                if source_email:
                    members[course_id]["emails"].add(source_email)
                if source_name:
                    members[course_id]["names"].add(source_name)
    return members


def install() -> None:
    report._eligible_members_by_course = _eligible_members_by_course
