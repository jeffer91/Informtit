from __future__ import annotations

import unittest
from unittest.mock import patch

import report_consistency_final as consistency


class ReportConsistencyFinalTests(unittest.TestCase):
    def test_modality_detection_uses_name_and_code(self) -> None:
        presencial = {"modality": "presencial"}
        online = {"modality": "en_linea"}
        self.assertTrue(consistency._matches_modality(presencial, "Administración", "560417A01-P-1701"))
        self.assertFalse(consistency._matches_modality(presencial, "Administración Online", "560417A01-L-1701"))
        self.assertTrue(consistency._matches_modality(online, "Administración", "560417A01-L-1701"))
        self.assertFalse(consistency._matches_modality(online, "Administración", "560417A01-P-1701"))

    def test_explicit_modality_overrides_career_text_for_reconciled_data(self) -> None:
        online = {"modality": "en_linea"}
        presencial = {"modality": "presencial"}
        self.assertTrue(
            consistency._matches_modality(
                online, "ENFERMERÍA", "", "en_linea"
            )
        )
        self.assertFalse(
            consistency._matches_modality(
                online, "ENFERMERÍA ONLINE", "", "presencial"
            )
        )
        self.assertTrue(
            consistency._matches_modality(
                presencial, "REDES Y TELECOMUNICACIONES ONLINE", "", "presencial"
            )
        )

    def test_display_report_does_not_refilter_student_domain_by_name(self) -> None:
        report = {
            "modality": "en_linea",
            "student_domain_applied": True,
            "careers": [{"name": "ENFERMERÍA"}],
        }
        with patch.object(
            consistency,
            "_ORIGINAL_DISPLAY_REPORT",
            lambda value: dict(value, careers=[dict(row) for row in value["careers"]]),
        ):
            result = consistency._display_report_filtered(report)
        self.assertEqual([row["name"] for row in result["careers"]], ["ENFERMERÍA"])

    def test_filename_uses_code_period_and_modality(self) -> None:
        report = {
            "code": "UTET-PRO-95",
            "period": "Febrero 2026 a Agosto 2026",
            "modality": "presencial",
        }
        self.assertEqual(
            consistency.download_filename(report),
            "UTET-PRO-95 - Informe Titulación - Febrero 2026 a Agosto 2026 - Presencial.pdf",
        )

    def test_filename_removes_windows_invalid_characters(self) -> None:
        report = {
            "code": "UTET/PRO:95",
            "period": "Febrero 2026 / Agosto 2026",
            "modality": "en_linea",
        }
        filename = consistency.download_filename(report)
        self.assertNotIn("/", filename)
        self.assertNotIn(":", filename)
        self.assertTrue(filename.endswith(" - Online.pdf"))

    def test_sanitize_text_fixes_common_singular_errors(self) -> None:
        text = (
            "El Instituto Tecnológico Superior Quito Metropolitano registró 1 estudiantes. "
            "Se identificaron 1 aprobados y 1 posibles duplicidades nominales correspondiente a el cierre."
        )
        clean = consistency._sanitize_text(text)
        self.assertIn("Instituto Superior Tecnológico Quito Metropolitano", clean)
        self.assertIn("1 estudiante", clean)
        self.assertIn("Se identificó 1 aprobado", clean)
        self.assertIn("1 posible duplicidad nominal", clean)
        self.assertIn("al cierre", clean)

    def test_filtered_projects_recomputes_summary(self) -> None:
        raw = {
            "projects": [
                {"full_name": "Presencial", "career_name": "Administración", "career_code": "A-P-1", "final_grade": 8.0},
                {"full_name": "Online", "career_name": "Administración Online", "career_code": "A-L-1", "final_grade": 9.0},
            ],
            "summary": {"total": 2, "average_final": 8.5, "approved": 2, "failed": 0},
        }
        with patch.object(consistency, "_ORIGINAL_GET_PROJECTS", lambda _report_id: raw), patch.object(
            consistency.report_quality,
            "_report_data",
            lambda _report_id: {"modality": "presencial"},
        ):
            result = consistency._filtered_projects(1)
        self.assertEqual(len(result["projects"]), 1)
        self.assertEqual(result["projects"][0]["full_name"], "Presencial")
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["average_final"], 8.0)

    def test_format_names_keeps_all_ties(self) -> None:
        self.assertEqual(consistency._format_names(["A"]), "A")
        self.assertEqual(consistency._format_names(["A", "B"]), "A y B")
        self.assertEqual(consistency._format_names(["A", "B", "C"]), "A, B y C")


if __name__ == "__main__":
    unittest.main()
