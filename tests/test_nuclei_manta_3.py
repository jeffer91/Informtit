import unittest

import nuclei_fixes
import nuclei_multicampus


GRADES = """
T- NUCLEO 3 ENFERMERIA [Mod 13, OCT-MAR26 Esp. MEC-A { l m v s } 19h00-22h00-Manta]
Menú de navegación del libro de calificaciones
T- NUCLEO 3 ENFERMERIA [Mod 13, OCT-MAR26 Esp. MEC-A { l m v s } 19h00-22h00-Manta]Mostrando calificaciones y totales
Nombre / Apellido(s)
Dirección de correo
CuestionarioEVALUACIÓN PARCIAL 1
CuestionarioEVALUACIÓN PARCIAL 2
CuestionarioEVALUACIÓN PARCIAL 3
CuestionarioEVALUACIÓN PARCIAL 4
TareaTALLER PRÁCTICO 1
Media de calificacionesTotal del curso
RA
ROSA ELVIRA ANCHUNDIA VELIZMatriculación de usuarios suspendida
ranchundia@itsqmet.edu.ec
Aprobado 9,25
Aprobado 10,00
Aprobado 10,00
Aprobado 10,00
8,60
9,57
SC
STEPHANY LISBETH CHIQUITO MOREIRAMatriculación de usuarios suspendida
schiquito@itsqmet.edu.ec
Aprobado 8,00
Aprobado 9,00
Suspenso 5,00
Aprobado 8,00
8,60
7,72
DC
DAYANNA GUADALUPE CUESTA LOORMatriculación de usuarios suspendida
dcuesta@itsqmet.edu.ec
Aprobado 7,00
Aprobado 9,00
Aprobado 8,00
Aprobado 9,00
8,60
8,32
MARIA JASMIN FRANCO ANCHUNDIAMatriculación de usuarios suspendida
mfranco@itsqmet.edu.ec
Aprobado 10,00
Aprobado 10,00
Aprobado 9,00
Aprobado 8,00
9,00
9,20
AJ
ARELIS MAYERLY JAEN CALDERONMatriculación de usuarios suspendida
ajaen@itsqmet.edu.ec
Aprobado 9,50
Aprobado 9,00
Aprobado 10,00
Aprobado 7,00
8,60
8,82
DL
DOMENICA ANGELINA LOPEZ BERMUDEZMatriculación de usuarios suspendida
dolopez@itsqmet.edu.ec
Aprobado 9,00
Aprobado 9,00
Aprobado 7,00
Aprobado 7,00
7,60
7,92
JM
JESUS DAVID MENDOZA ZAMORAMatriculación de usuarios suspendida
jmendozaz@itsqmet.edu.ec
Aprobado 10,00
Aprobado 10,00
Aprobado 10,00
Aprobado 10,00
7,80
9,56
MM
MARVIN MICHAEL MERA MACIASMatriculación de usuarios suspendida
mamera@itsqmet.edu.ec
Suspenso 6,50
Aprobado 10,00
Aprobado 8,00
Aprobado 7,00
8,60
8,02
LM
LUISA ADRIANA MERA MARCILLOMatriculación de usuarios suspendida
lmeram@itsqmet.edu.ec
Aprobado 9,50
Aprobado 10,00
Aprobado 10,00
Aprobado 9,00
7,60
9,22
KM
KATHERINE JAZMIN MOREIRA LOORMatriculación de usuarios suspendida
kmoreira@itsqmet.edu.ec
Aprobado 10,00
Aprobado 8,50
Aprobado 10,00
Aprobado 9,00
9,00
9,30
JP
JARIC JAMILETH PINCAY MEROMatriculación de usuarios suspendida
jpincay@itsqmet.edu.ec
Aprobado 7,50
Aprobado 9,50
Aprobado 10,00
Aprobado 10,00
8,60
9,12
Promedio general
8,75
9,45
8,82
8,55
8,42
8,80
"""

PARTICIPANTS = """
RAROSA ELVIRA ANCHUNDIA VELIZ\tranchundia@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
SCSTEPHANY LISBETH CHIQUITO MOREIRA\tschiquito@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
DCDAYANNA GUADALUPE CUESTA LOOR\tdcuesta@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
MARIA JASMIN FRANCO ANCHUNDIA\tmfranco@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
AJARELIS MAYERLY JAEN CALDERON\tajaen@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
DLDOMENICA ANGELINA LOPEZ BERMUDEZ\tdolopez@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
JMJESUS DAVID MENDOZA ZAMORA\tjmendozaz@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
MMMARVIN MICHAEL MERA MACIAS\tmamera@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
LMLUISA ADRIANA MERA MARCILLO\tlmeram@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
KMKATHERINE JAZMIN MOREIRA LOOR\tkmoreira@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
JPJARIC JAMILETH PINCAY MERO\tjpincay@itsqmet.edu.ec\tEstudiante\tNo hay grupos\tSuspendido
JSJOICE MAYLIN SANCHEZ FRANCO\tjsanchezf@itsqmet.edu.ec\tProfesor\tNo hay grupos\tSuspendido
"""


class MantaNucleus3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        nuclei_fixes.install()

    def test_understands_real_manta_nucleus_3(self):
        result = nuclei_multicampus.analyze_nucleus(
            {"grades_text": GRADES, "participants_text": PARTICIPANTS}
        )
        self.assertEqual(result["career_name"], "Enfermería")
        self.assertEqual(result["nucleus_number"], 3)
        self.assertEqual(result["campus"], "Manta")
        self.assertEqual(result["module_code"], "13")
        self.assertEqual(result["group_code"], "MEC-A")
        self.assertEqual(result["schedule"], "19h00-22h00")
        self.assertEqual(result["teacher_name"], "JOICE MAYLIN SANCHEZ FRANCO")
        self.assertEqual(result["graded_students"], 11)
        self.assertEqual(result["participant_students"], 11)
        self.assertEqual(result["matched_students"], 11)
        self.assertEqual(result["missing_grades"], 0)
        self.assertEqual(result["extra_grades"], 0)
        self.assertEqual(result["approved_count"], 11)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(result["source_course_average"], 8.80)
        self.assertEqual(result["calculated_course_average"], 8.80)
        expected = {
            "ranchundia@itsqmet.edu.ec": 9.57,
            "schiquito@itsqmet.edu.ec": 7.72,
            "dcuesta@itsqmet.edu.ec": 8.32,
            "mfranco@itsqmet.edu.ec": 9.20,
            "ajaen@itsqmet.edu.ec": 8.82,
            "dolopez@itsqmet.edu.ec": 7.92,
            "jmendozaz@itsqmet.edu.ec": 9.56,
            "mamera@itsqmet.edu.ec": 8.02,
            "lmeram@itsqmet.edu.ec": 9.22,
            "kmoreira@itsqmet.edu.ec": 9.30,
            "jpincay@itsqmet.edu.ec": 9.12,
        }
        self.assertEqual(
            {student["email"]: student["final_grade"] for student in result["students"]},
            expected,
        )


if __name__ == "__main__":
    unittest.main()
