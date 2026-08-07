import tempfile
import unittest
from pathlib import Path

import db
import nuclei_multicampus
from nuclei_course_edit import update_course_metadata


class NucleiCourseEditTests(unittest.TestCase):
    def setUp(self):
        self.original_data_dir = db.DATA_DIR
        self.original_db_path = db.DB_PATH
        self.temporary = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temporary.name)
        db.DB_PATH = db.DATA_DIR / "informtit.db"
        db.init_db()
        nuclei_multicampus.ensure_multicampus_schema()
        now = db.utcnow()
        with db.connection() as conn:
            report = conn.execute(
                """
                INSERT INTO reports (name, period, modality, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("Informe", "Octubre 2025 - Marzo 2026", "presencial", now, now),
            )
            self.report_id = int(report.lastrowid)
            data = {
                "career_name": "Sin carrera",
                "nucleus_number": 1,
                "campus": "Matriz",
                "module_code": "11",
                "period_label": "OCT-MAR26",
                "group_code": "S-A",
                "schedule": "19h00-22h00",
                "course_title": "T- NUCLEO 1",
            }
            key = nuclei_multicampus._course_key(data)
            course = conn.execute(
                """
                INSERT INTO nucleus_course_instances
                (report_id, career_name, nucleus_number, campus, module_code, period_label,
                 group_code, schedule, course_key, course_title, teacher_name,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.report_id,
                    data["career_name"],
                    data["nucleus_number"],
                    data["campus"],
                    data["module_code"],
                    data["period_label"],
                    data["group_code"],
                    data["schedule"],
                    key,
                    data["course_title"],
                    "DOCENTE PENDIENTE",
                    now,
                    now,
                ),
            )
            self.course_id = int(course.lastrowid)
            conn.execute(
                """
                INSERT INTO nucleus_instance_students
                (course_id, full_name, email, final_grade, final_status, participant_found)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.course_id,
                    "ESTUDIANTE PRUEBA",
                    "estudiante@itsqmet.edu.ec",
                    8.75,
                    "Aprobado",
                    1,
                ),
            )

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        self.temporary.cleanup()

    def test_manual_edit_updates_metadata_without_touching_grades(self):
        result = update_course_metadata(
            self.report_id,
            self.course_id,
            {
                "career_name": "Enfermería",
                "nucleus_number": 1,
                "campus": "Sur",
                "teacher_name": "VIVIANA ALBINO",
            },
        )
        self.assertTrue(result["ok"])
        with db.connection() as conn:
            course = conn.execute(
                "SELECT career_name, nucleus_number, campus, teacher_name FROM nucleus_course_instances WHERE id=?",
                (self.course_id,),
            ).fetchone()
            student = conn.execute(
                "SELECT full_name, final_grade, final_status FROM nucleus_instance_students WHERE course_id=?",
                (self.course_id,),
            ).fetchone()
        self.assertEqual(course["career_name"], "Enfermería")
        self.assertEqual(course["nucleus_number"], 1)
        self.assertEqual(course["campus"], "Sur")
        self.assertEqual(course["teacher_name"], "VIVIANA ALBINO")
        self.assertEqual(student["full_name"], "ESTUDIANTE PRUEBA")
        self.assertEqual(student["final_grade"], 8.75)
        self.assertEqual(student["final_status"], "Aprobado")

    def test_rejects_sin_carrera_as_final_value(self):
        with self.assertRaisesRegex(ValueError, "carrera válida"):
            update_course_metadata(
                self.report_id,
                self.course_id,
                {"career_name": "Sin carrera", "nucleus_number": 1},
            )


if __name__ == "__main__":
    unittest.main()
