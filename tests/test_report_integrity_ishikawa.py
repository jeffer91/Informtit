from __future__ import annotations

import unittest

import report_integrity_ishikawa as ishikawa


class ReportIntegrityIshikawaTests(unittest.TestCase):
    def test_nuclei_minimum_keeps_all_tied_careers(self):
        original_audit = ishikawa.integrity.audit_report
        original_strict = ishikawa.integrity.strict_nuclei
        ishikawa.integrity.audit_report = lambda report_id, resolve_resources=False: {
            "mode": "normal",
            "metrics": {
                "requirements": {"pending": 0, "incomplete": 0},
                "nuclei": {
                    "unevaluated": 0,
                    "careers": [
                        {"career": "Carrera A", "approval": 90.0},
                        {"career": "Carrera B", "approval": 90.0},
                        {"career": "Carrera C", "approval": 100.0},
                    ],
                },
                "complexive": {"failed": 0, "not_evaluated": 0},
                "thesis": {"failed": 0, "incomplete": 0},
                "schedules": {"pending_evaluation": 0, "incomplete_evidence": 0},
            },
            "duplicates": {"unresolved_probable": 0, "nuclei_exact_omitted": 0},
            "reconciliation": {"balanced": True, "reasons": {"Duplicado": 0}},
        }
        ishikawa.integrity.strict_nuclei = lambda report_id: {"course_rows": []}
        try:
            rows = ishikawa.factors(1, {})
        finally:
            ishikawa.integrity.audit_report = original_audit
            ishikawa.integrity.strict_nuclei = original_strict

        academic = dict(rows)["Preparación académica"]
        self.assertTrue(any("Carrera A y Carrera B" in item for item in academic))


if __name__ == "__main__":
    unittest.main()
