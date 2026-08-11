from __future__ import annotations

import base64
import io
import unittest
import zipfile

import nuclei_excel_import


HEADERS = [
    "nombre_carrera",
    "nombre_profesor",
    "nombre_estudiante",
    "materia",
    "nota_final",
    "estado",
    "trabajoTitulacion",
]


def _xlsx_bytes(rows: list[list[str]]) -> bytes:
    def cell(reference: str, value: str) -> str:
        escaped = (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return f'<c r="{reference}" t="inlineStr"><is><t>{escaped}</t></is></c>'

    xml_rows = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for index, value in enumerate(row):
            column = chr(ord("A") + index)
            cells.append(cell(f"{column}{row_number}", value))
        xml_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return stream.getvalue()


def _payload(rows: list[list[str]]) -> dict[str, str]:
    encoded = base64.b64encode(_xlsx_bytes(rows)).decode("ascii")
    return {
        "filename": "nucleos.xlsx",
        "data_url": f"data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{encoded}",
    }


class NucleiExcelImportTests(unittest.TestCase):
    def test_reads_required_columns_from_xlsx(self) -> None:
        rows = [
            HEADERS,
            [
                "TECNOLOGÍA SUPERIOR EN ADMINISTRACIÓN",
                "DOCENTE UNO",
                "ESTUDIANTE UNO",
                "T-Nucleo - Gestión Estratégica",
                "9.50",
                "APR",
                "Examen Complexivo",
            ],
        ]
        records, filename = nuclei_excel_import.parse_excel_payload(_payload(rows))
        self.assertEqual(filename, "nucleos.xlsx")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["nombre_estudiante"], "ESTUDIANTE UNO")
        self.assertEqual(records[0]["estado"], "APR")

    def test_source_status_is_authoritative(self) -> None:
        self.assertEqual(nuclei_excel_import._status("REP", 7.0), "Reprobado")
        self.assertEqual(nuclei_excel_import._status("APR", 6.0), "Aprobado")
        self.assertEqual(nuclei_excel_import._status("NULL", 0.0), "No evaluado")
        self.assertIsNone(nuclei_excel_import._grade("NULL"))

    def test_maps_administration_subjects_to_four_nuclei(self) -> None:
        career = "TECNOLOGÍA SUPERIOR EN ADMINISTRACIÓN ONLINE"
        records = [
            {"nombre_carrera": career, "materia": "T-Nucleo - Gestión Comercial"},
            {"nombre_carrera": career, "materia": "T-Nucleo - Gestión de Procesos y Calidad"},
            {"nombre_carrera": career, "materia": "T-Nucleo - Gestión Estratégica"},
            {"nombre_carrera": career, "materia": "T-Nucleo - Gestión Financiera"},
        ]
        mapping = nuclei_excel_import._subject_number_map(records)
        self.assertEqual(mapping[(career, "T-Nucleo - Gestión Estratégica")], 1)
        self.assertEqual(mapping[(career, "T-Nucleo - Gestión de Procesos y Calidad")], 2)
        self.assertEqual(mapping[(career, "T-Nucleo - Gestión Financiera")], 3)
        self.assertEqual(mapping[(career, "T-Nucleo - Gestión Comercial")], 4)

    def test_rejects_excel_without_required_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "Faltan columnas obligatorias"):
            nuclei_excel_import.parse_excel_payload(_payload([["nombre_carrera", "materia"], ["A", "B"]]))


if __name__ == "__main__":
    unittest.main()
