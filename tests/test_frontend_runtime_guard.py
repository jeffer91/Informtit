from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF_SCRIPT = ROOT / "static" / "pdf-validation-ui.js"
ROBUST_SCRIPT = ROOT / "static" / "robust-import-ui.js"
INDEPENDENT_SCRIPT = ROOT / "static" / "independent-modules-ui.js"
STRUCTURE_SCRIPT = ROOT / "static" / "report-structure-ui.js"


class FrontendRuntimeGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pdf_source = PDF_SCRIPT.read_text(encoding="utf-8")
        self.robust_source = ROBUST_SCRIPT.read_text(encoding="utf-8")
        self.independent_source = INDEPENDENT_SCRIPT.read_text(encoding="utf-8")
        self.structure_source = STRUCTURE_SCRIPT.read_text(encoding="utf-8")

    def test_import_dialog_observers_are_not_global(self) -> None:
        """Ningún flujo de importación debe vigilar document.body completo."""
        self.assertNotIn("observer.observe(document.body", self.pdf_source)
        self.assertNotIn("observer.observe(document.body", self.robust_source)
        self.assertIn("observer.observe(importDialog", self.pdf_source)
        self.assertIn("observer.observe(dialog", self.robust_source)

    def test_mutation_callbacks_only_write_when_content_changes(self) -> None:
        """Evita ciclos MutationObserver -> DOM write -> MutationObserver."""
        for source in (self.pdf_source, self.robust_source):
            self.assertIn("function setTextIfChanged", source)
            self.assertIn("function setHtmlIfChanged", source)
        self.assertNotIn("if (strong) strong.textContent", self.pdf_source)
        self.assertNotIn("if (span) span.textContent", self.pdf_source)

    def test_robust_import_observer_only_tracks_dialog_open_state(self) -> None:
        self.assertIn("attributeFilter: ['open']", self.robust_source)
        self.assertNotIn("childList: true", self.robust_source)
        self.assertNotIn("subtree: true", self.robust_source)

    def test_import_warning_has_one_canonical_text(self) -> None:
        """Dos observadores no deben alternar textos diferentes en el mismo diálogo."""
        canonical_title = (
            "La importación reemplazará únicamente la base de Requisitos de cada modalidad."
        )
        canonical_detail = (
            "Núcleos, Examen Complexivo y Trabajo de Titulación se conservan de forma independiente."
        )
        self.assertIn(canonical_title, self.pdf_source)
        self.assertIn(canonical_title, self.independent_source)
        self.assertIn(canonical_detail, self.pdf_source)
        self.assertIn(canonical_detail, self.independent_source)

    def test_supporting_observers_are_scoped_to_main_surface(self) -> None:
        """Los complementos de Requisitos no deben observar todo el body."""
        self.assertNotIn("observe(document.body", self.independent_source)
        self.assertNotIn("observe(document.body", self.structure_source)
        self.assertIn("observer.observe(mainRoot", self.independent_source)
        self.assertIn("}).observe(mainRoot", self.structure_source)


if __name__ == "__main__":
    unittest.main()
