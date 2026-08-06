import unittest

from analytics import enrich_student, summary
from parser import canonical_name_key, clean_moodle_name
from report_quality import ExportContext, _phase_after, _phase_before


class QualityRuleTests(unittest.TestCase):
    def test_weighted_average_does_not_compensate_failed_component(self):
        student = {
            "full_name": "RICHARD JAVIER BRITO PINSON",
            "ordinary_theory": 69.0,
            "ordinary_practical": 75.0,
            "supplementary_theory": None,
            "supplementary_practical": None,
        }
        enriched = enrich_student(student)
        self.assertEqual(enriched["ordinary_final"], 72.6)
        self.assertEqual(enriched["ordinary_status"], "Reprobado")
        self.assertEqual(enriched["final_status"], "Reprobado")
        self.assertEqual(summary([student], "consolidado")["failed"], 1)

    def test_supplementary_replaces_only_the_failed_component(self):
        student = {
            "ordinary_theory": 69.0,
            "ordinary_practical": 75.0,
            "supplementary_theory": 80.0,
            "supplementary_practical": None,
        }
        enriched = enrich_student(student)
        self.assertEqual(enriched["final_grade"], 77.0)
        self.assertEqual(enriched["final_status"], "Aprobado")

    def test_cleans_moodle_suffix_and_matches_reordered_name(self):
        first = clean_moodle_name("ALISSON RAMIREZMatriculación de usuarios suspendida")
        self.assertEqual(first, "ALISSON RAMIREZ")
        self.assertEqual(
            canonical_name_key("BARRE AVILA NATASHA PAOLA"),
            canonical_name_key("NATASHA PAOLA BARRE AVILA"),
        )

    def test_numbering_keeps_four_levels(self):
        context = ExportContext.create()
        self.assertEqual(context.heading(1, "Introducción"), "1. Introducción")
        self.assertEqual(context.heading(1, "Metodología"), "2. Metodología")
        self.assertEqual(context.heading(2, "Contenido"), "2.1. Contenido")
        self.assertEqual(context.heading(3, "Administración"), "2.1.1. Administración")
        self.assertEqual(context.heading(4, "Núcleo 1"), "2.1.1.1. Núcleo 1")

    def test_spanish_singular_and_consolidated_text(self):
        data = {
            "total": 1,
            "approved": 1,
            "failed": 0,
            "not_evaluated": 0,
            "approved_pct": 100.0,
            "average_final": 95.4,
        }
        self.assertIn("1 estudiante", _phase_before("ADMINISTRACION", "supletorio", data))
        self.assertIn("resultados consolidados", _phase_before("ADMINISTRACION", "consolidado", data))
        after = _phase_after(data)
        self.assertIn("1 registro analizado", after)
        self.assertIn("1 alcanzó", after)
        self.assertIn("100,00 %", after)


if __name__ == "__main__":
    unittest.main()
