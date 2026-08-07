import unittest
from unittest.mock import patch

import nuclei_multicampus_report as report_filter


class NucleiReportFilterTests(unittest.TestCase):
    def test_report_only_keeps_students_enabled_for_nuclei(self):
        raw = {
            "courses": [
                {
                    "id": 10,
                    "career_name": "Enfermería",
                    "campus": "Manta",
                    "nucleus_number": 1,
                    "assessments": [
                        {"name": "Evaluación 1"},
                        {"name": "Taller"},
                    ],
                    "activity_averages": [
                        {"name": "Evaluación 1", "calculated_average": 7.0},
                        {"name": "Taller", "calculated_average": 7.0},
                    ],
                    "students": [
                        {
                            "full_name": "ESTUDIANTE HABILITADA",
                            "email": "habilitada@itsqmet.edu.ec",
                            "final_grade": 9.0,
                            "final_status": "Aprobado",
                            "scores": [{"grade": 8.0}, {"grade": 10.0}],
                        },
                        {
                            "full_name": "ESTUDIANTE BLOQUEADA",
                            "email": "bloqueada@itsqmet.edu.ec",
                            "final_grade": 5.0,
                            "final_status": "Reprobado",
                            "scores": [{"grade": 4.0}, {"grade": 6.0}],
                        },
                    ],
                },
                {
                    "id": 11,
                    "career_name": "Enfermería",
                    "campus": "Manta",
                    "nucleus_number": 2,
                    "assessments": [{"name": "Evaluación 1"}],
                    "activity_averages": [{"name": "Evaluación 1", "calculated_average": 6.0}],
                    "students": [
                        {
                            "full_name": "OTRA BLOQUEADA",
                            "email": "otra@itsqmet.edu.ec",
                            "final_grade": 6.0,
                            "final_status": "Reprobado",
                            "scores": [{"grade": 6.0}],
                        }
                    ],
                },
            ]
        }
        eligibility = {
            "rows": [
                {
                    "student_id": 1,
                    "full_name": "ESTUDIANTE HABILITADA",
                    "email": "habilitada@itsqmet.edu.ec",
                    "career_name": "Enfermería",
                    "option": "Examen Complexivo",
                    "eligible_for_nuclei": True,
                    "nucleus_sources": {1: [{"course_id": 10, "grade": 9.0}]},
                },
                {
                    "student_id": 2,
                    "full_name": "ESTUDIANTE BLOQUEADA",
                    "email": "bloqueada@itsqmet.edu.ec",
                    "career_name": "Enfermería",
                    "option": "No habilitado para Núcleos",
                    "eligible_for_nuclei": False,
                    "nucleus_sources": {1: [{"course_id": 10, "grade": 5.0}]},
                },
                {
                    "student_id": 3,
                    "full_name": "OTRA BLOQUEADA",
                    "email": "otra@itsqmet.edu.ec",
                    "career_name": "Enfermería",
                    "option": "No habilitado para Núcleos",
                    "eligible_for_nuclei": False,
                    "nucleus_sources": {2: [{"course_id": 11, "grade": 6.0}]},
                },
            ]
        }

        with patch.object(report_filter, "get_raw_nuclei", return_value=raw), patch.object(
            report_filter, "get_eligibility", return_value=eligibility
        ):
            result = report_filter.get_report_nuclei(99)

        self.assertEqual(len(result["courses"]), 1)
        course = result["courses"][0]
        self.assertEqual(course["id"], 10)
        self.assertEqual([student["full_name"] for student in course["students"]], ["ESTUDIANTE HABILITADA"])
        self.assertEqual(course["graded_students"], 1)
        self.assertEqual(course["approved_count"], 1)
        self.assertEqual(course["failed_count"], 0)
        self.assertEqual(course["excluded_by_requirements"], 1)
        self.assertEqual(course["course_average"], 9.0)
        self.assertEqual(course["activity_averages"][0]["calculated_average"], 8.0)
        self.assertEqual(course["activity_averages"][1]["calculated_average"], 10.0)


if __name__ == "__main__":
    unittest.main()
