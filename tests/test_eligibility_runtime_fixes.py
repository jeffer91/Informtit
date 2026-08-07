import unittest

from eligibility_runtime_fixes import _clean_result


class EligibilityRuntimeFixesTests(unittest.TestCase):
    def test_only_real_missing_requirements_remain_as_prerequisite_conflicts(self):
        data = {
            "prerequisite_conflicts": [
                {"student_id": 1, "missing_requirements": []},
                {"student_id": 2, "missing_requirements": ["Financiero"]},
            ],
            "summary": {"nucleus_without_prerequisites": 2},
        }
        result = _clean_result(data)
        self.assertEqual(len(result["prerequisite_conflicts"]), 1)
        self.assertEqual(result["prerequisite_conflicts"][0]["student_id"], 2)
        self.assertEqual(result["summary"]["nucleus_without_prerequisites"], 1)


if __name__ == "__main__":
    unittest.main()
