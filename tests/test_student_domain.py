import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db
import student_domain_service as domain


class StudentDomainTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "test.db"
        self.original_data_dir = db.DATA_DIR
        self.original_db_path = db.DB_PATH
        db.DATA_DIR = Path(self.tempdir.name)
        db.DB_PATH = self.db_path
        domain.ensure_student_domain_schema = domain.ensure_student_domain_schema
        db.init_db()
        with db.connection() as conn:
            conn.execute(
                "INSERT INTO reports (name, period, modality, created_at, updated_at) VALUES ('T', 'P', 'presencial', 'x', 'x')"
            )
            self.report_id = int(conn.execute("SELECT id FROM reports").fetchone()[0])
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS requirements_students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id INTEGER NOT NULL,
                    identification TEXT DEFAULT '', full_name TEXT NOT NULL,
                    career_code TEXT DEFAULT '', career_name TEXT DEFAULT '', modality TEXT DEFAULT '',
                    schedule TEXT DEFAULT '', academic_status TEXT DEFAULT '', documentation_status TEXT DEFAULT '',
                    financial_status TEXT DEFAULT '', titulation_status TEXT DEFAULT '',
                    practices_linkage_status TEXT DEFAULT '', linkage_status TEXT DEFAULT '',
                    graduate_followup_status TEXT DEFAULT '', english_status TEXT DEFAULT '', data_update_status TEXT DEFAULT '',
                    personal_email TEXT DEFAULT '', email TEXT DEFAULT '', phone TEXT DEFAULT '', campus TEXT DEFAULT '',
                    titulation_approval TEXT DEFAULT '', complexive_approval TEXT DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                """
            )
        domain.ensure_student_domain_schema()

    def tearDown(self):
        db.DATA_DIR = self.original_data_dir
        db.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def _insert_requirement(self, identification="111", **overrides):
        values = {
            "full_name": "ANA PEREZ",
            "career_name": "ENFERMERIA",
            "modality": "presencial",
            "academic_status": "CUMPLE",
            "documentation_status": "CUMPLE",
            "financial_status": "CUMPLE",
            "practices_linkage_status": "CUMPLE",
            "linkage_status": "CUMPLE",
            "graduate_followup_status": "CUMPLE",
            "english_status": "CUMPLE",
            "data_update_status": "CUMPLE",
            "titulation_status": "",
            "titulation_approval": "",
            "complexive_approval": "",
            **overrides,
        }
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO requirements_students
                (report_id, identification, full_name, career_name, modality,
                 academic_status, documentation_status, financial_status,
                 practices_linkage_status, linkage_status, graduate_followup_status,
                 english_status, data_update_status, titulation_status,
                 titulation_approval, complexive_approval, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'x', 'x')
                """,
                (
                    self.report_id, identification, values["full_name"], values["career_name"], values["modality"],
                    values["academic_status"], values["documentation_status"], values["financial_status"],
                    values["practices_linkage_status"], values["linkage_status"], values["graduate_followup_status"],
                    values["english_status"], values["data_update_status"], values["titulation_status"],
                    values["titulation_approval"], values["complexive_approval"],
                ),
            )

    def test_default_route_is_complexive_and_manual_route_survives_sync(self):
        self._insert_requirement()
        domain.sync_report_students(self.report_id)
        data = domain.get_period_students(self.report_id)
        row = data["students"][0]
        self.assertEqual(row["route"], domain.ROUTE_COMPLEXIVE)
        domain.set_student_route(self.report_id, int(row["id"]), domain.ROUTE_THESIS)
        domain.sync_report_students(self.report_id)
        row = domain.get_period_students(self.report_id)["students"][0]
        self.assertEqual(row["route"], domain.ROUTE_THESIS)
        self.assertEqual(row["route_source"], "MANUAL")

    def test_one_missing_is_not_approved_and_two_missing_is_retired(self):
        self._insert_requirement(identification="1", financial_status="NO CUMPLE")
        self._insert_requirement(identification="2", financial_status="NO CUMPLE", english_status="NO CUMPLE")
        domain.sync_report_students(self.report_id)
        rows = {row["identification"]: row for row in domain.get_period_students(self.report_id)["students"]}
        self.assertEqual(rows["1"]["process_status"], domain.PROCESS_WITH_ONE_MISSING)
        self.assertEqual(rows["2"]["process_status"], domain.PROCESS_RETIRED)

    def test_graduated_is_defined_only_by_official_requirement_fields(self):
        self._insert_requirement(
            titulation_status="CUMPLE",
            complexive_approval="CUMPLE",
            titulation_approval="CUMPLE",
        )
        domain.sync_report_students(self.report_id)
        row = domain.get_period_students(self.report_id)["students"][0]
        self.assertEqual(row["official_graduated"], 1)
        self.assertEqual(row["official_titulation_completed"], 1)


    def test_get_period_students_can_read_without_resync(self):
        self._insert_requirement()
        domain.sync_report_students(self.report_id)
        with patch("student_domain_service.sync_report_students") as sync_mock:
            data = domain.get_period_students(self.report_id, sync=False)
        sync_mock.assert_not_called()
        self.assertEqual(len(data["students"]), 1)

    def test_indexed_match_uses_exact_name_and_career_without_fuzzy_scan(self):
        self._insert_requirement()
        domain.sync_report_students(self.report_id)
        students = domain.get_period_students(self.report_id, sync=False)["students"]
        index = domain.build_match_index(students)
        with patch("student_domain_service.SequenceMatcher", side_effect=AssertionError("fuzzy no debe ejecutarse")):
            result = domain.match_source_record(
                self.report_id,
                "NUCLEI",
                "row-indexed",
                {"full_name": "ANA PEREZ", "career_name": "ENFERMERIA"},
                persist=False,
                students=students,
                match_index=index,
            )
        self.assertEqual(result["status"], domain.MATCH_OK)
        self.assertEqual(result["method"], "NOMBRE_EXACTO")

    def test_matching_does_not_create_students(self):
        self._insert_requirement()
        domain.sync_report_students(self.report_id)
        result = domain.match_source_record(
            self.report_id,
            "NUCLEI",
            "row-1",
            {"full_name": "ANA PEREZ", "career_name": "ENFERMERIA"},
        )
        self.assertEqual(result["status"], domain.MATCH_OK)
        with db.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM period_students WHERE report_id=?", (self.report_id,)).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
