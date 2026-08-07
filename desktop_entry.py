from __future__ import annotations

import app as core
import completion_routes
import desktop_launcher
import layout_v3
import nuclei_catalog_export
import nuclei_export
import nuclei_fixes
import nuclei_matching_routes
import nuclei_multicampus
import nuclei_multicampus_report
import nuclei_multicampus_workflow
import nuclei_routes
import optional_content
import process_export
import process_routes
import report_completion
import report_completion_constants
import report_completion_fixes
import report_completion_runtime
import report_quality
import report_quality_runtime
import report_structure
import workflow_report_fixes
import workflow_report_runtime
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

    # desktop_launcher ya instaló sus rutas al importarse. Las extensiones
    # siguientes deben quedar como la última capa utilizada por Electron.
    layout_v3.install()
    process_routes.install()
    nuclei_routes.install()
    completion_routes.install()
    nuclei_matching_routes.install()
    process_export.install()
    optional_content.install()
    report_structure.install()
    nuclei_catalog_export.install()
    nuclei_export.install()
    report_quality_runtime.install()
    report_quality.install()
    nuclei_multicampus_report.install()
    report_completion_constants.install()
    report_completion.install()
    report_completion_fixes.install()
    report_completion_runtime.install()
    workflow_report_runtime.install()
    workflow_report_fixes.install()
    # Debe instalarse al final: agrega la sede a la matriz de habilitación
    # sin ser reemplazado por las capas generales del informe.
    nuclei_multicampus_workflow.install()


def main() -> None:
    prepare()
    desktop_launcher.main()


if __name__ == "__main__":
    main()
