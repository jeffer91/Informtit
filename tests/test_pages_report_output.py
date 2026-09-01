from pathlib import Path
import unittest


class PagesReportOutputTests(unittest.TestCase):
    def test_web_report_is_multipage_portrait_with_large_header(self):
        source = Path("docs/index.html").read_text(encoding="utf-8")
        self.assertIn("@page{size:A4 portrait", source)
        self.assertIn("height:26mm", source)
        self.assertIn("grid-template-rows:13mm 13mm", source)
        self.assertIn("ÍNDICE GENERAL", source)
        self.assertIn("Resumen ejecutivo", source)
        self.assertIn("Conclusiones", source)
        self.assertNotIn("@page{size:A4 landscape", source)

    def test_web_schedule_does_not_invent_evidence(self):
        source = Path("docs/index.html").read_text(encoding="utf-8")
        self.assertIn("const evidence=(x.evidence||'').trim() || '—';", source)
        self.assertIn("const observation=(x.observation||'').trim() || '—';", source)
        self.assertNotIn("Registro institucional de ejecución';", source)
        self.assertNotIn("Actividad ejecutada conforme a la planificación';", source)


if __name__ == "__main__":
    unittest.main()
