from __future__ import annotations

import unittest

import robust_import_fixes
import robust_import_runtime as robust


class RobustImportRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        robust.install()
        robust_import_fixes.install()

    def test_html_cp1252_detects_presencial_and_online(self) -> None:
        html = """<table>
        <tr><td>numeroIdentificacion</td><td>Nombres</td><td>CodigoCarrera</td><td>NombreCarrera</td><td>CorreoInstitucional</td><td>PrácticasVinculacion</td></tr>
        <tr><td>0101</td><td>Ana Álvarez</td><td>ABC-P-01</td><td>ADMINISTRACION</td><td>ana@itsqmet.edu.ec</td><td>CUMPLE</td></tr>
        <tr><td>0102</td><td>José Pérez</td><td>ABC-L-01</td><td>ADMINISTRACION ONLINE</td><td>jose@itsqmet.edu.ec</td><td>CUMPLE</td></tr>
        </table>""".encode("cp1252")

        parsed = robust.parse_roster_bytes(html, "reporte.xls")
        preview = parsed["preview"]
        self.assertEqual(preview["file_type"], "HTML antiguo compatible con Excel")
        self.assertEqual(preview["encoding"], "Windows-1252")
        self.assertEqual(preview["total"], 2)
        self.assertEqual(preview["presencial"], 1)
        self.assertEqual(preview["en_linea"], 1)

    def test_csv_accepts_header_aliases(self) -> None:
        csv_data = (
            "Cédula;Estudiante;Código Carrera;Carrera;Correo\n"
            "0101;Ana Alvarez;ABC-P-01;ADMINISTRACION;ana@itsqmet.edu.ec\n"
            "0102;Luis Perez;ABC-L-01;ADMINISTRACION ONLINE;luis@itsqmet.edu.ec\n"
        ).encode("utf-8")

        parsed = robust.parse_roster_bytes(csv_data, "requisitos.csv")
        preview = parsed["preview"]
        self.assertEqual(preview["total"], 2)
        self.assertEqual(preview["presencial"], 1)
        self.assertEqual(preview["en_linea"], 1)
        self.assertGreaterEqual(preview["columns_recognized"], 5)

    def test_ambiguous_modality_is_visible(self) -> None:
        html = """<table>
        <tr><td>numeroIdentificacion</td><td>Nombres</td><td>CodigoCarrera</td><td>NombreCarrera</td><td>CorreoInstitucional</td></tr>
        <tr><td>0101</td><td>Ana</td><td>550613A01</td><td>DESARROLLO DE SOFTWARE</td><td>ana@itsqmet.edu.ec</td></tr>
        </table>""".encode("utf-8")

        parsed = robust.parse_roster_bytes(html, "reporte.xls")
        self.assertEqual(parsed["preview"]["ambiguous_modality"], 1)
        self.assertEqual(parsed["records"][0]["modality_confidence"], "baja")

    def test_numeric_identification_does_not_gain_decimal_suffix(self) -> None:
        rows = [
            ["Cédula", "Nombres", "Código Carrera", "Carrera", "Correo"],
            [401135306.0, "Ana", "ABC-P-01", "ADMINISTRACION", "ana@itsqmet.edu.ec"],
        ]
        records, _meta = robust._records_from_rows(rows)
        self.assertEqual(records[0]["identification"], "401135306")


if __name__ == "__main__":
    unittest.main()
