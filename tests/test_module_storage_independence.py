import json
import tempfile
import unittest
from pathlib import Path

import db
from import_service import ensure_schema
from process_service import ensure_process_schema
from requirements_store import commit_preview_to_report, ensure_requirements_schema
from thesis_independent import parse_project_text


class ModuleStorageIndependenceTests(unittest.TestCase):
    def setUp(self):
        self.original_data_dir = db.DATA_DIR
        self.original_db_path = db.DB_PATH
        self.temporary = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temporary.name)
        db.DB_PATH = db.DATA_DIR / "informtit.db"
        db.init_db()
        ensure_schema()
        ensure_process_schema()
        now = db.utcnow()
        with db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("Informe independiente", "Octubre 2025 - Marzo 2026", "presencial", now, now),
            )
            self.report_id = int(cursor.lastrowid)
            cursor = conn.execute(
                """
                INSERT INTO careers (report_id, name, sort_order, created_at)
                VALUES (?, 'ENFERMERÍA', 1, ?)
                """,
                (self.report_id, now),
            )
            self.career_id = int(cursor.lastrowid)
            conn.execute(
                """
                INSERT INTO students
                (career_id, full_name, email, ordinary_theory, ordinary_practical,
                 created_at, updated_at, imported_from_roster)
                VALUES (?, ?, ?, 88, 92, ?, ?, 0)
                """,
                (
                    self.career_id,
                    "ESTUDIANTE COMPLEXIVO",
                    "complexivo@itsqmet.edu.ec",
                    now,
                    now,
                ),
            )

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        self.temporary.cleanup()

    def _preview_token(self, name: str, identification: str) -> str:
        token = "token_independiente_12345"
        imports = db.DATA_DIR / "imports"
        imports.mkdir(parents=True, exist_ok=True)
        parsed = {
            "preview": {
                "filename": "requisitos.xls",
                "period": "Octubre 2025 - Marzo 2026",
            },
            "records": [
                {
                    "identification": identification,
                    "full_name": name,
                    "career_code": "ENF",
                    "career_name": "ENFERMERÍA",
                    "modality": "presencial",
                    "schedule": "Nocturna",
                    "academic_status": "CUMPLE",
                    "documentation_status": "CUMPLE",
                    "financial_status": "CUMPLE",
                    "titulation_status": "",
                    "practices_linkage_status": "CUMPLE",
                    "linkage_status": "CUMPLE",
                    "graduate_followup_status": "CUMPLE",
                    "english_status": "CUMPLE",
                    "data_update_status": "CUMPLE",
                    "personal_email": "",
                    "email": f"{identification}@itsqmet.edu.ec",
                    "phone": "",
                    "campus": "Quito",
                    "titulation_approval": "",
                    "complexive_approval": "",
                }
            ],
        }
        (imports / f"{token}.json").write_text(json.dumps(parsed), encoding="utf-8")
        return token

    def test_reimporting_requirements_does_not_touch_complexive(self):
        ensure_requirements_schema()
        token = self._preview_token("ESTUDIANTE REQUISITOS", "1717171717")
        result = commit_preview_to_report(token, self.report_id, {})
        self.assertEqual(result["students"], 1)

        with db.connection() as conn:
            complexive = conn.execute(
                "SELECT full_name, ordinary_theory, ordinary_practical FROM students WHERE career_id=?",
                (self.career_id,),
            ).fetchall()
            requirements = conn.execute(
                "SELECT full_name FROM requirements_students WHERE report_id=?",
                (self.report_id,),
            ).fetchall()
        self.assertEqual(len(complexive), 1)
        self.assertEqual(complexive[0]["full_name"], "ESTUDIANTE COMPLEXIVO")
        self.assertEqual(complexive[0]["ordinary_theory"], 88)
        self.assertEqual(complexive[0]["ordinary_practical"], 92)
        self.assertEqual([row["full_name"] for row in requirements], ["ESTUDIANTE REQUISITOS"])

    def test_thesis_can_be_saved_without_any_student_link(self):
        result = parse_project_text(
            self.report_id,
            {
                "identification": "1800000001",
                "full_name": "ESTUDIANTE TESIS",
                "career_name": "ENFERMERÍA",
                "text": "CALIFICACIÓN TUTOR: 9,00\nCALIFICACIÓN LECTOR: 8,50",
            },
        )
        self.assertTrue(result["ok"])
        with db.connection() as conn:
            project = conn.execute(
                "SELECT student_id, identification, full_name, career_name FROM thesis_projects WHERE id=?",
                (result["project_id"],),
            ).fetchone()
        self.assertIsNone(project["student_id"])
        self.assertEqual(project["identification"], "1800000001")
        self.assertEqual(project["full_name"], "ESTUDIANTE TESIS")
        self.assertEqual(project["career_name"], "ENFERMERÍA")


if __name__ == "__main__":
    unittest.main()
