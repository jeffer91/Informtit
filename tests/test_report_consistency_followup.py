from __future__ import annotations

import unittest
from unittest.mock import patch

import report_consistency_followup as followup


class ReportConsistencyFollowupTests(unittest.TestCase):
    def test_schedule_analysis_uses_real_execution_state(self) -> None:
        source = {
            "schedules": {"complexive": [], "thesis": []},
            "total": 26,
            "evaluated": 0,
            "average": None,
            "pending": 26,
            "delayed": 0,
            "partial": 0,
            "not_complied": 0,
        }
        with patch.object(followup.schedule_truth, "_schedule_data", lambda _report_id: source):
            result = followup._schedule_analysis_real(1)
        self.assertEqual(result["total"], 26)
        self.assertEqual(result["evaluated"], 0)
        self.assertEqual(result["pending_evaluation"], 26)
        self.assertIsNone(result["average"])

    def test_methodology_explains_imported_vs_analyzed_nuclei(self) -> None:
        text = (
            "La base analizada contiene 266 registros en Requisitos, 106 cursos de Núcleos, "
            "354 registros en Examen Complexivo y 4 registros en Trabajo de Titulación."
        )
        raw = {"courses": [{} for _ in range(106)]}
        analyzed = {"courses": [{} for _ in range(61)]}
        report = {"modality": "presencial"}
        with patch.object(followup.consistency, "_ORIGINAL_NUCLEI_CONSOLIDATED", lambda _report_id: raw), patch.object(
            followup.consistency,
            "_master_nuclei",
            lambda _report_id: analyzed,
        ):
            result = followup._reconcile_methodology_text(text, 1, report)
        self.assertIn("106 cursos de Núcleos importados", result)
        self.assertIn("61 incluidos en este informe Presencial", result)
        self.assertNotIn("106 cursos de Núcleos,", result)

    def test_methodology_keeps_other_paragraphs_unchanged(self) -> None:
        text = "El tratamiento de los datos es descriptivo y comparativo."
        self.assertEqual(followup._reconcile_methodology_text(text, 1, {"modality": "presencial"}), text)


if __name__ == "__main__":
    unittest.main()
