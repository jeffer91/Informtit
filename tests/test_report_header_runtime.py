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


if __name__ == "__main__":
    unittest.main()
