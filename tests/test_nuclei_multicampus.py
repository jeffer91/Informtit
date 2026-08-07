import tempfile
import unittest
from pathlib import Path

import db
import nuclei_fixes
from nuclei_multicampus import analyze_nucleus, get_nuclei, save_nucleus


PARTICIPANT_TEMPLATE = """
ESTUDIANTE PRUEBA\testudiante@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
{teacher}\t{teacher_email}\tProfesor\tNo hay grupos\tSuspendido
"""


def grades(campus: str, module: int, nucleus: int, final_grade: str) -> str:
    return f"""
T- NUCLEO {nucleus} ENFERMERIA [Mod {module}, OCT-MAR26 Esp. MEC-A {{ l m v s }} 19h00-22h00-{campus}]
Nombre / Apellido(s)
Dirección de correo
CuestionarioEVALUACIÓN PARCIAL 1
Media de calificacionesTotal del curso
EP
ESTUDIANTE PRUEBAMatriculación de usuarios suspendida
estudiante@itsqmet.edu.ec
Aprobado {final_grade}
{final_grade}
Promedio general
{final_grade}
{final_grade}
"""


class NucleiMulticampusTests(unittest.TestCase):
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
                ("Informe multicampus", "Octubre 2025 - Marzo 2026", "presencial", now, now),
            )
            self.report_id = int(cursor.lastrowid)

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        self.temporary.cleanup()

    def test_extracts_moodle_site_module_period_group_and_schedule(self):
        result = analyze_nucleus(
            {
                "grades_text": grades("Manta", 13, 3, "8,80"),
                "participants_text": PARTICIPANT_TEMPLATE.format(
                    teacher="JOICE MAYLIN SANCHEZ FRANCO",
                    teacher_email="jsanchezf@itsqmet.edu.ec",
                ),
            }
        )
        self.assertEqual(result["career_name"], "Enfermería")
        self.assertEqual(result["nucleus_number"], 3)
        self.assertEqual(result["campus"], "Manta")
        self.assertEqual(result["module_code"], "13")
        self.assertEqual(result["period_label"], "OCT-MAR26")
        self.assertEqual(result["group_code"], "MEC-A")
        self.assertEqual(result["schedule"], "19h00-22h00")
        self.assertEqual(result["teacher_name"], "JOICE MAYLIN SANCHEZ FRANCO")
        self.assertEqual(result["calculated_course_average"], 8.8)

    def test_same_career_and_nucleus_can_coexist_in_quito_and_manta(self):
        save_nucleus(
            self.report_id,
            {
                "grades_text": grades("Manta", 13, 3, "8,80"),
                "participants_text": PARTICIPANT_TEMPLATE.format(
                    teacher="JOICE MAYLIN SANCHEZ FRANCO",
                    teacher_email="jsanchezf@itsqmet.edu.ec",
                ),
            },
        )
        save_nucleus(
            self.report_id,
            {
                "grades_text": grades("Quito", 23, 3, "9,10"),
                "participants_text": PARTICIPANT_TEMPLATE.format(
                    teacher="DOCENTE QUITO",
                    teacher_email="docentequito@itsqmet.edu.ec",
                ),
            },
        )

        courses = get_nuclei(self.report_id)["courses"]
        self.assertEqual(len(courses), 2)
        self.assertEqual({course["campus"] for course in courses}, {"Manta", "Quito"})
        self.assertEqual({course["nucleus_number"] for course in courses}, {3})
        self.assertEqual(
            {course["teacher_name"] for course in courses},
            {"JOICE MAYLIN SANCHEZ FRANCO", "DOCENTE QUITO"},
        )

    def test_reimporting_same_moodle_course_updates_instead_of_duplicating(self):
        payload = {
            "grades_text": grades("Manta", 13, 3, "8,80"),
            "participants_text": PARTICIPANT_TEMPLATE.format(
                teacher="JOICE MAYLIN SANCHEZ FRANCO",
                teacher_email="jsanchezf@itsqmet.edu.ec",
            ),
        }
        first = save_nucleus(self.report_id, payload)
        payload["grades_text"] = grades("Manta", 13, 3, "9,00")
        second = save_nucleus(self.report_id, payload)

        courses = get_nuclei(self.report_id)["courses"]
        self.assertEqual(first["course_id"], second["course_id"])
        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["course_average"], 9.0)


if __name__ == "__main__":
    unittest.main()
