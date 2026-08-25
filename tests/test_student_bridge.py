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

    @patch("student_domain_bridge.match_source_record")
    @patch("student_domain_bridge._manual_match")
    def test_manual_match_always_wins_over_automatic_matcher(self, manual_mock, automatic_mock):
        manual_mock.return_value = {
            "status": "OK",
            "method": "MANUAL",
            "confidence": 100.0,
            "period_student_id": 77,
            "candidates": [],
        }
        result = bridge._match(1, "NUCLEI", "source-1", {"full_name": "NOMBRE CAMBIADO"})
        self.assertEqual(result["period_student_id"], 77)
        self.assertEqual(result["method"], "MANUAL")
        automatic_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
