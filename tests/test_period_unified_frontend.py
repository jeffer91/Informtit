from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PeriodUnifiedFrontendTests(unittest.TestCase):
    def test_unified_script_precedes_final_desktop_rescue(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r'<script\s+src="([^"]+)"', html)
        self.assertTrue(scripts)
        unified = next(i for i, path in enumerate(scripts) if path.startswith('/period-unified-ui.js?'))
        rescue = next(i for i, path in enumerate(scripts) if path.startswith('/desktop-ui-rescue.js?'))
        self.assertTrue(any(path.startswith('/robust-import-ui.js?') for path in scripts))
        self.assertTrue(any(path.startswith('/pdf-validation-ui.js?') for path in scripts))
        self.assertGreater(rescue, unified)
        self.assertTrue(scripts[-1].startswith('/desktop-ui-rescue.js?'))

    def test_normal_period_has_three_views_and_separate_pdf_actions(self):
        script = (ROOT / "static" / "period-unified-ui.js").read_text(encoding="utf-8")
        generated = (ROOT / "static" / "generated-pdfs-ui.js").read_text(encoding="utf-8")
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        for expected in ("Todos", "Presencial", "Online"):
            self.assertIn(expected, script)
        self.assertNotIn("PDF Presencial", script)
        self.assertNotIn("PDF Online", script)
        self.assertIn("Generar informes", html)
        self.assertIn("PDFs generados", html)
        self.assertIn("PDF Presencial", generated)
        self.assertIn("PDF Online", generated)
        self.assertIn("period_project_id", script)
        self.assertIn("Cronograma compartido", script)

    def test_creation_dialog_exposes_explicit_pvc_option(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="new-pvc-report-btn"', html)
        self.assertIn('name="report_type"', html)
        self.assertIn('value="pvc"', html)
        self.assertIn("openReportDialog('pvc')", app)

    def test_creation_dialog_uses_structured_period_and_code_month(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        for field in (
            'name="period_start_month"',
            'name="period_start_year"',
            'name="period_end_month"',
            'name="period_end_year"',
            'name="code_month"',
        ):
            self.assertIn(field, html)
        self.assertIn('type="month" name="code_month"', html)
        self.assertIn("Informe Final del Proceso de Titulación -", app)
        self.assertIn("UTET-INF-01-PRO-95-", app)
        self.assertIn("refreshDerivedReportFields", app)

    def test_creation_defaults_to_current_academic_period_and_general_fields_are_readonly(self):
        app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        hotfix = (ROOT / "static" / "forms-hotfix.js").read_text(encoding="utf-8")
        self.assertIn("if (month >= 4 && month <= 9)", app)
        self.assertIn("startMonth = 10", app)
        self.assertIn("codeMonth:", app)
        self.assertIn("function readonlyField", app)
        for source in (app, hotfix):
            self.assertIn("readonlyField('name'", source)
            self.assertIn("readonlyField('period'", source)
            self.assertIn("readonlyField('code'", source)

    def test_dashboard_uses_one_card_per_period(self):
        script = (ROOT / "static" / "period-unified-ui.js").read_text(encoding="utf-8")
        self.assertIn("Períodos", script)
        self.assertIn("Presencial + Online", script)
        self.assertIn("data-open-period", script)


if __name__ == "__main__":
    unittest.main()
