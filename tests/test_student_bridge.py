import unittest
from unittest.mock import patch

import student_domain_bridge as bridge


class StudentBridgeTests(unittest.TestCase):
    @patch("student_domain_bridge.nuclei_service.get_nuclei", return_value={"courses": []})
    @patch("student_domain_bridge.reconcile_complexive", return_value={"ok": True, "matched": 0, "pending": 0, "route_conflicts": 0})
    @patch("student_domain_bridge.reconcile_thesis", return_value={"ok": True, "matched": 0, "pending": 0, "route_conflicts": 0})
    def test_reconcile_all_keeps_modules_separate(self, thesis_mock, complexive_mock, _nuclei_mock):
        with patch("student_domain_bridge.ensure_bridge_schema"):
            with patch("student_domain_bridge.connection"):
                result = bridge.reconcile_all(1)
        self.assertTrue(result["ok"])
        self.assertIn("nuclei", result)
        self.assertIn("complexive", result)
        self.assertIn("thesis", result)
        complexive_mock.assert_called_once_with(1)
        thesis_mock.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
