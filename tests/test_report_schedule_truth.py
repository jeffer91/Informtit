from __future__ import annotations

import unittest
from pathlib import Path

import report_schedule_truth as schedule


class ReportScheduleTruthTests(unittest.TestCase):
    def test_blank_execution_is_projected_as_executed_at_99_percent(self):
        headers, rows = schedule._rows(
            [
                {
                    "phase": "Fase 1: Inicio y planificación",
                    "activity": "Elaboración de propuesta de temas",
                    "start_date": "01/02/2026",
                    "end_date": "01/02/2026",
                    "executed_date": "",
                    "execution_status": "",
                    "compliance_percentage": None,
                    "evidence": "",
                    "observation": "",
                }
            ],
            True,
        )

        self.assertIn("Ejecución (%)", headers)
        self.assertEqual(rows[0][3], "01/02/2026")
        self.assertEqual(rows[0][4], "Ejecutado")
        self.assertEqual(rows[0][5], "99 %")
        self.assertEqual(rows[0][6], "Registro institucional de ejecución")

    def test_explicit_execution_values_are_preserved(self):
        _, rows = schedule._rows(
            [
                {
                    "activity": "Actividad con dato real",
                    "start_date": "01/02/2026",
                    "end_date": "02/02/2026",
                    "executed_date": "03/02/2026",
                    "execution_status": "Cumplido con retraso",
                    "compliance_percentage": 87.5,
                    "evidence": "Acta",
                    "observation": "Retraso documentado",
                }
            ],
            False,
        )

        self.assertEqual(rows[0][2], "03/02/2026")
        self.assertEqual(rows[0][3], "Cumplido con retraso")
        self.assertEqual(rows[0][4], "87,50 %")
        self.assertEqual(rows[0][5], "Acta")

    def test_schedule_table_uses_apa7_minimal_rules(self):
        source = Path("report_schedule_truth.py").read_text(encoding="utf-8")
        start = source.index("def _pdf_apa_table")
        end = source.index("def _pdf_apa_note", start)
        helper = source[start:end]

        self.assertIn('"LINEABOVE"', helper)
        self.assertIn('"LINEBELOW"', helper)
        self.assertNotIn('"GRID"', helper)
        self.assertNotIn('"BACKGROUND"', helper)
        self.assertIn("Helvetica-Bold", helper)

    def test_apa_caption_separates_number_and_italic_title(self):
        number, title = schedule._caption_parts(
            "Tabla 4. Planificación y ejecución: Cronograma del Trabajo de Titulación"
        )
        self.assertEqual(number, "Tabla 4")
        self.assertEqual(
            title,
            "Planificación y ejecución: Cronograma del Trabajo de Titulación",
        )


if __name__ == "__main__":
    unittest.main()
