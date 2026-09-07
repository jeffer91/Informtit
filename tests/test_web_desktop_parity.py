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

    def test_web_backend_still_boots_the_desktop_python_stack(self) -> None:
        source = (ROOT / "web_entry.py").read_text(encoding="utf-8")
        self.assertIn("desktop_entry.prepare()", source)
        self.assertIn("InformtitWebHandler(core.InformtitHandler)", source)

    def test_pages_can_deploy_with_optional_backend(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("INFORMTIT_API_BASE", workflow)
        self.assertIn("os.environ.get('INFORMTIT_API_BASE', '')", workflow)
        self.assertNotIn("Verify shared backend parity", workflow)
        self.assertNotIn("INFORMTIT_API_BASE no está configurada", workflow)

    def test_pages_keeps_the_approved_firebase_presentation_stack(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("cp -a static/. _site/", workflow)
        self.assertIn('<script src="./firebase-pages-runtime.js?v=1.0"></script>', workflow)
        self.assertIn('<script src="./firebase-global-period-final-ui.js?v=1.0"></script>', workflow)
        self.assertIn('<script src="./report-health-ui.js?v=1.0"></script>', workflow)
        self.assertIn('<script src="./gitpages-parity-ui.js?v=1.0"></script>', workflow)

    def test_gitpages_presentation_is_canonical_in_both_targets(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        desktop = (ROOT / "desktop_stability_runtime.py").read_text(encoding="utf-8")
        parity = (ROOT / "static" / "gitpages-parity-ui.js").read_text(encoding="utf-8")

        self.assertIn("gitpages-parity-ui.js?v=1.0", workflow)
        self.assertIn("gitpages-parity-ui.js?v=1.0", desktop)
        self.assertIn("report-health-ui.js?v=1.0", parity)
        self.assertIn("Período académico global", parity)
        self.assertIn("VALIDACION PENDIENTE", parity)
        self.assertIn("period-project-controls", parity)
        self.assertIn("consola", parity.lower())

    def test_shared_index_keeps_single_application_entrypoint(self) -> None:
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(index.count('/app.js?v=4.6'), 1)


if __name__ == "__main__":
    unittest.main()
