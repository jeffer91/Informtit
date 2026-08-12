from __future__ import annotations

import app as core
import completion_routes
import desktop_launcher
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
import process_export
import process_routes
import report_catalog_independent
import report_completion
import report_completion_constants
import report_completion_fixes
import report_decoupled
import report_enhancements
import report_final_overhaul
import report_quality
import report_quality_runtime
import report_schedule_truth
import report_structure
import report_table_style
from completion_service import ensure_completion_schema
from db import connection
from import_service import ensure_schema
from institutional_defaults import apply_defaults
from nuclei_service import ensure_nuclei_schema
from process_service import ensure_process_schema
from thesis_followup import ensure_thesis_followup_schema


def prepare() -> None:
    """Prepara la base y aplica extensiones en un orden determinista."""

    core.init_db()
    ensure_schema()
    ensure_process_schema()
    ensure_nuclei_schema()
    ensure_completion_schema()
    ensure_thesis_followup_schema()
    nuclei_fixes.install()
    nuclei_multicampus.install()
    with connection() as conn:
        apply_defaults(conn)

    # Las cuatro áreas del informe se conservan dentro del mismo proyecto,
    # pero no se utilizan como filtros o puertas de acceso entre sí.
    layout_v3.install()
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

    # Debe instalarse antes de report_completion para que sus envoltorios usen
    # narrativas y cálculos independientes por módulo.
    report_decoupled.install()
    report_completion.install()
    report_completion_fixes.install()

    # Capas de presentación académica e institucional.
    report_enhancements.install()
    report_catalog_independent.install()
    report_table_style.install()

    # Núcleos toma el Excel consolidado como fuente oficial.
    nuclei_excel_report.install()

    # Esta capa final concentra consolidados en el cuerpo, mueve listados
    # nominales a anexos y aplica el Ishikawa/análisis/plan de mejora definitivos.
    report_final_overhaul.install()

    # El cronograma se evalúa únicamente con datos reales de ejecución.
    report_schedule_truth.install()


def main() -> None:
    prepare()
    desktop_launcher.main()


if __name__ == "__main__":
    main()
