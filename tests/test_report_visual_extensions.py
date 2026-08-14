import unittest
from unittest.mock import patch

import report_visual_extensions as visual


class ReportVisualExtensionsTest(unittest.TestCase):
    def test_complexive_component_approval_uses_70_threshold(self):
        items = [
            {
                "name": "Administración",
                "ordinary": {
                    "rows": [
                        {"ordinary_theory": 75, "ordinary_practical": 80},
                        {"ordinary_theory": 65, "ordinary_practical": 70},
                    ]
                },
            },
            {
                "name": "Software",
                "ordinary": {
                    "rows": [
                        {"ordinary_theory": 90, "ordinary_practical": 60},
                        {"ordinary_theory": 70, "ordinary_practical": 68},
                    ]
                },
            },
        ]
        labels, theory, practical = visual.complexive_component_approval(items)
        self.assertEqual(labels, ["Administración", "Software"])
        self.assertEqual(theory, [50.0, 100.0])
        self.assertEqual(practical, [100.0, 0.0])

    def test_cohort_criterion_stats_normalizes_different_maximums(self):
        projects = [
            {
                "scores": [
                    {"evaluation_type": "defense", "criterion": "Uso de recursos", "max_score": 2, "vocal_1": 2, "vocal_2": 2, "vocal_3": 1},
                    {"evaluation_type": "defense", "criterion": "Solventar preguntas", "max_score": 4, "vocal_1": 1, "vocal_2": 2, "vocal_3": 1},
                ]
            },
            {
                "scores": [
                    {"evaluation_type": "defense", "criterion": "Uso de recursos", "max_score": 2, "vocal_1": 2, "vocal_2": 2, "vocal_3": 2},
                    {"evaluation_type": "defense", "criterion": "Solventar preguntas", "max_score": 4, "vocal_1": 2, "vocal_2": 2, "vocal_3": 2},
                ]
            },
        ]
        rows = visual.cohort_criterion_stats(projects, "defense")
        self.assertEqual(rows[0]["criterion"], "Solventar preguntas")
        self.assertAlmostEqual(rows[0]["percentage"], 41.67, places=2)
        self.assertEqual(rows[1]["criterion"], "Uso de recursos")
        self.assertAlmostEqual(rows[1]["percentage"], 91.67, places=2)

    def test_conclusion_mentions_small_cohort_not_single_observation(self):
        def base(_report_id, _report):
            return [
                "Trabajo de Titulación registró 6 estudiantes, 6 aprobados y un promedio final de 8,10; con una sola observación, el resultado es individual y no constituye una tendencia institucional."
            ]

        with patch.object(visual, "get_projects", return_value={"projects": [{"final_grade": 8}] * 6}):
            rows = visual._correct_conclusions(base, 1, {"id": 1})
        self.assertIn("únicamente 6 estudiantes", rows[0])
        self.assertNotIn("una sola observación", rows[0])

    def test_recommendation_uses_cohort_criterion_and_removes_arbitrary_plus_ten(self):
        projects = [
            {
                "scores": [
                    {"evaluation_type": "defense", "criterion": "Solventar preguntas", "max_score": 4, "vocal_1": 1, "vocal_2": 1, "vocal_3": 1},
                    {"evaluation_type": "defense", "criterion": "Uso de recursos", "max_score": 2, "vocal_1": 2, "vocal_2": 2, "vocal_3": 2},
                ]
            },
            {
                "scores": [
                    {"evaluation_type": "defense", "criterion": "Solventar preguntas", "max_score": 4, "vocal_1": 2, "vocal_2": 2, "vocal_3": 2},
                    {"evaluation_type": "defense", "criterion": "Uso de recursos", "max_score": 2, "vocal_1": 2, "vocal_2": 2, "vocal_3": 2},
                ]
            },
        ]

        def base(_report_id, _report):
            return [
                {
                    "hallazgo": "Menor aprobación en Núcleos: X (80.00 %)",
                    "accion": "Acción",
                    "responsable": "Responsable",
                    "indicador": "Aprobación de Núcleos",
                    "actual": "80.00 %",
                    "meta": "> 90.00 %",
                    "plazo": "Siguiente período",
                    "prioridad": "Alta",
                    "evidencia": "Evidencia",
                },
                {
                    "hallazgo": "Menor desempeño relativo en Trabajo de Titulación: Solventar preguntas (1.00/4.00)",
                    "accion": "Acción",
                    "responsable": "Responsable",
                    "indicador": "Promedio de Solventar preguntas",
                    "actual": "1.00/4.00",
                    "meta": "Mejorar al menos 10 %",
                    "plazo": "Próxima cohorte",
                    "prioridad": "Media",
                    "evidencia": "Rúbricas",
                },
            ]

        with patch.object(visual, "get_projects", return_value={"projects": projects}):
            rows = visual._correct_recommendations(base, 1, {"id": 1})
        nuclei = next(row for row in rows if row["indicador"] == "Aprobación de Núcleos")
        self.assertIn("línea base", nuclei["meta"])
        thesis = next(row for row in rows if row["hallazgo"].startswith("Menor desempeño promedio relativo"))
        self.assertIn("Solventar preguntas", thesis["hallazgo"])
        self.assertNotIn("1.00/4.00", thesis["hallazgo"])


if __name__ == "__main__":
    unittest.main()
