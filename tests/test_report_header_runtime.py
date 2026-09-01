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
        source = open("report_pdf_polish.py", encoding="utf-8").read()
        self.assertIn("row = 1.28 * cm", source)
        self.assertIn("left = 4.65 * cm", source)
        self.assertIn("right = 4.45 * cm", source)
        self.assertIn("total = width - 1.90 * cm", source)

if __name__ == "__main__":
    unittest.main()
