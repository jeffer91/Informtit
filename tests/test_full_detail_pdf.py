from __future__ import annotations

import unittest
from pathlib import Path

import report_full_detail


ROOT = Path(__file__).resolve().parents[1]


class FullDetailPdfTests(unittest.TestCase):
    def test_expected_report_targets_are_explicit(self) -> None:
        self.assertEqual(report_full_detail.TARGET_NUCLEI, 106)
        self.assertEqual(report_full_detail.TARGET_COMPLEXIVE_CAREERS, 10)

    def test_full_pdf_keeps_individual_sections(self) -> None:
        source = (ROOT / "report_full_detail.py").read_text(encoding="utf-8")
        self.assertIn("Resultados individuales de los cursos o núcleos", source)
        self.assertIn("Resultado individual {index:03d}", source)
        self.assertIn("Evaluación ordinaria", source)
        self.assertIn("Evaluación supletoria", source)
        self.assertIn("Resultado consolidado", source)
        self.assertIn("Comparación descriptiva entre Núcleos y Examen Complexivo", source)
        self.assertNotIn("los listados nominales se trasladan a los anexos", source.lower())

    def test_thesis_has_full_breakdown(self) -> None:
        source = (ROOT / "report_full_detail.py").read_text(encoding="utf-8")
        self.assertIn("Calificaciones del trabajo escrito", source)
        self.assertIn("Evaluación práctica", source)
        self.assertIn("Evaluación de la defensa", source)
        self.assertIn("Verificación de fórmulas", source)
        self.assertIn("Componentes del Trabajo de Titulación", source)

    def test_pdf_has_table_and_figure_indexes(self) -> None:
        source = (ROOT / "report_full_detail.py").read_text(encoding="utf-8")
        self.assertIn('"ÍNDICE DE TABLAS"', source)
        self.assertIn('"ÍNDICE DE FIGURAS"', source)
        self.assertIn("RecordingContext", source)

    def test_validation_is_integrated_before_progress_export(self) -> None:
        validation_runtime = (ROOT / "pdf_validation_runtime.py").read_text(encoding="utf-8")
        progress_runtime = (ROOT / "pdf_progress_runtime.py").read_text(encoding="utf-8")
        integrity_pdf = (ROOT / "report_integrity_pdf.py").read_text(encoding="utf-8")
        hooks = (ROOT / "report_integrity_hooks.py").read_text(encoding="utf-8")
        ui = (ROOT / "static" / "pdf-progress.js").read_text(encoding="utf-8")
        self.assertIn("validate-pdf", validation_runtime)
        self.assertIn("hooks.validation_integrity(report_id)", integrity_pdf)
        self.assertIn("prime_validation", integrity_pdf)
        self.assertIn("_primed_validation", hooks)
        self.assertNotIn("report_full_detail.validate_pdf_report(report_id)", progress_runtime)
        self.assertIn("pdf-jobs", ui)
        self.assertIn("progressbar", ui)
        self.assertIn("Tiempo transcurrido", ui)

    def test_desktop_installs_detail_after_old_overhaul(self) -> None:
        source = (ROOT / "desktop_entry.py").read_text(encoding="utf-8")
        self.assertLess(source.index("report_final_overhaul.install()"), source.index("report_full_detail.install()"))
        self.assertLess(source.index("report_full_detail.install()"), source.index("pdf_progress_runtime.install()"))
        self.assertLess(source.index("pdf_progress_runtime.install()"), source.index("pdf_only_runtime.install()"))


if __name__ == "__main__":
    unittest.main()
