from __future__ import annotations

import inspect
import unittest
from pathlib import Path

import report_pdf_polish as polish


ROOT = Path(__file__).resolve().parents[1]


class PdfPolishTests(unittest.TestCase):
    def test_career_names_are_short_and_clear(self) -> None:
        self.assertEqual(
            polish._display_career("TECNOLOGÍA SUPERIOR EN DESARROLLO DE SOFTWARE ONLINE"),
            "Desarrollo de Software Online",
        )
        self.assertEqual(
            polish._display_career("TECNOLOGÍA SUPERIOR EN CONTABILIDAD"),
            "Contabilidad",
        )

    def test_centros_infantiles_is_excluded(self) -> None:
        report = {"modality": "presencial"}
        self.assertFalse(polish._allowed_nuclei_career("ADMINISTRACIÓN DE CENTROS INFANTILES", report))

    def test_nuclei_respects_report_modality(self) -> None:
        self.assertTrue(polish._allowed_nuclei_career("CONTABILIDAD", {"modality": "presencial"}))
        self.assertFalse(polish._allowed_nuclei_career("CONTABILIDAD ONLINE", {"modality": "presencial"}))
        self.assertTrue(polish._allowed_nuclei_career("CONTABILIDAD ONLINE", {"modality": "en_linea"}))
        self.assertFalse(polish._allowed_nuclei_career("CONTABILIDAD", {"modality": "en_linea"}))

    def test_detail_precedes_consolidated_results(self) -> None:
        nuclei = inspect.getsource(polish._pdf_nuclei)
        thesis = inspect.getsource(polish._pdf_projects)
        self.assertLess(nuclei.index("Resultados por curso y estudiante"), nuclei.index("Consolidado por carrera"))
        self.assertLess(thesis.index("for idx, project"), thesis.index("Consolidado del Trabajo de Titulación"))

    def test_schedule_is_closed_without_empty_evidence_columns(self) -> None:
        source = inspect.getsource(polish._pdf_schedules)
        self.assertIn('"Cumplido"', source)
        self.assertIn('"100 %"', source)
        self.assertNotIn('"Sin evaluar"', source)
        self.assertNotIn('"Evidencia"', source)

    def test_toc_has_only_two_levels_and_no_extra_indexes(self) -> None:
        source = inspect.getsource(polish.build_pdf)
        toc_source = inspect.getsource(polish.TocTwoLevels.afterFlowable)
        self.assertNotIn("ÍNDICE DE TABLAS", source)
        self.assertNotIn("ÍNDICE DE FIGURAS", source)
        self.assertIn('"Heading1": 0', toc_source)
        self.assertIn('"Heading2": 1', toc_source)
        self.assertNotIn('"Heading3"', toc_source)

    def test_header_has_single_pagination_and_hides_it_on_cover(self) -> None:
        source = inspect.getsource(polish._draw_header)
        self.assertIn("if page > 1", source)
        self.assertNotIn("drawRightString", source)
        self.assertIn("Fecha de Elaboración:", source)

    def test_polish_is_installed_before_progress_runtime(self) -> None:
        source = (ROOT / "desktop_entry.py").read_text(encoding="utf-8")
        self.assertLess(source.index("report_full_detail.install()"), source.index("report_pdf_polish.install()"))
        self.assertLess(source.index("report_pdf_polish.install()"), source.index("pdf_progress_runtime.install()"))


if __name__ == "__main__":
    unittest.main()
