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


class EligibilityCampusLabelsTests(unittest.TestCase):
    @patch("eligibility_service.get_projects", return_value={"projects": []})
    @patch("eligibility_service.get_nuclei")
    @patch("eligibility_service.get_report_roster")
    def test_unique_identity_is_not_blocked_by_different_campus_label(
        self,
        roster_mock,
        nuclei_mock,
        _projects_mock,
    ):
        roster_mock.return_value = {
            "students": [
                {
                    "id": 1,
                    "identification": "1314737477",
                    "full_name": "GEMA GISSELLA ARTEAGA CHANCAY",
                    "email": "garteaga@itsqmet.edu.ec",
                    "career_name": "ENFERMERÍA",
                    "campus": "Quito",
                    **PRE_REQS,
                }
            ]
        }
        nuclei_mock.return_value = {
            "courses": [
                {
                    "id": 20,
                    "career_name": "Enfermería",
                    "campus": "Sur",
                    "nucleus_number": 2,
                    "teacher_name": "VIVIANA LIZETH ALBINO ALBINO",
                    "students": [
                        {
                            "full_name": "GEMA GISSELLA ARTEAGA CHANCAY",
                            "email": "garteaga@itsqmet.edu.ec",
                            "final_grade": 10.0,
                        }
                    ],
                }
            ]
        }

        result = get_eligibility(1)

        self.assertEqual(result["course_matches"][0]["read_students"], 1)
        self.assertEqual(result["course_matches"][0]["matched_students"], 1)
        self.assertEqual(result["course_matches"][0]["unmatched_students"], 0)
        self.assertEqual(result["unmatched"], [])
        self.assertEqual(result["rows"][0]["nucleus_2"], 10.0)
        self.assertIn("correo", result["rows"][0]["match_methods"][2])


if __name__ == "__main__":
    unittest.main()
