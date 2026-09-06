from __future__ import annotations

import json
import unittest
from pathlib import Path

import desktop_stability_runtime


ROOT = Path(__file__).resolve().parents[1]


class WebDesktopParityTests(unittest.TestCase):
    def test_runtime_build_matches_package_version(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(desktop_stability_runtime.BUILD_ID, package["version"])

    def test_web_backend_boots_the_same_python_stack(self) -> None:
        source = (ROOT / "web_entry.py").read_text(encoding="utf-8")
        self.assertIn("desktop_entry.prepare()", source)
        self.assertIn("InformtitWebHandler(core.InformtitHandler)", source)

    def test_pages_requires_the_shared_backend(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("Verify shared backend parity", workflow)
        self.assertIn("INFORMTIT_API_BASE", workflow)
        self.assertIn("/api/health", workflow)
        self.assertIn("/api/runtime-info", workflow)
        self.assertIn("runtime.get('build')", workflow)

    def test_pages_uses_same_static_frontend_without_web_emulators(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("cp -a static/. _site/", workflow)
        self.assertIn('<script src="./web-runtime.js?v=2.0"></script>', workflow)
        self.assertNotIn('<script src="./firebase-pages-runtime.js?v=', workflow)
        self.assertNotIn('<script src="./firebase-report-pages-runtime.js?v=', workflow)
        self.assertNotIn('<script src="./github-pages-guard.js?v=', workflow)
        self.assertNotIn('<script src="./firebase-global-period-runtime.js?v=', workflow)

    def test_shared_index_keeps_single_application_entrypoint(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(index.count('/app.js?v=4.6'), 1)


if __name__ == "__main__":
    unittest.main()
