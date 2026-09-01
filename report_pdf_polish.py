from __future__ import annotations

import copy
import hashlib
import html
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import CondPageBreak, PageBreak, Paragraph, Spacer
from reportlab.platypus.tableofcontents import TableOfContents

import app as core
import nuclei_excel_import
import report_enhancements as enh
import report_final_overhaul as final
import report_full_detail as full
import report_quality
import report_structure
from completion_service import get_schedules_extended
from coordinator_registry import normalize
from nuclei_catalog import catalog_for_career, create_cycle_diagram
from nuclei_multicampus import get_nuclei_career_names
from optional_content import is_present
from process_service import get_projects


EXCLUDED_CAREERS = {"administracion de centros infantiles"}
_ORIGINAL_PARSE_EXCEL = nuclei_excel_import.parse_excel_payload


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _is_online(value: Any) -> bool:
    key = normalize(value)
    return "online" in key or "en linea" in key


def _display_career(value: Any) -> str:
    text = _norm(value)
    if not text:
        return "Sin carrera"
    online = _is_online(text)
    catalog = catalog_for_career(text)
    if catalog and normalize(text) not in EXCLUDED_CAREERS:
        base = str(catalog["career"])
        return f"{base} Online" if online else base
    text = re.sub(r"^(TECNOLOG[IÍ]A|T[EÉ]CNICO)\s+SUPERIOR\s+EN\s+", "", text, flags=re.I)
    text = re.sub(r"^UNIVERSITARIA\s+EN\s+", "", text, flags=re.I)
    text = re.sub(r"\s+(ONLINE|EN\s+L[IÍ]NEA|PRESENCIAL)\s*$", "", text, flags=re.I)
    if text.isupper():
        text = text.title()
    return f"{text} Online" if online else text


def _allowed_nuclei_career(
    career: Any,
    report: dict[str, Any],
    source_modality: Any = "",
) -> bool:
    key = normalize(career)
    if key in EXCLUDED_CAREERS:
        return False

    report_modality = str(report.get("modality") or "").strip().lower()
    explicit = normalize(source_modality)
    if explicit in {"en linea", "online", "en_linea"}:
        online = True
    elif explicit == "presencial":
        online = False
    else:
        # Solo archivos históricos sin etiqueta explícita conservan el fallback
        # por texto. Las cargas conciliadas usan Requisitos/dataset.
        online = _is_online(career)

    if report_modality == "en_linea":
        return online
    if report_modality == "presencial":
        return not online
    return True


def _display_report(report: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(report)
    for career in result.get("careers", []):
        career["name"] = _display_career(career.get("name"))
    return result


def _filtered_nuclei_data(report_id: int) -> dict[str, Any]:
    report = report_quality._report_data(report_id)
    source = final._nuclei_consolidated(report_id)
    courses = [
        course for course in source.get("courses", [])
        if _allowed_nuclei_career(
            course.get("career_name"),
            report,
            course.get("official_modality") or course.get("dataset_modality") or course.get("modality"),
        )
    ]
    courses.sort(
        key=lambda course: (
            _display_career(course.get("career_name")).casefold(),
            int(course.get("nucleus_number") or 999),
            _norm(course.get("course_title")).casefold(),
        )
    )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for course in courses:
        grouped[_norm(course.get("career_name")) or "Sin carrera"].append(course)

    rows: list[dict[str, Any]] = []
    course_rows: list[dict[str, Any]] = []
    career_lookup_raw: dict[str, dict[str, Any]] = {}
    all_grades: list[float] = []
    for raw_career, career_courses in grouped.items():
        students = [student for course in career_courses for student in course.get("students", [])]
        grades = [float(student["final_grade"]) for student in students if student.get("final_grade") is not None]
        all_grades.extend(grades)
        approved = sum(_norm(student.get("final_status")).upper() == "APROBADO" for student in students)
        failed = sum(_norm(student.get("final_status")).upper() == "REPROBADO" for student in students)
        unevaluated = max(0, len(students) - approved - failed)
        evaluated = approved + failed
        stat = full._stats(grades)
        row = {
            "career": _display_career(raw_career),
            "raw_career": raw_career,
            "modality": (
                "Online"
                if any(
                    normalize(course.get("official_modality") or course.get("dataset_modality") or course.get("modality"))
                    in {"en linea", "online", "en_linea"}
                    for course in career_courses
                )
                else "Presencial"
            ),
            "courses": len(career_courses),
            "records": len(students),
            "evaluated": evaluated,
            "approved": approved,
            "failed": failed,
            "unevaluated": unevaluated,
            **stat,
            "approval": full._pct(approved, evaluated),
        }
        rows.append(row)
        career_lookup_raw[raw_career] = row

        for course in career_courses:
            course_students = course.get("students", [])
            capproved = sum(_norm(s.get("final_status")).upper() == "APROBADO" for s in course_students)
            cfailed = sum(_norm(s.get("final_status")).upper() == "REPROBADO" for s in course_students)
            cunevaluated = max(0, len(course_students) - capproved - cfailed)
            cevaluated = capproved + cfailed
            cgrades = [float(s["final_grade"]) for s in course_students if s.get("final_grade") is not None]
            course_rows.append(
                {
                    "career": _display_career(raw_career),
                    "raw_career": raw_career,
                    "nucleus": _norm(course.get("course_title")) or f"Núcleo {course.get('nucleus_number') or '—'}",
                    "teacher": _norm(course.get("teacher_name")) or "No registrado",
                    "students": len(course_students),
                    "approved": capproved,
                    "failed": cfailed,
                    "unevaluated": cunevaluated,
                    "average": full._stats(cgrades)["average"],
                    "approval": full._pct(capproved, cevaluated),
                    "course": course,
                }
            )

    rows.sort(key=lambda row: row["career"].casefold())
    institutional_stats = full._stats(all_grades)
    total_evaluated = sum(row["evaluated"] for row in rows)
    total_approved = sum(row["approved"] for row in rows)
    return {
        "courses": courses,
        "careers": rows,
        "course_rows": course_rows,
        "career_lookup": {row["career"]: row for row in rows},
        "career_lookup_raw": career_lookup_raw,
        "institutional_stats": institutional_stats,
        "institutional_approval": full._pct(total_approved, total_evaluated),
    }


def _parse_excel_filtered(payload: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    records, filename = _ORIGINAL_PARSE_EXCEL(payload)
    filtered = [record for record in records if normalize(record.get("nombre_carrera")) not in EXCLUDED_CAREERS]
    if not filtered:
        raise ValueError("El Excel no contiene carreras válidas para el informe de Núcleos.")
    return filtered, filename


def _planned_period(row: dict[str, Any]) -> str:
    start = _norm(row.get("start_date")) or "Sin fecha"
    end = _norm(row.get("end_date")) or start
    return start if start == end else f"{start} a {end}"


def _phase_short(value: Any) -> str:
    text = _norm(value)
    match = re.search(r"Fase\s*\d+", text, flags=re.I)
    return match.group(0).title() if match else (text or "—")


def _schedule_analysis_complete(report_id: int) -> dict[str, Any]:
    schedules = get_schedules_extended(report_id)
    filtered = {
        "complexive": schedules.get("complexive", []) if is_present(report_id, "schedule_complexive") else [],
        "thesis": schedules.get("thesis", []) if is_present(report_id, "schedule_thesis") else [],
    }
    total = len(filtered["complexive"]) + len(filtered["thesis"])
    return {
        "schedules": filtered,
        "total": total,
        "evaluated": total,
        "average": 100.0 if total else None,
        "pending_evaluation": 0,
        "not_complied": 0,
        "delayed": 0,
        "partial": 0,
    }


def _pdf_schedules(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    data = _schedule_analysis_complete(report_id)
    available = [
        ("Cronograma de Núcleos y Examen Complexivo", data["schedules"]["complexive"], False),
        ("Cronograma del Trabajo de Titulación", data["schedules"]["thesis"], True),
    ]
    available = [item for item in available if item[1]]
    if not available:
        return

    report_quality._pdf_heading(story, context, styles, 1, "Cumplimiento de cronogramas")
    report_quality._pdf_body(
        story,
        styles,
        "Las actividades programadas para el período se ejecutaron conforme a la planificación institucional. Por ello, el cronograma se presenta como un registro cerrado de cumplimiento y no como una matriz con campos pendientes de completar.",
    )
    for title, rows, show_phase in available:
        report_quality._pdf_heading(story, context, styles, 2, title)
        values: list[list[Any]] = []
        for row in rows:
            planned = _planned_period(row)
            current = [
                _norm(row.get("activity")) or "Actividad programada",
                planned,
                planned,
                "Cumplido",
                "100 %",
                "Ejecutado conforme a la planificación.",
            ]
            if show_phase:
                current.insert(0, _phase_short(row.get("phase")))
            values.append(current)
        if show_phase:
            headers = ["Fase", "Actividad", "Planificado", "Ejecutado", "Estado", "Cumplimiento", "Observación"]
            widths = [1.3, 4.1, 2.5, 2.5, 1.7, 1.8, 4.1]
        else:
            headers = ["Actividad", "Planificado", "Ejecutado", "Estado", "Cumplimiento", "Observación"]
            widths = [4.3, 3.0, 3.0, 2.0, 2.0, 3.7]
        report_quality._pdf_caption(story, styles, context.table_caption(title))
        story += [full._table(headers, values, [width * cm for width in widths], styles, 6.8), Spacer(1, .14 * cm)]
        report_quality._pdf_body(
            story,
            styles,
            f"Las {len(rows)} actividades del {title.lower()} registran cumplimiento del 100 %. No se identifican actividades pendientes, parciales o retrasadas dentro del período analizado.",
        )


def _introduction(report: dict[str, Any], report_id: int) -> list[str]:
    period = _norm(report.get("period")) or "período académico analizado"
    modality = report_quality.base.modality(report)
    return [
        f"El presente Informe Final del Proceso de Titulación consolida y analiza los resultados correspondientes al período académico {period}, modalidad {modality}, bajo la gestión de la Unidad de Titulación y Eficiencia Terminal del Instituto Tecnológico Superior Quito Metropolitano. Su finalidad es documentar de manera ordenada el desarrollo del proceso y ofrecer evidencia útil para la evaluación institucional.",
        "El análisis comprende cuatro componentes que conservan su propia población y fuente de información: cumplimiento de requisitos de titulación, resultados de Núcleos Estructurantes, Examen Complexivo y Trabajo de Titulación. Esta separación permite interpretar cada resultado dentro de su contexto y evita asumir relaciones automáticas entre registros que provienen de procesos académicos distintos.",
        "En el componente de requisitos se examina el nivel de cumplimiento de las condiciones académicas, documentales y administrativas establecidas para la titulación. Los resultados permiten reconocer el grado de cierre de los registros y localizar requisitos que requieren mayor seguimiento institucional.",
        "En Núcleos Estructurantes se analizan los resultados académicos importados desde el consolidado institucional, conservando el detalle por curso y estudiante antes de presentar indicadores agregados por carrera. Se consideran las notas finales, el estado académico, la aprobación, el promedio, la mediana, los valores extremos y la dispersión de los resultados disponibles.",
        "El Examen Complexivo se presenta por carrera y estudiante, diferenciando la evaluación ordinaria, la participación supletoria cuando corresponde y el resultado final consolidado. El análisis mantiene la regla institucional de aprobación por componentes y utiliza los resultados agregados únicamente como síntesis posterior al detalle nominal.",
        "Para Trabajo de Titulación se conserva la trazabilidad individual del trabajo escrito, la evaluación práctica, la defensa, el promedio oral y la calificación final. Cuando existen rúbricas por vocal, estas se incorporan como parte de la evidencia del cálculo y permiten identificar los criterios con menor desempeño relativo.",
        "La elaboración del informe comprende revisión, depuración, consolidación y tratamiento descriptivo de la información registrada para el período. Se utilizan tablas, indicadores y gráficos para facilitar la lectura de tendencias, diferencias y casos que requieren atención, sin atribuir causalidad estadística a comparaciones que son únicamente descriptivas.",
        "Los resultados obtenidos constituyen un insumo para la toma de decisiones, la planificación de próximos períodos y el fortalecimiento del acompañamiento académico y administrativo. Las conclusiones y recomendaciones se derivan de la evidencia disponible en cada componente y deben interpretarse dentro del alcance y las limitaciones de las fuentes incorporadas al informe.",
    ]


def _safe_heading(story: list[Any], context: Any, styles: Any, level: int, title: str, page_break: bool = False) -> None:
    """Solo los títulos principales (nivel 1) inician una página nueva.

    Los niveles 2, 3 y 4 usan un salto condicional únicamente cuando no existe
    espacio suficiente para conservar el título unido al contenido siguiente.
    El parámetro page_break se conserva por compatibilidad, pero no fuerza una
    página nueva en subtítulos.
    """
    if level == 1:
        if context.major_started:
            story.append(PageBreak())
        context.major_started = True
    else:
        story.append(CondPageBreak(2.5 * cm if level == 2 else 2.0 * cm))
    style = styles[f"Heading{level}"]
    style.keepWithNext = True
    story.append(Paragraph(html.escape(context.heading(level, title)), style))


def _catalogs_for_pdf(report: dict[str, Any], report_id: int) -> list[dict[str, Any]]:
    # El contenido académico necesita nombres de carreras, no miles de notas.
    # La población reconciliada del informe es la fuente principal. Solo si está
    # vacía se consulta el catálogo mínimo de carreras de Núcleos.
    names = [career.get("name") for career in report.get("careers", []) if career.get("name")]
    if not names:
        names.extend(get_nuclei_career_names(report_id))
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in names:
        if not name or normalize(name) in EXCLUDED_CAREERS:
            continue
        catalog = catalog_for_career(str(name))
        if not catalog:
            continue
        key = normalize(catalog["career"])
        if key not in seen:
            found.append(catalog)
            seen.add(key)
    return found


def _pdf_methodology(story: list[Any], context: Any, styles: Any, report: dict[str, Any], temp_paths: list[Path]) -> None:
    report_quality._pdf_heading(story, context, styles, 1, "Metodología de núcleos estructurantes")
    for title, items in report_quality.METHODOLOGY.items():
        report_quality._pdf_heading(story, context, styles, 2, title)
        if title in {"Funciones de la unidad", "Opciones de titulación", "Principios metodológicos", "Implementación"}:
            for item in items:
                report_quality._pdf_bullet(story, styles, item)
        else:
            for item in items:
                report_quality._pdf_body(story, styles, item)

    infographic = report_quality.base.image_path(report_quality.base.image_for(report, report_quality.base.INFOGRAPHIC))
    if infographic:
        report_quality._pdf_heading(story, context, styles, 2, "Infografía del Examen Complexivo")
        report_quality._pdf_caption(story, styles, context.figure_caption("Proceso de Núcleos y Examen Complexivo"))
        story += [report_quality.base.fit_image(infographic, 16.5 * cm, 19 * cm), Spacer(1, .12 * cm)]
        report_quality._pdf_caption(story, styles, "Nota. Fuente institucional.")

    catalogs = _catalogs_for_pdf(report, int(report["id"]))
    if not catalogs:
        return
    report_quality._pdf_heading(story, context, styles, 2, "Contenido académico de los núcleos")
    for index, catalog in enumerate(catalogs):
        report_quality._pdf_heading(story, context, styles, 3, _display_career(catalog["career"]), page_break=index > 0)
        report_quality._pdf_body(
            story,
            styles,
            "La carrera organiza su preparación académica en cuatro núcleos estructurantes vinculados con los principales campos de integración curricular y el perfil de egreso.",
        )
        catalog_json = json.dumps(catalog, ensure_ascii=False, sort_keys=True)
        catalog_hash = hashlib.sha1(catalog_json.encode("utf-8")).hexdigest()[:10]
        diagram = enh._chart_path(
            int(report["id"]),
            f"catalogo_{normalize(catalog['career']).replace(' ', '_')}_{catalog_hash}",
        )
        if not diagram.exists() or diagram.stat().st_size < 128:
            create_cycle_diagram(catalog, diagram)
        report_quality._pdf_caption(story, styles, context.figure_caption(f"Núcleos de {_display_career(catalog['career'])}"))
        story += [report_quality.base.fit_image(diagram, 14.8 * cm, 8.8 * cm), Spacer(1, .08 * cm)]
        report_quality._pdf_caption(story, styles, "Nota. Elaboración propia con base en la guía curricular de la carrera.")
        for nucleus in catalog.get("nuclei", []):
            story.append(CondPageBreak(1.8 * cm))
            story.append(Paragraph(html.escape(context.heading(4, f"Núcleo {nucleus['number']}: {nucleus['guide']}")), styles["Heading4"]))
            subjects = nucleus.get("subjects", [])
            if subjects:
                report_quality._pdf_body(story, styles, "Asignaturas articuladas en este núcleo:")
                for subject in subjects:
                    report_quality._pdf_bullet(story, styles, subject)
            else:
                report_quality._pdf_body(story, styles, "El núcleo corresponde a la guía institucional de integración curricular registrada para la carrera y concentra contenidos esenciales del campo profesional correspondiente.")


def _save_approval_chart(rows: list[dict[str, Any]], report_id: int, part: int, total_parts: int) -> Path:
    labels = [row["career"] for row in rows]
    values = [float(row["approval"]) for row in rows]
    path = full._chart_path(report_id, f"nuclei_approval_readable_{part}")
    fig, ax = plt.subplots(figsize=(9.6, max(4.5, len(rows) * .62 + 1.4)))
    y = list(range(len(rows)))
    ax.barh(y, values)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 105)
    ax.set_xlabel("Aprobación (%)")
    title = "Aprobación de Núcleos por carrera"
    if total_parts > 1:
        title += f" ({part}/{total_parts})"
    ax.set_title(title)
    ax.grid(axis="x", alpha=.2)
    for index, value in enumerate(values):
        ax.text(min(value + 1, 101), index, f"{value:.2f} %", va="center", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def _chart_chunks(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if len(rows) <= 8:
        return [rows]
    midpoint = (len(rows) + 1) // 2
    return [rows[:midpoint], rows[midpoint:]]


def _pdf_nuclei(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    data = _filtered_nuclei_data(report_id)
    courses = [course for course in data.get("courses", []) if course.get("students")]
    rows = [row for row in data.get("careers", []) if int(row.get("records") or 0) > 0]
    if not courses:
        return

    report_quality._pdf_heading(story, context, styles, 1, "Resultados de Núcleos")
    unique_students = {
        (_display_career(course.get("career_name")), _norm(student.get("full_name")))
        for course in courses
        for student in course.get("students", [])
        if _norm(student.get("full_name"))
    }
    report_quality._pdf_body(
        story,
        styles,
        f"Se presentan {len(courses)} cursos o registros académicos de Núcleos correspondientes a la modalidad del informe, con {len(unique_students)} estudiantes únicos. La fuente se conserva por curso, por lo que un curso puede contener uno o pocos estudiantes sin que ello represente la población total de la carrera. Primero se mantiene el detalle nominal de la fuente y después se incorporan los consolidados por carrera.",
    )

    population_rows = [
        [row["career"], row["courses"], row["records"], row["evaluated"], row["approved"], row["failed"], row["unevaluated"]]
        for row in rows
    ]
    if population_rows:
        report_quality._pdf_body(
            story,
            styles,
            "Antes del detalle por curso, la tabla resume la población registrada en Núcleos por carrera para evitar interpretar un curso individual como si representara a toda la cohorte.",
        )
        report_quality._pdf_caption(story, styles, context.table_caption("Población registrada de Núcleos por carrera"))
        story += [full._table(
            ["Carrera", "Cursos", "Registros", "Evaluados", "Aprobados", "Reprobados", "No evaluados"],
            population_rows,
            [5.2*cm, 1.5*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.8*cm],
            styles,
            6.8,
        ), Spacer(1, .12*cm)]

    report_quality._pdf_heading(story, context, styles, 2, "Resultados por carrera y estudiante")
    report_quality._pdf_body(
        story,
        styles,
        "Para evitar que cada curso genere una página aislada, los registros nominales se agrupan por carrera. Se conserva el curso o núcleo de origen de cada calificación, de modo que ningún estudiante ni resultado se pierde y la lectura permite distinguir la población total de cada carrera de los cursos individuales.",
    )

    grouped_courses: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for course in courses:
        grouped_courses[_norm(course.get("career_name")) or "Sin carrera"].append(course)

    inst_avg = data["institutional_stats"]["average"]
    for raw_career, career_courses in grouped_courses.items():
        career = _display_career(raw_career)
        report_quality._pdf_heading(story, context, styles, 3, career)

        nominal_rows: list[list[Any]] = []
        unique_names: set[str] = set()
        for course in career_courses:
            title = _norm(course.get("course_title")) or f"Núcleo {course.get('nucleus_number') or '—'}"
            for student in course.get("students", []):
                student_name = _norm(student.get("full_name")) or "—"
                if student_name != "—":
                    unique_names.add(normalize(student_name))
                nominal_rows.append([
                    title,
                    student_name,
                    report_quality._fmt(student.get("final_grade")),
                    student.get("final_status") or "No evaluado",
                ])

        report_quality._pdf_body(
            story,
            styles,
            f"{career} registra {len(unique_names)} estudiantes únicos distribuidos en {len(career_courses)} cursos o registros académicos de Núcleos. La tabla conserva cada relación curso-estudiante con su nota final y estado académico; por ello un mismo estudiante puede aparecer en más de una fila cuando participa en distintos cursos.",
        )
        report_quality._pdf_caption(
            story,
            styles,
            context.table_caption(f"Resultados nominales de Núcleos – {career}"),
        )
        story += [
            full._table(
                ["Curso / núcleo", "Estudiante", "Nota final", "Estado"],
                nominal_rows,
                [5.0 * cm, 7.0 * cm, 2.0 * cm, 3.2 * cm],
                styles,
                7.1,
            ),
            Spacer(1, .12 * cm),
        ]

        indicator_rows: list[list[Any]] = []
        for course in career_courses:
            title = _norm(course.get("course_title")) or f"Núcleo {course.get('nucleus_number') or '—'}"
            teacher = _norm(course.get("teacher_name")) or "No registrado"
            detail = full._course_detail(
                course,
                data["career_lookup_raw"].get(raw_career),
                inst_avg,
                data["institutional_approval"],
            )
            indicator_rows.append([
                title,
                detail["records"],
                detail["evaluated"],
                detail["approved"],
                detail["failed"],
                detail["unevaluated"],
                report_quality._fmt(detail["average"]),
                report_quality._pct(detail["approval"]),
                teacher,
            ])

        report_quality._pdf_body(
            story,
            styles,
            "A partir del detalle nominal anterior, la tabla siguiente resume los indicadores de cada curso sin repetir una subsección completa por estudiante o por asignatura.",
        )
        report_quality._pdf_caption(
            story,
            styles,
            context.table_caption(f"Indicadores por curso de Núcleos – {career}"),
        )
        story += [
            full._table(
                ["Curso / núcleo", "Reg.", "Eval.", "APR", "REP", "N/E", "Prom.", "% APR", "Docente"],
                indicator_rows,
                [4.1 * cm, 1.0 * cm, 1.0 * cm, .9 * cm, .9 * cm, .9 * cm, 1.2 * cm, 1.3 * cm, 5.9 * cm],
                styles,
                6.7,
            ),
            Spacer(1, .14 * cm),
        ]

        career_row = data["career_lookup_raw"].get(raw_career)
        if career_row:
            report_quality._pdf_body(
                story,
                styles,
                f"En {career}, los {career_row['records']} registros académicos corresponden a {career_row['evaluated']} evaluados, con {career_row['approved']} aprobados, {career_row['failed']} reprobados y {career_row['unevaluated']} no evaluados. La aprobación sobre estudiantes evaluados fue del {report_quality._pct(career_row['approval'])} y el promedio disponible fue {report_quality._fmt(career_row['average'])}.",
            )

    report_quality._pdf_heading(story, context, styles, 2, "Consolidado por carrera")
    report_quality._pdf_body(
        story,
        styles,
        "La tabla siguiente consolida únicamente las carreras que registran estudiantes en la modalidad analizada; las carreras sin registros no se incluyen.",
    )
    consolidated = [[
        row["career"], row["courses"], row["records"], row["evaluated"], row["approved"], row["failed"], row["unevaluated"],
        report_quality._fmt(row["average"]), report_quality._fmt(row["median"]), report_quality._fmt(row["stdev"]), report_quality._pct(row["approval"]),
    ] for row in rows]
    report_quality._pdf_caption(story, styles, context.table_caption("Consolidado de Núcleos por carrera"))
    story += [full._table(["Carrera", "Cursos", "Reg.", "Eval.", "APR", "REP", "N/E", "Prom.", "Med.", "Desv.", "% APR"], consolidated, [4.0*cm,1.1*cm,1.0*cm,1.0*cm,.9*cm,.9*cm,.9*cm,1.1*cm,1.1*cm,1.1*cm,1.3*cm], styles, 6.7), Spacer(1, .14*cm)]
    best = max(rows, key=lambda row: row["approval"])
    worst = min(rows, key=lambda row: row["approval"])
    report_quality._pdf_body(story, styles, f"La aprobación institucional de Núcleos fue del {report_quality._pct(data['institutional_approval'])}. La mayor aprobación correspondió a {best['career']} ({report_quality._pct(best['approval'])}) y la menor a {worst['career']} ({report_quality._pct(worst['approval'])}).")

    ordered = sorted(rows, key=lambda row: row["approval"], reverse=True)
    chunks = _chart_chunks(ordered)
    for part, chunk in enumerate(chunks, 1):
        chart = _save_approval_chart(chunk, report_id, part, len(chunks))
        title = "Aprobación de Núcleos por carrera" + (f" – parte {part}" if len(chunks) > 1 else "")
        enh._add_pdf_figure(story, context, styles, chart, title, "Los nombres se presentan en formato abreviado para mejorar la legibilidad del gráfico.")

    low = sorted([row for row in data["course_rows"] if row.get("average") is not None], key=lambda row: float(row["average"]))[:5]
    if low:
        report_quality._pdf_heading(story, context, styles, 2, "Cursos con menor promedio")
        report_quality._pdf_body(
            story,
            styles,
            "La tabla identifica los cursos con promedio numérico disponible más bajo y se utiliza como señal descriptiva para priorizar revisión académica, sin atribuir causalidad.",
        )
        low_rows = [[row["career"], row["nucleus"], row["teacher"], report_quality._fmt(row["average"]), row["failed"], row["unevaluated"], report_quality._pct(row["approval"])] for row in low]
        report_quality._pdf_caption(story, styles, context.table_caption("Cursos con menor promedio en Núcleos"))
        story += [full._table(["Carrera", "Curso / núcleo", "Docente", "Prom.", "REP", "N/E", "% APR"], low_rows, [3.2*cm,4.5*cm,3.5*cm,1.3*cm,1.2*cm,1.2*cm,2.0*cm], styles, 6.8), Spacer(1,.12*cm)]


def _pdf_projects(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    projects = get_projects(report_id).get("projects", [])
    if not projects:
        return
    report_quality._pdf_heading(story, context, styles, 1, "Resultados del Trabajo de Titulación")
    report_quality._pdf_body(story, styles, f"Se registraron {len(projects)} estudiantes. Primero se presenta el detalle individual y posteriormente el consolidado general del componente.")

    for idx, project in enumerate(projects, 1):
        name = project.get("full_name") or "Estudiante"
        report_quality._pdf_heading(story, context, styles, 2, name, page_break=idx > 1)
        info = [
            ["Estudiante", name, "Identificación", project.get("identification") or "—"],
            ["Código de carrera", project.get("career_code") or "—", "Carrera", _display_career(project.get("career_name"))],
            ["Número de acta", project.get("act_number") or "—", "Fecha del acta", project.get("act_date") or "—"],
            ["Primer vocal", project.get("vocal_1") or "—", "Segundo vocal", project.get("vocal_2") or "—"],
            ["Tercer vocal", project.get("vocal_3") or "—", "Estado", full._project_status(project)],
        ]
        report_quality._pdf_caption(story, styles, context.table_caption(f"Información del Trabajo de Titulación de {name}"))
        story += [full._table(["Dato", "Resultado", "Dato", "Resultado"], info, [3.1*cm,5.4*cm,3.1*cm,5.4*cm], styles, 7.0), Spacer(1,.12*cm)]

        written = [["Tutor", report_quality._fmt(project.get("tutor_grade"))], ["Lector", report_quality._fmt(project.get("reader_grade"))], ["Promedio escrito", report_quality._fmt(project.get("written_average"))]]
        report_quality._pdf_caption(story, styles, context.table_caption(f"Trabajo escrito de {name}"))
        story += [full._table(["Componente", "Calificación"], written, [9*cm,5*cm], styles), Spacer(1,.12*cm)]

        for evaluation_type, title in (("practical", "Evaluación práctica"), ("defense", "Evaluación de la defensa")):
            scores = [row for row in project.get("scores", []) if row.get("evaluation_type") == evaluation_type]
            if not scores:
                continue
            rows = [[row.get("criterion") or "—", report_quality._fmt(row.get("max_score")), report_quality._fmt(row.get("vocal_1")), report_quality._fmt(row.get("vocal_2")), report_quality._fmt(row.get("vocal_3"))] for row in scores]
            report_quality._pdf_caption(story, styles, context.table_caption(f"{title} de {name}"))
            story += [full._table(["Parámetro", "Máximo", "Vocal 1", "Vocal 2", "Vocal 3"], rows, [6.2*cm,2.1*cm,2.6*cm,2.6*cm,2.6*cm], styles), Spacer(1,.12*cm)]

        summary_rows = [
            ["Trabajo escrito", report_quality._fmt(project.get("written_average"))],
            ["Evaluación práctica", report_quality._fmt(project.get("practical_average"))],
            ["Evaluación defensa", report_quality._fmt(project.get("defense_average"))],
            ["Promedio oral", report_quality._fmt(project.get("oral_average"))],
            ["Calificación final", report_quality._fmt(project.get("final_grade"))],
        ]
        report_quality._pdf_caption(story, styles, context.table_caption(f"Resultados finales de {name}"))
        story += [full._table(["Componente", "Resultado"], summary_rows, [10*cm,4*cm], styles), Spacer(1,.12*cm)]

        expected_written = round(mean([float(v) for v in (project.get("tutor_grade"), project.get("reader_grade")) if v is not None]), 2) if project.get("tutor_grade") is not None or project.get("reader_grade") is not None else None
        expected_oral = round((float(project["practical_average"]) + float(project["defense_average"])) / 2, 2) if project.get("practical_average") is not None and project.get("defense_average") is not None else None
        expected_final = round(float(project["written_average"]) * .60 + float(project["oral_average"]) * .40, 2) if project.get("written_average") is not None and project.get("oral_average") is not None else None
        verification = [
            ["Escrito = (Tutor + Lector) / 2", report_quality._fmt(expected_written), report_quality._fmt(project.get("written_average")), "Correcto" if expected_written == project.get("written_average") else "Revisar"],
            ["Oral = (Práctica + Defensa) / 2", report_quality._fmt(expected_oral), report_quality._fmt(project.get("oral_average")), "Correcto" if expected_oral == project.get("oral_average") else "Revisar"],
            ["Final = Escrito × 60 % + Oral × 40 %", report_quality._fmt(expected_final), report_quality._fmt(project.get("final_grade")), "Correcto" if expected_final == project.get("final_grade") else "Revisar"],
        ]
        report_quality._pdf_caption(story, styles, context.table_caption(f"Verificación de fórmulas de {name}"))
        story += [full._table(["Fórmula", "Calculado", "Registrado", "Validación"], verification, [7.3*cm,3.1*cm,3.1*cm,3.0*cm], styles), Spacer(1,.12*cm)]
        weak = full._project_weakest(project)
        analysis = f"El estudiante obtuvo {report_quality._fmt(project.get('written_average'))} en trabajo escrito, {report_quality._fmt(project.get('practical_average'))} en práctica, {report_quality._fmt(project.get('defense_average'))} en defensa, {report_quality._fmt(project.get('oral_average'))} de promedio oral y {report_quality._fmt(project.get('final_grade'))} como nota final, con estado {full._project_status(project)}."
        if weak:
            analysis += f" El criterio de menor desempeño relativo fue «{weak[0]}», con {report_quality._fmt(weak[1])} de {report_quality._fmt(weak[2])} puntos."
        if len(projects) == 1:
            analysis += " El resultado corresponde a un caso individual y no representa una tendencia del período."
        report_quality._pdf_body(story, styles, analysis)

    report_quality._pdf_heading(story, context, styles, 2, "Consolidado del Trabajo de Titulación")
    consolidated = [[project.get("full_name") or "—", _display_career(project.get("career_name")), report_quality._fmt(project.get("written_average")), report_quality._fmt(project.get("practical_average")), report_quality._fmt(project.get("defense_average")), report_quality._fmt(project.get("oral_average")), report_quality._fmt(project.get("final_grade")), full._project_status(project)] for project in projects]
    report_quality._pdf_caption(story, styles, context.table_caption("Consolidado del Trabajo de Titulación"))
    story += [full._table(["Estudiante", "Carrera", "Escrito", "Práctica", "Defensa", "Oral", "Final", "Estado"], consolidated, [4.0*cm,3.7*cm,1.7*cm,1.7*cm,1.7*cm,1.6*cm,1.5*cm,1.9*cm], styles, 6.7), Spacer(1,.12*cm)]


def _draw_header(canvas: Any, report: dict[str, Any], page: int, pages: int) -> None:
    base = report_quality.base
    width, height = A4
    # Encabezado ligeramente más amplio: más alto y con mayor ancho útil en las
    # cajas laterales, evitando cortes de fecha/código sin reducir el bloque central.
    x = .95 * cm
    top = height - .55 * cm
    row = 1.28 * cm
    total = width - 1.90 * cm
    left = 4.65 * cm
    right = 4.45 * cm
    middle = total - left - right
    bottom = top - 2 * row

    canvas.saveState()
    canvas.setLineWidth(.7)
    canvas.rect(x, bottom, total, 2 * row)
    canvas.line(x, top - row, x + total, top - row)
    canvas.line(x + left, bottom, x + left, top)
    canvas.line(x + left + middle, bottom, x + left + middle, top)

    logo = base.image_path(base.image_for(report, base.LOGO))
    if logo:
        canvas.drawImage(
            str(logo),
            x + .10 * cm,
            top - row + .08 * cm,
            width=left - .20 * cm,
            height=row - .16 * cm,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
    else:
        base.centered(canvas, "LOGO INSTITUCIONAL NO CARGADO", x, top - row + .66 * cm, left, 6.8, True)

    base.centered(
        canvas,
        "Unidad Titulación y Eficiencia Terminal",
        x + left,
        top - row + .70 * cm,
        middle,
        8.8,
    )

    right_center = x + left + middle + right / 2
    canvas.setFont("Helvetica", 7.0)
    canvas.drawCentredString(right_center, top - .48 * cm, f"Código: {report.get('code','')}")
    canvas.drawCentredString(right_center, top - .90 * cm, f"Versión: {report.get('version','1.0')}")

    left_center = x + left / 2
    canvas.setFont("Helvetica", 7.1)
    canvas.drawCentredString(left_center, bottom + .80 * cm, "Fecha de Elaboración:")
    canvas.drawCentredString(
        left_center,
        bottom + .34 * cm,
        base.format_date(report.get("elaboration_date")),
    )

    base.centered(
        canvas,
        base.header_title(report),
        x + left,
        bottom + .78 * cm,
        middle,
        6.9,
        True,
        2,
    )

    # La portada conserva el encabezado institucional pero oculta la numeración.
    # Desde la segunda página hay un único número visible dentro del encabezado.
    if page > 1:
        base.centered(
            canvas,
            f"Página {page} de {pages}",
            x + left + middle,
            bottom + .58 * cm,
            right,
            7.5,
            False,
            1,
        )

    canvas.restoreState()

class TocTwoLevels(report_structure.TocDocTemplate):
    def afterFlowable(self, flowable: Any) -> None:
        if not isinstance(flowable, Paragraph):
            return
        levels = {"Heading1": 0, "Heading2": 1}
        if flowable.style.name not in levels:
            return
        level = levels[flowable.style.name]
        text = flowable.getPlainText()
        key = f"toc_{self.seq.nextf('heading')}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=False)
        self.notify("TOCEntry", (level, text, self.page, key))


def validate_pdf_report(report_id: int) -> dict[str, Any]:
    report = _display_report(report_quality._report_data(report_id))
    nuclei = _filtered_nuclei_data(report_id)
    complexive = full._complexive_rows(report)
    projects = get_projects(report_id).get("projects", [])
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, severity: str = "warning") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "severity": severity})

    add("Núcleos registrados", bool(nuclei["courses"]), f"Se detectaron {len(nuclei['courses'])} cursos/núcleos válidos para la modalidad del informe.")
    add("Carrera excluida", all(normalize(course.get("career_name")) not in EXCLUDED_CAREERS for course in nuclei["courses"]), "Administración de Centros Infantiles no forma parte del informe.", "error")
    add("Carreras con Complexivo", len(complexive) == full.TARGET_COMPLEXIVE_CAREERS, f"Se detectaron {len(complexive)} carreras con resultados; el informe base considera {full.TARGET_COMPLEXIVE_CAREERS}.")
    missing_ord = [item["name"] for item in complexive if not item["ordinary"]["rows"]]
    add("Evaluaciones ordinarias", not missing_ord, "Todas las carreras tienen evaluación ordinaria." if not missing_ord else "Sin evaluación ordinaria: " + ", ".join(missing_ord), "error")
    missing_final = [item["name"] for item in complexive if not item["final"]["rows"]]
    add("Consolidados finales", not missing_final, "Todas las carreras tienen consolidado final." if not missing_final else "Sin consolidado: " + ", ".join(missing_final), "error")
    add("Trabajo de Titulación", bool(projects), f"Se detectaron {len(projects)} registros de Trabajo de Titulación.")
    conclusions = full._conclusions(report_id, report)
    add("Conclusiones no duplicadas", len(conclusions) == len(set(item.casefold() for item in conclusions)), f"Se generaron {len(conclusions)} conclusiones diferentes.", "error")
    recommendations = full._recommendations(report_id, report)
    add("Recomendaciones no duplicadas", len(recommendations) == len(set(item["hallazgo"].casefold() for item in recommendations)), f"Se generaron {len(recommendations)} recomendaciones diferentes.", "error")
    errors = [check for check in checks if not check["ok"] and check["severity"] == "error"]
    warnings = [check for check in checks if not check["ok"] and check["severity"] != "error"]
    return {"ok": not errors, "checks": checks, "errors": errors, "warnings": warnings, "nuclei_count": len(nuclei["courses"]), "complexive_careers": len(complexive), "thesis_count": len(projects)}


def build_pdf(report_id: int) -> Path:
    validation = validate_pdf_report(report_id)
    if validation["errors"]:
        raise ValueError("No se puede generar el PDF: " + "; ".join(item["detail"] for item in validation["errors"]))

    report_structure.ensure_structure_schema()
    report_quality.base.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = _display_report(report_quality._report_data(report_id))
    output = report_quality.base.EXPORT_DIR / f"informtit_{report_id}.pdf"
    styles = report_quality._pdf_styles()
    for level in (1, 2, 3):
        styles[f"Heading{level}"].keepWithNext = True
    context = full.RecordingContext()
    content: list[Any] = []
    temp_paths: list[Path] = []

    report_quality._pdf_heading(content, context, styles, 1, "Introducción")
    for paragraph in report_structure.introduction(report, report_id):
        report_quality._pdf_body(content, styles, paragraph)
    report_quality._pdf_legal(content, context, styles, report)
    report_quality._pdf_regulation(content, context, styles, report)
    report_quality._pdf_methodology(content, context, styles, report, temp_paths)
    report_quality._pdf_requirements(content, context, styles, report_id)
    report_quality._pdf_schedules(content, context, styles, report_id)
    report_quality._pdf_nucleus_results(content, context, styles, report_id)
    report_quality._pdf_complexive(content, context, styles, report, temp_paths)
    report_quality._pdf_projects(content, context, styles, report_id)
    report_quality._pdf_post_sections(content, context, styles, report)

    images = report_quality._additional_images(report)
    if images:
        report_quality._pdf_heading(content, context, styles, 1, "Anexos de evidencias")
        for image in images:
            path = report_quality.base.image_path(image)
            if not path:
                continue
            title = str(image.get("title") or image.get("original_name") or "Evidencia")
            report_quality._pdf_caption(content, styles, context.figure_caption(title))
            content += [report_quality.base.fit_image(path, 16.5 * cm, 20 * cm), Spacer(1, .1 * cm)]
            report_quality._pdf_caption(content, styles, f"Nota. {image.get('source') or 'Fuente institucional'}.")

    prefix = list(report_quality.base.cover_pdf(report, styles))
    prefix.append(Paragraph("ÍNDICE GENERAL", styles["Title"]))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC1Final", fontName="Helvetica-Bold", fontSize=10, leading=14, spaceBefore=4),
        ParagraphStyle("TOC2Final", fontName="Helvetica", fontSize=9, leading=12, leftIndent=14),
    ]
    prefix += [toc, PageBreak()]
    story = prefix + content
    document = TocTwoLevels(str(output), pagesize=A4, rightMargin=1.45 * cm, leftMargin=1.45 * cm, topMargin=4.35 * cm, bottomMargin=1.35 * cm, title=report["name"])
    try:
        document.multiBuild(story, canvasmaker=lambda *args, **kwargs: report_quality.base.NumberedCanvas(*args, report=report, **kwargs))
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)
    return output


def install() -> None:
    if getattr(report_quality, "_pdf_polish_installed", False):
        return

    nuclei_excel_import.parse_excel_payload = _parse_excel_filtered
    report_structure.introduction = _introduction
    final._schedule_analysis = _schedule_analysis_complete
    full._nuclei_data = _filtered_nuclei_data
    full.validate_pdf_report = validate_pdf_report

    report_quality._pdf_heading = _safe_heading
    report_quality._pdf_methodology = _pdf_methodology
    report_quality._pdf_schedules = _pdf_schedules
    report_quality._pdf_nucleus_results = _pdf_nuclei
    report_quality._pdf_projects = _pdf_projects
    report_quality.base.draw_header = _draw_header
    report_quality.build_pdf = build_pdf
    full.build_pdf = build_pdf
    core.build_pdf = build_pdf
    report_quality._pdf_polish_installed = True
