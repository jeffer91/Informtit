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

    def test_requirements_use_their_own_table(self):
        source = (ROOT / "requirements_store.py").read_text(encoding="utf-8")
        roster = (ROOT / "roster_service.py").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS requirements_students", source)
        self.assertIn("DELETE FROM requirements_students WHERE report_id=?", source)
        self.assertNotIn("DELETE FROM careers", source)
        self.assertNotIn("DELETE FROM students", source)
        self.assertIn("requirements_store", roster)

    def test_complexive_ui_does_not_load_workflow_filter(self):
        loader = (ROOT / "static" / "completion-ui.js").read_text(encoding="utf-8")
        completion = (ROOT / "static" / "completion-ui-v2.js").read_text(encoding="utf-8")
        routes = (ROOT / "completion_routes.py").read_text(encoding="utf-8")
        self.assertNotIn("workflow-ui.js", loader)
        self.assertNotIn("/nuclei/eligibility", completion)
        self.assertNotIn("Habilitación para el Examen Complexivo", completion)
        self.assertNotIn("/nuclei/eligibility", routes)

    def test_thesis_ui_does_not_query_roster(self):
        source = (ROOT / "static" / "process-independent-ui.js").read_text(encoding="utf-8")
        search = (ROOT / "static" / "project-search.js").read_text(encoding="utf-8")
        backend = (ROOT / "thesis_independent.py").read_text(encoding="utf-8")
        self.assertNotIn("/roster", source)
        self.assertNotIn("/roster", search)
        self.assertNotIn("student_id", source)
        self.assertIn("student_id=NULL", backend)
        self.assertNotIn("FROM students", backend)

    def test_independent_ui_updates_are_idempotent_and_batched(self):
        source = (ROOT / "static" / "independent-modules-ui.js").read_text(encoding="utf-8")
        self.assertIn("requestAnimationFrame", source)
        self.assertIn("if (node && node.textContent !== value)", source)
        self.assertIn("if (scanQueued) return", source)
        self.assertIn("if (scanning) return", source)
        self.assertNotIn("if (heading) heading.textContent", source)
        self.assertNotIn("description.innerHTML =", source)

    def test_desktop_entry_does_not_install_cross_module_workflow(self):
        source = (ROOT / "desktop_entry.py").read_text(encoding="utf-8")
        self.assertIn("report_decoupled.install()", source)
        self.assertNotIn("workflow_report_runtime.install()", source)
        self.assertNotIn("workflow_report_fixes.install()", source)
        self.assertNotIn("nuclei_matching_routes.install()", source)
        self.assertNotIn("eligibility_runtime_fixes.install()", source)


if __name__ == "__main__":
    unittest.main()
