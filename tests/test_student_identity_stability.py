import unittest

import student_domain_service as domain


class StudentIdentityStabilityTests(unittest.TestCase):
    def test_missing_identification_uses_stable_email_key(self):
        before = {
            "id": 10,
            "identification": "",
            "full_name": "Ana Pérez López",
            "email": "ANA@ITSQMET.EDU.EC",
            "career_name": "Enfermería",
            "modality": "presencial",
        }
        after = {**before, "id": 999, "email": "ana@itsqmet.edu.ec"}
        self.assertEqual(domain._stable_identification(before), domain._stable_identification(after))
        self.assertEqual(domain._stable_identification(before), "NOID:EMAIL:ana@itsqmet.edu.ec")

    def test_internal_identifiers_are_never_treated_as_cedulas(self):
        self.assertEqual(domain._id_number("REQ-17171886"), "")
        self.assertEqual(domain._id_number("NOID:PROFILE:1717188637"), "")
        self.assertEqual(domain._id_number("1717188637"), "1717188637")

    def test_profile_fallback_is_independent_from_database_row_id(self):
        before = {
            "id": 5,
            "identification": "",
            "full_name": "José Luis Andrade",
            "email": "",
            "personal_email": "",
            "career_code": "ABC-P-100",
            "career_name": "Mecánica Automotriz",
            "modality": "presencial",
            "campus": "Norte",
            "schedule": "Nocturna",
        }
        after = {**before, "id": 5000}
        self.assertEqual(domain._stable_identification(before), domain._stable_identification(after))
        self.assertTrue(domain._stable_identification(before).startswith("NOID:PROFILE:"))


if __name__ == "__main__":
    unittest.main()
