from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SectionTemplate:
    key: str
    title: str
    mode: str
    order: int
    content: str
    help_text: str


MARCO_LEGAL_Y_NORMATIVO = """El proceso de titulación del Instituto Superior Tecnológico Quito Metropolitano se fundamenta en las disposiciones constitucionales, legales, reglamentarias e institucionales que regulan el Sistema de Educación Superior del Ecuador. Este marco establece los principios, derechos, requisitos, responsabilidades, modalidades de titulación, mecanismos de evaluación y procedimientos que deben observarse durante la planificación, ejecución, seguimiento y finalización del proceso.

Constitución de la República del Ecuador

El artículo 26 reconoce a la educación como un derecho de las personas a lo largo de su vida y como un deber ineludible e inexcusable del Estado. Asimismo, la considera un área prioritaria de la política pública, una garantía para la igualdad e inclusión social y una condición indispensable para el buen vivir. Este principio sustenta la responsabilidad institucional de garantizar procesos educativos organizados, accesibles, equitativos y respetuosos de los derechos de los estudiantes.

El artículo 350 determina que el Sistema de Educación Superior tiene como finalidades la formación académica y profesional con visión científica y humanista; la investigación científica y tecnológica; la innovación; la promoción, desarrollo y difusión de los saberes y las culturas; y la construcción de soluciones para los problemas del país. En este contexto, el proceso de titulación permite demostrar la integración y aplicación de los conocimientos, habilidades y competencias adquiridos durante la formación académica.

El artículo 351 establece que el Sistema de Educación Superior se regirá, entre otros, por los principios de igualdad de oportunidades, calidad, pertinencia, integralidad y autodeterminación para la producción del pensamiento y el conocimiento. Estos principios orientan la planificación, ejecución, evaluación y mejora continua del proceso institucional de titulación.

El artículo 352 reconoce a los institutos superiores técnicos y tecnológicos como instituciones integrantes del Sistema de Educación Superior. En consecuencia, los procesos académicos y de titulación desarrollados por el Instituto deben sujetarse a las normas, políticas y mecanismos de aseguramiento de la calidad aplicables a dicho sistema.

Ley Orgánica de Educación Superior

El artículo 4 establece que el derecho a la educación superior consiste en el ejercicio efectivo de la igualdad de oportunidades, en función de los méritos respectivos, para acceder a una formación académica y profesional con producción de conocimiento pertinente y de excelencia. Este principio fundamenta la aplicación de criterios académicos objetivos y verificables en las diferentes etapas del proceso de titulación.

El artículo 5, literal a) reconoce como derecho de las y los estudiantes acceder, movilizarse, permanecer, egresar y titularse sin discriminación, conforme a sus méritos académicos. Por tanto, los requisitos, evaluaciones y decisiones relacionados con la titulación deben aplicarse de manera transparente, equitativa y respetando los derechos de los estudiantes.

El artículo 71 desarrolla el principio de igualdad de oportunidades y determina que los actores del Sistema de Educación Superior deben contar con las mismas posibilidades de acceso, permanencia, movilidad y egreso, sin discriminación. Este principio debe observarse en la inscripción, habilitación, evaluación, aprobación y finalización del proceso de titulación.

El artículo 123 dispone que el Consejo de Educación Superior aprobará el Reglamento de Régimen Académico encargado de regular los títulos, grados académicos, duración, créditos y demás aspectos relacionados con la formación y titulación dentro del Sistema de Educación Superior. Esta disposición constituye el fundamento legal para la aplicación del Reglamento de Régimen Académico.

Reglamento de Régimen Académico

El Reglamento de Régimen Académico, expedido mediante Resolución RPC-SE-08-No.023-2022, es aplicable a las instituciones de educación superior públicas y particulares, incluidos los institutos y conservatorios superiores. Su objeto es regular y orientar las funciones sustantivas y la gestión académica de las instituciones que integran el Sistema de Educación Superior.

El artículo 3 establece como objetivos garantizar una formación de calidad, excelencia y pertinencia; fortalecer la articulación entre docencia, investigación y vinculación con la sociedad; y promover la innovación, la sostenibilidad y el mejoramiento continuo de los procesos académicos.

El artículo 12 reconoce los títulos de tercer nivel técnico-tecnológico que pueden otorgar los institutos superiores una vez cumplidos los requisitos establecidos en la normativa aplicable, entre ellos Técnico Superior, Tecnólogo Superior y Tecnólogo Superior Universitario, según corresponda.

El artículo 26 determina que cada institución de educación superior establecerá en su normativa interna los requisitos para acceder a la titulación y las opciones para su aprobación. También dispone que el título podrá emitirse únicamente cuando el estudiante haya aprobado todos los requisitos académicos y administrativos establecidos por la institución, lo cual deberá constar en el acta consolidada de finalización de estudios.

El artículo 38 establece que las instituciones de educación superior deben expedir políticas de ética y honestidad académica. Considera como conductas de fraude o deshonestidad académica la vulneración de los derechos de autor, la utilización de recursos no autorizados durante una evaluación, la reproducción de creaciones intelectuales sin el reconocimiento correspondiente, la suplantación de identidad y el acceso no autorizado a reactivos o respuestas. Estas disposiciones son aplicables al Examen Complexivo, al Proyecto de Titulación y al Artículo Científico.

El artículo 85 dispone que, una vez aprobados todos los créditos del plan de estudios y cumplidos los requisitos académicos y administrativos establecidos para la graduación, la institución emitirá el acta consolidada de finalización de estudios y el título correspondiente. El acta deberá contener los datos de identificación del estudiante, el registro de calificaciones y la información académica requerida por la normativa.

Reglamento de la Unidad de Titulación y Eficiencia Terminal

En el ámbito institucional, el proceso se regula mediante el Reglamento de la Unidad de Titulación y Eficiencia Terminal, identificado con el código UTET-REG-25, versión 2.0. Este documento constituye el instrumento interno que establece las condiciones específicas para la organización, ejecución, evaluación y finalización del proceso de titulación del Instituto.

El Reglamento tiene por objeto normar el proceso de titulación de las carreras de tercer nivel técnico, tecnológico superior y tecnológico universitario ofertadas por el Instituto. Su finalidad es establecer los lineamientos, requisitos, modalidades, procedimientos, responsabilidades y criterios de evaluación aplicables a todas las fases del proceso, garantizando su pertinencia, transparencia, equidad y correspondencia con el perfil de egreso de cada carrera.

Sus disposiciones son de cumplimiento obligatorio para los estudiantes, docentes, tutores, tribunales evaluadores, coordinadores de carrera, autoridades institucionales y personal académico-administrativo que participe en el proceso de titulación. El Reglamento es aplicable a las diferentes modalidades académicas, jornadas, sedes y carreras de tercer nivel técnico y tecnológico del Instituto.

La normativa institucional regula los requisitos académicos, administrativos y financieros que debe cumplir el estudiante para acceder al proceso. Entre los requisitos académicos se encuentran la aprobación de la totalidad de las asignaturas de la malla curricular, el registro completo de las calificaciones en el sistema académico institucional y la inexistencia de inconsistencias que afecten el historial académico del estudiante. La verificación de estos requisitos corresponde a las unidades académicas y administrativas responsables.

El Reglamento reconoce como modalidades institucionales el Proyecto de Titulación, el Examen Complexivo y el Artículo Científico. Cada modalidad cuenta con requisitos, procedimientos, responsables, instrumentos de evaluación, oportunidades ordinarias y mecanismos supletorios específicos.

Para el Examen Complexivo, la normativa institucional establece un componente teórico y un componente práctico. El componente teórico corresponde al 40 % y el componente práctico al 60 %. Cada componente debe alcanzar una calificación mínima de 7/10 y no se permite compensar una calificación inferior mediante el promedio entre las partes.

Para el Proyecto de Titulación se establece una ponderación del 60 % para el documento escrito y del 40 % para la defensa oral. Para los proyectos y artículos se contempla, además, la aplicación de instrumentos institucionales de evaluación y la revisión mediante software antiplagio, de acuerdo con los criterios definidos por la unidad responsable.

La normativa interna también regula la planificación y publicación de los cronogramas, las convocatorias oficiales, la inscripción de estudiantes, la designación de responsables, la asignación de tutores y tribunales, el registro de calificaciones, la emisión de actas, los procesos de apelación, las oportunidades supletorias y la finalización institucional del proceso de titulación.

Manual de Procesos de la Unidad de Titulación y Eficiencia Terminal

El Manual de Procesos de la Unidad de Titulación y Eficiencia Terminal, versión 2, constituye el instrumento institucional mediante el cual se organizan de manera sistemática los procesos, actividades, responsables, documentos e indicadores relacionados con la gestión de la titulación y la eficiencia terminal.

El Manual tiene como objetivo establecer de forma clara y ordenada los procesos, procedimientos, responsabilidades e indicadores que rigen el funcionamiento de la Unidad de Titulación y Eficiencia Terminal. Asimismo, busca garantizar una gestión académica y administrativa eficiente, transparente y oportuna, facilitar la planificación, ejecución, seguimiento y evaluación de las modalidades de titulación y contribuir al mejoramiento continuo de los procesos académicos institucionales.

Para el desarrollo y evaluación del proceso de titulación, el Manual contempla los siguientes procesos institucionales:

UTET-PRO-94: Regulación de la normativa de la Unidad de Titulación y Eficiencia Terminal.
UTET-PRO-56: Planificación semestral del proceso de titulación.
UTET-PRO-95: Evaluación semestral del proceso de titulación.
UTET-PRO-58: Seguimiento de requisitos.
UTET-PRO-59: Gestión de guías de integración curricular.
UTET-PRO-88: Ejecución de seminarios complexivos.
UTET-PRO-93: Ejecución del Examen Complexivo.
UTET-PRO-96: Ingreso al Trabajo de Titulación.
UTET-PRO-164: Ejecución del Trabajo de Titulación.
UTET-PRO-57: Gestión del Artículo Académico.
UTET-PRO-97: Inducción al proceso de titulación.

Estos procesos establecen las actividades que deben ejecutarse durante la regulación, planificación, inducción, verificación de requisitos, preparación académica, evaluación, registro de resultados y cierre del proceso de titulación.

De manera particular, el proceso UTET-PRO-95, Evaluación Semestral del Proceso de Titulación, establece la revisión de las actividades planificadas, la consolidación de los resultados, la identificación de observaciones, la recopilación de evidencias y la elaboración del Informe Final del Proceso de Titulación. También contempla la revisión, aprobación, respaldo y archivo de la documentación generada.

Aplicación del marco legal y normativo

El presente Informe Final del Proceso de Titulación se elabora en observancia de las disposiciones constitucionales, legales, reglamentarias e institucionales anteriormente señaladas. Su contenido permite documentar la planificación y ejecución de las actividades, verificar el cumplimiento de los requisitos académicos y administrativos, consolidar los resultados por carrera y modalidad de titulación, diferenciar las evaluaciones ordinarias y supletorias, determinar el estado final de los estudiantes y generar información para el seguimiento institucional.

Las condiciones específicas relacionadas con los requisitos de habilitación, las modalidades de titulación, las ponderaciones, la calificación mínima de aprobación, las oportunidades supletorias, la actuación de tutores y evaluadores, el registro de calificaciones y la emisión de actas se aplican conforme al Reglamento de la Unidad de Titulación y Eficiencia Terminal y a los procedimientos establecidos en el Manual de Procesos de la UTET.

Este marco legal y normativo garantiza que el proceso de titulación se desarrolle bajo criterios de legalidad, igualdad de oportunidades, transparencia, calidad académica, honestidad, trazabilidad y mejora continua."""


SECTION_TEMPLATES: tuple[SectionTemplate, ...] = (
    SectionTemplate(
        key="marco_legal",
        title="Marco legal y normativo",
        mode="fixed",
        order=10,
        help_text="Plantilla institucional estable. Debe confirmarse la vigencia del Reglamento UTET-REG-25, versión 2.0, y del Manual de Procesos, versión 2, para el período analizado.",
        content=MARCO_LEGAL_Y_NORMATIVO,
    ),
    SectionTemplate(
        key="reglamento",
        title="Reglamento del examen complexivo",
        mode="fixed",
        order=20,
        help_text="Plantilla institucional estable. Revise únicamente reglas que hayan cambiado.",
        content="""El examen complexivo constituye una opción de titulación mediante la cual los estudiantes demuestran el dominio integral de las competencias, conocimientos y resultados de aprendizaje previstos en el perfil de egreso de su carrera.

Para el período {{periodo}}, el proceso correspondiente a la modalidad {{modalidad}} comprende la verificación de requisitos, la preparación académica, la aplicación de la evaluación ordinaria, el registro de calificaciones y, cuando corresponda, la evaluación supletoria.

La evaluación se integra por dos componentes: el componente teórico, con una ponderación del 40 %, y el componente práctico, con una ponderación del 60 %. La calificación final se expresa sobre 100 puntos y se considera aprobatoria cuando alcanza al menos 70 puntos.

El componente teórico valora la comprensión y aplicación de conocimientos esenciales de la carrera. El componente práctico valora la capacidad para resolver casos, problemas, simulaciones o situaciones propias del campo profesional. Ambos componentes deben guardar correspondencia con los núcleos estructurantes y con el perfil de egreso.

Los estudiantes que no alcancen la calificación mínima en la evaluación ordinaria podrán rendir el componente supletorio que corresponda, de acuerdo con la planificación institucional. La nota supletoria reemplaza únicamente el componente evaluado para efectos del resultado final utilizado por Informtit, sin alterar el registro original proveniente de la plataforma académica.

La Coordinación de Titulación organiza y supervisa el proceso; las coordinaciones de carrera y los docentes responsables garantizan la pertinencia de los instrumentos; y los estudiantes deben cumplir los requisitos, fechas y disposiciones comunicadas oficialmente.""",
    ),
    SectionTemplate(
        key="metodologia",
        title="Metodología de núcleos estructurantes",
        mode="fixed",
        order=30,
        help_text="Plantilla institucional estable. El contenido específico de cada núcleo se administra por carrera.",
        content="""La metodología de núcleos estructurantes orienta la preparación y evaluación de los estudiantes mediante la integración de conocimientos teóricos, prácticos y metodológicos vinculados con el perfil de egreso de cada carrera.

Cada carrera organiza sus contenidos esenciales en núcleos que articulan asignaturas, ejes temáticos y resultados de aprendizaje. Esta organización permite evaluar el dominio de saberes fundamentales y la capacidad para aplicarlos en problemas, casos o situaciones relacionadas con el ejercicio profesional.

La metodología se desarrolla mediante cuatro momentos complementarios: planificación de competencias y contenidos; preparación académica; aplicación de actividades y evaluaciones; y seguimiento de resultados. Durante el proceso se emplean estrategias como análisis de casos, resolución de problemas, simulaciones, proyectos integradores, bancos de preguntas y retroalimentación académica.

Los contenidos particulares de los núcleos se presentan por carrera y pueden actualizarse cuando existan cambios curriculares, ajustes en el perfil de egreso o necesidades identificadas por las coordinaciones académicas.""",
    ),
    SectionTemplate(
        key="cronograma",
        title="Cronograma del proceso",
        mode="periodic",
        order=40,
        help_text="Se conserva la estructura; en cada informe se actualizan el período, las fechas, responsables y actividades que hayan cambiado.",
        content="""El proceso de titulación correspondiente al período {{periodo}} se ejecutó mediante una planificación que comprendió la convocatoria, verificación de requisitos, preparación académica, aplicación del examen complexivo ordinario, registro de calificaciones, evaluación supletoria y publicación de resultados.

La tabla del cronograma debe conservar la estructura institucional de actividades, responsable, fecha de inicio, fecha de finalización y estado. Para este informe únicamente se actualizarán las fechas, responsables o actividades que hayan variado con respecto al período anterior.""",
    ),
    SectionTemplate(
        key="analisis_estrategico",
        title="Análisis estratégico",
        mode="generated",
        order=90,
        help_text="Contenido variable. Debe generarse con los resultados consolidados del período y revisarse antes de exportar.",
        content="""El análisis estratégico del período {{periodo}} se desarrolla a partir de los resultados consolidados de las carreras de modalidad {{modalidad}}, considerando el cumplimiento de requisitos, la participación en las evaluaciones ordinarias y supletorias, los porcentajes de aprobación y las diferencias observadas entre los componentes teórico y práctico.

Este apartado deberá completarse automáticamente con los principales hallazgos de la cohorte y revisarse para evitar afirmaciones que no estén sustentadas en los datos procesados por Informtit.""",
    ),
    SectionTemplate(
        key="conclusiones",
        title="Conclusiones",
        mode="generated",
        order=100,
        help_text="Contenido variable. Se genera con los resultados del período y requiere aprobación humana.",
        content="""Las conclusiones del período {{periodo}} deben sintetizar los resultados generales del proceso de titulación, el nivel de aprobación alcanzado, la incidencia de las evaluaciones supletorias y los principales hallazgos identificados por carrera.

Informtit generará este apartado a partir de los datos consolidados. La versión final deberá ser revisada y aprobada antes de incorporarse al informe institucional.""",
    ),
    SectionTemplate(
        key="recomendaciones",
        title="Recomendaciones",
        mode="generated",
        order=110,
        help_text="Contenido variable. Se deriva de los hallazgos y requiere revisión antes de exportar.",
        content="""Las recomendaciones del período {{periodo}} deben responder directamente a los hallazgos cuantitativos y cualitativos del informe, priorizando acciones de mejora relacionadas con la preparación académica, la gestión de requisitos, la evaluación de los componentes teórico y práctico y el seguimiento de estudiantes.

Informtit generará una propuesta inicial basada en los resultados. Las recomendaciones definitivas deberán ser pertinentes, viables y revisadas por los responsables institucionales.""",
    ),
)


LEGACY_PLACEHOLDERS = {
    "El presente apartado consolida la normativa institucional y nacional que sustenta el proceso de titulación.",
    "Este apartado describe los lineamientos aplicables al componente teórico, práctico, ordinario y supletorio.",
    "La metodología integra conocimientos teóricos y prácticos de acuerdo con el perfil de egreso de cada carrera.",
    "Registre aquí las actividades, responsables, fechas y estado de ejecución del proceso de titulación.",
    "El análisis estratégico se completará con base en los resultados consolidados de la cohorte.",
    "Las conclusiones deberán ser revisadas y aprobadas antes de exportar el informe final.",
    "Las recomendaciones deberán corresponder a los hallazgos cuantitativos y cualitativos del informe.",
}


def template_by_key(section_key: str) -> SectionTemplate | None:
    return next((template for template in SECTION_TEMPLATES if template.key == section_key), None)


def readable_modality(value: str) -> str:
    return "en línea" if value == "en_linea" else "presencial"


def resolve_template(template: str, report: dict[str, Any]) -> str:
    replacements = {
        "{{periodo}}": str(report.get("period") or "el período académico correspondiente"),
        "{{modalidad}}": readable_modality(str(report.get("modality") or "presencial")),
        "{{nombre_informe}}": str(report.get("name") or "Informe final del proceso de titulación"),
    }
    resolved = template
    for token, value in replacements.items():
        resolved = resolved.replace(token, value)
    return resolved
