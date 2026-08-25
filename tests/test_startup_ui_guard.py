from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class StartupUiGuardTests(unittest.TestCase):
    def test_startup_guard_is_loaded_and_checked_after_app(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r'<script\s+src="([^"]+)"', html)
        app_index = next(i for i, item in enumerate(scripts) if item.startswith('/app.js?'))
        guard_index = next(i for i, item in enumerate(scripts) if item.startswith('/startup-guard.js?'))
        self.assertGreater(guard_index, app_index)

    def test_unified_import_layers_are_loaded(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('/robust-import-ui.js?', html)
        self.assertIn('/period-unified-ui.js?', html)
        self.assertIn('/desktop-ui-rescue.js?', html)

    def test_import_helpers_do_not_observe_document_body(self) -> None:
        for filename in ("pdf-validation-ui.js", "import-modality-guard-ui.js"):
            source = (STATIC / filename).read_text(encoding="utf-8")
            self.assertNotIn('observe(document.body', source, filename)

    def test_core_controls_have_base_backup_and_final_handlers(self) -> None:
        app = (STATIC / "app.js").read_text(encoding="utf-8")
        guard = (STATIC / "startup-guard.js").read_text(encoding="utf-8")
        rescue = (STATIC / "desktop-ui-rescue.js").read_text(encoding="utf-8")
        self.assertIn("#new-report-btn", app)
        self.assertIn("#refresh-btn", app)
        self.assertIn("new-report-btn", guard)
        self.assertIn("refresh-btn", guard)
        self.assertIn("/api/health", guard)
        self.assertIn("#new-report-btn", rescue)
        self.assertIn("#refresh-btn", rescue)
        self.assertIn("/api/reports", rescue)

    def test_desktop_rescue_is_last_after_unified_layer(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r'<script\s+src="([^"]+)"', html)
        unified_index = next(i for i, item in enumerate(scripts) if item.startswith('/period-unified-ui.js?'))
        rescue_index = next(i for i, item in enumerate(scripts) if item.startswith('/desktop-ui-rescue.js?'))
        self.assertGreater(rescue_index, unified_index)
        self.assertTrue(scripts[-1].startswith('/desktop-ui-rescue.js?'))


if __name__ == "__main__":
    unittest.main()
