from __future__ import annotations

import re
from typing import Any

import app as core
import completion_routes
import completion_service
import nuclei_excel_import
import nuclei_routes
import process_routes
import process_service
import report_completion
import report_consistency_final as consistency
import report_final_overhaul as final
import report_full_detail as full
import report_integrity_core as integrity
import report_integrity_hooks as hooks
import report_integrity_pdf as integrity_pdf
import report_pdf_polish as polish
import report_quality


def install() -> None:
    if getattr(report_quality, "_report_integrity_runtime_installed", False):
        return

    raw_nuclei_provider = consistency._ORIGINAL_NUCLEI_CONSOLIDATED or final._nuclei_consolidated
    integrity.set_raw_nuclei_provider(raw_nuclei_provider)
    integrity.ensure_integrity_schema()

    hooks.configure(
        validate=full.validate_pdf_report,
        executive_data=report_completion._executive_data,
        conclusions=full._conclusions,
        replace_schedule=process_service.replace_schedule,
        replace_schedule_extended=completion_service.replace_schedule_extended,
        import_nuclei_excel=nuclei_excel_import.import_nuclei_excel,
    )
    integrity_pdf.configure(
        build_pdf=core.build_pdf,
        display_report=polish._display_report,
        cover_pdf=report_quality.base.cover_pdf,
        pdf_body=report_quality._pdf_body,
        pdf_bullet=report_quality._pdf_bullet,
        pdf_methodology=report_quality._pdf_methodology,
        pdf_post_sections=report_quality._pdf_post_sections,
    )

    # No evaluado se conserva en el total, pero jamás se usa como nota estadística.
    consistency._master_nuclei = integrity.strict_nuclei
    final._nuclei_consolidated = integrity.strict_nuclei
    polish._filtered_nuclei_data = integrity.strict_nuclei
    full._nuclei_data = integrity.strict_nuclei
    full._course_detail = hooks.strict_course_detail

    # El cronograma usa un identificador normalizado de actividad y elimina
    # duplicados antiguos o nuevos antes de llegar al análisis/PDF.
    integrity.schedule_summary = hooks.schedule_summary_strict
    hooks.cleanup_existing_schedule_duplicates()
    process_service.replace_schedule = hooks.replace_schedule_deduped
    process_routes.replace_schedule = hooks.replace_schedule_deduped
    completion_service.replace_schedule_extended = hooks.replace_schedule_extended_deduped
    completion_routes.replace_schedule_extended = hooks.replace_schedule_extended_deduped

    # Duplicados de Núcleos quedan trazados como exactos o probables.
    nuclei_excel_import.import_nuclei_excel = hooks.import_nuclei_audited
    nuclei_routes.import_nuclei_excel = hooks.import_nuclei_audited

    # El resumen, las acciones y las conclusiones consumen el mismo objeto de métricas.
    report_completion._executive_data = hooks.executive_data_integrity
    report_completion._automatic_actions = hooks.automatic_actions_integrity
    full._conclusions = hooks.conclusions_integrity

    # Estado documental dinámico: BORRADOR / APTO PARA EMITIR / SIN POBLACIÓN.
    polish._display_report = integrity_pdf.display_report_integrity
    report_quality.base.header_title = integrity_pdf.header_title
    report_quality.base.cover_pdf = integrity_pdf.cover_pdf_integrity
    report_quality._pdf_body = integrity_pdf.pdf_body_integrity
    report_quality._pdf_bullet = integrity_pdf.pdf_bullet_integrity
    report_quality._pdf_methodology = integrity_pdf.pdf_methodology_integrity
    report_quality._pdf_post_sections = integrity_pdf.pdf_post_sections_integrity

    # Validación y generación final. El modo SIN POBLACIÓN evita secciones vacías.
    polish.validate_pdf_report = hooks.validation_integrity
    full.validate_pdf_report = hooks.validation_integrity
    core.build_pdf = integrity_pdf.build_pdf_integrity
    report_quality.build_pdf = integrity_pdf.build_pdf_integrity
    full.build_pdf = integrity_pdf.build_pdf_integrity
    polish.build_pdf = integrity_pdf.build_pdf_integrity

    previous_get = core.InformtitHandler._handle_api_get

    def audit_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)/audit", path)
        if match:
            self._send_json({"ok": True, "audit": integrity.audit_report(int(match.group(1)))})
            return
        previous_get(self, path, query)

    core.InformtitHandler._handle_api_get = audit_get
    report_quality._report_integrity_runtime_installed = True
