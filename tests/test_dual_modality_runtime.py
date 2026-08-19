import json
import tempfile
import unittest
from pathlib import Path

import db
import dual_modality_runtime as dual
import import_service
import requirements_store


class DualModalityRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.original_data_dir = db.DATA_DIR
        self.original_db_path = db.DB_PATH
        self.original_import_data_dir = import_service.DATA_DIR
        self.temporary = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temporary.name)
        db.DB_PATH = db.DATA_DIR / "informtit.db"
        import_service.DATA_DIR = db.DATA_DIR
        db.init_db()
        requirements_store.ensure_requirements_schema()

        now = db.utcnow()
        with db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, code, version, elaboration_date,
                 prepared_by, prepared_role, reviewed_by, reviewed_role,
                 approved_by, approved_role, status, created_at, updated_at)
                VALUES (?, ?, 'presencial', ?, '1.0', ?, '', '', '', '', '', '', 'borrador', ?, ?)
                """,
                (
                    "Informe Final del Proceso de Titulación",
                    "Octubre 2025 - Marzo 2026",
                    "UTET-INF-01-PRO-95-2025-08",
                    "2026-08-05",
                    now,
                    now,
                ),
            )
            self.report_id = int(cursor.lastrowid)

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        import_service.DATA_DIR = self.original_import_data_dir
        self.temporary.cleanup()

    def _record(self, name, career, code, modality):
        return {
            "identification": code[-10:],
            "full_name": name,
            "career_code": code,
            "career_name": career,
            "modality": modality,
            "schedule": "",
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
            "email": "",
            "phone": "",
            "campus": "Quito",
            "titulation_approval": "",
            "complexive_approval": "",
        }

    def _token(self):
        token = "dual_modal_token_123456"
        imports = import_service.DATA_DIR / "imports"
        imports.mkdir(parents=True, exist_ok=True)
        records = [
            self._record("PRESENCIAL UNO", "ENFERMERÍA", "560-P-1701-0001", "presencial"),
            self._record("ONLINE UNO", "REDES Y TELECOMUNICACIONES ONLINE", "560-L-1701-0002", "en_linea"),
        ]
        payload = {
            "preview": {
                "filename": "requisitos.xls",
                "period": "Octubre 2025 - Marzo 2026",
                "total": 2,
                "presencial": 1,
                "en_linea": 1,
            },
            "records": records,
        }
        (imports / f"{token}.json").write_text(json.dumps(payload), encoding="utf-8")
        return token

    def test_recognizes_en_linea_with_and_without_accent(self):
        self.assertEqual(dual._robust_modality("Pedagogía EN LÍNEA", "ABC"), "en_linea")
        self.assertEqual(dual._robust_modality("Pedagogia EN LINEA", "ABC"), "en_linea")
        self.assertEqual(dual._robust_modality("Redes", "560-L-1701"), "en_linea")
        self.assertEqual(dual._robust_modality("Enfermería", "560-P-1701"), "presencial")

    def test_one_import_creates_presencial_and_online_reports(self):
        result = dual.commit_preview_to_pair(self._token(), self.report_id, {})
        self.assertEqual(result["report_ids"]["presencial"], self.report_id)
        self.assertIn("en_linea", result["report_ids"])
        self.assertEqual(result["students"], 2)
        self.assertEqual(result["presencial"], 1)
        self.assertEqual(result["en_linea"], 1)

        online_id = result["report_ids"]["en_linea"]
        with db.connection() as conn:
            reports = conn.execute(
                "SELECT id, modality, source_import_id FROM reports ORDER BY id"
            ).fetchall()
            presencial_count = conn.execute(
                "SELECT COUNT(*) FROM requirements_students WHERE report_id=?",
                (self.report_id,),
            ).fetchone()[0]
            online_count = conn.execute(
                "SELECT COUNT(*) FROM requirements_students WHERE report_id=?",
                (online_id,),
            ).fetchone()[0]
        self.assertEqual(len(reports), 2)
        self.assertEqual({row["modality"] for row in reports}, {"presencial", "en_linea"})
        self.assertEqual(reports[0]["source_import_id"], reports[1]["source_import_id"])
        self.assertEqual(presencial_count, 1)
        self.assertEqual(online_count, 1)

    def test_reimport_reuses_existing_online_report(self):
        token = self._token()
        first = dual.commit_preview_to_pair(token, self.report_id, {})
        online_id = first["report_ids"]["en_linea"]
        second = dual.commit_preview_to_pair(token, self.report_id, {})
        self.assertEqual(second["report_ids"]["en_linea"], online_id)
        with db.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
