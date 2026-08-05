import unittest

from analytics import final_after_supplementary, ordinary_final
from parser import parse_moodle_text


SAMPLE = """
Nombre / Apellido(s)
Dirección de correo
CA
CARLOS VIDAL AGILA SOTO
cagila@itsqmet.edu.ec
65,00
Ocultar
-
Ocultar
26,00
75,00
Ocultar
-
45,00
71,00
KB
KEVIN MAURICIO BENAVIDES BATALLAS
kebenavides@itsqmet.edu.ec
87,50
Ocultar
80,00
Ocultar
33,50
15,00
Ocultar
67,00
24,60
58,10
Promedio general
65,98
"""


class ParserTests(unittest.TestCase):
    def test_detects_students(self):
        result = parse_moodle_text(SAMPLE)
        self.assertEqual(result["detected"], 2)
        self.assertEqual(result["students"][0]["full_name"], "CARLOS VIDAL AGILA SOTO")
        self.assertEqual(result["students"][0]["ordinary_theory"], 65.0)
        self.assertIsNone(result["students"][0]["supplementary_theory"])

    def test_replacement_rule(self):
        student = parse_moodle_text(SAMPLE)["students"][1]
        self.assertEqual(ordinary_final(student), 44.0)
        self.assertEqual(final_after_supplementary(student), 72.2)


if __name__ == "__main__":
    unittest.main()
