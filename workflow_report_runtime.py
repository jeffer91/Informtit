from __future__ import annotations

import html
from typing import Any

from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

import report_completion
import report_quality
import report_structure
from eligibility_service import get_eligibility
from roster_service import get_report_roster


_ORIGINAL_COMPLEXIVE_DATA = report_completion._complexive_data


def _has_complexive_grade(student: dict[str, Any]) -> bool:
    return any(
        student.get(key) is not None
        for key in (
            "ordinary_theory",
            "ordinary_practical",
            "supplementary_theory",
            "supplementary_practical",
            "source_total_course",
        )
    )


def _eligible_keys(report_id: int) -> tuple[set[int], set[tuple[str, str]]]:
    eligibility = get_eligibility(report_id)
    ids: set[int] = set()
    names: set[tuple[str, str]] = set()
    for row in eligibility.get("complexive_rows", []):
        if row.get("student_id"):
            ids.add(int(row["student_id"]))
        names.add(
            (
                str(row.get("career_name") or "").strip().casefold(),
                str(row.get("full_name") or "").strip().casefold(),
            )
        )
    return ids, names


def _filtered_report(report: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report_id = int(report.get("id") or 0)
    if not report_id:
        return report, []
    eligible_ids, eligible_names = _eligible_keys(report_id)
    filtered = dict(report)
    filtered_careers: list[dict[str, Any]] = []
    blocked_with_grades: list[dict[str, Any]] = []

    for career in report.get("careers", []):
        career_copy = dict(career)
        allowed_students: list[dict[str, Any]] = []
        for student in career.get("students", []):
            student_id = int(student.get("id") or 0)
            name_key = (
                str(career.get("name") or "").strip().casefold(),
                str(student.get("full_name") or "").strip().casefold(),
            )
            allowed = (student_id and student_id in eligible_ids) or name_key in eligible_names
            if allowed:
                allowed_students.append(student)
            elif _has_complexive_grade(student):
                blocked_with_grades.append(
                    {
                        "student_id": student_id or None,
                        "full_name": student.get("full_name") or "",
                        "career_name": career.get("name") or "",
                    }
                )
        career_copy["students"] = allowed_students
        filtered_careers.append(career_copy)

    filtered["careers"] = filtered_careers
    return filtered, blocked_with_grades


def complexive_data(report: dict[str, Any]) -> dict[str, Any]:
    filtered, blocked = _filtered_report(report)
    data = _ORIGINAL_COMPLEXIVE_DATA(filtered)
    data["blocked_with_grades"] = blocked
    data["blocked_with_grades_count"] = len(blocked)
    return data


def process_funnel(report_id: int) -> dict[str, Any]:
    roster = get_report_roster(report_id)
    eligibility = get_eligibility(report_id)
    summary = eligibility["summary"]
    return {
        "registered": roster["summary"]["students"],
        "eligible_for_nuclei": summary["eligible_for_nuclei"],
        "blocked_before_nuclei": summary["blocked_before_nuclei"],
        "eligible_for_complexive": summary["eligible_for_complexive"],
        "titulation_marked": summary["titulation_marked"],
        "complexive_project_approved": summary["complexive_project_approved"],
        "titles_uploaded": summary["titles_uploaded"],
    }


def _add_docx_funnel(document: Any, context: Any, report_id: int) -> None:
    data = process_funnel(report_id)
    report_quality._docx_heading(document, context, 2, "Trazabilidad de las etapas de habilitación")
    report_quality._docx_body(
        document,
        "El proceso se analizó de forma secuencial. Los ocho requisitos previos habilitan el ingreso a Núcleos; la aprobación de los cuatro núcleos con una nota mínima de 7,00 habilita el Examen Complexivo. Los campos Titulación, Aprobación Complexivo/Proyecto y Aprobación de Titulación corresponden a etapas posteriores y no se utilizaron como requisitos de ingreso a Núcleos.",
    )
    rows = [
        ["Base institucional", data["registered"], "Población registrada en el período"],
        ["Habilitados para Núcleos", data["eligible_for_nuclei"], "Cumplen Académico, Documentación, Inglés, Financiero, Actualización de datos, Seguimiento a graduados, Prácticas y Vinculación"],
        ["Habilitados para Examen Complexivo", data["eligible_for_complexive"], "Aprobaron los cuatro núcleos con nota mínima de 7,00"],
        ["Titulación = CUMPLE", data["titulation_marked"], "Marca institucional posterior a la aprobación de Núcleos"],
        ["Aprobación Complexivo/Proyecto = CUMPLE", data["complexive_project_approved"], "Resultado posterior a aprobar el Examen Complexivo o el Proyecto"],
        ["Aprobación de Titulación = CUMPLE", data["titles_uploaded"], "Etapa final, una vez cargados los títulos"],
    ]
    report_quality._docx_caption(document, context.table_caption("Flujo institucional de habilitación y cierre"))
    report_quality._docx_table(document, ["Etapa", "Estudiantes", "Interpretación"], rows, [2.2, 0.9, 3.6])


def _add_pdf_funnel(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    data = process_funnel(report_id)
    report_quality._pdf_heading(story, context, styles, 2, "Trazabilidad de las etapas de habilitación")
    report_quality._pdf_body(
        story,
        styles,
        "El proceso se analizó de forma secuencial. Los ocho requisitos previos habilitan el ingreso a Núcleos; la aprobación de los cuatro núcleos con una nota mínima de 7,00 habilita el Examen Complexivo. Los campos Titulación, Aprobación Complexivo/Proyecto y Aprobación de Titulación corresponden a etapas posteriores y no se utilizaron como requisitos de ingreso a Núcleos.",
    )
    raw_rows = [
        ["Base institucional", data["registered"], "Población registrada en el período"],
        ["Habilitados para Núcleos", data["eligible_for_nuclei"], "Cumplen los ocho requisitos previos"],
        ["Habilitados para Examen Complexivo", data["eligible_for_complexive"], "Aprobaron los cuatro núcleos con nota mínima de 7,00"],
        ["Titulación = CUMPLE", data["titulation_marked"], "Marca posterior a la aprobación de Núcleos"],
        ["Aprobación Complexivo/Proyecto = CUMPLE", data["complexive_project_approved"], "Resultado posterior a aprobar la evaluación"],
        ["Aprobación de Titulación = CUMPLE", data["titles_uploaded"], "Etapa final después de cargar los títulos"],
    ]
    rows = [
        [Paragraph(html.escape(str(row[0])), styles["TableCell"]), row[1], Paragraph(html.escape(str(row[2])), styles["TableCell"])]
        for row in raw_rows
    ]
    report_quality._pdf_caption(story, styles, context.table_caption("Flujo institucional de habilitación y cierre"))
    story += [
        report_quality._pdf_table(["Etapa", "Estudiantes", "Interpretación"], rows, [5.2 * cm, 2.4 * cm, 9.0 * cm]),
        Spacer(1, 0.2 * cm),
    ]


def _add_docx_eligibility(document: Any, context: Any, report_id: int) -> None:
    eligibility = get_eligibility(report_id)
    if not eligibility.get("careers") and not eligibility.get("unmatched"):
        return
    summary = eligibility["summary"]
    report_quality._docx_heading(document, context, 2, "Habilitación para el Examen Complexivo")
    report_quality._docx_body(
        document,
        f"De {summary['eligible_for_nuclei']} estudiantes que cumplieron los ocho requisitos previos e ingresaron a Núcleos, {summary['eligible_for_complexive']} aprobaron los cuatro núcleos y quedaron habilitados para rendir el Examen Complexivo, {summary['not_habilitated']} registraron uno o más núcleos reprobados y {summary['pending']} mantuvieron uno o más núcleos pendientes. El porcentaje de habilitación desde la etapa de Núcleos fue {report_quality._pct(summary['habilitation_percentage'])}.",
    )
    report_quality._docx_caption(document, context.table_caption("Habilitación para el Examen Complexivo por carrera"))
    report_quality._docx_table(
        document,
        ["Carrera", "Ingresaron a Núcleos", "Habilitados Complexivo", "Núcleos reprobados", "Pendientes", "% habilitación"],
        [[row["career_name"], row["total"], row["habilitated"], row["not_habilitated"], row["pending"], report_quality._pct(row["habilitation_percentage"])] for row in eligibility["careers"]],
        [2.25, 0.9, 0.95, 0.95, 0.75, 0.9],
    )
    for career in eligibility["careers"]:
        rows = [
            row for row in eligibility["rows"]
            if row["career_name"] == career["career_name"] and row["option"] == "Examen Complexivo"
        ]
        if not rows:
            continue
        report_quality._docx_heading(document, context, 3, career["career_name"])
        report_quality._docx_table(
            document,
            ["Estudiante", "Núcleo 1", "Núcleo 2", "Núcleo 3", "Núcleo 4", "Estado"],
            [[row["full_name"], report_quality._fmt(row["nucleus_1"]), report_quality._fmt(row["nucleus_2"]), report_quality._fmt(row["nucleus_3"]), report_quality._fmt(row["nucleus_4"]), row["stage_status"]] for row in rows],
            [2.65, 0.65, 0.65, 0.65, 0.65, 1.2],
        )


def _add_pdf_eligibility(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    eligibility = get_eligibility(report_id)
    if not eligibility.get("careers") and not eligibility.get("unmatched"):
        return
    summary = eligibility["summary"]
    report_quality._pdf_heading(story, context, styles, 2, "Habilitación para el Examen Complexivo")
    report_quality._pdf_body(
        story,
        styles,
        f"De {summary['eligible_for_nuclei']} estudiantes que cumplieron los ocho requisitos previos e ingresaron a Núcleos, {summary['eligible_for_complexive']} aprobaron los cuatro núcleos y quedaron habilitados para rendir el Examen Complexivo, {summary['not_habilitated']} registraron uno o más núcleos reprobados y {summary['pending']} mantuvieron uno o más núcleos pendientes. El porcentaje de habilitación desde la etapa de Núcleos fue {report_quality._pct(summary['habilitation_percentage'])}.",
    )
    report_quality._pdf_caption(story, styles, context.table_caption("Habilitación para el Examen Complexivo por carrera"))
    career_rows = [
        [Paragraph(html.escape(row["career_name"]), styles["TableCell"]), row["total"], row["habilitated"], row["not_habilitated"], row["pending"], report_quality._pct(row["habilitation_percentage"])]
        for row in eligibility["careers"]
    ]
    story += [
        report_quality._pdf_table(
            ["Carrera", "Núcleos", "Habilitados", "Reprobados", "Pendientes", "% habilitación"],
            career_rows,
            [5.4 * cm, 2.0 * cm, 2.1 * cm, 2.1 * cm, 2.0 * cm, 2.4 * cm],
        ),
        Spacer(1, 0.2 * cm),
    ]
    for career in eligibility["careers"]:
        rows = [
            row for row in eligibility["rows"]
            if row["career_name"] == career["career_name"] and row["option"] == "Examen Complexivo"
        ]
        if not rows:
            continue
        report_quality._pdf_heading(story, context, styles, 3, career["career_name"])
        values = [
            [Paragraph(html.escape(row["full_name"]), styles["TableCell"]), report_quality._fmt(row["nucleus_1"]), report_quality._fmt(row["nucleus_2"]), report_quality._fmt(row["nucleus_3"]), report_quality._fmt(row["nucleus_4"]), Paragraph(html.escape(row["stage_status"]), styles["TableCell"])]
            for row in rows
        ]
        story += [
            report_quality._pdf_table(
                ["Estudiante", "Núcleo 1", "Núcleo 2", "Núcleo 3", "Núcleo 4", "Estado"],
                values,
                [6.7 * cm, 1.65 * cm, 1.65 * cm, 1.65 * cm, 1.65 * cm, 3.6 * cm],
            ),
            Spacer(1, 0.2 * cm),
        ]


def install() -> None:
    if getattr(report_quality, "_workflow_report_runtime_installed", False):
        return

    report_completion.REQUIREMENT_DEFINITIONS["practices_linkage_status"] = (
        "Confirma el cumplimiento de las prácticas preprofesionales requeridas antes del ingreso a Núcleos."
    )
    report_completion.REQUIREMENT_DEFINITIONS["linkage_status"] = (
        "Confirma el cumplimiento de las actividades de vinculación con la sociedad requeridas antes del ingreso a Núcleos."
    )

    original_methodology = report_completion._methodology_paragraphs
    original_incidents = report_completion._automatic_incidents
    original_docx_definitions = report_completion._add_docx_requirement_definitions
    original_pdf_definitions = report_completion._add_pdf_requirement_definitions
    current_docx_complexive = report_quality._docx_complexive
    current_pdf_complexive = report_quality._pdf_complexive
    current_docx_heading = report_quality._docx_heading
    current_pdf_heading = report_quality._pdf_heading
    current_docx_caption = report_quality._docx_caption
    current_pdf_caption = report_quality._pdf_caption
    original_content_flags = report_structure._content_flags

    def methodology(report_id: int, report: dict[str, Any]) -> list[str]:
        paragraphs = original_methodology(report_id, report)
        replacement: list[str] = []
        for paragraph in paragraphs:
            if paragraph.startswith("Para la habilitación al Examen Complexivo"):
                replacement.extend(
                    [
                        "Para ingresar a los Núcleos, cada estudiante debía registrar CUMPLE en los ocho requisitos previos: Académico, Documentación, Inglés, Financiero, Actualización de datos, Seguimiento a graduados, Prácticas y Vinculación. Quienes no cumplieron esta condición fueron excluidos de la población habilitada para Núcleos y, por consecuencia, de la lista del Examen Complexivo.",
                        "Una vez superados los requisitos previos, la habilitación al Examen Complexivo exigió aprobar individualmente los cuatro núcleos con una calificación mínima de 7,00. Los núcleos no se compensaron entre sí y los estudiantes con una nota inferior a 7,00 o con un núcleo sin calificación no ingresaron a la lista de habilitados para el Complexivo.",
                        "El campo Titulación se interpretó como una marca posterior a la aprobación de Núcleos. AprobacionComplexivoProyecto se interpretó como un resultado posterior a aprobar el Examen Complexivo o el Proyecto, mientras que AprobacionTitulacion se interpretó como la etapa final una vez cargados los títulos. Ninguno de estos tres campos se utilizó como requisito previo de ingreso a Núcleos.",
                    ]
                )
            else:
                replacement.append(paragraph)
        return replacement

    def incidents(data: dict[str, Any]) -> list[dict[str, str]]:
        items = original_incidents(data)
        blocked = data.get("complexive", {}).get("blocked_with_grades_count", 0)
        if blocked:
            items.append(
                {
                    "category": "Habilitación al Complexivo",
                    "description": f"Se encontraron {blocked} estudiante(s) con calificaciones de Examen Complexivo que no cumplen la habilitación secuencial de requisitos y cuatro núcleos.",
                    "responsible": "Coordinación de Titulación y coordinaciones de carrera",
                    "treatment": "Excluir estos registros del consolidado del Complexivo y verificar la fuente antes del cierre del informe.",
                    "status": "En seguimiento",
                    "evidence": "Cruce de requisitos, núcleos y calificaciones del Complexivo",
                }
            )
        conflicts = data.get("eligibility", {}).get("summary", {}).get("nucleus_without_prerequisites", 0)
        if conflicts:
            items.append(
                {
                    "category": "Ingreso a Núcleos",
                    "description": f"Se identificaron {conflicts} estudiante(s) con notas de Núcleos pese a no tener completos los ocho requisitos previos.",
                    "responsible": "Coordinación de Titulación",
                    "treatment": "Revisar la habilitación previa y corregir la trazabilidad del estudiante antes de consolidar el período.",
                    "status": "En seguimiento",
                    "evidence": "Matriz de requisitos y cruce de Núcleos",
                }
            )
        return items

    def docx_definitions(document: Any, context: Any, report_id: int) -> None:
        original_docx_definitions(document, context, report_id)
        _add_docx_funnel(document, context, report_id)

    def pdf_definitions(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
        original_pdf_definitions(story, context, styles, report_id)
        _add_pdf_funnel(story, context, styles, report_id)

    def docx_complexive(document: Any, context: Any, report: dict[str, Any]) -> None:
        filtered, _blocked = _filtered_report(report)
        current_docx_complexive(document, context, filtered)

    def pdf_complexive(story: list[Any], context: Any, styles: Any, report: dict[str, Any], temp_paths: list[Any]) -> None:
        filtered, _blocked = _filtered_report(report)
        current_pdf_complexive(story, context, styles, filtered, temp_paths)

    def docx_heading(document: Any, context: Any, level: int, title: str, page_break: bool = False):
        if title == "Análisis del cumplimiento de requisitos de titulación":
            title = "Análisis de requisitos previos para ingreso a Núcleos"
        return current_docx_heading(document, context, level, title, page_break)

    def pdf_heading(story: list[Any], context: Any, styles: Any, level: int, title: str, page_break: bool = False):
        if title == "Análisis del cumplimiento de requisitos de titulación":
            title = "Análisis de requisitos previos para ingreso a Núcleos"
        return current_pdf_heading(story, context, styles, level, title, page_break)

    def docx_caption(document: Any, text: str) -> None:
        text = text.replace("Cumplimiento de los requisitos de titulación", "Cumplimiento de los requisitos previos para Núcleos")
        current_docx_caption(document, text)

    def pdf_caption(story: list[Any], styles: Any, text: str) -> None:
        text = text.replace("Cumplimiento de los requisitos de titulación", "Cumplimiento de los requisitos previos para Núcleos")
        current_pdf_caption(story, styles, text)

    def content_flags(report: dict[str, Any], report_id: int) -> dict[str, bool]:
        flags = original_content_flags(report, report_id)
        flags["complexive"] = bool(complexive_data(report)["totals"]["registered"])
        return flags

    current_executive = report_completion._executive_data

    def executive(report_id: int) -> dict[str, Any]:
        data = current_executive(report_id)
        renamed = []
        for label, value in data.get("indicators", []):
            if label == "Cumplieron requisitos":
                label = "Cumplieron los 8 requisitos / habilitados para Núcleos"
            elif label == "Habilitados por los cuatro núcleos":
                label = "Habilitados para Complexivo por los 4 núcleos"
            renamed.append((label, value))
        data["indicators"] = renamed
        return data

    report_completion._complexive_data = complexive_data
    report_completion._methodology_paragraphs = methodology
    report_completion._automatic_incidents = incidents
    report_completion._add_docx_requirement_definitions = docx_definitions
    report_completion._add_pdf_requirement_definitions = pdf_definitions
    report_completion._add_docx_eligibility = _add_docx_eligibility
    report_completion._add_pdf_eligibility = _add_pdf_eligibility
    report_completion._executive_data = executive
    report_quality._docx_complexive = docx_complexive
    report_quality._pdf_complexive = pdf_complexive
    report_quality._docx_heading = docx_heading
    report_quality._pdf_heading = pdf_heading
    report_quality._docx_caption = docx_caption
    report_quality._pdf_caption = pdf_caption
    report_structure._content_flags = content_flags
    report_quality._workflow_report_runtime_installed = True
