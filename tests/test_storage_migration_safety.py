from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from storage_migration import _database_score


class StorageMigrationSafetyTests(unittest.TestCase):
    def test_seeded_shell_database_scores_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shell.db"
            conn = sqlite3.connect(path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE reports (
                        id INTEGER PRIMARY KEY,
                        source_import_id INTEGER
                    );
                    CREATE TABLE schedule_items (
                        id INTEGER PRIMARY KEY,
                        report_id INTEGER,
                        executed_date TEXT DEFAULT '',
                        execution_status TEXT DEFAULT '',
                        compliance_percentage REAL,
                        evidence TEXT DEFAULT '',
                        observation TEXT DEFAULT ''
                    );
                    INSERT INTO reports(id, source_import_id) VALUES (1, NULL);
                    INSERT INTO schedule_items(
                        id, report_id, executed_date, execution_status,
                        compliance_percentage, evidence, observation
                    ) VALUES (1, 1, '', '', NULL, '', '');
                    """
                )
                conn.commit()
            finally:
                conn.close()

            self.assertEqual(_database_score(path), 0)

    def test_real_student_data_scores_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.db"
            conn = sqlite3.connect(path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE students (id INTEGER PRIMARY KEY);
                    INSERT INTO students(id) VALUES (1);
                    """
                )
                conn.commit()
            finally:
                conn.close()

            self.assertGreater(_database_score(path), 0)

    def test_executed_schedule_counts_as_real_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schedule.db"
            conn = sqlite3.connect(path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE schedule_items (
                        id INTEGER PRIMARY KEY,
                        report_id INTEGER,
                        executed_date TEXT DEFAULT '',
                        execution_status TEXT DEFAULT '',
                        compliance_percentage REAL,
                        evidence TEXT DEFAULT '',
                        observation TEXT DEFAULT ''
                    );
                    INSERT INTO schedule_items(
                        id, report_id, executed_date, execution_status,
                        compliance_percentage, evidence, observation
                    ) VALUES (1, 1, '2026-08-21', 'EJECUTADO', 100, '', '');
                    """
                )
                conn.commit()
            finally:
                conn.close()

            self.assertGreater(_database_score(path), 0)


if __name__ == "__main__":
    unittest.main()
