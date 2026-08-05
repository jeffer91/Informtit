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


SECTION_TEMPLATES: tuple[SectionTemplate, ...] = (
    SectionTemplate(
        key="marco_legal",
        title="Marco legal",
        mode="fixed",
        order=10,
        help_text="Plantilla institucional estable. Solo debe modificarse cuando cambie la normativa aplicable.",
        content="""El presente marco legal fundamenta el proceso de titulación desarrollado por el Instituto Tecnológico Superior Quito Metropolitano durante el período {{periodo}}, en concordancia con la Constitución de la República del Ecuador, la Ley Orgánica de Educación Superior, el Reglamento de Régimen Académico, la normativa emitida por los organismos de educación superior y la reglamentación institucional vigente.

Estas disposiciones orientan la planificación, ejecución, evaluación y registro de las opciones de titulación, garantizando igualdad de oportunidades, transparencia, calidad académica y correspondencia con el perfil de egreso de cada carrera.

En este marco, el examen complexivo se concibe como una evaluación integral de los conocimientos, habilidades y desempeños desarrollados durante la formación. El proceso contempla la verificación previa de requisitos académicos, administrativos y financieros; la aplicación de los componentes teórico y práctico; el registro de resultados; y, cuando corresponda, la evaluación supletoria.

La institución mantiene el compromiso de revisar periódicamente la normativa aplicable y de ajustar sus procedimientos cuando se produzcan reformas legales, reglamentarias o institucionales que incidan en el proceso de titulación.""",
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
    return next(
        (template for template in SECTION_TEMPLATES if template.key == section_key),
        None,
    )


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
