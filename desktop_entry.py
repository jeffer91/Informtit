from __future__ import annotations

import app as core
import completion_routes
import desktop_launcher
import dual_modality_runtime
import firebase_catalog_runtime
import firebase_integrity_runtime
import firebase_sync_runtime
import layout_v3
import nuclei_catalog_export
import nuclei_course_edit
import nuclei_excel_report
import nuclei_export
import nuclei_fixes
import nuclei_multicampus
import nuclei_multicampus_report
import nuclei_routes
import optional_content
import pdf_only_runtime
import pdf_progress_runtime
import pdf_validation_runtime
import period_import_guard
import period_policy_runtime
import period_unified_runtime
import process_export
import process_routes
import report_catalog_independent
import report_completion
import report_completion_constants
import report_completion_fixes
import report_consistency_final
import report_consistency_followup
import report_decoupled
import report_enhancements
import report_final_overhaul
import report_full_detail
import report_integrity_ishikawa
import report_integrity_last_guard
import report_integrity_runtime
import report_pdf_guard
import report_pdf_polish
import report_quality
import report_quality_runtime
import report_schedule_truth
import report_structure
import report_table_style
import report_visual_extensions
import storage_migration
import thesis_parser_flex
from completion_service import ensure_completion_schema
from db import connection
from import_service import ensure_schema
from institutional_defaults import apply_defaults
from nuclei_service import ensure_nuclei_schema
from process_service import ensure_process_schema
from thesis_followup import ensure_thesis_followup_schema


def prepare() -> None:
    """Prepara la base y aplica extensiones en un orden determinista."""

    storage_migration.migrate_legacy_storage()
    period_policy_runtime.configure_storage()

    core.init_db()
    ensure_schema()
    period_policy_runtime.ensure_schema()
    ensure_process_schema()
    ensure_nuclei_schema()
    ensure_completion_schema()
    ensure_thesis_followup_schema()
    nuclei_fixes.install()
    nuclei_multicampus.install()
    with connection() as conn:
        apply_defaults(conn)

    layout_v3.install()
    thesis_parser_flex.install()
    process_routes.install()
    nuclei_routes.install()
    nuclei_course_edit.install()
    completion_routes.install()
    process_export.install()
    optional_content.install()
    report_structure.install()
    nuclei_catalog_export.install()
    nuclei_export.install()
    report_quality_runtime.install()
    report_quality.install()
    nuclei_multicampus_report.install()
    report_completion_constants.install()

    report_decoupled.install()
    report_completion.install()
    report_completion_fixes.install()
    report_enhancements.install()
    report_catalog_independent.install()
    report_table_style.install()
    nuclei_excel_report.install()
    report_final_overhaul.install()
    report_schedule_truth.install()
    report_full_detail.install()
    report_pdf_polish.install()
    report_pdf_guard.install()
    report_visual_extensions.install()
    report_consistency_final.install()
    report_consistency_followup.install()
    pdf_progress_runtime.install()
    pdf_validation_runtime.install()
    pdf_only_runtime.install()

    # Períodos normales: una sola fuente con datasets Presencial + Online.
    period_policy_runtime.prepare_dual_policy()
    dual_modality_runtime.install()
    period_policy_runtime.install()
    firebase_catalog_runtime.install()
    firebase_sync_runtime.install()
    firebase_integrity_runtime.install()

    report_integrity_runtime.install()
    report_integrity_last_guard.install()
    report_integrity_ishikawa.install()

    # Un proyecto visible por período con dos salidas PDF filtradas.
    period_unified_runtime.install()

    # Última guarda: vuelve a clasificar NombreCarrera/CodigoCarrera justo antes
    # de confirmar la importación y evita que un archivo con Online termine en 0.
    period_import_guard.install()


def main() -> None:
    prepare()
    desktop_launcher.main()


if __name__ == "__main__":
    main()
