import unittest
from unittest.mock import patch

import student_report_integration as integration


class StudentReportIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.master_rows = [
            {"id": 101, "route": "COMPLEXIVO", "process_status": "ACTIVO", "identification": "111", "full_name": "ANA", "official_graduated": 1, "official_titulation_completed": 1},
            {"id": 102, "route": "TRABAJO_TITULACION", "process_status": "ACTIVO", "identification": "222", "full_name": "BEA", "official_graduated": 1, "official_titulation_completed": 1},
            {"id": 103, "route": "COMPLEXIVO", "process_status": "RETIRADO", "identification": "333", "full_name": "CARLA", "official_graduated": 0, "official_titulation_completed": 0},
        ]

    @patch("student_report_integration.reconcile_all", return_value={"ok": True})
    @patch("student_report_integration.get_period_students")
    @patch("student_report_integration.nuclei_multicampus.get_nuclei")
    def test_nuclei_report_only_uses_active_complexive_route(self, nuclei_mock, students_mock, _reconcile):
        students_mock.return_value = {"students": self.master_rows}
        nuclei_mock.return_value = {"courses": [{"id": 1, "graded_students": 3, "approved_count": 3, "course_average": 8.0, "students": [
            {"id": 1, "period_student_id": 101, "full_name": "ANA", "final_grade": 8},
            {"id": 2, "period_student_id": 102, "full_name": "BEA", "final_grade": 9},
            {"id": 3, "period_student_id": 103, "full_name": "CARLA", "final_grade": 7},
        ]}]}
        result = integration.filtered_nuclei(1)
        course = result["courses"][0]
        self.assertEqual([row["full_name"] for row in course["students"]], ["ANA"])
        self.assertEqual(course["graded_students"], 1)
        self.assertEqual(course["approved_count"], 1)
        self.assertEqual(course["failed_count"], 0)
        self.assertEqual(course["course_average"], 8.0)

    @patch("student_report_integration.reconcile_all", return_value={"ok": True})
    @patch("student_report_integration.get_period_students")
    @patch("student_report_integration.raw_get_projects")
    def test_thesis_report_only_uses_active_manual_thesis_route(self, projects_mock, students_mock, _reconcile):
        students_mock.return_value = {"students": self.master_rows}
        projects_mock.return_value = {"projects": [
            {"id": 1, "period_student_id": 101, "full_name": "ANA", "final_grade": 9},
            {"id": 2, "period_student_id": 102, "full_name": "BEA", "final_grade": ""},
        ]}
        result = integration.filtered_projects(1)
        self.assertEqual([row["full_name"] for row in result["projects"]], ["BEA"])
        self.assertEqual(result["omitted_route_conflicts"], 1)
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["incomplete"], 1)

    @patch("student_report_integration.reconcile_all", return_value={"ok": True})
    @patch("student_report_integration.get_period_students")
    def test_complexive_report_excludes_thesis_and_retired(self, students_mock, _reconcile):
        students_mock.return_value = {"students": self.master_rows}
        original = integration._BASE_REPORT_DATA
        integration._BASE_REPORT_DATA = lambda _rid: {"careers": [{"students": [
            {"period_student_id": 101, "full_name": "ANA"},
            {"period_student_id": 102, "full_name": "BEA"},
            {"period_student_id": 103, "full_name": "CARLA"},
        ]}]}
        try:
            result = integration.filtered_report_data(1)
        finally:
            integration._BASE_REPORT_DATA = original
        self.assertEqual([row["full_name"] for row in result["careers"][0]["students"]], ["ANA"])
        self.assertTrue(result["student_domain_applied"])


if __name__ == "__main__":
    unittest.main()
