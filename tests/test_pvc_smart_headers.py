from __future__ import annotations

import io
import unittest

from openpyxl import Workbook

import pvc_report_runtime as pvc


def workbook_bytes(headers, values):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    sheet.append(values)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class PvcSmartHeaderTests(unittest.TestCase):
    def test_common_header_aliases_are_detected_automatically(self) -> None:
        data = workbook_bytes(
            [
                "Nombres completos",
                "Cédula",
                "Nota tutor",
                "Nota lector",
                "Defensa oral",
                "Nota final",
            ],
            ["ANA PEREZ", "0100000000", 8, 8, 8, 8],
        )
        inspection = pvc.inspect_pvc_workbook(data)
        self.assertTrue(inspection["ok"])
        rows = pvc.parse_pvc_workbook(data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["identification"], "0100000000")
        self.assertEqual(rows[0]["final_calculated"], 8.0)

    def test_unknown_headers_can_be_mapped_manually(self) -> None:
        data = workbook_bytes(
            ["A", "B", "C", "D", "E", "F"],
            ["ANA PEREZ", "0100000000", 8, 8, 8, 8],
        )
        inspection = pvc.inspect_pvc_workbook(data)
        self.assertFalse(inspection["ok"])
        mapping = {
            "nombre_estudiante": 0,
            "identificacion_estudiante": 1,
            "evaluacionTutor": 2,
            "evaluacionLector": 3,
            "nota_defensa_oral": 4,
            "notaTrabajoTitulacion": 5,
        }
        rows = pvc.parse_pvc_workbook(data, mapping)
        self.assertEqual(rows[0]["source_name"], "ANA PEREZ")
        self.assertEqual(rows[0]["final_status"], "APROBADO")


if __name__ == "__main__":
    unittest.main()
