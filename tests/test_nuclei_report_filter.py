import unittest
from unittest.mock import patch

import nuclei_multicampus_report as report_filter


class NucleiReportFilterTests(unittest.TestCase):
    def test_report_keeps_every_student_loaded_in_each_nucleus_course(self):
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
                            "full_name": "ESTUDIANTE UNO",
                            "email": "uno@itsqmet.edu.ec",
                            "final_grade": 9.0,
                            "final_status": "Aprobado",
                            "scores": [{"grade": 8.0}, {"grade": 10.0}],
                        },
                        {
                            "full_name": "ESTUDIANTE DOS",
                            "email": "dos@itsqmet.edu.ec",
                            "final_grade": 5.0,
                            "final_status": "Reprobado",
                            "scores": [{"grade": 4.0}, {"grade": 6.0}],
                        },
                    ],
                },
                {
                    "id": 11,
                    "career_name": "Enfermería",
                    "campus": "Sur",
                    "nucleus_number": 2,
                    "assessments": [{"name": "Evaluación 1"}],
                    "activity_averages": [{"name": "Evaluación 1", "calculated_average": 6.0}],
                    "students": [
                        {
                            "full_name": "ESTUDIANTE TRES",
                            "email": "tres@itsqmet.edu.ec",
                            "final_grade": 6.0,
                            "final_status": "Reprobado",
                            "scores": [{"grade": 6.0}],
                        }
                    ],
                },
            ]
        }

        with patch.object(report_filter, "get_raw_nuclei", return_value=raw):
            result = report_filter.get_report_nuclei(99)

        self.assertEqual(len(result["courses"]), 2)
        first = result["courses"][0]
        self.assertEqual(
            [student["full_name"] for student in first["students"]],
            ["ESTUDIANTE UNO", "ESTUDIANTE DOS"],
        )
        self.assertEqual(first["graded_students"], 2)
        self.assertEqual(first["approved_count"], 1)
        self.assertEqual(first["failed_count"], 1)
        self.assertEqual(first["course_average"], 7.0)
        self.assertEqual(first["activity_averages"][0]["calculated_average"], 6.0)
        self.assertEqual(first["activity_averages"][1]["calculated_average"], 8.0)

        second = result["courses"][1]
        self.assertEqual(len(second["students"]), 1)
        self.assertEqual(second["failed_count"], 1)


if __name__ == "__main__":
    unittest.main()
