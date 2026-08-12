from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pdf_progress_runtime as progress


class PdfProgressRuntimeTests(unittest.TestCase):
    def wait_job(self, job_id: str, timeout: float = 2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = progress.get_job(job_id)
            if job and job["status"] in {"completed", "error"}:
                return job
            time.sleep(0.02)
        self.fail("El trabajo PDF no terminó dentro del tiempo esperado.")

    def test_job_completes_and_exposes_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "informe.pdf"

            def fake_build(report_id: int):
                self.assertEqual(report_id, 91)
                progress._set_progress(55, "Generando resultados de Núcleos")
                output.write_bytes(b"%PDF-1.4\n")
                return output

            with patch.object(progress.report_full_detail, "validate_pdf_report", return_value={"errors": [], "warnings": []}), patch.object(progress.core, "build_pdf", side_effect=fake_build):
                started = progress.start_job(91)
                job = self.wait_job(started["id"])

            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["progress"], 100)
            self.assertEqual(job["stage"], "PDF listo")
            self.assertTrue(job["download_ready"])
            self.assertEqual(progress.get_job_path(started["id"]), output)

    def test_validation_error_stops_generation(self):
        validation = {
            "errors": [{"name": "Consolidados finales", "detail": "Falta un consolidado final."}],
            "warnings": [],
        }
        with patch.object(progress.report_full_detail, "validate_pdf_report", return_value=validation), patch.object(progress.core, "build_pdf") as build:
            started = progress.start_job(92)
            job = self.wait_job(started["id"])

        self.assertEqual(job["status"], "error")
        self.assertIn("Falta un consolidado final", job["error"])
        build.assert_not_called()

    def test_frontend_uses_job_progress_endpoints(self):
        source = Path("static/pdf-progress.js").read_text(encoding="utf-8")
        self.assertIn("pdf-jobs", source)
        self.assertIn("role=\"progressbar\"", source)
        self.assertIn("/download", source)
        self.assertIn("Generando resultados de Núcleos", Path("pdf_progress_runtime.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
