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


def roster_student(student_id, identification, full_name, email, **extra):
    return {
        "id": student_id,
        "identification": identification,
        "full_name": full_name,
        "email": email,
        "career_name": "ENFERMERÍA",
        **PRE_REQS,
        **extra,
    }


ROSTER = {
    "students": [
        roster_student(1, "111", "ANA MARIA PEREZ", "ana@itsqmet.edu.ec"),
        roster_student(2, "222", "LUIS JOSE LOPEZ", "luis@itsqmet.edu.ec"),
        roster_student(3, "333", "MARIA PAZ VEGA", "maria@itsqmet.edu.ec"),
    ]
}


def course(number, ana, luis, maria):
    return {
        "id": number,
        "career_name": "Enfermería",
        "nucleus_number": number,
        "teacher_name": "DOCENTE DE PRUEBA",
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
        self.assertEqual(rows[1]["stage_status"], "Habilitado para Complexivo")
        self.assertTrue(rows[1]["eligible_for_complexive"])
        self.assertEqual(rows[1]["approved_nuclei"], 4)
        self.assertEqual(rows[2]["status"], "No habilitado")
        self.assertEqual(rows[2]["stage_status"], "Núcleos reprobados")
        self.assertEqual(rows[2]["failed_nuclei"], 1)
        self.assertEqual(rows[3]["status"], "Trabajo de Titulación")
        self.assertEqual(result["summary"]["complexive_candidates"], 2)
        self.assertEqual(result["summary"]["eligible_for_complexive"], 1)
        self.assertEqual(result["summary"]["habilitated"], 1)
        self.assertEqual(result["summary"]["not_habilitated"], 1)
        self.assertEqual(result["summary"]["thesis_students"], 1)
        self.assertEqual(len(result["course_matches"]), 4)
        self.assertTrue(all(item["read_students"] == 3 for item in result["course_matches"]))
        # El estudiante de Trabajo de Titulación no recibe notas de Núcleos.
        self.assertTrue(all(item["matched_students"] == 2 for item in result["course_matches"]))
        self.assertTrue(all(item["unmatched_students"] == 1 for item in result["course_matches"]))

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
        self.assertEqual(result["rows"][0]["stage_status"], "En Núcleos / pendiente")
        self.assertEqual(result["rows"][0]["missing_nuclei"], 1)

    @patch("eligibility_service.get_projects", return_value={"projects": []})
    @patch("eligibility_service.get_nuclei")
    @patch("eligibility_service.get_report_roster")
    def test_reports_course_students_without_roster_match(
        self,
        roster_mock,
        nuclei_mock,
        _projects_mock,
    ):
        roster_mock.return_value = {"students": [ROSTER["students"][0]]}
        nuclei_mock.return_value = {"courses": [NUCLEI["courses"][0]]}
        result = get_eligibility(1)
        self.assertEqual(result["course_matches"][0]["read_students"], 3)
        self.assertEqual(result["course_matches"][0]["matched_students"], 1)
        self.assertEqual(result["course_matches"][0]["unmatched_students"], 2)
        self.assertEqual(len(result["unmatched"]), 2)

    @patch("eligibility_service.get_projects", return_value={"projects": []})
    @patch("eligibility_service.get_nuclei")
    @patch("eligibility_service.get_report_roster")
    def test_student_without_prerequisites_never_enters_complexive_list(
        self,
        roster_mock,
        nuclei_mock,
        _projects_mock,
    ):
        blocked = roster_student(
            10,
            "1010",
            "ESTUDIANTE BLOQUEADO",
            "bloqueado@itsqmet.edu.ec",
            financial_status="NO CUMPLE",
            titulation_status="CUMPLE",
            complexive_approval="CUMPLE",
            titulation_approval="CUMPLE",
        )
        roster_mock.return_value = {"students": [blocked]}
        nuclei_mock.return_value = {
            "courses": [
                {
                    "id": 99,
                    "career_name": "Enfermería",
                    "nucleus_number": 1,
                    "teacher_name": "DOCENTE",
                    "students": [
                        {
                            "full_name": "ESTUDIANTE BLOQUEADO",
                            "email": "bloqueado@itsqmet.edu.ec",
                            "final_grade": 9.5,
                        }
                    ],
                }
            ]
        }

        result = get_eligibility(1)
        row = result["rows"][0]
        self.assertFalse(row["eligible_for_nuclei"])
        self.assertFalse(row["eligible_for_complexive"])
        self.assertEqual(row["option"], "No habilitado para Núcleos")
        self.assertEqual(row["stage_status"], "No habilitado para Núcleos")
        self.assertIn("Financiero", row["missing_requirements"])
        self.assertEqual(result["summary"]["complexive_candidates"], 0)
        self.assertEqual(result["summary"]["blocked_before_nuclei"], 1)
        self.assertEqual(result["summary"]["nucleus_without_prerequisites"], 1)
        # Los tres campos posteriores no pueden saltarse la etapa de requisitos.
        self.assertTrue(row["titulation_marked"])
        self.assertTrue(row["complexive_project_approved"])
        self.assertTrue(row["titles_uploaded"])


if __name__ == "__main__":
    unittest.main()
