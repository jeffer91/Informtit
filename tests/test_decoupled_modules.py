import unittest
from pathlib import Path
from unittest.mock import patch

import nuclei_multicampus_report


ROOT = Path(__file__).resolve().parents[1]


class DecoupledModulesTests(unittest.TestCase):
    def test_nuclei_report_keeps_all_course_students_without_roster_filter(self):
        data = {
            "courses": [
                {
                    "id": 1,
                    "career_name": "Enfermería",
                    "nucleus_number": 2,
                    "campus": "Sur",
                    "students": [
                        {"full_name": "ESTUDIANTE UNO", "email": "uno@itsqmet.edu.ec", "final_grade": 9.5, "scores": []},
                        {"full_name": "ESTUDIANTE DOS", "email": "dos@itsqmet.edu.ec", "final_grade": 8.0, "scores": []},
                    ],
                    "assessments": [],
                    "activity_averages": [],
                }
            ]
        }
        with patch("nuclei_multicampus_report.get_raw_nuclei", return_value=data):
            result = nuclei_multicampus_report.get_report_nuclei(1)
        self.assertEqual(len(result["courses"]), 1)
        self.assertEqual(len(result["courses"][0]["students"]), 2)
        self.assertEqual(result["courses"][0]["graded_students"], 2)
        self.assertEqual(result["courses"][0]["approved_count"], 2)

    def test_nuclei_ui_does_not_query_requirements_or_eligibility(self):
        source = (ROOT / "static" / "nuclei-ui.js").read_text(encoding="utf-8")
        self.assertNotIn("/nuclei/eligibility", source)
        self.assertNotIn("Habilitación para Complexivo", source)
        self.assertIn("Módulo independiente", source)

    def test_complexive_ui_no_longer_loads_workflow_filter(self):
        source = (ROOT / "static" / "completion-ui.js").read_text(encoding="utf-8")
        self.assertNotIn("workflow-ui.js", source)
        self.assertIn("data-complexive-eligibility-warning", source)

    def test_desktop_entry_does_not_install_cross_module_workflow(self):
        source = (ROOT / "desktop_entry.py").read_text(encoding="utf-8")
        self.assertIn("report_decoupled.install()", source)
        self.assertNotIn("workflow_report_runtime.install()", source)
        self.assertNotIn("workflow_report_fixes.install()", source)
        self.assertNotIn("nuclei_matching_routes.install()", source)
        self.assertNotIn("eligibility_runtime_fixes.install()", source)


if __name__ == "__main__":
    unittest.main()
