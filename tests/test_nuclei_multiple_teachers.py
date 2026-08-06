import tempfile
import unittest
from pathlib import Path

import db
import nuclei_fixes
from nuclei_service import get_nuclei, save_nucleus


PARTICIPANTS = """
ALUMNA PRUEBA\talumna@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
LIZETH POLETH GAVELA CONDE\tlgavela@itsqmet.edu.ec\tProfesor\tNo hay grupos\tSuspendido
"""


def grades(nucleus_number: int, final_grade: str) -> str:
    return f"""
T- NUCLEO {nucleus_number} ENFERMERIA [OCT-MAR26]
Nombre / Apellido(s)
Dirección de correo
CuestionarioEVALUACIÓN PARCIAL 1
Media de calificacionesTotal del curso
AP
ALUMNA PRUEBAMatriculación de usuarios suspendida
alumna@itsqmet.edu.ec
Aprobado {final_grade}
{final_grade}
Promedio general
{final_grade}
{final_grade}
"""


class MultipleNucleiTeacherTests(unittest.TestCase):
    def setUp(self):
        self.original_data_dir = db.DATA_DIR
        self.original_db_path = db.DB_PATH
        self.temporary = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temporary.name)
        db.DB_PATH = db.DATA_DIR / "informtit.db"
        db.init_db()
        nuclei_fixes.install()
        now = db.utcnow()
        with db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("Informe de prueba", "Octubre 2025 - Marzo 2026", "presencial", now, now),
            )
            self.report_id = int(cursor.lastrowid)

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        self.temporary.cleanup()

    def test_same_teacher_can_be_saved_in_multiple_nuclei(self):
        teacher = "LIZETH POLETH GAVELA CONDE"
        for nucleus_number, final_grade in ((1, "8,50"), (2, "9,20")):
            save_nucleus(
                self.report_id,
                {
                    "grades_text": grades(nucleus_number, final_grade),
                    "participants_text": PARTICIPANTS,
                    "teacher_name": teacher,
                },
            )

        courses = get_nuclei(self.report_id)["courses"]
        self.assertEqual(len(courses), 2)
        self.assertEqual([course["nucleus_number"] for course in courses], [1, 2])
        self.assertEqual({course["teacher_name"] for course in courses}, {teacher})


if __name__ == "__main__":
    unittest.main()
