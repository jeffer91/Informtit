import unittest

from reportlab.lib.units import cm

import report_header_runtime as header


class ReportHeaderRuntimeTests(unittest.TestCase):
    def test_right_header_lines_stay_above_divider(self):
        top = 100.0
        row = 1.08 * cm
        divider = top - row
        baselines = header._right_top_baselines(top, row)
        self.assertEqual(len(baselines), 3)
        self.assertTrue(all(y > divider for y in baselines))
        self.assertGreater(min(baselines) - divider, 0.20 * cm)



    def test_active_pdf_header_uses_larger_boxes(self):
        source = open("report_integrity_last_guard.py", encoding="utf-8").read()
        self.assertIn("row = 1.50 * cm", source)
        self.assertIn("left = 4.80 * cm", source)
        self.assertIn("right = 4.60 * cm", source)
        self.assertIn("total = width - 1.80 * cm", source)
        self.assertIn("def _draw_cell_text", source)
        self.assertNotIn('canvas.drawRightString(width - 1.35 * cm', source)

if __name__ == "__main__":
    unittest.main()
