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

    @patch("student_report_integration.get_period_students")
    def test_report_snapshot_reuses_master_read_and_expires_after_build(self, students_mock):
        students_mock.return_value = {"students": self.master_rows}
        with integration.report_read_snapshot():
            first = integration._master(1)
            second = integration._master(1)
        third = integration._master(1)

        self.assertIs(first, second)
        self.assertEqual(first, third)
        self.assertEqual(students_mock.call_count, 2)

    def test_report_admission_requires_current_requirements_and_no_master_conflict(self):
        base = {
            "route": integration.ROUTE_COMPLEXIVE,
            "process_status": "ACTIVO",
            "requirements_present": 1,
            "modality_conflict": 0,
            "reconciliation_status": "OK",
        }
        self.assertTrue(integration._active_for_route(base, integration.ROUTE_COMPLEXIVE))
        self.assertFalse(integration._active_for_route(
            {**base, "requirements_present": 0}, integration.ROUTE_COMPLEXIVE
        ))
        self.assertFalse(integration._active_for_route(
            {**base, "modality_conflict": 1}, integration.ROUTE_COMPLEXIVE
        ))
        self.assertFalse(integration._active_for_route(
            {**base, "reconciliation_status": "DUPLICATE"}, integration.ROUTE_COMPLEXIVE
        ))

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

    @patch("student_report_integration._project_report_ids", return_value=[1])
    @patch("student_report_integration._selected_grade", return_value=None)
    @patch("student_report_integration.reconcile_all", return_value={"ok": True})
    @patch("student_report_integration.get_period_students")
    @patch("student_report_integration.nuclei_multicampus.get_nuclei")
    def test_nuclei_is_split_by_official_requirements_career(
        self, nuclei_mock, students_mock, _reconcile, _selected, _reports
    ):
        masters = [
            {
                "id": 201, "route": "COMPLEXIVO", "process_status": "ACTIVO",
                "requirements_present": 1, "modality_conflict": 0,
                "reconciliation_status": "OK", "identification": "201",
                "full_name": "ANA", "career_name": "ADMINISTRACION",
            },
            {
                "id": 202, "route": "COMPLEXIVO", "process_status": "ACTIVO",
                "requirements_present": 1, "modality_conflict": 0,
                "reconciliation_status": "OK", "identification": "202",
                "full_name": "BEA", "career_name": "CONTABILIDAD",
            },
        ]
        students_mock.return_value = {"students": masters}
        nuclei_mock.return_value = {"courses": [{
            "id": 1,
            "nucleus_number": 1,
            "career_name": "CARRERA MAL CARGADA",
            "students": [
                {"id": 1, "period_student_id": 201, "full_name": "ANA", "final_grade": 8.0, "scores": []},
                {"id": 2, "period_student_id": 202, "full_name": "BEA", "final_grade": 9.0, "scores": []},
            ],
            "assessments": [],
            "activity_averages": [],
        }]}

        result = integration.filtered_nuclei(1)
        careers = {
            course["career_name"]: [row["full_name"] for row in course["students"]]
            for course in result["courses"]
        }
        self.assertEqual(careers["ADMINISTRACION"], ["ANA"])
        self.assertEqual(careers["CONTABILIDAD"], ["BEA"])
        self.assertNotIn("CARRERA MAL CARGADA", careers)


    @patch("student_report_integration._project_report_ids", return_value=[1, 2])
    @patch("student_report_integration._selected_grade", return_value=None)
    @patch("student_report_integration.reconcile_all", return_value={"ok": True})
    @patch("student_report_integration.get_period_students")
    @patch("student_report_integration.nuclei_multicampus.get_nuclei")
    def test_nuclei_same_student_and_grade_in_both_datasets_is_counted_once(
        self, nuclei_mock, students_mock, _reconcile, _selected, _reports
    ):
        students_mock.return_value = {"students": self.master_rows}

        def nuclei(report_id):
            return {"courses": [{
                "id": report_id,
                "nucleus_number": 1,
                "career_name": "CARRERA",
                "students": [{
                    "id": report_id,
                    "period_student_id": 101,
                    "full_name": "ANA",
                    "final_grade": 8.0,
                    "scores": [],
                }],
                "assessments": [],
                "activity_averages": [],
            }]}

        nuclei_mock.side_effect = nuclei
        result = integration.filtered_nuclei(1)
        rows = [student for course in result["courses"] for student in course["students"]]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["full_name"], "ANA")
        self.assertEqual(result["omitted_grade_conflicts"], 0)

    @patch("student_report_integration._project_report_ids", return_value=[1, 2])
    @patch("student_report_integration._selected_grade", return_value=None)
    @patch("student_report_integration.reconcile_all", return_value={"ok": True})
    @patch("student_report_integration.get_period_students")
    @patch("student_report_integration.nuclei_multicampus.get_nuclei")
    def test_nuclei_conflicting_grades_are_omitted_until_human_decision(
        self, nuclei_mock, students_mock, _reconcile, _selected, _reports
    ):
        students_mock.return_value = {"students": self.master_rows}

        def nuclei(report_id):
            return {"courses": [{
                "id": report_id,
                "nucleus_number": 1,
                "career_name": "CARRERA",
                "students": [{
                    "id": report_id,
                    "period_student_id": 101,
                    "full_name": "ANA",
                    "final_grade": 8.0 if report_id == 1 else 9.0,
                    "scores": [],
                }],
                "assessments": [],
                "activity_averages": [],
            }]}

        nuclei_mock.side_effect = nuclei
        result = integration.filtered_nuclei(1)
        rows = [student for course in result["courses"] for student in course["students"]]
        self.assertEqual(rows, [])
        self.assertEqual(result["omitted_grade_conflicts"], 1)


    @patch("student_report_integration._project_report_ids", return_value=[1])
    @patch("student_report_integration._selected_grade", return_value=6.0)
    @patch("student_report_integration.reconcile_all", return_value={"ok": True})
    @patch("student_report_integration.get_period_students")
    @patch("student_report_integration.raw_get_projects")
    def test_thesis_manual_grade_is_effective_and_status_does_not_override_it(
        self, projects_mock, students_mock, _reconcile, _selected, _reports
    ):
        students_mock.return_value = {"students": self.master_rows}
        projects_mock.return_value = {"projects": [
            {
                "id": 1, "report_id": 1, "period_student_id": 102,
                "full_name": "BEA", "final_grade": 6.0, "final_status": "APROBADO",
            },
            {
                "id": 2, "report_id": 1, "period_student_id": 102,
                "full_name": "BEA", "final_grade": 9.0, "final_status": "REPROBADO",
            },
        ], "summary": {}}

        result = integration.filtered_projects(1)
        self.assertEqual(len(result["projects"]), 1)
        self.assertEqual(result["projects"][0]["final_grade"], 6.0)
        self.assertEqual(result["summary"]["approved"], 0)
        self.assertEqual(result["summary"]["failed"], 1)

    @patch("student_report_integration._project_report_ids", return_value=[1])
    @patch("student_report_integration._selected_grade", return_value=None)
    @patch("student_report_integration.reconcile_all", return_value={"ok": True})
    @patch("student_report_integration.get_period_students")
    @patch("student_report_integration.raw_get_projects")
    def test_thesis_conflicting_grades_are_omitted_until_human_decision(
        self, projects_mock, students_mock, _reconcile, _selected, _reports
    ):
        students_mock.return_value = {"students": self.master_rows}
        projects_mock.return_value = {"projects": [
            {"id": 1, "report_id": 1, "period_student_id": 102, "full_name": "BEA", "final_grade": 6.0},
            {"id": 2, "report_id": 1, "period_student_id": 102, "full_name": "BEA", "final_grade": 9.0},
        ], "summary": {}}

        result = integration.filtered_projects(1)
        self.assertEqual(result["projects"], [])
        self.assertEqual(result["summary"]["total"], 0)
        self.assertEqual(result["omitted_grade_conflicts"], 1)

    @patch("student_report_integration._project_report_ids", return_value=[1, 2])
    @patch("student_report_integration._selected_grade", return_value=None)
    @patch("student_report_integration.reconcile_all", return_value={"ok": True})
    @patch("student_report_integration.get_period_students")
    def test_complexive_same_student_in_both_datasets_is_counted_once(
        self, students_mock, _reconcile, _selected, _reports
    ):
        students_mock.return_value = {"students": self.master_rows}
        original = integration._BASE_REPORT_DATA

        def report_data(report_id):
            return {
                "careers": [{
                    "id": report_id,
                    "name": "CARRERA",
                    "students": [{
                        "id": report_id,
                        "period_student_id": 101,
                        "full_name": "ANA",
                        "ordinary_theory": 80,
                        "ordinary_practical": 80,
                    }],
                    "images": [],
                    "analyses": {},
                }]
            }

        integration._BASE_REPORT_DATA = report_data
        try:
            result = integration.filtered_report_data(1)
        finally:
            integration._BASE_REPORT_DATA = original

        rows = result["careers"][0]["students"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["full_name"], "ANA")


    def test_nuclei_modality_comes_from_dataset_not_career_name(self):
        original = integration._BASE_NUCLEI_CONSOLIDATED
        integration._BASE_NUCLEI_CONSOLIDATED = lambda _rid: {
            "careers": [{"career": "Enfermería", "modality": "Presencial"}],
            "course_rows": [{"career": "Enfermería", "modality": "Presencial"}],
        }
        try:
            with patch("student_report_integration._dataset_modality_label", return_value="Online"):
                data = integration._nuclei_consolidated_with_dataset_modality(1)
        finally:
            integration._BASE_NUCLEI_CONSOLIDATED = original
        self.assertEqual(data["careers"][0]["modality"], "Online")
        self.assertEqual(data["course_rows"][0]["modality"], "Online")

    @patch("student_report_integration.filtered_projects", return_value={"summary": {"total": 2}})
    @patch("student_report_integration.report_completion._complexive_data", return_value={"totals": {"registered": 8}})
    @patch("student_report_integration.report_decoupled._nucleus_summary", return_value={"courses": 4})
    @patch("student_report_integration.report_completion.corrected_requirement_analysis", return_value={"total": 10})
    def test_methodology_describes_master_student_flow(self, _requirements, _nuclei, _complexive, _projects):
        paragraphs = integration._integrated_methodology_paragraphs(1, {"period": "Mayo - Noviembre 2026"})
        text = " ".join(paragraphs).casefold()
        self.assertIn("población maestra", text)
        self.assertIn("se concilian", text)
        self.assertNotIn("no generan relaciones automáticas", text)
        self.assertNotIn("cuatro componentes independientes", text)


if __name__ == "__main__":
    unittest.main()
