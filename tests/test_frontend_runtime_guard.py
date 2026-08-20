from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "static" / "pdf-validation-ui.js"


class FrontendRuntimeGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = SCRIPT.read_text(encoding="utf-8")

    def test_import_dialog_observer_is_not_global(self) -> None:
        """El observador de importación no debe vigilar todo document.body."""
        self.assertNotIn("observer.observe(document.body", self.source)
        self.assertIn("observer.observe(importDialog", self.source)

    def test_mutation_callback_only_writes_when_content_changes(self) -> None:
        """Evita ciclos MutationObserver -> textContent -> MutationObserver."""
        self.assertIn("function setTextIfChanged", self.source)
        self.assertIn("function setHtmlIfChanged", self.source)
        self.assertNotIn("if (strong) strong.textContent", self.source)
        self.assertNotIn("if (span) span.textContent", self.source)


if __name__ == "__main__":
    unittest.main()
