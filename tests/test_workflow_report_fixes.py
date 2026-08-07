import unittest
from unittest.mock import patch

import workflow_report_fixes


PRE = {
    "academic_status": "CUMPLE",
    "documentation_status": "CUMPLE",
    "english_status": "CUMPLE",
    "financial_status": "CUMPLE",
    "data_update_status": "CUMPLE",
    "graduate_followup_status": "CUMPLE",
    "practices_linkage_status": "CUMPLE",
    "linkage_status": "CUMPLE",
}


def student(student_id, identification, name, **extra):
    return {
        "id": student_id,
        "identification": identification,
        "full_name": name,
        "email": f"{student_id}@itsqmet.edu.ec",
        "career_name": "Enfermería",
        **PRE,
        **extra,
    }


class WorkflowReportFixesTests(unittest.TestCase):
    @patch("workflow_report_fixes._raw_get_report_roster")
    def test_report_requirement_analysis_uses_only_eight_prerequisites(self, roster_mock):
        roster_mock.return_value = {
            "students": [
                student(
                    1,
                    "111",
                    "ANA PRUEBA",
                    titulation_status="NO CUMPLE",
                    complexive_approval="NO CUMPLE",
                    titulation_approval="NO CUMPLE",
                ),
                student(2, "222", "LUIS PRUEBA", financial_status="NO CUMPLE"),
            ],
            "summary": {"students": 2},
        }

        result = workflow_report_fixes.prerequisite_requirement_analysis(1)
        self.assertIsNotNone(result)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["complete"], 1)
        self.assertEqual(result["pending"], 1)
        self.assertEqual(len(result["requirements"]), 8)
        keys = {row["key"] for row in result["requirements"]}
        self.assertNotIn("titulation_status", keys)
        self.assertNotIn("complexive_approval", keys)
        self.assertNotIn("titulation_approval", keys)

    def test_duplicate_students_are_consolidated_without_losing_later_approvals(self):
        first = student(
            1,
            "111",
            "ANA PRUEBA",
            email="ana@itsqmet.edu.ec",
            titulation_status="",
            complexive_approval="",
            titulation_approval="",
        )
        second = student(
            2,
            "111",
            "PRUEBA ANA",
            email="ana@itsqmet.edu.ec",
            titulation_status="CUMPLE",
            complexive_approval="CUMPLE",
            titulation_approval="CUMPLE",
        )
        merged = workflow_report_fixes.dedupe_workflow_students([first, second])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["titulation_status"], "CUMPLE")
        self.assertEqual(merged[0]["complexive_approval"], "CUMPLE")
        self.assertEqual(merged[0]["titulation_approval"], "CUMPLE")
        self.assertTrue(all(merged[0][key] == "CUMPLE" for key in PRE))

    def test_failed_prerequisite_wins_when_duplicate_sources_disagree(self):
        first = student(1, "111", "ANA PRUEBA")
        second = student(2, "111", "PRUEBA ANA", financial_status="NO CUMPLE")
        merged = workflow_report_fixes.dedupe_workflow_students([first, second])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["financial_status"], "NO CUMPLE")


if __name__ == "__main__":
    unittest.main()
