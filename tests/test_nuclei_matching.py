import unittest
from unittest.mock import patch

from eligibility_service import get_eligibility


PRE_REQS = {
    "academic_status": "CUMPLE",
    "documentation_status": "CUMPLE",
    "english_status": "CUMPLE",
    "financial_status": "CUMPLE",
    "data_update_status": "CUMPLE",
    "graduate_followup_status": "CUMPLE",
    "practices_linkage_status": "CUMPLE",
    "linkage_status": "CUMPLE",
}


STUDENT = {
    "id": 1,
    "identification": "1314737477",
    "full_name": "GEMA GISSELLA ARTEAGA CHANCAY",
    "email": "garteaga@itsqmet.edu.ec",
    "career_name": "Enfermería",
    "campus": "Quito",
    **PRE_REQS,
}


def course(course_id, grade, email="garteaga@itsqmet.edu.ec", name="GEMA GISSELLA ARTEAGA CHANCAY"):
    return {
        "id": course_id,
        "career_name": "Enfermería",
        "campus": "Sur",
        "nucleus_number": 2,
        "teacher_name": "VIVIANA LIZETH ALBINO ALBINO",
        "students": [
            {
                "full_name": name,
                "email": email,
                "final_grade": grade,
            }
        ],
    }


class NucleiMatchingTests(unittest.TestCase):
    @patch("eligibility_service._load_grade_resolutions", return_value={})
    @patch("eligibility_service._load_manual_matches", return_value={"email:correo-mal@itsqmet.edu.ec": 1})
    @patch("eligibility_service.get_projects", return_value={"projects": []})
    @patch("eligibility_service.get_nuclei")
    @patch("eligibility_service.get_report_roster")
    def test_remembered_manual_match_registers_grade(
        self, roster_mock, nuclei_mock, _projects_mock, _manual_mock, _resolution_mock
    ):
        roster_mock.return_value = {"students": [STUDENT]}
        nuclei_mock.return_value = {
            "courses": [
                course(
                    20,
                    9.6,
                    email="correo-mal@itsqmet.edu.ec",
                    name="GEMA GISELA ARTEAGA CHANCAY",
                )
            ]
        }

        result = get_eligibility(1)
        row = result["rows"][0]
        self.assertEqual(row["nucleus_2"], 9.6)
        self.assertEqual(result["unmatched"], [])
        self.assertIn("asociación manual", row["match_methods"][2])

    @patch("eligibility_service._load_grade_resolutions", return_value={})
    @patch("eligibility_service._load_manual_matches", return_value={})
    @patch("eligibility_service.get_projects", return_value={"projects": []})
    @patch("eligibility_service.get_nuclei")
    @patch("eligibility_service.get_report_roster")
    def test_unmatched_record_proposes_best_enabled_candidate(
        self, roster_mock, nuclei_mock, _projects_mock, _manual_mock, _resolution_mock
    ):
        roster_mock.return_value = {"students": [STUDENT]}
        nuclei_mock.return_value = {
            "courses": [
                course(
                    20,
                    10.0,
                    email="gartegaa@itsqmet.edu.ec",
                    name="GEMA GISELA ARTEGA CHANCAY",
                )
            ]
        }

        result = get_eligibility(1)
        self.assertEqual(len(result["unmatched"]), 1)
        suggestions = result["unmatched"][0]["suggestions"]
        self.assertTrue(suggestions)
        self.assertEqual(suggestions[0]["student_id"], 1)
        self.assertGreater(suggestions[0]["similarity"], 80)

    @patch("eligibility_service._load_grade_resolutions", return_value={(1, 2): 9.0})
    @patch("eligibility_service._load_manual_matches", return_value={})
    @patch("eligibility_service.get_projects", return_value={"projects": []})
    @patch("eligibility_service.get_nuclei")
    @patch("eligibility_service.get_report_roster")
    def test_selected_grade_resolves_different_duplicate_values(
        self, roster_mock, nuclei_mock, _projects_mock, _manual_mock, _resolution_mock
    ):
        roster_mock.return_value = {"students": [STUDENT]}
        nuclei_mock.return_value = {
            "courses": [course(20, 8.5), course(21, 9.0)]
        }

        result = get_eligibility(1)
        row = result["rows"][0]
        self.assertEqual(row["nucleus_2"], 9.0)
        self.assertFalse(row["has_grade_conflict"])
        self.assertEqual(result["grade_conflicts"], [])
        self.assertEqual(len(result["resolved_grade_conflicts"]), 1)

    @patch("eligibility_service._load_grade_resolutions", return_value={})
    @patch("eligibility_service._load_manual_matches", return_value={})
    @patch("eligibility_service.get_projects", return_value={"projects": []})
    @patch("eligibility_service.get_nuclei")
    @patch("eligibility_service.get_report_roster")
    def test_equal_duplicate_grades_are_accepted_without_question(
        self, roster_mock, nuclei_mock, _projects_mock, _manual_mock, _resolution_mock
    ):
        roster_mock.return_value = {"students": [STUDENT]}
        nuclei_mock.return_value = {
            "courses": [course(20, 9.2), course(21, 9.2)]
        }

        result = get_eligibility(1)
        row = result["rows"][0]
        self.assertEqual(row["nucleus_2"], 9.2)
        self.assertEqual(result["grade_conflicts"], [])


if __name__ == "__main__":
    unittest.main()
