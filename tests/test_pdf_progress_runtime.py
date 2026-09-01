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
            self.assertEqual(job["stage"], "PDF generado")
            self.assertTrue(job["download_ready"])
            self.assertGreaterEqual(job["elapsed_seconds"], 0)
            self.assertTrue(job["steps"])
            saved = progress.get_job_path(started["id"])
            self.assertIsNotNone(saved)
            self.assertEqual(saved.read_bytes(), output.read_bytes())

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

    def test_preflight_is_consumed_once_by_matching_job(self):
        payload = {"audit": {"state": "BORRADOR"}, "ok": True}
        token = progress.store_preflight(777, "normal", payload)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "informe.pdf"
            def fake_build(report_id: int):
                reused = progress.consume_preflight(report_id, "normal")
                self.assertEqual(reused["audit"]["state"], "BORRADOR")
                self.assertIsNone(progress.consume_preflight(report_id, "normal"))
                output.write_bytes(b"%PDF-1.4\n")
                return output
            with patch.object(progress.core, "build_pdf", side_effect=fake_build):
                started = progress.start_job(777, token)
                job = self.wait_job(started["id"])
        self.assertEqual(job["status"], "completed")

    def test_generated_pdf_history_is_persisted_and_generation_never_reuses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            db_path = data_dir / "informtit.db"
            db_path.write_bytes(b"database-v1")
            first = data_dir / "generated-1.pdf"
            first.write_bytes(b"%PDF-1.4\nfirst")
            second = data_dir / "generated-2.pdf"
            second.write_bytes(b"%PDF-1.4\nsecond")

            with patch.object(progress.db, "DATA_DIR", data_dir), patch.object(
                progress.db, "DB_PATH", db_path
            ):
                progress._store_cached_pdf(301, first)
                status = progress.cache_status(301)
                self.assertTrue(status["available"])

                # La acción Generar debe volver a construir aunque exista un PDF vigente.
                with patch.object(progress.core, "build_pdf", return_value=second) as build:
                    started = progress.start_job(301)
                    job = self.wait_job(started["id"])
                build.assert_called_once_with(301)
                self.assertEqual(job["status"], "completed")
                self.assertFalse(job["cached"])
                self.assertEqual(job["stage"], "PDF generado")

                history = progress.list_generated_pdfs(301)
                self.assertGreaterEqual(len(history), 2)
                self.assertEqual(history[0]["status"], "vigente")
                self.assertIn(history[1]["status"], {"historico", "desactualizado"})

                progress.invalidate_cached_pdf(301, "Cambio académico")
                status = progress.cache_status(301)
                self.assertTrue(status["saved"])
                self.assertTrue(status["stale"])
                self.assertFalse(status["available"])
                history = progress.list_generated_pdfs(301)
                self.assertTrue(all(item["status"] == "desactualizado" for item in history))

    def test_stalled_flag_uses_last_progress_time(self):
        now = time.time()
        job_id = "a" * 32
        with progress._LOCK:
            progress._JOBS[job_id] = {
                "id": job_id, "report_id": 778, "status": "running",
                "progress": 10, "stage": "Preparando contenido académico",
                "detail": "", "error": "", "path": "", "steps": [],
                "created_at": now - 700, "updated_at": now - 10,
                "last_progress_at": now - progress._STALL_WARNING_SECONDS - 1,
            }
        try:
            public = progress.get_job(job_id)
        finally:
            with progress._LOCK:
                progress._JOBS.pop(job_id, None)
        self.assertTrue(public["stalled"])
        self.assertGreaterEqual(public["seconds_without_progress"], progress._STALL_WARNING_SECONDS)

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
        self.assertIn("pdf-jobs", source)
        self.assertIn("PDF generado y guardado en el historial", source)
        self.assertNotIn("No fue necesario regenerar el documento", source)
        generated_ui = Path("static/generated-pdfs-ui.js").read_text(encoding="utf-8")
        self.assertIn("generated-pdfs", generated_ui)
        self.assertIn("Generar nueva versión", generated_ui)
        self.assertIn("Descargar nunca vuelve a generar", generated_ui)
        self.assertIn("desktop.savePdf", generated_ui)
        self.assertIn("Tiempo transcurrido", source)
        self.assertIn("No cierre Informtit", source)
        self.assertIn("pdf-progress-steps", source)
        self.assertIn("Validando informe", source)
        self.assertIn('/pdf-progress.js?', html)
        self.assertNotIn("data-pdf-report-id", period)
        self.assertNotIn("/export/presencial", period)
        self.assertNotIn("/export/online", period)
        runtime = Path("pdf_progress_runtime.py").read_text(encoding="utf-8")
        desktop = Path("desktop_entry.py").read_text(encoding="utf-8")
        electron_main = Path("electron/main.cjs").read_text(encoding="utf-8")
        preload = Path("electron/preload.cjs").read_text(encoding="utf-8")
        self.assertIn("Generando resultados de Núcleos", runtime)
        self.assertIn("informtit:save-pdf", electron_main)
        self.assertIn("downloadBackendPdf", electron_main)
        self.assertIn("header.toString('ascii') !== '%PDF-'", electron_main)
        self.assertIn(".informtit-backup-", electron_main)
        self.assertIn("selection.filePath.toLowerCase().endsWith('.pdf')", electron_main)
        self.assertIn("savePdf:", preload)
        self.assertIn("install_cache_invalidation", runtime)
        self.assertIn("pdf_progress_runtime.install_cache_invalidation()", desktop)
        self.assertIn("report_read_snapshot", runtime)
        self.assertIn("Etapa completada en", runtime)
        self.assertIn("store_preflight", runtime)
        self.assertIn("export/pdf", runtime)
        self.assertIn("preflight_token", source)
        self.assertIn("job.stalled", source)


if __name__ == "__main__":
    unittest.main()
