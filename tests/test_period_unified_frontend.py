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
