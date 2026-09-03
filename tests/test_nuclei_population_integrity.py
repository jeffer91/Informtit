from __future__ import annotations

import unittest
from unittest.mock import patch

import nuclei_population_integrity as population
import student_domain_read_model as read_model


class NucleiPopulationIntegrityTests(unittest.TestCase):
    def _domain(self):
        return {
            "students": [
                {
                    "id": 1,
                    "identification": "111",
                    "full_name": "ANA PEREZ",
                    "career_name": "DESARROLLO DE SOFTWARE",
                    "modality": "presencial",
                    "route": "COMPLEXIVO",
                    "process_status": "ACTIVO",
                    "has_nuclei": True,
                    "nuclei_records": [
                        {"nucleus_number": 1},
                        {"nucleus_number": 2},
                        {"nucleus_number": 3},
                        {"nucleus_number": 4},
                    ],
                    "reconciliation_status": "OK",
                    "reconciliation_detail": "",
                },
                {
                    "id": 2,
                    "identification": "222",
                    "full_name": "SACOTO GUZMAN ANA PAULINA",
                    "career_name": "DESARROLLO DE SOFTWARE",
                    "modality": "presencial",
                    "route": "COMPLEXIVO",
                    "process_status": "ACTIVO",
                    "has_nuclei": False,
                    "nuclei_records": [],
                    "reconciliation_status": "REVIEW_REQUIRED",
                    "reconciliation_detail": "Sin Núcleos",
                },
                {
                    "id": 3,
                    "identification": "333",
                    "full_name": "ESTUDIANTE TESIS",
                    "career_name": "DESARROLLO DE SOFTWARE",
                    "modality": "presencial",
                    "route": "TRABAJO_TITULACION",
                    "process_status": "ACTIVO",
                    "has_nuclei": False,
                    "nuclei_records": [],
                    "reconciliation_status": "OK",
                    "reconciliation_detail": "",
                },
                {
                    "id": 4,
                    "identification": "444",
                    "full_name": "RETIRADO",
                    "career_name": "DESARROLLO DE SOFTWARE",
                    "modality": "presencial",
                    "route": "COMPLEXIVO",
                    "process_status": "RETIRADO",
                    "has_nuclei": False,
                    "nuclei_records": [],
                    "reconciliation_status": "OK",
                    "reconciliation_detail": "",
                },
            ]
        }

    @patch("nuclei_population_integrity.get_excel_import_summary")
    @patch("nuclei_population_integrity.consolidated_students")
    @patch("nuclei_population_integrity.bridge.reconcile_all")
    def test_master_population_detects_missing_active_complexive_student(
        self, reconcile, consolidated, summary
    ):
        consolidated.return_value = self._domain()
        reconcile.return_value = {
            "ok": True,
            "nuclei": {"matched": 1, "pending": 0, "conflicts": 0, "route_conflicts": 0},
        }
        summary.return_value = {
            "source_rows": 8,
            "imported_rows": 8,
            "students": 1,
            "courses": 4,
        }

        result = population.reconcile_population(10, refresh=True)

        reconcile.assert_called_once_with(10)
        consolidated.assert_called_once_with(10, sync=False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["expected_students"], 2)
        self.assertEqual(result["with_nuclei"], 1)
        self.assertEqual(result["missing_students"], 1)
        self.assertEqual(result["coverage"], 50.0)
        self.assertEqual(result["missing"][0]["full_name"], "SACOTO GUZMAN ANA PAULINA")
        self.assertEqual(result["careers"][0]["expected"], 2)
        self.assertEqual(result["careers"][0]["missing"], 1)

    @patch("nuclei_population_integrity.get_excel_import_summary", return_value={})
    @patch("nuclei_population_integrity.consolidated_students")
    @patch("nuclei_population_integrity.bridge.reconcile_all")
    def test_source_reconciliation_conflict_is_blocking_even_when_students_are_present(
        self, reconcile, consolidated, _summary
    ):
        domain = self._domain()
        domain["students"][1]["has_nuclei"] = True
        domain["students"][1]["nuclei_records"] = [
            {"nucleus_number": 1},
            {"nucleus_number": 2},
            {"nucleus_number": 3},
            {"nucleus_number": 4},
        ]
        consolidated.return_value = domain
        reconcile.return_value = {
            "ok": True,
            "nuclei": {"matched": 2, "pending": 0, "conflicts": 1, "route_conflicts": 0},
        }

        result = population.reconcile_population(10, refresh=True)

        self.assertEqual(result["missing_students"], 0)
        self.assertEqual(result["coverage"], 100.0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["source_links"]["conflicts"], 1)

    @patch("nuclei_population_integrity.get_excel_import_summary", return_value={})
    @patch("nuclei_population_integrity.consolidated_students")
    @patch("nuclei_population_integrity.bridge.reconcile_all")
    def test_partial_nucleus_series_is_not_considered_complete(
        self, reconcile, consolidated, _summary
    ):
        domain = self._domain()
        domain["students"][0]["nuclei_records"] = [
            {"nucleus_number": 1},
            {"nucleus_number": 2},
            {"nucleus_number": 3},
        ]
        consolidated.return_value = domain
        reconcile.return_value = {
            "ok": True,
            "nuclei": {"matched": 1, "pending": 0, "conflicts": 0, "route_conflicts": 0},
        }

        result = population.reconcile_population(10, refresh=True)

        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_students"], 2)
        ana = next(item for item in result["missing"] if item["identification"] == "111")
        self.assertEqual(ana["missing_nuclei"], [4])

    def test_active_complexive_without_nuclei_is_review_required(self):
        row = {
            "route": "COMPLEXIVO",
            "process_status": "ACTIVO",
            "has_nuclei": False,
            "nuclei_records": [],
            "complexive_records": [],
            "official_graduated": False,
            "official_titulation_completed": False,
        }
        issues = read_model._academic_consistency(row)
        self.assertTrue(
            any(
                status == "REVIEW_REQUIRED" and "no tiene registros conciliados de Núcleos" in detail
                for status, detail in issues
            )
        )


if __name__ == "__main__":
    unittest.main()
