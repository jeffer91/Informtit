from __future__ import annotations

import unittest
from unittest.mock import patch

import report_enhancements


class ReportEnhancementsTest(unittest.TestCase):
    def test_references_meet_minimum_and_are_public_facing(self) -> None:
        self.assertGreaterEqual(len(report_enhancements.APA_REFERENCES), 23)
        self.assertFalse(any("Informtit" in item for item in report_enhancements.APA_REFERENCES))

    def test_objectives_are_result_oriented(self) -> None:
        objective = report_enhancements.OBJECTIVE_GENERAL.format(period="Octubre 2025 - Marzo 2026")
        self.assertIn("Evaluar los resultados del proceso de titulación", objective)
        self.assertNotIn("mediante cuatro componentes independientes", objective)
        self.assertEqual(len(report_enhancements.SPECIFIC_OBJECTIVES), 5)
        self.assertTrue(report_enhancements.SPECIFIC_OBJECTIVES[0].startswith("Determinar"))
        self.assertTrue(report_enhancements.SPECIFIC_OBJECTIVES[-1].startswith("Identificar"))

    def test_public_text_removes_application_name(self) -> None:
        cleaned = report_enhancements.public_text(
            "Fuente institucional cargada en Informtit y procesada por Informtit."
        )
        self.assertNotIn("Informtit", cleaned)
        self.assertIn("registros institucionales", cleaned)

    def test_schedule_is_consolidated_as_fully_complied(self) -> None:
        fake = {
            "complexive": [
                {"activity": "Núcleo 1", "start_date": "30/03/2026", "end_date": "02/04/2026"},
                {"activity": "Núcleo 2", "start_date": "06/04/2026", "end_date": "09/04/2026"},
            ],
            "thesis": [],
        }
        with patch.object(report_enhancements, "get_schedules_extended", return_value=fake), patch.object(
            report_enhancements,
            "is_present",
            side_effect=lambda report_id, key: key == "schedule_complexive",
        ):
            data = report_enhancements._schedule_data_all_complied(1)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["evaluated"], 2)
        self.assertEqual(data["average_compliance"], 100.0)
        self.assertEqual(data["not_complied"], 0)
        self.assertEqual(data["delayed"], 0)
        self.assertEqual(data["partial"], 0)

    def test_assessment_headers_are_human_readable(self) -> None:
        self.assertEqual(
            report_enhancements._pretty_assessment("EVALUACIÓN PARCIAL 1"),
            "Evaluación parcial 1",
        )
        self.assertEqual(
            report_enhancements._pretty_assessment("TALLER PRÁCTICO 1"),
            "Taller práctico 1",
        )


if __name__ == "__main__":
    unittest.main()
