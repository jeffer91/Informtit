import tempfile
import unittest
from pathlib import Path

from nuclei_catalog import catalog_for_career, catalogs_for_report, create_cycle_diagram


class NucleiCatalogTests(unittest.TestCase):
    def test_matches_esthetics_career_without_accents(self):
        catalog = catalog_for_career("ESTETICA INTEGRAL")
        self.assertIsNotNone(catalog)
        self.assertEqual(catalog["career"], "ESTÉTICA INTEGRAL")
        self.assertEqual(len(catalog["nuclei"]), 4)
        self.assertEqual(
            catalog["nuclei"][0]["subjects"],
            ["QUIMÍCA COSMETICA", "COSMIATRÍA", "DERMOCOSMETICA"],
        )

    def test_only_includes_catalog_when_career_is_in_report(self):
        report = {
            "careers": [
                {"name": "ADMINISTRACION"},
                {"name": "ESTÉTICA INTEGRAL"},
            ]
        }
        catalogs = catalogs_for_report(report)
        self.assertEqual(len(catalogs), 1)
        self.assertEqual(catalogs[0]["career"], "ESTÉTICA INTEGRAL")

    def test_creates_four_node_cycle_diagram(self):
        catalog = catalog_for_career("Estética Integral")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "diagram.png"
            create_cycle_diagram(catalog, output)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
