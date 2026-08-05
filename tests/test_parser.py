import unittest

from analytics import final_after_supplementary, ordinary_final
from parser import parse_moodle_text


CLASSIC_SAMPLE = """
Nombre / Apellido(s)
Dirección de correo
CuestionarioCOMPONENTE TEÓRICO EXAMEN COMPLEXIVO
CuestionarioCOMPONENTE TEÓRICO EXAMEN COMPLEXIVO -SUPLETORIO
Media de calificacionesTotal Teórico
CuestionarioCOMPONENTE PRACTICO EXAMEN COMPLEXIVO
CuestionarioCOMPONENTE PRACTICO EXAMEN COMPLEXIVO -SUPLETORIO
Media de calificacionesTotal Práctico
SumaTotal del curso
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


EXTENDED_SAMPLE = """
Nombre / Apellido(s)
Dirección de correo
CuestionarioCOMPONENTE TEÓRICO EXAMEN COMPLEXIVO
CuestionarioCOMPONENTE TEÓRICO EXAMEN COMPLEXIVO (VERSION 2)
CuestionarioCOMPONENTE TEÓRICO EXAMEN COMPLEXIVO Supletorio
CuestionarioCOMPONENTE TEÓRICO EXAMEN COMPLEXIVO -SUPLETORIO
Media de calificacionesTotal Teórico
CuestionarioCOMPONENTE PRACTICO EXAMEN COMPLEXIVO
CuestionarioCOMPONENTE PRACTICO EXAMEN COMPLEXIVO (VERSIÓN 2))
CuestionarioCOMPONENTE PRACTICO EXAMEN COMPLEXIVO Supletorio
CuestionarioCOMPONENTE PRACTICO EXAMEN COMPLEXIVO -SUPLETORIO
Media de calificacionesTotal Práctico
SumaTotal del curso
CARLOS EDUARDO ACOSTA CHICA
caacosta@itsqmet.edu.ec
96,00
-
-
-
38,40
60,00
-
-
-
36,00
74,40
EDISON FRANCISCO MEDINA VEGA
edmedina@itsqmet.edu.ec
72,00
-
96,00
-
33,60
50,00
-
95,00
-
43,50
77,10
YM
YAJAIRA MARILIN MOROCHO MUÑOZ
ymorocho@itsqmet.edu.ec
-
96,00
-
-
38,40
-
95,00
-
-
57,00
95,40
Promedio general
89,00
96,00
96,00
-
35,92
77,83
95,00
95,00
-
47,69
83,60
"""


class ParserTests(unittest.TestCase):
    def test_detects_classic_students(self):
        result = parse_moodle_text(CLASSIC_SAMPLE)
        self.assertEqual(result["detected"], 2)
        self.assertEqual(result["grade_columns"], 7)
        self.assertEqual(
            result["students"][0]["full_name"], "CARLOS VIDAL AGILA SOTO"
        )
        self.assertEqual(result["students"][0]["ordinary_theory"], 65.0)
        self.assertIsNone(result["students"][0]["supplementary_theory"])
        self.assertEqual(result["students"][0]["ordinary_practical"], 75.0)
        self.assertEqual(result["students"][0]["source_total_course"], 71.0)

    def test_classic_replacement_rule(self):
        student = parse_moodle_text(CLASSIC_SAMPLE)["students"][1]
        self.assertEqual(ordinary_final(student), 44.0)
        self.assertEqual(final_after_supplementary(student), 72.2)

    def test_extended_columns_are_not_shifted(self):
        result = parse_moodle_text(EXTENDED_SAMPLE)
        self.assertEqual(result["detected"], 3)
        self.assertEqual(result["grade_columns"], 11)

        carlos = result["students"][0]
        self.assertEqual(carlos["ordinary_theory"], 96.0)
        self.assertEqual(carlos["source_total_theory"], 38.4)
        self.assertEqual(carlos["ordinary_practical"], 60.0)
        self.assertIsNone(carlos["supplementary_practical"])
        self.assertEqual(carlos["source_total_practical"], 36.0)
        self.assertEqual(carlos["source_total_course"], 74.4)
        self.assertEqual(ordinary_final(carlos), 74.4)

    def test_version_two_is_an_ordinary_alternative(self):
        yajaira = parse_moodle_text(EXTENDED_SAMPLE)["students"][2]
        self.assertEqual(yajaira["ordinary_theory"], 96.0)
        self.assertEqual(yajaira["ordinary_practical"], 95.0)
        self.assertIsNone(yajaira["supplementary_theory"])
        self.assertIsNone(yajaira["supplementary_practical"])
        self.assertEqual(ordinary_final(yajaira), 95.4)

    def test_supplementary_columns_are_consolidated(self):
        edison = parse_moodle_text(EXTENDED_SAMPLE)["students"][1]
        self.assertEqual(edison["ordinary_theory"], 72.0)
        self.assertEqual(edison["supplementary_theory"], 96.0)
        self.assertEqual(edison["ordinary_practical"], 50.0)
        self.assertEqual(edison["supplementary_practical"], 95.0)
        self.assertEqual(edison["source_total_course"], 77.1)
        self.assertEqual(ordinary_final(edison), 58.8)
        self.assertEqual(final_after_supplementary(edison), 95.4)


if __name__ == "__main__":
    unittest.main()
