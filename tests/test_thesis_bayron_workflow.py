import tempfile
import unittest
from pathlib import Path

import db
import import_service
from import_service import ensure_schema
from process_service import ensure_process_schema
from thesis_independent import analyze_project_text, save_project_data


BAYRON_TEXT = """Nombres:\tCedula:\tCódigo de Carrera:\tCarrera:
ALOMOTO PAZMIÑO BAYRON JAVIER\t1752222404\t550613A01-P-1701\tTECNOLOGÍA SUPERIOR EN DESARROLLO DE SOFTWARE

TRABAJO ESCRITO PROYECTO DE TITULACIÓN
NÚMERO DE ACTA DE GRADO:\t4134
FECHA ACTA DE GRADO:
14/04/2026
CALIFICACIÓN TUTOR:\t9,00
CALIFICACIÓN LECTOR:\t9,00
PROMEDIO TRABAJO ESCRITO:\t9,00

DEFENSA DE PROYECTO
PARÁMETROS DE EVALUACIÓN\tPUNTAJE MÁXIMO\tPRIMER VOCAL
PAZMINO QUIÑONEZ JUAN CARLOS\tSEGUNDO VOCAL
NAVARRETE ARROYO PABLO STEVE\tTERCER VOCAL
ZAPATA YANEZ VERONICA MARCELA

EVALUACIÓN PRACTICA

Diseño\t2,5
2,00
2,00
2,00
Construcción\t2,5
2,00
2,00
2,00
Funcionamiento\t2,5
2,00
2,00
2,00
Aplicación\t2,5
1,00
1,00
1,00
7,00
7,00
7,00

EVALUACIÓN DE LA DEFENSA

Sustento del marco teórico\t2
2,00
2,00
2,00
Sustento de la propuesta\t2
2,00
2,00
2,00
Uso de recursos\t2
2,00
2,00
2,00
Solventar preguntas\t4
2,00
2,00
2,00
8,00
8,00
8,00

1. PROMEDIO TRABAJO ESCRITO (Calf. Tutor + Calif. Lector):
   9,00
2. PROMEDIO EVALUACION PRACTICA:
   7,00
3. PROMEDIO EVALUACION DEFENSA:
   8,00
4. PROMEDIO DEFENSA ORAL DEL PROYECTO DE TITULACION (2. + 3.):
   7,50
5. CALIFICACION FINAL DEL PROYECTO DE TITULACION (1. + 4.):
   8,4
"""


class ThesisBayronWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.original_data_dir = db.DATA_DIR
        self.original_db_path = db.DB_PATH
        self.original_import_data_dir = import_service.DATA_DIR
        self.temporary = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temporary.name)
        db.DB_PATH = db.DATA_DIR / "informtit.db"
        import_service.DATA_DIR = db.DATA_DIR
        db.init_db()
        ensure_schema()
        ensure_process_schema()
        now = db.utcnow()
        with db.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO reports (name, period, modality, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("Informe", "Octubre 2025 - Marzo 2026", "presencial", now, now),
            )
            self.report_id = int(cursor.lastrowid)

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        import_service.DATA_DIR = self.original_import_data_dir
        self.temporary.cleanup()

    def test_real_block_is_interpreted_and_calculated(self):
        result = analyze_project_text(self.report_id, {"text": BAYRON_TEXT})
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        project = result["projects"][0]
        self.assertEqual(project["identification"], "1752222404")
        self.assertEqual(project["full_name"], "ALOMOTO PAZMIÑO BAYRON JAVIER")
        self.assertEqual(project["career_code"], "550613A01-P-1701")
        self.assertEqual(project["career_name"], "TECNOLOGÍA SUPERIOR EN DESARROLLO DE SOFTWARE")
        self.assertEqual(project["act_number"], "4134")
        self.assertEqual(project["act_date"], "14/04/2026")
        self.assertEqual(project["tutor_grade"], 9.0)
        self.assertEqual(project["reader_grade"], 9.0)
        self.assertEqual(project["written_average"], 9.0)
        self.assertEqual(project["practical_vocal_totals"], [7.0, 7.0, 7.0])
        self.assertEqual(project["practical_average"], 7.0)
        self.assertEqual(project["defense_vocal_totals"], [8.0, 8.0, 8.0])
        self.assertEqual(project["defense_average"], 8.0)
        self.assertEqual(project["oral_average"], 7.5)
        self.assertEqual(project["final_grade"], 8.4)
        self.assertEqual(project["final_status"], "APROBADO")
        self.assertEqual(project["lowest_parameter"], "Aplicación")
        self.assertFalse(project["validation"]["errors"])

        saved = save_project_data(self.report_id, {"projects": [project]})
        self.assertEqual(saved["count"], 1)
        with db.connection() as conn:
            row = conn.execute(
                "SELECT identification, full_name, career_code, career_name, final_grade, final_status, lowest_parameter FROM thesis_projects WHERE report_id=?",
                (self.report_id,),
            ).fetchone()
        self.assertEqual(row["identification"], "1752222404")
        self.assertEqual(row["final_grade"], 8.4)
        self.assertEqual(row["final_status"], "APROBADO")
        self.assertEqual(row["lowest_parameter"], "Aplicación")


if __name__ == "__main__":
    unittest.main()
