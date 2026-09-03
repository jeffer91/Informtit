import unittest
from unittest.mock import patch

import student_domain_integrations as integrations
import student_domain_service as domain


class StudentRouteContractTests(unittest.TestCase):
    @patch("student_domain_integrations.get_period_students")
    def test_project_keys_use_manual_route_not_existing_project(self, students_mock):
        students_mock.return_value = {
            "students": [
                {
                    "id": 10,
                    "requirements_student_id": 1,
                    "identification": "111",
                    "email": "a@x.com",
                    "full_name": "ANA PEREZ",
                    "career_name": "ENFERMERIA",
                    "route": "COMPLEXIVO",
                },
                {
                    "id": 20,
                    "requirements_student_id": 2,
                    "identification": "222",
                    "email": "b@x.com",
                    "full_name": "BEA LOPEZ",
                    "career_name": "ENFERMERIA",
                    "route": "TRABAJO_TITULACION",
                },
            ]
        }
        ids, identifications, emails, names = integrations._project_student_keys(1)
        self.assertNotIn(1, ids)
        self.assertIn(2, ids)
        self.assertNotIn("111", identifications)
        self.assertIn("222", identifications)
        self.assertIn("b@x.com", emails)


    def test_regular_period_rejects_article_route(self):
        with self.assertRaisesRegex(ValueError, "solo corresponde a períodos PVC"):
            domain._validate_route_for_period(domain.ROUTE_COMPLEXIVE, domain.ROUTE_ARTICLE)

    def test_pvc_period_rejects_regular_routes(self):
        for route in (domain.ROUTE_COMPLEXIVE, domain.ROUTE_THESIS):
            with self.assertRaisesRegex(ValueError, "períodos PVC"):
                domain._validate_route_for_period(domain.ROUTE_ARTICLE, route)

    def test_pvc_period_accepts_article_route(self):
        domain._validate_route_for_period(domain.ROUTE_ARTICLE, domain.ROUTE_ARTICLE)



if __name__ == "__main__":
    unittest.main()
