from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import report_consistency_final as consistency
import report_final_overhaul as final
import report_quality
import report_schedule_truth as schedule_truth


_BASE_METHODOLOGY: Callable[..., Any] | None = None


def _schedule_analysis_real(report_id: int) -> dict[str, Any]:
    """Expone el estado real del cronograma con las claves esperadas por el informe."""
    data = schedule_truth._schedule_data(report_id)
    return {
        "schedules": data.get("schedules", {}),
        "total": int(data.get("total") or 0),
        "evaluated": int(data.get("evaluated") or 0),
        "average": data.get("average"),
        "pending_evaluation": int(data.get("pending") or 0),
        "not_complied": int(data.get("not_complied") or 0),
        "delayed": int(data.get("delayed") or 0),
        "partial": int(data.get("partial") or 0),
    }


def _reconcile_methodology_text(text: Any, report_id: int, report: dict[str, Any]) -> str:
    """Aclara cursos importados frente a cursos incluidos en la modalidad del PDF."""
    value = str(text or "")
    if not value.startswith("La base analizada contiene") or "cursos de Núcleos" not in value:
        return value

    raw_source = consistency._ORIGINAL_NUCLEI_CONSOLIDATED
    if raw_source is None:
        return value

    raw_count = len(raw_source(report_id).get("courses", []))
    analyzed_count = len(consistency._master_nuclei(report_id).get("courses", []))
    if raw_count <= 0:
        return value

    modality = report_quality.base.modality(report)
    replacement = f"{raw_count} cursos de Núcleos importados"
    if analyzed_count != raw_count:
        replacement += (
            f" ({analyzed_count} incluidos en este informe {modality} "
            "tras aplicar el filtro de modalidad)"
        )

    return re.sub(r"\d+\s+cursos de Núcleos", replacement, value, count=1)


def _pdf_methodology_followup(
    story: list[Any],
    context: Any,
    styles: Any,
    report: dict[str, Any],
    temp_paths: list[Path],
) -> None:
    if _BASE_METHODOLOGY is None:
        return

    report_id = int(report["id"])
    base_body = report_quality._pdf_body

    def reconciled_body(target_story: list[Any], target_styles: Any, text: str) -> Any:
        return base_body(
            target_story,
            target_styles,
            _reconcile_methodology_text(text, report_id, report),
        )

    report_quality._pdf_body = reconciled_body
    try:
        _BASE_METHODOLOGY(story, context, styles, report, temp_paths)
    finally:
        report_quality._pdf_body = base_body


def install() -> None:
    global _BASE_METHODOLOGY

    if getattr(report_quality, "_report_consistency_followup_installed", False):
        return

    _BASE_METHODOLOGY = report_quality._pdf_methodology

    # report_pdf_polish sustituía el análisis real por uno que marcaba todo al 100 %.
    # Se restaura una sola fuente basada en executed_date, execution_status y porcentaje.
    final._schedule_analysis = _schedule_analysis_real

    # La metodología deja explícita la diferencia entre el universo importado y
    # los cursos realmente incluidos en el PDF Presencial u Online.
    report_quality._pdf_methodology = _pdf_methodology_followup

    report_quality._report_consistency_followup_installed = True
