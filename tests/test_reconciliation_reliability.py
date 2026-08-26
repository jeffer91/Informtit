import tempfile
import unittest
from pathlib import Path

import db
import reconciliation_reliability_runtime as reliability
import student_domain_bridge as bridge
import student_domain_service as domain
import student_final_audit as audit
import requirements_store


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

    def test_nuclei_counts_as_complexive_route_evidence(self):
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO student_source_links
                (report_id, period_student_id, source_module, source_key, source_name,
                 source_email, source_identification, source_career, match_status,
                 match_method, match_confidence, candidates_json, detail, source_active,
                 created_at, updated_at)
                VALUES (?, ?, 'NUCLEI', 'nuclei:test-route',
                        'ALOMOTO PAZMIÑO BAYRON JAVIER', '',
                        '1752222404', 'DESARROLLO DE SOFTWARE', 'OK',
                        'CEDULA', 100, '[]', '', 1, 'x', 'x')
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
                VALUES (?, ?, 'THESIS', 'thesis:test-route',
                        'ALOMOTO PAZMIÑO BAYRON JAVIER', '',
                        '1752222404', 'DESARROLLO DE SOFTWARE', 'OK',
                        'CEDULA', 100, '[]', '', 1, 'x', 'x')
                """,
                (self.report_id, self.student_id),
            )
            conn.execute(
                "UPDATE period_students SET route='COMPLEXIVO', route_source='DEFAULT' WHERE id=?",
                (self.student_id,),
            )

        stats = reliability._normalize_routes(77)
        self.assertEqual(stats["route_conflicts"], 1)
        cases = reliability._route_cases(77)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["match_status"], domain.MATCH_ROUTE_CONFLICT)


    def test_manual_thesis_route_excludes_nuclei_without_leaving_route_conflict(self):
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO student_source_links
                (report_id, period_student_id, source_module, source_key, source_name,
                 source_email, source_identification, source_career, match_status,
                 match_method, match_confidence, candidates_json, detail, source_active,
                 created_at, updated_at)
                VALUES (?, ?, 'NUCLEI', 'nuclei:manual-route',
                        'ALOMOTO PAZMIÑO BAYRON JAVIER', '',
                        '1752222404', 'DESARROLLO DE SOFTWARE', 'ROUTE_CONFLICT',
                        'CEDULA', 100, '[]', 'Conflicto de ruta', 1, 'x', 'x')
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
                VALUES (?, ?, 'THESIS', 'thesis:manual-route',
                        'ALOMOTO PAZMIÑO BAYRON JAVIER', '',
                        '1752222404', 'DESARROLLO DE SOFTWARE', 'OK',
                        'CEDULA', 100, '[]', '', 1, 'x', 'x')
                """,
                (self.report_id, self.student_id),
            )

        reliability._set_route_manual_final(
            77, self.student_id, domain.ROUTE_THESIS
        )
        with db.connection() as conn:
            nuclei = conn.execute(
                """
                SELECT match_status, match_method FROM student_source_links
                WHERE source_key='nuclei:manual-route'
                """
            ).fetchone()
            thesis = conn.execute(
                """
                SELECT match_status, match_method FROM student_source_links
                WHERE source_key='thesis:manual-route'
                """
            ).fetchone()
        self.assertEqual(nuclei["match_status"], "OK")
        self.assertEqual(nuclei["match_method"], "ROUTE_EXCLUDED_MANUAL")
        self.assertEqual(thesis["match_status"], "OK")
        self.assertEqual(thesis["match_method"], "MANUAL_ROUTE_INCLUDED")


    def test_auto_route_returns_to_complexive_when_supporting_evidence_disappears(self):
        with db.connection() as conn:
            conn.execute(
                """
                UPDATE period_students
                SET route='TRABAJO_TITULACION', route_source='AUTO_EVIDENCE'
                WHERE id=?
                """,
                (self.student_id,),
            )
            conn.execute(
                """
                UPDATE student_source_links
                SET source_active=0
                WHERE period_student_id=? AND source_module IN ('COMPLEXIVE','THESIS')
                """,
                (self.student_id,),
            )

        reliability._normalize_routes(77)
        with db.connection() as conn:
            row = conn.execute(
                "SELECT route, route_source FROM period_students WHERE id=?",
                (self.student_id,),
            ).fetchone()
        self.assertEqual(row["route"], domain.ROUTE_COMPLEXIVE)
        self.assertEqual(row["route_source"], "DEFAULT")


    def test_double_route_becomes_one_manual_case_and_choice_resolves_it(self):
        with db.connection() as conn:
            conn.execute(
                "UPDATE period_students SET route='COMPLEXIVO', route_source='DEFAULT' WHERE id=?",
                (self.student_id,),
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

    def test_cedula_and_email_pointing_to_different_students_never_auto_link(self):
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO period_students
                (period_project_id, report_id, identification, full_name, email,
                 career_name, modality, route, route_source, process_status,
                 requirements_present, created_at, updated_at)
                VALUES (77, ?, '1758888888', 'OTRA PERSONA',
                        'otra@itsqmet.edu.ec', 'DESARROLLO DE SOFTWARE',
                        'presencial', 'COMPLEXIVO', 'DEFAULT', 'ACTIVO', 1, 'x', 'x')
                """,
                (self.report_id,),
            )

        source = {
            "identification": "1752222404",
            "email": "otra@itsqmet.edu.ec",
            "full_name": "ALOMOTO PAZMIÑO BAYRON JAVIER",
            "career_name": "DESARROLLO DE SOFTWARE",
        }
        guarded = reliability._guard_strong_identity_conflict(
            self.report_id,
            "COMPLEXIVE",
            "complexive:test-conflict",
            source,
            {
                "status": domain.MATCH_OK,
                "method": "CEDULA",
                "confidence": 100.0,
                "period_student_id": self.student_id,
                "candidates": [],
                "detail": "",
            },
        )
        self.assertEqual(guarded["status"], audit.MATCH_IDENTITY_CONFLICT)
        self.assertIsNone(guarded["period_student_id"])
        self.assertEqual(guarded["method"], "CEDULA_CORREO_CONFLICTO")
        self.assertEqual(len(guarded["candidates"]), 2)


    def test_name_only_homonyms_are_not_grouped_into_one_manual_case(self):
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO period_students
                (period_project_id, report_id, identification, full_name, email,
                 career_name, modality, route, route_source, process_status,
                 requirements_present, created_at, updated_at)
                VALUES (77, ?, '1759999999', 'NOMBRE HOMONIMO',
                        '', 'CARRERA B', 'presencial', 'COMPLEXIVO', 'DEFAULT',
                        'ACTIVO', 1, 'x', 'x')
                """,
                (self.report_id,),
            )
            for key in ("nuclei:course:a:name:nombre homonimo", "nuclei:course:b:name:nombre homonimo"):
                conn.execute(
                    """
                    INSERT INTO student_source_links
                    (report_id, period_student_id, source_module, source_key, source_name,
                     source_email, source_identification, source_career, match_status,
                     match_method, match_confidence, candidates_json, detail, source_active,
                     created_at, updated_at)
                    VALUES (?, NULL, 'NUCLEI', ?, 'NOMBRE HOMONIMO', '', '', '',
                            'AMBIGUOUS', 'HOMONIMO', 100, '[]', '', 1, 'x', 'x')
                    """,
                    (self.report_id, key),
                )

        cases = [
            case for case in reliability._identity_cases(77)
            if case["source_name"] == "NOMBRE HOMONIMO"
        ]
        self.assertEqual(len(cases), 2)
        self.assertTrue(all(case["occurrences"] == 1 for case in cases))

    def test_merge_master_rewrites_route_and_grade_decision_identity_keys(self):
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, period_project_id, created_at, updated_at)
                VALUES ('Online', 'P', 'en_linea', 77, 'x', 'x')
                """
            )
            online_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.execute(
                """
                INSERT INTO period_students
                (period_project_id, report_id, identification, full_name, email,
                 career_name, modality, route, route_source, process_status,
                 requirements_present, created_at, updated_at)
                VALUES (77, ?, '1753333333', 'OTRO ESTUDIANTE', '',
                        'DESARROLLO DE SOFTWARE', 'en_linea', 'TRABAJO_TITULACION',
                        'MANUAL', 'ACTIVO', 1, 'x', 'x')
                """,
                (online_id,),
            )
            drop_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        reliability._store_decision(
            77, "ROUTE", f"student:{drop_id}", reliability.DECISION_ROUTE,
            decision_scope="route", target_student_id=drop_id,
            decision_value="TRABAJO_TITULACION",
        )
        reliability._store_decision(
            77, "GRADE_NUCLEI", f"student:{drop_id}:nucleus:2",
            reliability.DECISION_GRADE, decision_scope="selected",
            target_student_id=drop_id, decision_value="8.5",
        )

        with db.connection() as conn:
            reliability._merge_master_rows(conn, self.student_id, drop_id)

        with db.connection() as conn:
            keys = {
                row["identity_key"]: row["target_student_id"]
                for row in conn.execute(
                    """
                    SELECT identity_key, target_student_id
                    FROM student_manual_decisions
                    WHERE period_project_id=77
                    """
                ).fetchall()
            }
        self.assertEqual(keys[f"student:{self.student_id}"], self.student_id)
        self.assertEqual(
            keys[f"student:{self.student_id}:nucleus:2"],
            self.student_id,
        )

    def test_master_moves_to_online_when_cedula_is_added_to_previous_noid_student(self):
        requirements_store.ensure_requirements_schema()
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, period_project_id, created_at, updated_at)
                VALUES ('Online', 'P', 'en_linea', 77, 'x', 'x')
                """
            )
            online_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.execute(
                """
                INSERT INTO period_students
                (period_project_id, report_id, identification, full_name, email,
                 career_name, modality, route, route_source, process_status,
                 requirements_present, created_at, updated_at)
                VALUES (77, ?, 'NOID:EMAIL:sincedula@itsqmet.edu.ec',
                        'ESTUDIANTE SIN CEDULA', 'sincedula@itsqmet.edu.ec',
                        'DESARROLLO DE SOFTWARE', 'presencial', 'COMPLEXIVO',
                        'DEFAULT', 'ACTIVO', 1, 'x', 'x')
                """,
                (self.report_id,),
            )
            noid_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.execute(
                """
                INSERT INTO requirements_students
                (report_id, identification, full_name, career_name, modality,
                 email, created_at, updated_at)
                VALUES (?, '1754444444', 'ESTUDIANTE SIN CEDULA',
                        'DESARROLLO DE SOFTWARE', 'en_linea',
                        'sincedula@itsqmet.edu.ec', 'x', 'x')
                """,
                (online_id,),
            )

        result = reliability._migrate_project_master(77)
        self.assertEqual(result["moved"], 1)
        with db.connection() as conn:
            row = conn.execute(
                "SELECT id, report_id, identification FROM period_students WHERE id=?",
                (noid_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(int(row["id"]), noid_id)
        self.assertEqual(int(row["report_id"]), online_id)
        self.assertEqual(row["identification"], "1754444444")


    def test_migration_merges_legacy_noid_copy_with_new_cedula_master(self):
        requirements_store.ensure_requirements_schema()
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, period_project_id, created_at, updated_at)
                VALUES ('Online', 'P', 'en_linea', 77, 'x', 'x')
                """
            )
            online_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

            conn.execute(
                """
                INSERT INTO period_students
                (period_project_id, report_id, identification, full_name, email,
                 career_name, modality, route, route_source, process_status,
                 requirements_present, created_at, updated_at)
                VALUES (77, ?, 'NOID:EMAIL:legacy@itsqmet.edu.ec',
                        'ESTUDIANTE LEGACY', 'legacy@itsqmet.edu.ec',
                        'DESARROLLO DE SOFTWARE', 'presencial', 'TRABAJO_TITULACION',
                        'MANUAL', 'ACTIVO', 1, 'x', 'x')
                """,
                (self.report_id,),
            )
            legacy_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

            conn.execute(
                """
                INSERT INTO period_students
                (period_project_id, report_id, identification, full_name, email,
                 career_name, modality, route, route_source, process_status,
                 requirements_present, created_at, updated_at)
                VALUES (77, ?, '1755555555', 'ESTUDIANTE LEGACY',
                        'legacy@itsqmet.edu.ec', 'DESARROLLO DE SOFTWARE',
                        'en_linea', 'COMPLEXIVO', 'DEFAULT', 'ACTIVO', 1, 'x', 'x')
                """,
                (online_id,),
            )
            duplicate_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

            conn.execute(
                """
                INSERT INTO requirements_students
                (report_id, identification, full_name, career_name, modality,
                 email, created_at, updated_at)
                VALUES (?, '1755555555', 'ESTUDIANTE LEGACY',
                        'DESARROLLO DE SOFTWARE', 'en_linea',
                        'legacy@itsqmet.edu.ec', 'x', 'x')
                """,
                (online_id,),
            )

        result = reliability._migrate_project_master(77)
        self.assertEqual(result["merged"], 1)
        with db.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, report_id, identification, route, route_source
                FROM period_students
                WHERE period_project_id=77 AND email='legacy@itsqmet.edu.ec'
                ORDER BY id
                """
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["id"]), legacy_id)
        self.assertNotEqual(int(rows[0]["id"]), duplicate_id)
        self.assertEqual(int(rows[0]["report_id"]), online_id)
        self.assertEqual(rows[0]["identification"], "1755555555")
        self.assertEqual(rows[0]["route"], "TRABAJO_TITULACION")
        self.assertEqual(rows[0]["route_source"], "MANUAL")


    def test_grade_conflict_waits_until_route_conflict_is_resolved(self):
        with db.connection() as conn:
            conn.execute(
                "UPDATE period_students SET route='COMPLEXIVO', route_source='DEFAULT' WHERE id=?",
                (self.student_id,),
            )
            conn.execute(
                """
                INSERT INTO student_source_links
                (report_id, period_student_id, source_module, source_key, source_name,
                 source_email, source_identification, source_career, match_status,
                 match_method, match_confidence, candidates_json, detail, source_active,
                 created_at, updated_at)
                VALUES (?, ?, 'THESIS', 'thesis:route-grade-order',
                        'ALOMOTO PAZMIÑO BAYRON JAVIER', '',
                        '1752222404', 'DESARROLLO DE SOFTWARE', 'OK',
                        'CEDULA', 100, '[]', '', 1, 'x', 'x')
                """,
                (self.report_id, self.student_id),
            )
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
                VALUES (?, 'ALOMOTO PAZMIÑO BAYRON JAVIER',
                        'bayron.otro@itsqmet.edu.ec', 90, 90, 'x', 'x', ?)
                """,
                (career_id, self.student_id),
            )

        self.assertEqual(len(reliability._route_cases(77)), 1)
        complexive_grades = [
            case for case in reliability._grade_cases(77)
            if case["source_module"] == "COMPLEXIVE"
        ]
        self.assertEqual(complexive_grades, [])

        reliability._set_route_manual_final(
            77, self.student_id, domain.ROUTE_COMPLEXIVE
        )
        complexive_grades = [
            case for case in reliability._grade_cases(77)
            if case["source_module"] == "COMPLEXIVE"
        ]
        self.assertEqual(len(complexive_grades), 1)


    def test_grade_conflict_requires_manual_choice_and_then_disappears(self):
        with db.connection() as conn:
            conn.execute(
                "UPDATE period_students SET route='COMPLEXIVO', route_source='MANUAL' WHERE id=?",
                (self.student_id,),
            )
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
