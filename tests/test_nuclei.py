import unittest

import nuclei_fixes
from nuclei_service import analyze_nucleus, parse_grades_text


GRADES = """
T- NUCLEO 1 ENFERMERIA [Mod 11]
Nombre / Apellido(s)
Dirección de correo
CuestionarioEVALUACIÓN PARCIAL 1
CuestionarioEVALUACIÓN PARCIAL 2
TareaTALLER PRÁCTICO 1
Media de calificacionesTotal del curso
JA
JULEIDY TATIANA AMUY SANCHEZMatriculación de usuarios suspendida
jamuy@itsqmet.edu.ec
Suspenso 4,00
Aprobado 7,00
Aprobado 8,80
Retroalimentación proporcionada
7,27
EA
ERICK DAMIAN ANALUISA CHANGOMatriculación de usuarios suspendida
eranaluisa@itsqmet.edu.ec
Aprobado 8,00
Aprobado 8,00
Aprobado 7,60
7,92
Promedio general
6,00
7,50
8,20
7,60
"""

PARTICIPANTS = """
JAJULEIDY TATIANA AMUY SANCHEZ\tjamuy@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
EAERICK DAMIAN ANALUISA CHANGO\teranaluisa@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
ADRIANA YARITZA MENDOZA SABANDO\tadmendoza@itsqmet.edu.ec\tProfesor\tNo hay grupos\tSuspendido
"""


class NucleiParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        nuclei_fixes.install()

    def test_parses_dynamic_assessments_without_cutting_names(self):
        result = parse_grades_text(GRADES)
        self.assertEqual(result["career_name"], "Enfermería")
        self.assertEqual(result["nucleus_number"], 1)
        self.assertEqual(len(result["assessments"]), 3)
        self.assertEqual(result["students"][0]["full_name"], "JULEIDY TATIANA AMUY SANCHEZ")
        self.assertEqual(result["students"][0]["final_grade"], 7.27)
        self.assertEqual(result["students"][0]["final_status"], "Aprobado")

    def test_identifies_teacher_and_matches_participants(self):
        result = analyze_nucleus({"grades_text": GRADES, "participants_text": PARTICIPANTS})
        self.assertEqual(result["teacher_name"], "ADRIANA YARITZA MENDOZA SABANDO")
        self.assertEqual(result["coordinator"]["coordinator"], "Ana Emilia Guzman")
        self.assertEqual(result["participant_students"], 2)
        self.assertEqual(result["graded_students"], 2)
        self.assertEqual(result["matched_students"], 2)
        self.assertEqual(result["missing_grades"], 0)
        self.assertEqual(result["approved_count"], 2)


if __name__ == "__main__":
    unittest.main()
