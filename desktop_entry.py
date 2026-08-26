from __future__ import annotations

import app as core
import completion_routes
import coordinator_admin_runtime
import database_hardening
import desktop_launcher
import desktop_stability_runtime
import dual_modality_runtime
import firebase_catalog_runtime
import firebase_incremental_runtime
import firebase_integrity_runtime
import firebase_nuclei_bridge
import firebase_sync_runtime
import import_preview_runtime
import layout_v3
import modality_classifier_runtime
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
import period_readonly_runtime
import period_unified_runtime
import process_export
import process_routes
import read_performance_runtime
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
import robust_import_context
import robust_import_fixes
import robust_import_policy
import robust_import_runtime
import schedule_defaults_runtime
import smart_reconciliation_runtime
import sqlite_concurrency_runtime
import storage_migration
import student_domain_integrations
import student_domain_runtime
import student_final_audit
import student_period_runtime
import student_report_integration
import thesis_parser_flex
from completion_service import ensure_completion_schema
from db import connection
from import_service import ensure_schema
from institutional_defaults import apply_defaults
from nuclei_service import ensure_nuclei_schema
from process_service import ensure_process_schema
from student_domain_service import ensure_student_domain_schema
from thesis_followup import ensure_thesis_followup_schema


def prepare() -> None:
    """Prepara la base y aplica extensiones en un orden determinista."""

    storage_migration.migrate_legacy_storage()
    period_policy_runtime.configure_storage()

    core.init_db()
    database_hardening.install()
    ensure_schema()
    period_policy_runtime.ensure_schema()
    ensure_process_schema()
    ensure_nuclei_schema()
    ensure_completion_schema()
    ensure_thesis_followup_schema()
    ensure_student_domain_schema()

    # Las antiguas fechas semilla de 2025/2026 se eliminan únicamente cuando
    # permanecen intactas. Los cronogramas editados o con ejecución se conservan.
    schedule_defaults_runtime.install()

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

    # Detecta el contenido real del archivo (HTML antiguo, XLS, XLSX, XML, CSV/TSV)
    # y normaliza encabezados antes de clasificar las modalidades.
    robust_import_runtime.install()
    robust_import_fixes.install()
    robust_import_policy.install()
    robust_import_context.install()

    dual_modality_runtime.install()
    modality_classifier_runtime.install()
    period_policy_runtime.install()
    firebase_catalog_runtime.install()
    firebase_sync_runtime.install()
    firebase_integrity_runtime.install()

    # Firebase trabaja con la entidad multicampus actual de Núcleos. Las tablas
    # legacy quedan únicamente como fuente de migración de instalaciones antiguas.
    firebase_nuclei_bridge.install()

    # Solo se escriben documentos cuyo contenido académico cambió. updatedAt no
    # forma parte del hash para evitar escrituras falsas en cada sincronización.
    firebase_incremental_runtime.install()

    report_integrity_runtime.install()
    report_integrity_last_guard.install()
    report_integrity_ishikawa.install()

    # Un proyecto visible por período con dos salidas PDF filtradas.
    period_unified_runtime.install()

    # Después de la conciliación inicial, consultar un período no vuelve a
    # reescribir proyectos ni cronogramas. Las conciliaciones quedan en writes.
    period_readonly_runtime.install()

    # Vuelve a clasificar NombreCarrera/CodigoCarrera justo antes de confirmar.
    period_import_guard.install()

    # Se instala al final para que el análisis no atraviese toda la cadena de
    # wrappers de escritura y para mostrar errores reales de forma inmediata.
    import_preview_runtime.install()

    # CRUD persistente para nombre, Telegram y carreras de cada coordinador.
    coordinator_admin_runtime.install()

    # Dominio maestro local: Requisitos crea la identidad; Núcleos, Complexivo y
    # Trabajo de Titulación solo aportan evidencia. No modifica Firebase compartida.
    student_domain_runtime.install()
    student_domain_integrations.install()
    student_period_runtime.install()

    # Auditoría final: estabiliza identidad, vínculos históricos, homónimos,
    # conflictos de modalidad y operaciones manuales antes de construir reportes.
    student_final_audit.install_pre_report()

    # Los reportes consumen la misma población maestra que la pantalla Estudiantes:
    # Complexivo/Núcleos solo para ruta Complexivo activa y proyectos solo para
    # Trabajo de Titulación activo. Las fuentes crudas de carga permanecen intactas.
    student_report_integration.install()
    student_final_audit.install_post_report()

    # Última capa: sirve siempre la interfaz actual sin caché y expone diagnóstico
    # del archivo SQLite realmente abierto por el proceso de escritorio.
    desktop_stability_runtime.install()

    # SQLite admite un único escritor. La capa final elimina writers anidados,
    # serializa escrituras y deja el dominio maestro sincronizado tras cada carga.
    sqlite_concurrency_runtime.install()

    # Navegar por Todos/Estudiantes debe ser lectura pura. La conciliación pesada
    # queda para cargas, cambios y el botón explícito Reconciliar.
    read_performance_runtime.install()

    # Capa final de matching: identidad fuerte antes que similitud, agrupación de
    # evidencias repetidas y conciliación en segundo plano con progreso observable.
    smart_reconciliation_runtime.install()


def main() -> None:
    prepare()
    desktop_launcher.main()


if __name__ == "__main__":
    main()
