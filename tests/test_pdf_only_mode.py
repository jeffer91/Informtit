from __future__ import annotations

import inspect
import unittest
from pathlib import Path

import institutional_export
import pdf_only_runtime


ROOT = Path(__file__).resolve().parents[1]


class PdfOnlyModeTests(unittest.TestCase):
    def test_frontend_only_shows_pdf_export(self) -> None:
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="export-pdf"', html)
        self.assertNotIn('>Word</a>', html)
        self.assertIn('id="export-docx"', html)
        self.assertIn('style="display:none"', html)

    def test_image_bank_does_not_request_signatures_or_nuclei_diagrams(self) -> None:
        script = (ROOT / "static" / "assets-ui.js").read_text(encoding="utf-8")
        self.assertIn("logo_institucional", script)
        self.assertIn("infografia_complexivo", script)
        self.assertNotIn("title: '2. Firma", script)
        self.assertNotIn("title: '3. Firma", script)
        self.assertNotIn("title: '4. Firma", script)
        self.assertNotIn("Diagrama de núcleos -", script)
        self.assertIn("No se suben firmas, QR, gráficos, Ishikawa ni diagramas de Núcleos", script)

    def test_pdf_responsible_blocks_never_insert_signature_images(self) -> None:
        pdf_only_runtime.install()
        source = inspect.getsource(institutional_export.signature_items)
        self.assertNotIn("image_path", source)
        self.assertNotIn("FIRMA / QR", source)
        self.assertIn("NOMBRE", source)
        self.assertIn("CARGO", source)

    def test_docx_endpoint_is_blocked_by_runtime(self) -> None:
        source = inspect.getsource(pdf_only_runtime.install)
        self.assertIn("export/docx", source)
        self.assertIn("exportación Word está deshabilitada", source)


if __name__ == "__main__":
    unittest.main()
