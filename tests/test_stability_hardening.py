from __future__ import annotations

import unittest
from pathlib import Path

import firebase_incremental_runtime
import firebase_nuclei_bridge


ROOT = Path(__file__).resolve().parents[1]


class StabilityHardeningTests(unittest.TestCase):
    def test_packaged_backend_is_outside_asar(self):
        forge = (ROOT / "forge.config.cjs").read_text(encoding="utf-8")
        main = (ROOT / "electron" / "main.cjs").read_text(encoding="utf-8")
        self.assertIn("asar: false", forge)
        self.assertIn("path.join(process.resourcesPath, 'app')", main)
        self.assertIn("desktop_entry.py", main)

    def test_firebase_ui_is_loaded_directly(self):
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(index.count('/firebase-ui.js?v=1.0'), 1)

    def test_period_reads_do_not_reconcile(self):
        source = (ROOT / "period_readonly_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("reconcile_projects()", source)
        self.assertIn("visible_projects_read_only", source)
        entry = (ROOT / "desktop_entry.py").read_text(encoding="utf-8")
        self.assertIn("period_readonly_runtime.install()", entry)

    def test_nuclei_firebase_uses_modern_tables(self):
        source = (ROOT / "firebase_nuclei_bridge.py").read_text(encoding="utf-8")
        self.assertIn("nucleus_course_instances", source)
        self.assertIn("nucleus_instance_students", source)
        self.assertNotIn("FROM nucleus_courses", source)
        self.assertNotIn("FROM nucleus_students", source)

    def test_incremental_hash_ignores_transport_timestamp(self):
        left = firebase_incremental_runtime._payload_hash(
            {"periodoId": "P1", "nota": 8.5, "updatedAt": "2026-01-01"}
        )
        right = firebase_incremental_runtime._payload_hash(
            {"periodoId": "P1", "nota": 8.5, "updatedAt": "2026-12-31"}
        )
        changed = firebase_incremental_runtime._payload_hash(
            {"periodoId": "P1", "nota": 9.0, "updatedAt": "2026-12-31"}
        )
        self.assertEqual(left, right)
        self.assertNotEqual(left, changed)

    def test_multicampus_course_ids_do_not_collide(self):
        first = firebase_nuclei_bridge._document_id(
            "P1", "PRESENCIAL", {"career_name": "Redes", "nucleus_number": 1, "course_key": "quito-a"}
        )
        second = firebase_nuclei_bridge._document_id(
            "P1", "PRESENCIAL", {"career_name": "Redes", "nucleus_number": 1, "course_key": "manta-a"}
        )
        self.assertNotEqual(first, second)

    def test_section_visibility_is_not_forced_on_startup(self):
        launcher = (ROOT / "desktop_launcher.py").read_text(encoding="utf-8")
        self.assertNotIn("UPDATE institutional_sections SET visible = 1", launcher)

    def test_legacy_schedule_seeds_are_disabled_after_migration(self):
        runtime = (ROOT / "schedule_defaults_runtime.py").read_text(encoding="utf-8")
        entry = (ROOT / "desktop_entry.py").read_text(encoding="utf-8")
        self.assertIn("cleanup_untouched_defaults()", runtime)
        self.assertIn("process_service.seed_schedules = seed_schedules_without_legacy_defaults", runtime)
        self.assertIn("schedule_defaults_runtime.install()", entry)


if __name__ == "__main__":
    unittest.main()
