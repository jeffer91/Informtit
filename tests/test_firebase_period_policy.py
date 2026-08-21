from __future__ import annotations

import unittest

import firebase_sync_runtime
import period_policy_runtime


class PeriodPolicyTests(unittest.TestCase):
    def test_regular_academic_periods(self) -> None:
        self.assertEqual(period_policy_runtime.classify_period("2026-04__2026-09"), "normal")
        self.assertEqual(period_policy_runtime.classify_period("2025-10__2026-03"), "normal")
        self.assertEqual(
            period_policy_runtime.classify_period("Abril 2026 - Septiembre 2026"),
            "normal",
        )
        self.assertEqual(
            period_policy_runtime.classify_period("Octubre 2025 - Marzo 2026"),
            "normal",
        )

    def test_any_other_period_is_pvc(self) -> None:
        self.assertEqual(period_policy_runtime.classify_period("2026-02__2026-08"), "pvc")
        self.assertEqual(period_policy_runtime.classify_period("Mayo 2026 - Noviembre 2026"), "pvc")

    def test_canonical_period_id(self) -> None:
        self.assertEqual(
            period_policy_runtime.canonical_period_id("Abril 2026 - Septiembre 2026"),
            "2026-04__2026-09",
        )


class FirebaseProtectionTests(unittest.TestCase):
    def test_existing_collections_are_read_only(self) -> None:
        expected = {
            "Estudiante",
            "carreras",
            "historial",
            "importaciones",
            "matriculas",
            "periodos",
            "requisitos",
        }
        self.assertEqual(firebase_sync_runtime.READ_ONLY_COLLECTIONS, expected)

    def test_only_four_new_collections_are_writable(self) -> None:
        self.assertEqual(
            firebase_sync_runtime.WRITABLE_COLLECTIONS,
            {"nucleos", "complexivo", "titulacion", "cronogramas"},
        )

    def test_write_guard_blocks_existing_collection(self) -> None:
        with self.assertRaises(ValueError):
            firebase_sync_runtime.write_document(
                "requisitos",
                "2026-04__2026-09__0000000000",
                {"periodoId": "2026-04__2026-09"},
            )


if __name__ == "__main__":
    unittest.main()
