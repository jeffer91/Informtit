from __future__ import annotations

import unittest
from unittest.mock import patch

import firebase_bootstrap_runtime as bootstrap


class FirebaseBootstrapRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        bootstrap._ATTEMPTED = False
        bootstrap._LAST_RESULT = {
            "ok": True,
            "attempted": False,
            "source": "Firebase",
            "periods": 0,
            "created": 0,
            "updated": 0,
            "warnings": [],
        }

    def test_bootstrap_catalog_reads_all_periods_and_reconciles_when_changed(self) -> None:
        periods = [
            {"periodoId": "2025-10__2026-03", "label": "Octubre 2025 - Marzo 2026"},
            {"periodoId": "2026-04__2026-09", "label": "Abril 2026 - Septiembre 2026"},
        ]
        ensured = [
            {
                "periodoId": periods[0]["periodoId"],
                "created": 2,
                "updated": 0,
                "report_ids": {"presencial": 1, "en_linea": 2},
            },
            {
                "periodoId": periods[1]["periodoId"],
                "created": 2,
                "updated": 0,
                "report_ids": {"presencial": 3, "en_linea": 4},
            },
        ]

        with patch.object(bootstrap.firebase, "list_periods", return_value=periods), patch.object(
            bootstrap, "_ensure_catalog_period", side_effect=ensured
        ) as ensure_period, patch.object(
            bootstrap.unified,
            "reconcile_projects",
            return_value={"ok": True, "projects_created": 2, "datasets_linked": 4},
        ) as reconcile:
            result = bootstrap.bootstrap_catalog()

        self.assertTrue(result["ok"])
        self.assertEqual(result["periods"], 2)
        self.assertEqual(result["created"], 4)
        self.assertEqual(result["updated"], 0)
        self.assertTrue(result["preserved_local_data"])
        self.assertEqual(ensure_period.call_count, 2)
        reconcile.assert_called_once_with()

    def test_bootstrap_once_falls_back_to_local_without_breaking_startup(self) -> None:
        with patch.object(
            bootstrap,
            "bootstrap_catalog",
            side_effect=RuntimeError("sin conexión"),
        ) as run:
            first = bootstrap._bootstrap_once()
            second = bootstrap._bootstrap_once()

        self.assertFalse(first["ok"])
        self.assertEqual(first["fallback"], "local")
        self.assertTrue(first["preserved_local_data"])
        self.assertEqual(first, second)
        run.assert_called_once_with()

    def test_bootstrap_does_not_reconcile_when_catalog_is_already_current(self) -> None:
        periods = [{"periodoId": "2026-04__2026-09"}]
        with patch.object(bootstrap.firebase, "list_periods", return_value=periods), patch.object(
            bootstrap,
            "_ensure_catalog_period",
            return_value={
                "periodoId": periods[0]["periodoId"],
                "created": 0,
                "updated": 0,
                "report_ids": {"presencial": 1, "en_linea": 2},
            },
        ), patch.object(bootstrap.unified, "reconcile_projects") as reconcile:
            result = bootstrap.bootstrap_catalog()

        self.assertTrue(result["ok"])
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 0)
        reconcile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
