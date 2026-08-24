from __future__ import annotations

import unittest

import report_integrity_last_guard as guard


class ReportIntegrityLastGuardTests(unittest.TestCase):
    def test_schedule_wrapper_restores_presence(self):
        calls: list[tuple[int, str, bool]] = []
        original = guard.set_presence
        guard.set_presence = lambda report_id, key, included: calls.append((report_id, key, included))
        try:
            wrapped = guard._with_presence(
                lambda report_id, schedule_type, entries: {
                    "ok": True,
                    "report_id": report_id,
                    "schedule_type": schedule_type,
                    "count": len(entries),
                }
            )
            result = wrapped(7, "complexive", [{"activity": "Núcleo 1"}])
        finally:
            guard.set_presence = original

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [(7, "schedule_complexive", True)])


if __name__ == "__main__":
    unittest.main()
