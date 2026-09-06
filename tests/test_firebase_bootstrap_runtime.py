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
            "reports": 0,
            "students": 0,
            "warnings": [],
        }

    def test_bootstrap_uses_published_reports_not_every_period(self) -> None:
        periods = [
            {"periodoId": "2025-10__2026-03"},
            {"periodoId": "2026-02__2026-08"},
            {"periodoId": "2026-04__2026-09"},
            {"periodoId": "2026-05__2026-11"},
        ]
        remote = [
            {
                "periodId": "2025-10__2026-03",
                "period": "Octubre 2025 a Marzo 2026",
                "reportType": "normal",
                "codePresencial": "UTET-INF-02-PRO-95-2025-12",
                "active": True,
            },
            {
                "periodId": "2026-04__2026-09",
                "period": "Abril 2026 a Septiembre 2026",
                "reportType": "normal",
                "codePresencial": "UTET-INF-02-PRO-95-2026-06",
                "active": True,
            },
        ]
        sync_results = [
            {
                "report_type": "normal",
                "period": remote[0]["period"],
                "report_ids": {"presencial": 1, "en_linea": 2},
                "requirements": {"students": 10, "presencial": 8, "en_linea": 2},
            },
            {
                "report_type": "normal",
                "period": remote[1]["period"],
                "report_ids": {"presencial": 3, "en_linea": 4},
                "requirements": {"students": 12, "presencial": 9, "en_linea": 3},
            },
        ]

        with patch.object(bootstrap.firebase, "list_periods", return_value=periods), patch.object(
            bootstrap, "_list_remote_reports", return_value=remote
        ), patch.object(
            bootstrap, "_prune_legacy_catalog_shells", return_value=2
        ) as prune, patch.object(
            bootstrap.firebase, "sync_period", side_effect=sync_results
        ) as sync, patch.object(
            bootstrap, "_apply_remote_metadata"
        ) as metadata, patch.object(
            bootstrap.unified,
            "reconcile_projects",
            return_value={"ok": True, "projects_created": 0, "datasets_linked": 4},
        ) as reconcile:
            result = bootstrap.bootstrap_catalog()

        self.assertTrue(result["ok"])
        self.assertEqual(result["periods"], 4)
        self.assertEqual(result["reports"], 2)
        self.assertEqual(result["synced"], 2)
        self.assertEqual(result["students"], 22)
        self.assertEqual(result["removed_legacy_shells"], 2)
        self.assertEqual(sync.call_count, 2)
        self.assertEqual(metadata.call_count, 2)
        prune.assert_called_once_with({"2025-10__2026-03", "2026-04__2026-09"})
        reconcile.assert_called_once_with()

    def test_remote_period_id_accepts_web_metadata_shapes(self) -> None:
        self.assertEqual(
            bootstrap._remote_period_id({"periodId": "2026-04__2026-09"}),
            "2026-04__2026-09",
        )
        self.assertEqual(
            bootstrap._remote_period_id({"period": "Abril 2026 - Septiembre 2026"}),
            "2026-04__2026-09",
        )
        self.assertEqual(
            bootstrap._remote_period_id({"periodKey": "normal:2025-10__2026-03"}),
            "2025-10__2026-03",
        )

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

    def test_dedupes_duplicate_remote_metadata_by_period(self) -> None:
        rows = [
            {
                "periodId": "2026-04__2026-09",
                "reportType": "normal",
                "codePresencial": "OLD",
                "_updateTime": "2026-09-01T00:00:00Z",
            },
            {
                "periodId": "2026-04__2026-09",
                "reportType": "normal",
                "codePresencial": "NEW",
                "_updateTime": "2026-09-02T00:00:00Z",
            },
        ]
        result = bootstrap._dedupe_remote_reports(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["codePresencial"], "NEW")


if __name__ == "__main__":
    unittest.main()
