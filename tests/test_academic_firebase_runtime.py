from __future__ import annotations

import unittest
from unittest.mock import patch

import academic_firebase_runtime as academic
import firebase_sync_runtime as firebase


class FirebaseSourceSyncTests(unittest.TestCase):
    def test_sync_period_never_bulk_publishes_academic_collections(self) -> None:
        with (
            patch.object(firebase, "_period_doc", return_value={"label": "Abril 2026 a Septiembre 2026"}),
            patch.object(
                firebase,
                "_ensure_reports",
                return_value=("normal", "Abril 2026 a Septiembre 2026", {"presencial": 10, "en_linea": 11}),
            ),
            patch.object(
                firebase,
                "_load_requirements_to_local",
                return_value={
                    "students": 2,
                    "requirements": 2,
                    "enrollments": 2,
                    "presencial": 1,
                    "en_linea": 1,
                    "student_map": {"1": {}, "2": {}},
                    "unmatched_students": [],
                },
            ),
            patch.object(firebase, "write_document") as writer,
        ):
            result = firebase.sync_period("2026-04__2026-09")

        writer.assert_not_called()
        self.assertEqual(result["mode"], "read_only_sources")
        self.assertTrue(all(value == 0 for value in result["written"].values()))

    def test_student_collection_wins_for_current_career_and_campus(self) -> None:
        row = firebase._make_requirement_record(
            "0100000000",
            {
                "nombres": "ESTUDIANTE OFICIAL",
                "codigoCarreraActual": "OFICIAL-P",
                "nombreCarreraActual": "CARRERA OFICIAL",
                "sede": "Matriz",
                "correoInstitucional": "oficial@example.edu",
            },
            {
                "codigoCarrera": "ANTIGUA-P",
                "nombreCarrera": "CARRERA ANTIGUA",
                "sede": "Campus anterior",
                "retirado": True,
            },
            {"valores": {}},
            {},
            "normal",
        )
        self.assertEqual(row["career_code"], "OFICIAL-P")
        self.assertEqual(row["career_name"], "CARRERA OFICIAL")
        self.assertEqual(row["campus"], "Matriz")
        self.assertTrue(row["retired"])


class AcademicPublicationTests(unittest.TestCase):
    def test_publish_is_incremental_and_never_deletes_remote_records(self) -> None:
        documents = [
            ("2026-04__2026-09__111", {"periodoId": "2026-04__2026-09", "cedula": "111"}),
            ("2026-04__2026-09__222", {"periodoId": "2026-04__2026-09", "cedula": "222"}),
        ]
        report = {
            "id": 1,
            "firebase_period_id": "2026-04__2026-09",
            "report_type": "normal",
            "period": "Abril 2026 - Septiembre 2026",
        }
        with (
            patch.object(
                academic,
                "_documents_for",
                return_value=(documents, [], [], report),
            ),
            patch.object(
                academic.firebase_sync,
                "write_document",
                side_effect=[True, False],
            ) as writer,
        ):
            result = academic.publish_module(1, "complexivo")

        self.assertTrue(result["ok"])
        self.assertEqual(result["written"], 1)
        self.assertEqual(result["unchanged"], 1)
        self.assertEqual(writer.call_count, 2)

    def test_audit_issues_block_every_write(self) -> None:
        report = {
            "id": 1,
            "firebase_period_id": "2026-04__2026-09",
            "report_type": "normal",
            "period": "Abril 2026 - Septiembre 2026",
        }
        with (
            patch.object(
                academic,
                "_documents_for",
                return_value=([], ["Estudiante sin conciliar."], [], report),
            ),
            patch.object(academic.firebase_sync, "write_document") as writer,
        ):
            result = academic.publish_module(1, "nucleos")

        self.assertFalse(result["ok"])
        self.assertEqual(result["written"], 0)
        writer.assert_not_called()

    def test_target_collections_match_academic_contract(self) -> None:
        self.assertEqual(
            firebase.WRITABLE_COLLECTIONS,
            {"nucleos", "complexivo", "trabajoTitulacion", "articulo"},
        )
        self.assertNotIn("titulacion", firebase.ALL_ALLOWED_COLLECTIONS)
        self.assertNotIn("cronogramas", firebase.ALL_ALLOWED_COLLECTIONS)


if __name__ == "__main__":
    unittest.main()
