from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import db
import import_service
import period_policy_runtime
import period_unified_runtime as unified
import process_service
import requirements_store
import report_integrity_last_guard as last_guard


class PeriodUnifiedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.original_data_dir = db.DATA_DIR
        self.original_db_path = db.DB_PATH
        self.original_import_data_dir = import_service.DATA_DIR
        self.temporary = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temporary.name)
        db.DB_PATH = db.DATA_DIR / "informtit.db"
        import_service.DATA_DIR = db.DATA_DIR
        db.init_db()
        period_policy_runtime.ensure_schema()
        requirements_store.ensure_requirements_schema()
        process_service.ensure_process_schema()

        created = period_policy_runtime._create_manual_reports(
            {
                "name": "Informe Final del Proceso de Titulación",
                "period": "Octubre 2025 - Marzo 2026",
                "code": "UTET-INF-01-PRO-95-2025-08",
                "version": "1.0",
                "elaboration_date": "2026-08-24",
            }
        )
        self.presencial_id = int(created["report_ids"]["presencial"])
        self.online_id = int(created["report_ids"]["en_linea"])

        now = db.utcnow()
        with db.connection() as conn:
            base = {
                "identification": "1700000001",
                "full_name": "ESTUDIANTE PRESENCIAL",
                "career_code": "560-P-001",
                "career_name": "ENFERMERÍA",
                "modality": "presencial",
                "academic_status": "CUMPLE",
                "documentation_status": "CUMPLE",
                "financial_status": "CUMPLE",
                "practices_linkage_status": "CUMPLE",
                "linkage_status": "CUMPLE",
                "graduate_followup_status": "CUMPLE",
                "english_status": "CUMPLE",
                "data_update_status": "CUMPLE",
            }
            requirements_store._insert_requirement_record(conn, self.presencial_id, base, now)
            online = dict(base)
            online.update(
                identification="1700000002",
                full_name="ESTUDIANTE ONLINE",
                career_code="560-L-002",
                career_name="REDES Y TELECOMUNICACIONES ONLINE",
                modality="en_linea",
            )
            requirements_store._insert_requirement_record(conn, self.online_id, online, now)

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        import_service.DATA_DIR = self.original_import_data_dir
        self.temporary.cleanup()

    def test_explicit_pvc_can_use_same_calendar_months_as_regular(self):
        created = period_policy_runtime._create_manual_reports(
            {
                "name": "Informe PVC - Artículo Científico",
                "period": "Octubre 2025 - Marzo 2026",
                "report_type": "pvc",
                "code": "UTET-INF-PVC-01",
                "version": "1.0",
            }
        )
        self.assertEqual(created["report_type"], "pvc")
        self.assertEqual(set(created["report_ids"]), {"pvc"})
        pvc_id = int(created["report_ids"]["pvc"])
        with db.connection() as conn:
            row = conn.execute("SELECT report_type, modality FROM reports WHERE id=?", (pvc_id,)).fetchone()
        self.assertEqual(row["report_type"], "pvc")
        self.assertEqual(row["modality"], "presencial")

    def test_visible_projects_exposes_one_card_for_two_modalities(self):
        unified.reconcile_projects()
        projects = unified.visible_projects()
        self.assertEqual(len(projects), 1)
        project = projects[0]
        self.assertEqual(project["presencial_report_id"], self.presencial_id)
        self.assertEqual(project["online_report_id"], self.online_id)
        self.assertEqual(project["presencial_students"], 1)
        self.assertEqual(project["online_students"], 1)
        self.assertFalse(project["population_error"])

    def test_shared_general_updates_both_modality_datasets(self):
        unified.reconcile_projects()
        unified._sync_shared_general(
            self.presencial_id,
            {"code": "CODIGO-COMPARTIDO", "version": "2.0"},
        )
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT code, version FROM reports ORDER BY id"
            ).fetchall()
        self.assertEqual({row["code"] for row in rows}, {"CODIGO-COMPARTIDO"})
        self.assertEqual({row["version"] for row in rows}, {"2.0"})

    def test_shared_schedule_conciliates_both_datasets(self):
        unified.reconcile_projects()
        process_service.replace_schedule(
            self.presencial_id,
            "complexive",
            [{"activity": "Núcleo 1", "start_date": "2026-10-05", "end_date": "2026-10-08"}],
        )
        process_service.replace_schedule(
            self.online_id,
            "complexive",
            [{"activity": "Núcleo 2", "start_date": "2026-10-12", "end_date": "2026-10-15"}],
        )
        project_id = unified._project_for_report(self.presencial_id)["id"]
        unified.sync_project_schedule(int(project_id))
        with db.connection() as conn:
            presencial = conn.execute(
                "SELECT activity FROM schedule_items WHERE report_id=? AND schedule_type='complexive' ORDER BY activity",
                (self.presencial_id,),
            ).fetchall()
            online = conn.execute(
                "SELECT activity FROM schedule_items WHERE report_id=? AND schedule_type='complexive' ORDER BY activity",
                (self.online_id,),
            ).fetchall()
        self.assertEqual([row["activity"] for row in presencial], ["Núcleo 1", "Núcleo 2"])
        self.assertEqual([row["activity"] for row in online], ["Núcleo 1", "Núcleo 2"])

    def test_regular_import_rejects_missing_modality(self):
        token = "unified_missing_online_123"
        imports = import_service.DATA_DIR / "imports"
        imports.mkdir(parents=True, exist_ok=True)
        payload = {
            "preview": {"filename": "requisitos.xls", "period": "Octubre 2025 - Marzo 2026"},
            "records": [{"modality": "presencial", "full_name": "UNO"}],
        }
        (imports / f"{token}.json").write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Online"):
            unified.validate_dual_preview(token)

    def test_zero_population_is_import_error_not_no_population(self):
        mode = last_guard.source_mode_strict(
            {
                "requirements": {"registered": 0},
                "nuclei": {"records": 0},
                "complexive": {"registered": 0},
                "thesis": {"total": 0},
            },
            {"exists": True, "source_modality_count": 0},
        )
        self.assertEqual(mode, "import_error")


if __name__ == "__main__":
    unittest.main()
