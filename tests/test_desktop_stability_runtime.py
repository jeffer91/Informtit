from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DesktopStabilityRuntimeTests(unittest.TestCase):
    def test_desktop_always_uses_persistent_user_data(self):
        source = (ROOT / "electron" / "main.cjs").read_text(encoding="utf-8")
        self.assertIn("return app.getPath('userData');", source)
        self.assertIn("INFORMTIT_STORAGE_DIR: storage", source)
        self.assertIn("Almacenamiento persistente", source)

    def test_electron_clears_cache_and_cache_busts_root_document(self):
        source = (ROOT / "electron" / "main.cjs").read_text(encoding="utf-8")
        self.assertIn("session.defaultSession.clearCache()", source)
        self.assertIn("loadURL(`${appUrl}/?build=${Date.now()}`)", source)

    def test_runtime_is_installed_last_and_disables_static_cache(self):
        entry = (ROOT / "desktop_entry.py").read_text(encoding="utf-8")
        runtime = (ROOT / "desktop_stability_runtime.py").read_text(encoding="utf-8")
        self.assertIn("desktop_stability_runtime.install()", entry)
        self.assertGreater(
            entry.index("desktop_stability_runtime.install()"),
            entry.index("import_preview_runtime.install()"),
        )
        self.assertIn('"Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"', runtime)
        self.assertIn('path == "/api/runtime-info"', runtime)

    def test_navigation_guard_calls_show_view_when_available(self):
        source = (ROOT / "static" / "startup-guard.js").read_text(encoding="utf-8")
        self.assertIn("showView(name);", source)
        self.assertIn("/api/runtime-info", source)
        self.assertIn("Base activa:", source)

    def test_renderer_errors_are_forwarded_to_terminal(self):
        source = (ROOT / "electron" / "main.cjs").read_text(encoding="utf-8")
        self.assertIn("console-message", source)
        self.assertIn("Informtit renderer ERROR", source)


if __name__ == "__main__":
    unittest.main()
