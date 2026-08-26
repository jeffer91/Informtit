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


    def test_unlink_removes_positive_manual_decision_and_persists_veto(self):
        link = reliability._project_link(77, self.link_id)
        identity = reliability._identity_key_link(link)
        reliability._store_decision(
            77, "COMPLEXIVE", identity, reliability.DECISION_MATCH,
            target_student_id=self.student_id, decision_value=str(self.student_id),
        )
        reliability._unlink_project_case(77, self.link_id)
        self.assertEqual(
            reliability._manual_decisions(77, "COMPLEXIVE", identity, reliability.DECISION_MATCH),
            [],
        )
        blocked = reliability._blocked_targets(77, "COMPLEXIVE", identity)
        self.assertIn(self.student_id, blocked)

    def test_double_route_becomes_one_manual_case_and_choice_resolves_it(self):
        with db.connection() as conn:
            conn.execute(
                "UPDATE period_students SET route='COMPLEXIVO', route_source='DEFAULT' WHERE id=?",
                (self.student_id,),
            )
            conn.execute(
                """
                INSERT INTO thesis_projects
                (report_id, identification, full_name, career_name, final_grade,
                 final_status, created_at, updated_at, period_student_id)
                VALUES (?, '1752222404', 'ALOMOTO PAZMIÑO BAYRON JAVIER',
                        'DESARROLLO DE SOFTWARE', 8.4, 'APROBADO', 'x', 'x', ?)
                """,
                (self.report_id, self.student_id),
            )
            conn.execute(
                """
                INSERT INTO student_source_links
                (report_id, period_student_id, source_module, source_key, source_name,
                 source_email, source_identification, source_career, match_status,
                 match_method, match_confidence, candidates_json, detail, source_active,
                 created_at, updated_at)
                VALUES (?, ?, 'THESIS', 'thesis:id:1752222404',
                        'ALOMOTO PAZMIÑO BAYRON JAVIER', 'balomoto@itsqmet.edu.ec',
                        '1752222404', 'DESARROLLO DE SOFTWARE', 'OK',
                        'CEDULA', 100, '[]', '', 1, 'x', 'x')
                """,
                (self.report_id, self.student_id),
            )
        stats = reliability._normalize_routes(77)
        self.assertEqual(stats["route_conflicts"], 1)
        self.assertEqual(len(reliability._route_cases(77)), 1)

        result = reliability._set_route_manual_final(
            77, self.student_id, domain.ROUTE_THESIS
        )
        self.assertEqual(result["route_source"], "MANUAL")
        self.assertEqual(reliability._route_cases(77), [])
        with db.connection() as conn:
            methods = {
                row["source_module"]: row["match_method"]
                for row in conn.execute(
                    """
                    SELECT source_module, match_method FROM student_source_links
                    WHERE period_student_id=? AND source_module IN ('COMPLEXIVE','THESIS')
                    """,
                    (self.student_id,),
                ).fetchall()
            }
        self.assertEqual(methods["COMPLEXIVE"], "ROUTE_EXCLUDED_MANUAL")
        self.assertEqual(methods["THESIS"], "MANUAL_ROUTE_INCLUDED")

    def test_grade_conflict_requires_manual_choice_and_then_disappears(self):
        with db.connection() as conn:
            conn.execute(
                """
                UPDATE students
                SET ordinary_theory=80, ordinary_practical=80
                WHERE period_student_id=?
                """,
                (self.student_id,),
            )
            career_id = int(conn.execute("SELECT career_id FROM students LIMIT 1").fetchone()[0])
            conn.execute(
                """
                INSERT INTO students
                (career_id, full_name, email, ordinary_theory, ordinary_practical,
                 created_at, updated_at, period_student_id)
                VALUES (?, 'ALOMOTO PAZMIÑO BAYRON JAVIER', 'bayron.alt@itsqmet.edu.ec',
                        90, 90, 'x', 'x', ?)
                """,
                (career_id, self.student_id),
            )
        cases = [
            case for case in reliability._grade_cases(77)
            if case["source_module"] == "COMPLEXIVE"
        ]
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["grade_options"], [80.0, 90.0])

        reliability._resolve_grade_case(
            77, "COMPLEXIVE", self.student_id, 90
        )
        remaining = [
            case for case in reliability._grade_cases(77)
            if case["source_module"] == "COMPLEXIVE"
        ]
        self.assertEqual(remaining, [])


if __name__ == "__main__":
    unittest.main()
