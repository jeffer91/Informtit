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

    def test_source_key_is_stable_when_database_row_id_changes(self):
        first = bridge._stable_source_key(
            "NUCLEI",
            {"id": 10, "email": "ANA@ITSQMET.EDU.EC", "full_name": "ANA PEREZ", "career_name": "Enfermería"},
            "course:4",
        )
        second = bridge._stable_source_key(
            "NUCLEI",
            {"id": 999, "email": "ana@itsqmet.edu.ec", "full_name": "ANA PEREZ", "career_name": "Enfermería"},
            "course:4",
        )
        self.assertEqual(first, second)
        self.assertIn("email:ana@itsqmet.edu.ec", first)

    def test_excel_generated_email_does_not_become_student_identity(self):
        course_before = {
            "id": 4,
            "career_name": "Enfermería",
            "nucleus_number": 1,
            "course_title": "Fundamentos clínicos",
            "teacher_name": "Docente Uno",
        }
        course_after = {**course_before, "id": 987}
        context_before = bridge._nucleus_context(course_before)
        context_after = bridge._nucleus_context(course_after)
        first = bridge._stable_source_key(
            "NUCLEI",
            {
                "email": "aaa111@excel.local",
                "full_name": "PÉREZ LÓPEZ ANA MARÍA",
                "career_name": "Enfermería",
            },
            context_before,
        )
        second = bridge._stable_source_key(
            "NUCLEI",
            {
                "email": "bbb999@excel.local",
                "full_name": "ANA MARÍA PÉREZ LÓPEZ",
                "career_name": "Enfermería",
            },
            context_after,
        )
        self.assertEqual(context_before, context_after)
        self.assertEqual(first, second)
        self.assertIn("name:", first)
        self.assertNotIn("excel.local", first)


if __name__ == "__main__":
    unittest.main()
