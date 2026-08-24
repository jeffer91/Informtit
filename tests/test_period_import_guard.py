from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import db
import dual_modality_runtime as dual
import import_service
import period_import_guard
import requirements_store


class PeriodImportGuardTests(unittest.TestCase):
    def setUp(self):
        self.original_data_dir = db.DATA_DIR
        self.original_db_path = db.DB_PATH
        self.original_import_data_dir = import_service.DATA_DIR
        self.temporary = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temporary.name)
        db.DB_PATH = db.DATA_DIR / "informtit.db"
        import_service.DATA_DIR = db.DATA_DIR
        db.init_db()
        import_service.ensure_schema()
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

    def _record(self, name: str, career: str, code: str, modality: str) -> dict[str, str]:
        return {
            "identification": code[-10:],
            "full_name": name,
            "career_code": code,
            "career_name": career,
            # Simula una previsualización antigua o incorrecta.
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

    def _token(self) -> str:
        token = "period_guard_token_123456"
        imports = import_service.DATA_DIR / "imports"
        imports.mkdir(parents=True, exist_ok=True)
        records = [
            self._record("PRESENCIAL UNO", "ADMINISTRACION", "550413A02-P-1701", "presencial"),
            self._record("ONLINE UNO", "ADMINISTRACION ONLINE", "550413A02-L-1701", "presencial"),
        ]
        payload = {
            "preview": {
                "filename": "requisitos.xls",
                "period": "Octubre 2025 - Marzo 2026",
                "total": 2,
                "presencial": 2,
                "en_linea": 0,
            },
            "records": records,
        }
        (imports / f"{token}.json").write_text(json.dumps(payload), encoding="utf-8")
        return token

    def test_validation_recalculates_online_from_code_and_name(self):
        counts = period_import_guard.validate_dual_preview(self._token())
        self.assertEqual(counts, {"presencial": 1, "en_linea": 1})

    def test_commit_reclassifies_stale_preview_and_persists_both_modalities(self):
        result = dual.commit_preview_to_pair(self._token(), self.report_id, {})
        self.assertEqual(result["presencial"], 1)
        self.assertEqual(result["en_linea"], 1)
        self.assertEqual(result["persisted_presencial"], 1)
        self.assertEqual(result["persisted_en_linea"], 1)

        online_id = result["report_ids"]["en_linea"]
        with db.connection() as conn:
            presencial = conn.execute(
                "SELECT COUNT(*) FROM requirements_students WHERE report_id=?",
                (self.report_id,),
            ).fetchone()[0]
            online = conn.execute(
                "SELECT COUNT(*) FROM requirements_students WHERE report_id=?",
                (online_id,),
            ).fetchone()[0]
        self.assertEqual(presencial, 1)
        self.assertEqual(online, 1)


if __name__ == "__main__":
    unittest.main()
