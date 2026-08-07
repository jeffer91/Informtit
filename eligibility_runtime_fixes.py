from __future__ import annotations

from typing import Any

import eligibility_service


_ORIGINAL_GET_ELIGIBILITY = eligibility_service.get_eligibility


def _clean_result(data: dict[str, Any]) -> dict[str, Any]:
    """Evita reportar como fallo de requisitos casos que no tienen requisito pendiente.

    Por ejemplo, una persona perteneciente a Trabajo de Titulación puede aparecer
    accidentalmente en un curso Moodle de Núcleos. Debe quedar fuera de las notas
    de Núcleos, pero no contarse como "nota sin requisitos" si sus ocho requisitos
    estaban completos.
    """

    cleaned = dict(data)
    conflicts = [
        item
        for item in data.get("prerequisite_conflicts", [])
        if item.get("missing_requirements")
    ]
    cleaned["prerequisite_conflicts"] = conflicts
    summary = dict(data.get("summary") or {})
    summary["nucleus_without_prerequisites"] = len(conflicts)
    cleaned["summary"] = summary
    return cleaned


def get_eligibility(report_id: int) -> dict[str, Any]:
    return _clean_result(_ORIGINAL_GET_ELIGIBILITY(report_id))


def install() -> None:
    eligibility_service.get_eligibility = get_eligibility

    # Estos módulos importan la función directamente, por lo que se actualizan
    # sus referencias después de instalar todas las demás extensiones.
    import completion_routes
    import nuclei_multicampus_report
    import nuclei_multicampus_workflow
    import report_completion
    import workflow_report_runtime

    completion_routes.get_eligibility = get_eligibility
    nuclei_multicampus_report.get_eligibility = get_eligibility
    nuclei_multicampus_workflow.get_eligibility = get_eligibility
    report_completion.get_eligibility = get_eligibility
    workflow_report_runtime.get_eligibility = get_eligibility
