import tempfile
import unittest
from pathlib import Path

import db
import project_wide_reconciliation_runtime as project_runtime
import student_domain_bridge as bridge
import student_domain_service as domain


class ProjectWideReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_data_dir = db.DATA_DIR
        self.original_db_path = db.DB_PATH
        db.DATA_DIR = Path(self.tempdir.name)
        db.DB_PATH = Path(self.tempdir.name) / "test.db"
        db.init_db()
        with db.connection() as conn:
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
            if "period_project_id" not in columns:
                conn.execute("ALTER TABLE reports ADD COLUMN period_project_id INTEGER")
            conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, period_project_id, created_at, updated_at)
                VALUES ('Presencial', 'P', 'presencial', 77, 'x', 'x')
                """
            )
            self.presencial_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, period_project_id, created_at, updated_at)
                VALUES ('Online', 'P', 'en_linea', 77, 'x', 'x')
                """
            )
            self.online_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        domain.ensure_student_domain_schema()
        bridge.ensure_bridge_schema()
        with db.connection() as conn:
            ps_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(period_students)").fetchall()}
            if "requirements_present" not in ps_columns:
                conn.execute("ALTER TABLE period_students ADD COLUMN requirements_present INTEGER DEFAULT 1")
            conn.execute(
                """
                INSERT INTO period_students
                (period_project_id, report_id, identification, full_name, email,
                 career_name, modality, route, process_status, created_at, updated_at,
                 requirements_present)
                VALUES (77, ?, '1111111111', 'PERSONA PRESENCIAL', 'p@itsqmet.edu.ec',
                        'ADMINISTRACION', 'presencial', 'COMPLEXIVO', 'ACTIVO', 'x', 'x', 1)
                """,
                (self.presencial_id,),
            )
            conn.execute(
                """
                INSERT INTO period_students
                (period_project_id, report_id, identification, full_name, email,
                 career_name, modality, route, process_status, created_at, updated_at,
                 requirements_present)
                VALUES (77, ?, '1755732896', 'ZAPATA TRUJILLO ABIGAIL NICOLE',
                        'abzapata@itsqmet.edu.ec', 'CONTABILIDAD ONLINE', 'en_linea',
                        'COMPLEXIVO', 'ACTIVO', 'x', 'x', 1)
                """,
                (self.online_id,),
            )
            self.online_student_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.execute(
                "INSERT INTO careers (report_id, name, created_at) VALUES (?, 'CONTABILIDAD', 'x')",
                (self.presencial_id,),
            )
            career_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.execute(
                """
                INSERT INTO students
                (career_id, full_name, email, created_at, updated_at, period_student_id)
                VALUES (?, 'ABIGAIL NICOLE ZAPATA TRUJILLO', 'abzapata@itsqmet.edu.ec',
                        'x', 'x', ?)
                """,
                (career_id, self.online_student_id),
            )

        # Las funciones directas necesitan la lectura base para instalaciones sin proyecto.
        project_runtime._BASE_BRIDGE_GET = domain.get_period_students

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def test_project_index_finds_online_student_from_presencial_source(self):
        index = project_runtime._project_master_index(self.presencial_id)
        matches = index["by_email"]["abzapata@itsqmet.edu.ec"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(int(matches[0]["report_id"]), self.online_id)
        source_tokens = tuple(sorted(project_runtime._identity_fold("ABIGAIL NICOLE ZAPATA TRUJILLO").split()))
        self.assertEqual(int(index["by_tokens"][source_tokens][0]["id"]), self.online_student_id)

    def test_cross_loaded_complexive_evidence_is_read_by_official_online_dataset(self):
        online = project_runtime._complexive_records_project(self.online_id)
        presencial = project_runtime._complexive_records_project(self.presencial_id)
        self.assertIn(self.online_student_id, online)
        self.assertEqual(online[self.online_student_id][0]["source_report_id"], self.presencial_id)
        self.assertNotIn(self.online_student_id, presencial)

    def test_name_noise_na_and_period_are_ignored(self):
        source = project_runtime._identity_fold("MARTINA NA PONCE ZULETA")
        target = project_runtime._identity_fold("PONCE ZULETA MARTINA .")
        self.assertEqual(tuple(sorted(source.split())), tuple(sorted(target.split())))


if __name__ == "__main__":
    unittest.main()
