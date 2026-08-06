import tempfile
import unittest
from pathlib import Path

from nuclei_catalog import NUCLEI_CATALOG, catalog_for_career, catalogs_for_report, create_cycle_diagram


class NucleiCatalogTests(unittest.TestCase):
    def test_contains_ten_active_career_catalogs(self):
        self.assertEqual(len(NUCLEI_CATALOG), 10)
        self.assertTrue(all(len(item["nuclei"]) == 4 for item in NUCLEI_CATALOG.values()))

    def test_matches_esthetics_career_without_accents(self):
        catalog = catalog_for_career("ESTETICA INTEGRAL")
        self.assertIsNotNone(catalog)
        self.assertEqual(catalog["career"], "Estética Integral")
        self.assertEqual(
            catalog["nuclei"][0]["subjects"],
            ["Química cosmética", "Cosmiatría", "Dermocosmética"],
        )

    def test_only_includes_active_careers(self):
        report = {
            "careers": [
                {"name": "ADMINISTRACION"},
                {"name": "ESTÉTICA INTEGRAL"},
            ]
        }
        catalogs = catalogs_for_report(report)
        self.assertEqual([item["career"] for item in catalogs], ["Administración", "Estética Integral"])

    def test_creates_legible_four_node_cycle_diagram(self):
        catalog = catalog_for_career("Estética Integral")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "diagram.png"
            create_cycle_diagram(catalog, output)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
