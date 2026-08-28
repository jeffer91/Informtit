from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pdf_progress_runtime as progress
import report_integrity_hooks as integrity_hooks


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

            with patch.object(progress.core, "build_pdf", side_effect=fake_build):
                started = progress.start_job(91)
                job = self.wait_job(started["id"])

            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["progress"], 100)
            self.assertEqual(job["stage"], "PDF listo")
            self.assertTrue(job["download_ready"])
            self.assertGreaterEqual(job["elapsed_seconds"], 0)
            self.assertTrue(job["steps"])
            self.assertEqual(progress.get_job_path(started["id"]), output)

    def test_build_validation_error_is_reported_by_progress_job(self):
        with patch.object(
            progress.core,
            "build_pdf",
            side_effect=ValueError("No se puede generar el PDF: Falta un consolidado final."),
        ):
            started = progress.start_job(92)
            job = self.wait_job(started["id"])

        self.assertEqual(job["status"], "error")
        self.assertIn("Falta un consolidado final", job["error"])
        self.assertIsNotNone(job["duration_seconds"])

    def test_progress_job_does_not_run_a_duplicate_prevalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "informe.pdf"
            output.write_bytes(b"%PDF-1.4\n")
            with patch.object(progress.report_full_detail, "validate_pdf_report") as validation, patch.object(
                progress.core, "build_pdf", return_value=output
            ):
                started = progress.start_job(93)
                job = self.wait_job(started["id"])

        self.assertEqual(job["status"], "completed")
        validation.assert_not_called()

    def test_primed_integrity_validation_is_reused_in_same_thread(self):
        cached = {
            "ok": True,
            "checks": [],
            "errors": [],
            "warnings": [],
            "audit": {"can_generate_pdf": True, "state": "BORRADOR"},
        }
        integrity_hooks.prime_validation(501, cached)
        try:
            with patch.object(integrity_hooks.integrity, "audit_report", side_effect=AssertionError("no debe recalcular")):
                result = integrity_hooks.validation_integrity(501)
        finally:
            integrity_hooks.clear_primed_validation()
        self.assertEqual(result["audit"]["state"], "BORRADOR")

    def test_pdf_builds_are_serialized_across_reports(self):
        active = 0
        max_active = 0
        guard = threading.Lock()

        with tempfile.TemporaryDirectory() as tmp:
            def fake_build(report_id: int):
                nonlocal active, max_active
                with guard:
                    active += 1
                    max_active = max(max_active, active)
                try:
                    time.sleep(0.08)
                    output = Path(tmp) / f"informe_{report_id}.pdf"
                    output.write_bytes(b"%PDF-1.4\n")
                    return output
                finally:
                    with guard:
                        active -= 1

            with patch.object(progress.core, "build_pdf", side_effect=fake_build):
                first = progress.start_job(201)
                second = progress.start_job(202)
                first_job = self.wait_job(first["id"])
                second_job = self.wait_job(second["id"])

        self.assertEqual(first_job["status"], "completed")
        self.assertEqual(second_job["status"], "completed")
        self.assertEqual(max_active, 1)

    def test_frontend_uses_job_progress_endpoints(self):
        source = Path("static/pdf-progress.js").read_text(encoding="utf-8")
        html = Path("static/index.html").read_text(encoding="utf-8")
        period = Path("static/period-unified-ui.js").read_text(encoding="utf-8")
        self.assertIn("pdf-jobs", source)
        self.assertIn("role=\"progressbar\"", source)
        self.assertIn("/download", source)
        self.assertIn("await downloadJob(jobId)", source)
        self.assertIn("Tiempo transcurrido", source)
        self.assertIn("No cierre Informtit", source)
        self.assertIn("pdf-progress-steps", source)
        self.assertIn("Validando informe", source)
        self.assertIn('/pdf-progress.js?', html)
        self.assertIn("data-pdf-report-id", period)
        self.assertNotIn("/export/presencial", period)
        self.assertNotIn("/export/online", period)
        self.assertIn("Generando resultados de Núcleos", Path("pdf_progress_runtime.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
