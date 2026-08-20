from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF_SCRIPT = ROOT / "static" / "pdf-validation-ui.js"
INDEPENDENT_SCRIPT = ROOT / "static" / "independent-modules-ui.js"
STRUCTURE_SCRIPT = ROOT / "static" / "report-structure-ui.js"


class FrontendRuntimeGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pdf_source = PDF_SCRIPT.read_text(encoding="utf-8")
        self.independent_source = INDEPENDENT_SCRIPT.read_text(encoding="utf-8")
        self.structure_source = STRUCTURE_SCRIPT.read_text(encoding="utf-8")

    def test_import_dialog_observer_is_not_global(self) -> None:
        """El observador de importación no debe vigilar todo document.body."""
        self.assertNotIn("observer.observe(document.body", self.pdf_source)
        self.assertIn("observer.observe(importDialog", self.pdf_source)

    def test_mutation_callback_only_writes_when_content_changes(self) -> None:
        """Evita ciclos MutationObserver -> textContent -> MutationObserver."""
        self.assertIn("function setTextIfChanged", self.pdf_source)
        self.assertIn("function setHtmlIfChanged", self.pdf_source)
        self.assertNotIn("if (strong) strong.textContent", self.pdf_source)
        self.assertNotIn("if (span) span.textContent", self.pdf_source)

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
