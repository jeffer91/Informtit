from pathlib import Path
import unittest


class ReportLayoutPolicyTests(unittest.TestCase):
    def test_only_level_one_heading_forces_page_break(self):
        source = Path("report_pdf_polish.py").read_text(encoding="utf-8")
        start = source.index("def _safe_heading")
        end = source.index("def _catalogs_for_pdf", start)
        helper = source[start:end]
        self.assertIn("if level == 1:", helper)
        self.assertNotIn("elif page_break:", helper)
        self.assertIn("CondPageBreak", helper)

    def test_pdf_frame_reserves_space_for_taller_header(self):
        source = Path("report_pdf_polish.py").read_text(encoding="utf-8")
        self.assertIn("topMargin=4.35 * cm", source)

    def test_nuclei_output_filters_empty_courses_and_explains_population(self):
        source = Path("report_pdf_polish.py").read_text(encoding="utf-8")
        self.assertIn("if course.get(\"students\")", source)
        self.assertIn("Población registrada de Núcleos por carrera", source)
        self.assertIn("un curso puede contener uno o pocos estudiantes", source)

    def test_table_context_guard_is_installed(self):
        source = Path("report_integrity_last_guard.py").read_text(encoding="utf-8")
        self.assertIn("_contextual_pdf_caption", source)
        self.assertIn("La siguiente tabla presenta", source)


if __name__ == "__main__":
    unittest.main()
