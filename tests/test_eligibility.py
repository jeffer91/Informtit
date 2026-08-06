import unittest
from unittest.mock import patch

from eligibility_service import get_eligibility


ROSTER = {
    "students": [
        {
            "id": 1,
            "identification": "111",
            "full_name": "ANA MARIA PEREZ",
            "email": "ana@itsqmet.edu.ec",
            "career_name": "ENFERMERÍA",
        },
        {
            "id": 2,
            "identification": "222",
            "full_name": "LUIS JOSE LOPEZ",
            "email": "luis@itsqmet.edu.ec",
            "career_name": "ENFERMERÍA",
        },
        {
            "id": 3,
            "identification": "333",
            "full_name": "MARIA PAZ VEGA",
            "email": "maria@itsqmet.edu.ec",
            "career_name": "ENFERMERÍA",
        },
    ]
}


def course(number, ana, luis, maria):
    return {
        "career_name": "Enfermería",
        "nucleus_number": number,
        "students": [
            {"full_name": "ANA MARIA PEREZ", "email": "ana@itsqmet.edu.ec", "final_grade": ana},
            {"full_name": "LUIS JOSE LOPEZ", "email": "luis@itsqmet.edu.ec", "final_grade": luis},
            {"full_name": "MARIA PAZ VEGA", "email": "maria@itsqmet.edu.ec", "final_grade": maria},
        ],
    }


NUCLEI = {
    "courses": [
        course(1, 8.0, 8.0, 9.0),
        course(2, 7.0, 6.5, 9.0),
        course(3, 9.0, 8.0, 9.0),
        course(4, 7.5, 8.0, 9.0),
    ]
}


class EligibilityTests(unittest.TestCase):
    @patch("eligibility_service.get_projects")
    @patch("eligibility_service.get_nuclei")
    @patch("eligibility_service.get_report_roster")
    def test_matches_students_and_requires_four_approved_nuclei(
        self,
        roster_mock,
        nuclei_mock,
        projects_mock,
    ):
        roster_mock.return_value = ROSTER
        nuclei_mock.return_value = NUCLEI
        projects_mock.return_value = {
            "projects": [
                {
                    "student_id": 3,
                    "identification": "333",
                    "full_name": "MARIA PAZ VEGA",
                    "career_name": "ENFERMERÍA",
                }
            ]
        }

        result = get_eligibility(1)
        rows = {row["student_id"]: row for row in result["rows"]}

        self.assertEqual(rows[1]["status"], "Habilitado")
        self.assertEqual(rows[1]["approved_nuclei"], 4)
        self.assertEqual(rows[2]["status"], "No habilitado")
        self.assertEqual(rows[2]["failed_nuclei"], 1)
        self.assertEqual(rows[3]["status"], "Trabajo de Titulación")
        self.assertEqual(result["summary"]["complexive_candidates"], 2)
        self.assertEqual(result["summary"]["habilitated"], 1)
        self.assertEqual(result["summary"]["not_habilitated"], 1)
        self.assertEqual(result["summary"]["thesis_students"], 1)

    @patch("eligibility_service.get_projects", return_value={"projects": []})
    @patch("eligibility_service.get_nuclei")
    @patch("eligibility_service.get_report_roster")
    def test_missing_nucleus_keeps_student_pending(
        self,
        roster_mock,
        nuclei_mock,
        _projects_mock,
    ):
        roster_mock.return_value = {"students": [ROSTER["students"][0]]}
        nuclei_mock.return_value = {"courses": NUCLEI["courses"][:3]}
        result = get_eligibility(1)
        self.assertEqual(result["rows"][0]["status"], "Pendiente")
        self.assertEqual(result["rows"][0]["missing_nuclei"], 1)


if __name__ == "__main__":
    unittest.main()
