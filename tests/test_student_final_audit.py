import tempfile
import unittest
from pathlib import Path

import db
import requirements_store
import student_domain_service as domain
import student_final_audit as audit


class StudentFinalAuditTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_data_dir = db.DATA_DIR
        self.original_db_path = db.DB_PATH
        db.DATA_DIR = Path(self.tempdir.name)
        db.DB_PATH = Path(self.tempdir.name) / "audit.db"
        db.init_db()
        requirements_store.ensure_requirements_schema()
        with db.connection() as conn:
            # En escritorio period_policy_runtime.ensure_schema() crea esta columna
            # antes de instalar el dominio maestro. La prueba reproduce ese contrato.
            if "period_project_id" not in {
                str(row[1]) for row in conn.execute("PRAGMA table_info(reports)").fetchall()
            }:
                conn.execute("ALTER TABLE reports ADD COLUMN period_project_id INTEGER")
            conn.execute(
                """
                INSERT INTO reports (name, period, modality, created_at, updated_at)
                VALUES ('Auditoría', 'P', 'presencial', 'x', 'x')
                """
            )
            self.report_id = int(conn.execute("SELECT id FROM reports").fetchone()[0])
        audit.ensure_schema()

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def _insert_requirement(self, identification="1717171717", email="ana@itsqmet.edu.ec", **overrides):
        values = {
            "full_name": "ANA PEREZ",
            "career_code": "ENF-P-01",
            "career_name": "ENFERMERIA",
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
            "phone": "",
            "campus": "Norte",
            "titulation_approval": "",
            "complexive_approval": "",
            **overrides,
        }
        with db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO requirements_students
                (report_id, identification, full_name, career_code, career_name, modality, schedule,
                 academic_status, documentation_status, financial_status, titulation_status,
                 practices_linkage_status, linkage_status, graduate_followup_status, english_status,
                 data_update_status, personal_email, email, phone, campus, titulation_approval,
                 complexive_approval, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'x', 'x')
                """,
                (
                    self.report_id,
                    identification,
                    values["full_name"],
                    values["career_code"],
                    values["career_name"],
                    values["modality"],
                    values["schedule"],
                    values["academic_status"],
                    values["documentation_status"],
                    values["financial_status"],
                    values["titulation_status"],
                    values["practices_linkage_status"],
                    values["linkage_status"],
                    values["graduate_followup_status"],
                    values["english_status"],
                    values["data_update_status"],
                    values["personal_email"],
                    email,
                    values["phone"],
                    values["campus"],
                    values["titulation_approval"],
                    values["complexive_approval"],
                ),
            )
            return int(cursor.lastrowid)

    def test_exact_homonyms_are_ambiguous_not_auto_linked(self):
        students = [
            {
                "id": 1,
                "identification": "1111111111",
                "full_name": "ANA MARIA PEREZ LOPEZ",
                "email": "",
                "career_name": "ENFERMERIA",
                "requirements_present": 1,
            },
            {
                "id": 2,
                "identification": "2222222222",
                "full_name": "LOPEZ ANA MARIA PEREZ",
                "email": "",
                "career_name": "ENFERMERIA",
                "requirements_present": 1,
            },
        ]
        token = audit._MATCH_CACHE.set(students)
        try:
            result = audit.match_source_record(
                1,
                "NUCLEI",
                "x",
                {"full_name": "ANA MARIA PEREZ LOPEZ", "career_name": "ENFERMERIA"},
                persist=False,
            )
        finally:
            audit._MATCH_CACHE.reset(token)
        self.assertEqual(result["status"], domain.MATCH_AMBIGUOUS)
        self.assertIsNone(result["period_student_id"])

    def test_conflicting_cedula_and_email_never_auto_link(self):
        students = [
            {
                "id": 1,
                "identification": "1111111111",
                "full_name": "ANA PEREZ",
                "email": "ana@itsqmet.edu.ec",
                "career_name": "ENFERMERIA",
                "requirements_present": 1,
            },
            {
                "id": 2,
                "identification": "2222222222",
                "full_name": "BEA LOPEZ",
                "email": "bea@itsqmet.edu.ec",
                "career_name": "ENFERMERIA",
                "requirements_present": 1,
            },
        ]
        token = audit._MATCH_CACHE.set(students)
        try:
            result = audit.match_source_record(
                1,
                "COMPLEXIVE",
                "x",
                {
                    "identification": "1111111111",
                    "email": "bea@itsqmet.edu.ec",
                    "full_name": "ANA PEREZ",
                    "career_name": "ENFERMERIA",
                },
                persist=False,
            )
        finally:
            audit._MATCH_CACHE.reset(token)
        self.assertEqual(result["status"], audit.MATCH_IDENTITY_CONFLICT)
        self.assertIsNone(result["period_student_id"])

    def test_synthetic_keys_are_not_exposed_as_cedulas(self):
        self.assertEqual(audit._public_identification("NOID:EMAIL:ana@example.com"), "")
        self.assertEqual(audit._public_identification("REQ-88"), "")
        self.assertEqual(audit._public_identification("1717171717"), "1717171717")

    def test_identity_survives_when_official_cedula_is_added_later(self):
        self._insert_requirement(identification="", email="ana@itsqmet.edu.ec")
        audit.sync_report_students(self.report_id)
        with db.connection() as conn:
            first = conn.execute(
                "SELECT id, identification FROM period_students WHERE report_id=?",
                (self.report_id,),
            ).fetchone()
        self.assertTrue(str(first["identification"]).startswith("NOID:EMAIL:"))
        domain.set_student_route(self.report_id, int(first["id"]), domain.ROUTE_THESIS)

        with db.connection() as conn:
            conn.execute("DELETE FROM requirements_students WHERE report_id=?", (self.report_id,))
        self._insert_requirement(identification="1717171717", email="ana@itsqmet.edu.ec")
        audit.sync_report_students(self.report_id)

        with db.connection() as conn:
            rows = conn.execute(
                "SELECT id, identification, route, route_source FROM period_students WHERE report_id=?",
                (self.report_id,),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], first["id"])
        self.assertEqual(rows[0]["identification"], "1717171717")
        self.assertEqual(rows[0]["route"], domain.ROUTE_THESIS)
        self.assertEqual(rows[0]["route_source"], "MANUAL")

    def test_removed_requirement_is_marked_absent_and_cannot_enter_report(self):
        self._insert_requirement()
        audit.sync_report_students(self.report_id)
        with db.connection() as conn:
            row = dict(
                conn.execute(
                    "SELECT * FROM period_students WHERE report_id=?",
                    (self.report_id,),
                ).fetchone()
            )
        self.assertEqual(row["requirements_present"], 1)
        self.assertTrue(audit._active_for_route(row, domain.ROUTE_COMPLEXIVE))

        with db.connection() as conn:
            conn.execute("DELETE FROM requirements_students WHERE report_id=?", (self.report_id,))
        audit.sync_report_students(self.report_id)
        with db.connection() as conn:
            row = dict(
                conn.execute(
                    "SELECT * FROM period_students WHERE report_id=?",
                    (self.report_id,),
                ).fetchone()
            )
        self.assertEqual(row["requirements_present"], 0)
        self.assertEqual(row["reconciliation_status"], domain.MATCH_REVIEW)
        self.assertFalse(audit._active_for_route(row, domain.ROUTE_COMPLEXIVE))

    def test_duplicate_requirements_are_flagged_and_excluded(self):
        self._insert_requirement(identification="9999999999", email="uno@itsqmet.edu.ec")
        self._insert_requirement(identification="9999999999", email="dos@itsqmet.edu.ec")
        audit.sync_report_students(self.report_id)
        with db.connection() as conn:
            row = dict(
                conn.execute(
                    "SELECT * FROM period_students WHERE report_id=? AND identification='9999999999'",
                    (self.report_id,),
                ).fetchone()
            )
        self.assertEqual(row["reconciliation_status"], audit.MATCH_DUPLICATE)
        self.assertFalse(audit._active_for_route(row, domain.ROUTE_COMPLEXIVE))

    def test_stale_source_links_are_deactivated_without_deleting_history(self):
        with db.connection() as conn:
            now = db.utcnow()
            conn.execute(
                """
                INSERT INTO student_source_links
                (report_id, source_module, source_key, source_name, match_status,
                 candidates_json, created_at, updated_at, source_active)
                VALUES (?, 'NUCLEI', 'current', 'ANA', 'UNMATCHED', '[]', ?, ?, 1)
                """,
                (self.report_id, now, now),
            )
            conn.execute(
                """
                INSERT INTO student_source_links
                (report_id, source_module, source_key, source_name, match_status,
                 candidates_json, created_at, updated_at, source_active)
                VALUES (?, 'NUCLEI', 'stale', 'BEA', 'UNMATCHED', '[]', ?, ?, 1)
                """,
                (self.report_id, now, now),
            )
        audit._mark_current_source_keys(self.report_id, "NUCLEI", {"current"})
        with db.connection() as conn:
            values = {
                row["source_key"]: row["source_active"]
                for row in conn.execute(
                    "SELECT source_key, source_active FROM student_source_links WHERE report_id=?",
                    (self.report_id,),
                ).fetchall()
            }
        self.assertEqual(values["current"], 1)
        self.assertEqual(values["stale"], 0)

    def test_same_cedula_in_presencial_and_online_is_a_modality_conflict(self):
        with db.connection() as conn:
            if "period_project_id" not in {
                str(row[1]) for row in conn.execute("PRAGMA table_info(reports)").fetchall()
            }:
                conn.execute("ALTER TABLE reports ADD COLUMN period_project_id INTEGER")
            conn.execute(
                "UPDATE reports SET period_project_id=77 WHERE id=?",
                (self.report_id,),
            )
            conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, created_at, updated_at, period_project_id)
                VALUES ('Online', 'P', 'en_linea', 'x', 'x', 77)
                """
            )
            online_report = int(conn.execute("SELECT max(id) FROM reports").fetchone()[0])
            now = db.utcnow()
            conn.execute(
                """
                INSERT INTO period_students
                (period_project_id, report_id, requirements_student_id, identification, full_name,
                 modality, route, route_source, process_status, process_status_source,
                 reconciliation_status, requirements_present, modality_conflict,
                 created_at, updated_at)
                VALUES (77, ?, 1, '1234567890', 'ANA', 'presencial', 'COMPLEXIVO',
                        'DEFAULT', 'ACTIVO', 'DERIVED', 'OK', 1, 0, ?, ?)
                """,
                (self.report_id, now, now),
            )
            conn.execute(
                """
                INSERT INTO period_students
                (period_project_id, report_id, requirements_student_id, identification, full_name,
                 modality, route, route_source, process_status, process_status_source,
                 reconciliation_status, requirements_present, modality_conflict,
                 created_at, updated_at)
                VALUES (77, ?, 2, '1234567890', 'ANA', 'en_linea', 'COMPLEXIVO',
                        'DEFAULT', 'ACTIVO', 'DERIVED', 'OK', 1, 0, ?, ?)
                """,
                (online_report, now, now),
            )
        conflict_ids = audit._refresh_modality_conflicts(77)
        self.assertEqual(len(conflict_ids), 2)
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT reconciliation_status, modality_conflict FROM period_students WHERE period_project_id=77"
            ).fetchall()
        self.assertTrue(all(row["reconciliation_status"] == audit.MATCH_MODALITY_CONFLICT for row in rows))
        self.assertTrue(all(row["modality_conflict"] == 1 for row in rows))

    def test_reconciliation_priority_surfaces_identity_conflict(self):
        row = {
            "reconciliation_status": domain.MATCH_REVIEW,
            "reconciliation_detail": "base",
            "source_links": [
                {
                    "source_active": 1,
                    "match_status": audit.MATCH_IDENTITY_CONFLICT,
                    "detail": "cédula y correo no coinciden",
                }
            ],
            "route": domain.ROUTE_COMPLEXIVE,
            "process_status": domain.PROCESS_ACTIVE,
            "nuclei": [],
            "complexive": [],
            "thesis": [],
        }
        status, detail = audit._effective_reconciliation(row)
        self.assertEqual(status, audit.MATCH_IDENTITY_CONFLICT)
        self.assertIn("cédula", detail)


if __name__ == "__main__":
    unittest.main()
