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
import pdf_only_runtime
import pdf_progress_runtime
import pdf_validation_runtime
import process_export
import process_routes
import report_catalog_independent
import report_completion
import report_completion_constants
import report_completion_fixes
import report_consistency_final
import report_decoupled
import report_enhancements
import report_final_overhaul
import report_full_detail
import report_pdf_guard
import report_pdf_polish
import report_quality
import report_quality_runtime
import report_schedule_truth
import report_structure
import report_table_style
import report_visual_extensions
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

    # Trabajo de Titulación acepta variantes reales del encabezado institucional
    # y códigos de carrera presenciales/en línea sin depender de una letra fija.
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

    # Conserva los consolidados y análisis estratégicos agregados.
    report_final_overhaul.install()

    # El cronograma se evalúa únicamente con datos reales de ejecución.
    report_schedule_truth.install()

    # Restauración final del detalle: los consolidados ya no sustituyen las
    # subsecciones nominales de Núcleos, Complexivo o Trabajo de Titulación.
    report_full_detail.install()

    # Pulido definitivo del PDF: TOC de dos niveles, detalle antes del
    # consolidado, nombres cortos y gráficos legibles.
    report_pdf_polish.install()

    # Guardia final: elimina variantes largas de carreras excluidas antes de
    # importar, analizar o renderizar el PDF.
    report_pdf_guard.install()

    # Capa visual final: añade gráficos de requisitos, cronograma, Núcleos,
    # Complexivo, Trabajo de Titulación y priorización estratégica.
    report_visual_extensions.install()

    # Consistencia final: una sola población por modalidad, cronograma basado
    # en ejecución real, empates correctos, rúbricas agregadas, validación
    # ampliada y nombre institucional del archivo PDF.
    report_consistency_final.install()

    # La generación del PDF se ejecuta como un trabajo consultable. La barra
    # refleja etapas reales del generador y permite que la interfaz siga activa.
    pdf_progress_runtime.install()
    pdf_validation_runtime.install()

    # La aplicación final trabaja exclusivamente con PDF. Las firmas/QR no se
    # cargan como imágenes; la portada conserva solo nombres y cargos.
    pdf_only_runtime.install()


def main() -> None:
    prepare()
    desktop_launcher.main()


if __name__ == "__main__":
    main()
