import tempfile
import unittest
from pathlib import Path

import db
import reconciliation_reliability_runtime as reliability
import student_domain_bridge as bridge
import student_domain_service as domain
import student_final_audit as audit


class ReconciliationReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_data_dir = db.DATA_DIR
        self.original_db_path = db.DB_PATH
        db.DATA_DIR = Path(self.tempdir.name)
        db.DB_PATH = Path(self.tempdir.name) / "test.db"
        db.init_db()

        with db.connection() as conn:
            report_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
            if "period_project_id" not in report_columns:
                conn.execute("ALTER TABLE reports ADD COLUMN period_project_id INTEGER")
            conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, period_project_id, created_at, updated_at)
                VALUES ('Presencial', 'P', 'presencial', 77, 'x', 'x')
                """
            )
            self.report_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        domain.ensure_student_domain_schema()
        audit.ensure_schema()
        bridge.ensure_bridge_schema()

        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO period_students
                (period_project_id, report_id, identification, full_name, email,
                 career_name, modality, route, route_source, process_status,
                 requirements_present, created_at, updated_at)
                VALUES (77, ?, '1752222404', 'ALOMOTO PAZMIÑO BAYRON JAVIER',
                        'balomoto@itsqmet.edu.ec', 'DESARROLLO DE SOFTWARE', 'presencial',
                        'TRABAJO_TITULACION', 'MANUAL', 'ACTIVO', 1, 'x', 'x')
                """,
                (self.report_id,),
            )
            self.student_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

            conn.execute(
                "INSERT INTO careers (report_id, name, created_at) VALUES (?, 'DESARROLLO DE SOFTWARE', 'x')",
                (self.report_id,),
            )
            career_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.execute(
                """
                INSERT INTO students
                (career_id, full_name, email, created_at, updated_at, period_student_id)
                VALUES (?, 'ALOMOTO PAZMIÑO BAYRON JAVIER', 'balomoto@itsqmet.edu.ec',
                        'x', 'x', ?)
                """,
                (career_id, self.student_id),
            )
            raw = dict(conn.execute("SELECT s.*, c.name AS career_name FROM students s JOIN careers c ON c.id=s.career_id").fetchone())
            source_key = bridge._stable_source_key("COMPLEXIVE", raw)
            conn.execute(
                """
                INSERT INTO student_source_links
                (report_id, period_student_id, source_module, source_key, source_name,
                 source_email, source_identification, source_career, match_status,
                 match_method, match_confidence, candidates_json, detail, source_active,
                 created_at, updated_at)
                VALUES (?, ?, 'COMPLEXIVE', ?, ?, ?, '', ?, 'ROUTE_CONFLICT',
                        'CEDULA', 100, '[]', 'Conflicto de ruta', 1, 'x', 'x')
                """,
                (
                    self.report_id,
                    self.student_id,
                    source_key,
                    raw["full_name"],
                    raw["email"],
                    raw["career_name"],
                ),
            )
            self.link_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def test_unlink_complexive_clears_real_source_and_leaves_manual_review_barrier(self):
        result = reliability.unlink_period_source(77, self.link_id)
        self.assertTrue(result["ok"])
        self.assertEqual(result["module"], "COMPLEXIVE")
        self.assertEqual(result["unlinked_source_rows"], 1)

        with db.connection() as conn:
            link = conn.execute("SELECT * FROM student_source_links WHERE id=?", (self.link_id,)).fetchone()
            source = conn.execute("SELECT period_student_id FROM students").fetchone()

        self.assertIsNone(link["period_student_id"])
        self.assertEqual(link["match_status"], domain.MATCH_REVIEW)
        self.assertEqual(link["match_method"], "MANUAL_REVIEW")
        self.assertIsNone(source["period_student_id"])

        decision = audit._manual_review_decision(
            self.report_id,
            "COMPLEXIVE",
            link["source_key"],
            {
                "full_name": link["source_name"],
                "email": link["source_email"],
                "career_name": link["source_career"],
            },
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision["method"], "MANUAL_REVIEW")
        self.assertIsNone(decision["period_student_id"])

    def test_safe_start_returns_json_error_job_instead_of_raising_for_missing_project(self):
        job = reliability._safe_start_job(999999)
        self.assertEqual(job["status"], "error")
        self.assertIn("datasets", job["error"])
        self.assertEqual(job["progress"], 0)


if __name__ == "__main__":
    unittest.main()
