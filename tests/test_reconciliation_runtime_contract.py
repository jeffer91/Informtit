from __future__ import annotations

import inspect
import unittest

import project_wide_reconciliation_runtime as project_wide
import reconciliation_reliability_runtime as reliability
import smart_reconciliation_performance_runtime as perf
import smart_reconciliation_runtime as smart
import sqlite_concurrency_runtime as sqlite_guard
import student_domain_bridge as bridge
import student_domain_service as domain
import student_final_audit as audit


class ReconciliationRuntimeContractTests(unittest.TestCase):
    def assert_accepts(self, func, *names: str) -> None:
        params = inspect.signature(func).parameters
        has_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in params.values()
        )
        for name in names:
            self.assertTrue(
                name in params or has_kwargs,
                f"{func.__module__}.{func.__name__} no acepta {name}",
            )

    def test_all_reconciliation_layers_accept_shared_context(self):
        for func in (
            bridge.reconcile_nuclei,
            bridge.reconcile_complexive,
            bridge.reconcile_thesis,
            audit.reconcile_nuclei,
            audit.reconcile_complexive,
            audit.reconcile_thesis,
            sqlite_guard._safe_reconcile_nuclei,
            sqlite_guard._safe_reconcile_complexive,
            sqlite_guard._safe_reconcile_thesis,
        ):
            self.assert_accepts(func, "students", "match_index")

    def test_all_matching_wrappers_accept_shared_context(self):
        for func in (
            bridge._match,
            audit._audited_bridge_match,
            smart._smart_match,
            perf._tracked_match,
            reliability._final_match,
        ):
            self.assert_accepts(func, "students", "match_index")

    def test_read_layers_accept_sync_flag(self):
        self.assert_accepts(domain.get_period_students, "sync")
        self.assert_accepts(audit.get_period_students, "sync")
        self.assert_accepts(project_wide._project_students_for_bridge, "sync")


if __name__ == "__main__":
    unittest.main()
