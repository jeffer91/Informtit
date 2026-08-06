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

REAL_GRADES = """
T- NUCLEO 1 ENFERMERIA [Mod 11, OCT-MAR26 Esp. MEC-A { l m mi j } 19h00-22h00-Manta]
Menú de navegación del libro de calificaciones
T- NUCLEO 1 ENFERMERIA [Mod 11, OCT-MAR26 Esp. MEC-A { l m mi j } 19h00-22h00-Manta]Mostrando calificaciones y totales
Nombre / Apellido(s)
Dirección de correo
CuestionarioEVALUACIÓN PARCIAL 1
Ocultar
CuestionarioEVALUACIÓN PARCIAL 2
Ocultar
CuestionarioEVALUACIÓN PARCIAL 3
CuestionarioEVALUACIÓN PARCIAL 4
TareaTALLER PRÁCTICO 1
Media de calificacionesTotal del curso
RA
ROSA ELVIRA ANCHUNDIA VELIZMatriculación de usuarios suspendida
ranchundia@itsqmet.edu.ec
8,00
Ocultar
10,00
Ocultar
Aprobado 9,00
Aprobado 10,00
9,20
9,24
SC
STEPHANY LISBETH CHIQUITO MOREIRAMatriculación de usuarios suspendida
schiquito@itsqmet.edu.ec
9,00
Ocultar
9,00
Ocultar
Aprobado 8,00
Aprobado 7,00
9,20
8,44
Promedio general
8,50
9,50
8,50
8,50
9,20
8,84
Mostrar
Todos
"""

REAL_PARTICIPANTS = """
RAROSA ELVIRA ANCHUNDIA VELIZ\tranchundia@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido Base de datos externa Dar de baja
SCSTEPHANY LISBETH CHIQUITO MOREIRA\tschiquito@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido Base de datos externa Dar de baja
MPMELISSA LISBETH PICO QUIMI\tmpico@itsqmet.edu.ec\tProfesor\tNo hay grupos\tSuspendido Base de datos externa Dar de baja
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

    def test_understands_real_gradebook_with_hidden_rows_and_mixed_labels(self):
        result = analyze_nucleus({
            "grades_text": REAL_GRADES,
            "participants_text": REAL_PARTICIPANTS,
        })
        self.assertEqual(result["career_name"], "Enfermería")
        self.assertEqual(result["nucleus_number"], 1)
        self.assertEqual(len(result["assessments"]), 5)
        self.assertEqual(result["assessments"][0], "EVALUACIÓN PARCIAL 1")
        self.assertEqual(result["assessments"][4], "TALLER PRÁCTICO 1")
        self.assertEqual(result["students"][0]["full_name"], "ROSA ELVIRA ANCHUNDIA VELIZ")
        self.assertEqual(result["students"][0]["scores"][0]["grade"], 8.0)
        self.assertEqual(result["students"][0]["scores"][2]["grade"], 9.0)
        self.assertEqual(result["students"][0]["final_grade"], 9.24)
        self.assertEqual(result["students"][1]["final_grade"], 8.44)
        self.assertEqual(result["source_course_average"], 8.84)
        self.assertEqual(result["calculated_course_average"], 8.84)
        self.assertEqual(result["teacher_name"], "MELISSA LISBETH PICO QUIMI")
        self.assertEqual(result["participant_students"], 2)
        self.assertEqual(result["graded_students"], 2)
        self.assertEqual(result["matched_students"], 2)
        self.assertEqual(result["missing_grades"], 0)
        self.assertEqual(result["extra_grades"], 0)
        self.assertEqual(result["approved_count"], 2)
        self.assertEqual(result["failed_count"], 0)


if __name__ == "__main__":
    unittest.main()
