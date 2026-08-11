from __future__ import annotations

from typing import Any

import report_enhancements
from coordinator_registry import normalize
from nuclei_catalog import catalog_for_career
from nuclei_multicampus import get_nuclei


def catalogs_for_independent_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Incluye carreras presentes en Complexivo o en Núcleos, sin vincular sus poblaciones."""

    names: list[str] = [
        str(career.get("name") or "").strip()
        for career in report.get("careers", [])
        if str(career.get("name") or "").strip()
    ]
    report_id = int(report.get("id") or 0)
    if report_id:
        names.extend(
            str(course.get("career_name") or "").strip()
            for course in get_nuclei(report_id).get("courses", [])
            if str(course.get("career_name") or "").strip()
        )

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in names:
        catalog = catalog_for_career(name)
        if not catalog:
            continue
        key = normalize(catalog.get("career"))
        if key in seen:
            continue
        result.append(catalog)
        seen.add(key)
    return result


def install() -> None:
    # report_enhancements resuelve este nombre en tiempo de ejecución; sustituirlo
    # aquí permite respetar la independencia de módulos sin duplicar contenido.
    report_enhancements.catalogs_for_report = catalogs_for_independent_report
