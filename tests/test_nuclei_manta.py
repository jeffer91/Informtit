import unittest

import nuclei_fixes
from nuclei_service import parse_grades_text


MANTA_NUCLEUS_1 = """
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
DC
DAYANNA GUADALUPE CUESTA LOORMatriculación de usuarios suspendida
dcuesta@itsqmet.edu.ec
9,00
Ocultar
10,00
Ocultar
Aprobado 10,00
Aprobado 10,00
9,80
9,76
MARIA JASMIN FRANCO ANCHUNDIAMatriculación de usuarios suspendida
mfranco@itsqmet.edu.ec
9,00
Ocultar
10,00
Ocultar
Aprobado 10,00
Aprobado 8,00
9,80
9,36
AJ
ARELIS MAYERLY JAEN CALDERONMatriculación de usuarios suspendida
ajaen@itsqmet.edu.ec
9,00
Ocultar
9,00
Ocultar
Aprobado 10,00
Suspenso 6,00
10,00
8,80
DL
DOMENICA ANGELINA LOPEZ BERMUDEZMatriculación de usuarios suspendida
dolopez@itsqmet.edu.ec
6,00
Ocultar
7,00
Ocultar
Aprobado 8,00
Aprobado 9,00
8,40
7,68
JM
JESUS DAVID MENDOZA ZAMORAMatriculación de usuarios suspendida
jmendozaz@itsqmet.edu.ec
10,00
Ocultar
10,00
Ocultar
Aprobado 10,00
Aprobado 10,00
9,20
9,84
MM
MARVIN MICHAEL MERA MACIASMatriculación de usuarios suspendida
mamera@itsqmet.edu.ec
7,00
Ocultar
9,00
Ocultar
Aprobado 10,00
Aprobado 9,00
8,60
8,72
LM
LUISA ADRIANA MERA MARCILLOMatriculación de usuarios suspendida
lmeram@itsqmet.edu.ec
9,00
Ocultar
9,00
Ocultar
Aprobado 10,00
Suspenso 4,00
8,00
8,00
KM
KATHERINE JAZMIN MOREIRA LOORMatriculación de usuarios suspendida
kmoreira@itsqmet.edu.ec
8,00
Ocultar
10,00
Ocultar
Aprobado 10,00
Suspenso 6,00
10,00
8,80
JP
JARIC JAMILETH PINCAY MEROMatriculación de usuarios suspendida
jpincay@itsqmet.edu.ec
8,00
Ocultar
10,00
Ocultar
Aprobado 10,00
Aprobado 8,00
8,60
8,92
Promedio general
8,36
9,36
9,55
7,91
9,16
8,87
"""


class MantaNucleusParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        nuclei_fixes.install()

    def test_reads_all_eleven_students_and_exact_totals(self):
        result = parse_grades_text(MANTA_NUCLEUS_1)
        self.assertEqual(result["career_name"], "Enfermería")
        self.assertEqual(result["nucleus_number"], 1)
        self.assertEqual(len(result["assessments"]), 5)
        self.assertEqual(len(result["students"]), 11)
        expected = {
            "ranchundia@itsqmet.edu.ec": 9.24,
            "schiquito@itsqmet.edu.ec": 8.44,
            "dcuesta@itsqmet.edu.ec": 9.76,
            "mfranco@itsqmet.edu.ec": 9.36,
            "ajaen@itsqmet.edu.ec": 8.80,
            "dolopez@itsqmet.edu.ec": 7.68,
            "jmendozaz@itsqmet.edu.ec": 9.84,
            "mamera@itsqmet.edu.ec": 8.72,
            "lmeram@itsqmet.edu.ec": 8.00,
            "kmoreira@itsqmet.edu.ec": 8.80,
            "jpincay@itsqmet.edu.ec": 8.92,
        }
        parsed = {student["email"]: student["final_grade"] for student in result["students"]}
        self.assertEqual(parsed, expected)
        self.assertEqual(result["source_course_average"], 8.87)
        self.assertEqual(result["calculated_course_average"], 8.87)
        self.assertTrue(all(student["final_status"] == "Aprobado" for student in result["students"]))


if __name__ == "__main__":
    unittest.main()
