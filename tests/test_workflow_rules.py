import unittest
from unittest.mock import patch

import workflow_report_runtime
from workflow_rules import POST_NUCLEUS_FIELDS, PRE_NUCLEUS_REQUIREMENTS, downstream_state, prerequisite_state


class WorkflowRulesTests(unittest.TestCase):
    def test_only_eight_fields_gate_entry_to_nuclei(self):
        self.assertEqual(len(PRE_NUCLEUS_REQUIREMENTS), 8)
        labels = [label for _key, label in PRE_NUCLEUS_REQUIREMENTS]
        self.assertEqual(
            labels,
            [
                "Académico",
                "Documentación",
                "Inglés",
                "Financiero",
                "Actualización de datos",
                "Seguimiento a graduados",
                "Prácticas",
                "Vinculación",
            ],
        )
        post_keys = {key for key, _label in POST_NUCLEUS_FIELDS}
        self.assertNotIn("titulation_status", {key for key, _label in PRE_NUCLEUS_REQUIREMENTS})
        self.assertEqual(post_keys, {"titulation_status", "complexive_approval", "titulation_approval"})

    def test_downstream_approvals_cannot_override_failed_prerequisite(self):
        student = {key: "CUMPLE" for key, _label in PRE_NUCLEUS_REQUIREMENTS}
        student.update(
            {
                "financial_status": "NO CUMPLE",
                "titulation_status": "CUMPLE",
                "complexive_approval": "CUMPLE",
                "titulation_approval": "CUMPLE",
            }
        )
        state = prerequisite_state(student)
        downstream = downstream_state(student)
        self.assertFalse(state["complete"])
        self.assertIn("Financiero", state["missing"])
        self.assertTrue(downstream["titulation_marked"])
        self.assertTrue(downstream["complexive_project_approved"])
        self.assertTrue(downstream["titles_uploaded"])

    @patch("workflow_report_runtime._eligible_keys")
    def test_report_complexive_filter_excludes_students_not_habilitated(self, eligible_mock):
        eligible_mock.return_value = ({1}, set())
        report = {
            "id": 9,
            "careers": [
                {
                    "name": "Enfermería",
                    "students": [
                        {"id": 1, "full_name": "HABILITADO", "ordinary_theory": 80.0},
                        {"id": 2, "full_name": "BLOQUEADO", "ordinary_theory": 95.0},
                    ],
                }
            ],
        }
        filtered, blocked = workflow_report_runtime._filtered_report(report)
        self.assertEqual([row["id"] for row in filtered["careers"][0]["students"]], [1])
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["full_name"], "BLOQUEADO")


if __name__ == "__main__":
    unittest.main()
