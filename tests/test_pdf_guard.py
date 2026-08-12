from __future__ import annotations

import unittest

import report_pdf_guard as guard


class PdfGuardTests(unittest.TestCase):
    def test_excluded_career_detects_long_variants(self) -> None:
        variants = [
            "ADMINISTRACIÓN DE CENTROS INFANTILES",
            "TECNOLOGÍA EN ADMINISTRACIÓN DE CENTROS INFANTILES",
            "TECNOLOGÍA SUPERIOR EN ADMINISTRACIÓN DE CENTROS INFANTILES",
            "TECNOLOGIA SUPERIOR EN ADMINISTRACION DE CENTROS INFANTILES PRESENCIAL",
        ]
        for value in variants:
            with self.subTest(value=value):
                self.assertTrue(guard._is_excluded_career(value))
                self.assertFalse(guard._allowed_nuclei_career(value, {"modality": "presencial"}))

    def test_valid_administration_is_not_excluded(self) -> None:
        self.assertFalse(guard._is_excluded_career("TECNOLOGÍA SUPERIOR EN ADMINISTRACIÓN"))
        self.assertTrue(guard._allowed_nuclei_career("TECNOLOGÍA SUPERIOR EN ADMINISTRACIÓN", {"modality": "presencial"}))

    def test_display_names_remove_long_prefixes(self) -> None:
        self.assertEqual(
            guard._display_career("TECNOLOGÍA EN DESARROLLO DE SOFTWARE"),
            "Desarrollo de Software",
        )
        self.assertEqual(
            guard._display_career("TECNOLOGÍA SUPERIOR EN CONTABILIDAD ONLINE"),
            "Contabilidad Online",
        )

    def test_display_report_removes_excluded_career(self) -> None:
        report = {
            "careers": [
                {"id": 1, "name": "TECNOLOGÍA EN ADMINISTRACIÓN DE CENTROS INFANTILES"},
                {"id": 2, "name": "TECNOLOGÍA SUPERIOR EN CONTABILIDAD"},
            ]
        }
        cleaned = guard._display_report(report)
        self.assertEqual(len(cleaned["careers"]), 1)
        self.assertEqual(cleaned["careers"][0]["name"], "Contabilidad")


if __name__ == "__main__":
    unittest.main()
