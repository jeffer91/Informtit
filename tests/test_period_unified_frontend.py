from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PeriodUnifiedFrontendTests(unittest.TestCase):
    def test_unified_script_is_loaded_last(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('/period-unified-ui.js?v=4.0', html)
        self.assertGreater(
            html.index('/period-unified-ui.js?v=4.0'),
            html.index('/pdf-validation-ui.js?v=4.0'),
        )

    def test_normal_period_has_three_views_and_two_pdf_buttons(self):
        script = (ROOT / "static" / "period-unified-ui.js").read_text(encoding="utf-8")
        for expected in ("Todos", "Presencial", "Online", "PDF Presencial", "PDF Online"):
            self.assertIn(expected, script)
        self.assertIn("period_project_id", script)
        self.assertIn("Cronograma compartido", script)

    def test_dashboard_uses_one_card_per_period(self):
        script = (ROOT / "static" / "period-unified-ui.js").read_text(encoding="utf-8")
        self.assertIn("Períodos", script)
        self.assertIn("Presencial + Online", script)
        self.assertIn("data-open-period", script)


if __name__ == "__main__":
    unittest.main()
