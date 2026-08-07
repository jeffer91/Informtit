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


def student(campus="Manta"):
    return {
        "id": 1,
        "identification": "1316499787",
        "full_name": "ROSA ELVIRA ANCHUNDIA VELIZ",
        "email": "ranchundia@itsqmet.edu.ec",
        "career_name": "Enfermería",
        "campus": campus,
        **PRE_REQS,
    }


def course(course_id, nucleus, campus, grade, teacher):
    return {
        "id": course_id,
        "career_name": "Enfermería",
        "campus": campus,
        "nucleus_number": nucleus,
        "module_code": str(10 + course_id),
        "group_code": "MEC-A",
        "teacher_name": teacher,
        "students": [
            {
                "full_name": "ROSA ELVIRA ANCHUNDIA VELIZ",
                "email": "ranchundia@itsqmet.edu.ec",
                "final_grade": grade,
            }
        ],
    }


class EligibilityMulticampusTests(unittest.TestCase):
    @patch("eligibility_service.get_projects", return_value={"projects": []})
    @patch("eligibility_service.get_nuclei")
    @patch("eligibility_service.get_report_roster")
    def test_course_from_other_campus_does_not_replace_students_real_campus(
        self, roster_mock, nuclei_mock, _projects_mock
    ):
        roster_mock.return_value = {"students": [student("Manta")]}
        nuclei_mock.return_value = {
            "courses": [
                course(1, 1, "Manta", 8.5, "DOCENTE MANTA"),
                course(2, 1, "Quito", 5.0, "DOCENTE QUITO"),
                course(3, 2, "Manta", 8.0, "DOCENTE MANTA"),
                course(4, 3, "Manta", 9.0, "DOCENTE MANTA"),
                course(5, 4, "Manta", 7.5, "DOCENTE MANTA"),
            ]
        }

        result = get_eligibility(1)
        row = result["rows"][0]
        self.assertEqual(row["nucleus_1"], 8.5)
        self.assertTrue(row["eligible_for_complexive"])
        self.assertEqual(row["stage_status"], "Habilitado para Complexivo")
        self.assertEqual(len(result["unmatched"]), 1)
        self.assertEqual(result["unmatched"][0]["campus"], "Quito")
        self.assertEqual(result["unmatched"][0]["reason"], "sede no coincide")

    @patch("eligibility_service.get_projects", return_value={"projects": []})
    @patch("eligibility_service.get_nuclei")
    @patch("eligibility_service.get_report_roster")
    def test_different_grades_for_same_nucleus_create_conflict_instead_of_overwrite(
        self, roster_mock, nuclei_mock, _projects_mock
    ):
        roster_mock.return_value = {"students": [student("")]}
        nuclei_mock.return_value = {
            "courses": [
                course(1, 1, "Manta", 8.5, "DOCENTE MANTA"),
                course(2, 1, "Quito", 6.0, "DOCENTE QUITO"),
                course(3, 2, "Manta", 8.0, "DOCENTE MANTA"),
                course(4, 3, "Manta", 9.0, "DOCENTE MANTA"),
                course(5, 4, "Manta", 7.5, "DOCENTE MANTA"),
            ]
        }

        result = get_eligibility(1)
        row = result["rows"][0]
        self.assertIsNone(row["nucleus_1"])
        self.assertFalse(row["eligible_for_complexive"])
        self.assertEqual(row["status"], "Conflicto")
        self.assertEqual(row["stage_status"], "Conflicto de notas de Núcleos")
        self.assertTrue(row["has_grade_conflict"])
        self.assertEqual(result["summary"]["grade_conflicts"], 1)
        self.assertEqual(len(result["grade_conflicts"]), 1)
        self.assertEqual(result["grade_conflicts"][0]["grades"], [6.0, 8.5])


if __name__ == "__main__":
    unittest.main()
