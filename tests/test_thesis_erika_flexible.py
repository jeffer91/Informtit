import tempfile
import unittest
from pathlib import Path

import db
import import_service
from import_service import ensure_schema
from process_service import ensure_process_schema
import thesis_parser_flex
from thesis_independent import analyze_project_text


ERIKA_TEXT = """Nombres:\tCedula:\tCódigo de Carrera:\tCarrera:
GARCIA PALMA ERIKA TATIANA\t1311960064\t550413A02-L-1701\tTECNOLOGÍA SUPERIOR EN ADMINISTRACIÓN ONLINE

Informacion ProyectoMiembros ProyectoNotas Proyecto
VocalEvaluación Final Proyecto

TRABAJO ESCRITO PROYECTO DE TITULACIÓN
NÚMERO DE ACTA DE GRADO:\t4137
FECHA ACTA DE GRADO:
14/04/2026
CALIFICACIÓN TUTOR:\t8,00
CALIFICACIÓN LECTOR:\t8,00
PROMEDIO TRABAJO ESCRITO:\t8,00

DEFENSA DE PROYECTO
PARÁMETROS DE EVALUACIÓN\tPUNTAJE MÁXIMO\tPRIMER VOCAL
ESPINOZA PEREZ WILLAM RODRIGO\tSEGUNDO VOCAL
UQUILLAS ERAZO JORGE ROBERTO\tTERCER VOCAL
ZAMBRANO URGILEZ JOSE SEBASTIAN

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
1,00
1,00
1,00
7,00
7,00
7,00

1. PROMEDIO TRABAJO ESCRITO (Calf. Tutor + Calif. Lector):
8,00
2. PROMEDIO EVALUACION PRACTICA:
7,00
3. PROMEDIO EVALUACION DEFENSA:
7,00
4. PROMEDIO DEFENSA ORAL DEL PROYECTO DE TITULACION (2. + 3.):
7,00
5. CALIFICACION FINAL DEL PROYECTO DE TITULACION (1. + 4.):
7,6
"""


class ThesisErikaFlexibleParserTest(unittest.TestCase):
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
                ("Informe", "Octubre 2025 - Marzo 2026", "en_linea", now, now),
            )
            self.report_id = int(cursor.lastrowid)
        thesis_parser_flex.install()

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        import_service.DATA_DIR = self.original_import_data_dir
        self.temporary.cleanup()

    def test_online_code_and_career_are_detected(self):
        result = analyze_project_text(self.report_id, {"text": ERIKA_TEXT})
        self.assertTrue(result["ok"])
        project = result["projects"][0]
        self.assertEqual(project["full_name"], "GARCIA PALMA ERIKA TATIANA")
        self.assertEqual(project["identification"], "1311960064")
        self.assertEqual(project["career_code"], "550413A02-L-1701")
        self.assertEqual(project["career_name"], "TECNOLOGÍA SUPERIOR EN ADMINISTRACIÓN ONLINE")
        self.assertEqual(project["act_number"], "4137")
        self.assertEqual(project["act_date"], "14/04/2026")
        self.assertEqual(project["written_average"], 8.0)
        self.assertEqual(project["practical_average"], 7.0)
        self.assertEqual(project["defense_average"], 7.0)
        self.assertEqual(project["oral_average"], 7.0)
        self.assertEqual(project["final_grade"], 7.6)
        self.assertEqual(project["final_status"], "APROBADO")
        self.assertEqual(project["lowest_parameter"], "Solventar preguntas")
        self.assertFalse(project["validation"]["errors"])
        self.assertNotIn("No se detectó el código de carrera.", project["validation"]["warnings"])


if __name__ == "__main__":
    unittest.main()
