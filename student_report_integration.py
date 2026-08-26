from __future__ import annotations

from statistics import mean

import analytics
from typing import Any, Callable

import nuclei_export
import nuclei_multicampus
import report_completion
import report_decoupled
import report_final_overhaul
import report_full_detail
import report_integrity_core
import report_quality
from db import connection
from process_service import get_projects as raw_get_projects
from student_domain_bridge import reconcile_all
from student_domain_service import ROUTE_COMPLEXIVE, ROUTE_THESIS, get_period_students

_INSTALLED = False
_BASE_REPORT_DATA: Callable[[int], dict[str, Any]] | None = None
_BASE_INTEGRITY_PROCESS_SERVICE: Any = None
_BASE_NUCLEI_CONSOLIDATED: Callable[[int], dict[str, Any]] | None = None
_BASE_DOCX_POST: Callable[..., Any] | None = None
_BASE_PDF_POST: Callable[..., Any] | None = None

_OLD_INDEPENDENCE_SENTENCE = (
    "Los resultados de las cuatro secciones son independientes y no implican "
    "correspondencia automática de estudiantes entre módulos."
)
_INTEGRATED_SENTENCE = (
    "Los resultados se integran sobre la población maestra de Requisitos: cada "
    "evidencia de Núcleos, Examen Complexivo o Trabajo de Titulación se atribuye "
    "al estudiante conciliado y a la ruta que le corresponde."
)


def _master(report_id: int) -> dict[int, dict[str, Any]]:
    return {int(row["id"]): row for row in get_period_students(report_id).get("students", [])}


def _active_for_route(row: dict[str, Any] | None, route: str) -> bool:
    return bool(
        row
        and row.get("route") == route
        and row.get("process_status") == "ACTIVO"
    )


def _grade(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _project_report_ids(report_id: int) -> list[int]:
    """Reports físicos que pertenecen al mismo período académico."""
    with connection() as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
        if "period_project_id" not in columns:
            return [report_id]
        row = conn.execute(
            "SELECT period_project_id FROM reports WHERE id=?", (report_id,)
        ).fetchone()
        if not row or row[0] is None:
            return [report_id]
        ids = [
            int(item[0])
            for item in conn.execute(
                "SELECT id FROM reports WHERE period_project_id=? ORDER BY id",
                (int(row[0]),),
            ).fetchall()
        ]
    return ids or [report_id]


def _selected_grade(report_id: int, module: str, student_id: int, nucleus_number: int = 0) -> float | None:
    """Lee una resolución manual de nota sin alterar las evidencias originales."""
    with connection() as conn:
        decision_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='student_manual_decisions'"
        ).fetchone()
        report_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
        if not decision_table or "period_project_id" not in report_columns:
            return None
        project = conn.execute(
            "SELECT period_project_id FROM reports WHERE id=?", (report_id,)
        ).fetchone()
        if not project or project[0] is None:
            return None
        identity = (
            f"student:{student_id}:nucleus:{int(nucleus_number)}"
            if module == "NUCLEI" else f"student:{student_id}"
        )
        row = conn.execute(
            """
            SELECT decision_value FROM student_manual_decisions
            WHERE period_project_id=? AND source_module=? AND identity_key=?
              AND decision_type='GRADE'
            ORDER BY id DESC LIMIT 1
            """,
            (int(project[0]), f"GRADE_{module}", identity),
        ).fetchone()
    return _grade(row[0]) if row else None


def _grade_selected(
    report_id: int,
    module: str,
    student_id: int,
    grade: float | None,
    nucleus_number: int = 0,
) -> bool:
    selected = _selected_grade(report_id, module, student_id, nucleus_number)
    return selected is None or (
        grade is not None and round(float(grade), 4) == round(float(selected), 4)
    )


def _recalculate_nucleus(course: dict[str, Any]) -> None:
    students = list(course.get("students", []))
    grades = [_grade(student.get("final_grade")) for student in students]
    evaluated = [grade for grade in grades if grade is not None]
    approved = sum(grade is not None and grade >= 7 for grade in grades)
    failed = sum(grade is not None and grade < 7 for grade in grades)
    unevaluated = len(students) - approved - failed
    course["participant_students"] = len(students)
    course["graded_students"] = len(evaluated)
    course["matched_students"] = len(students)
    course["missing_grades"] = unevaluated
    course["extra_grades"] = 0
    course["approved_count"] = approved
    course["failed_count"] = failed
    course["unevaluated_count"] = unevaluated
    course["course_average"] = round(mean(evaluated), 2) if evaluated else None

    source_averages = {
        str(item.get("name") or ""): item.get("source_average")
        for item in course.get("activity_averages", [])
        if isinstance(item, dict)
    }
    recalculated: list[dict[str, Any]] = []
    for assessment in course.get("assessments", []):
        assessment_id = int(assessment.get("id") or 0)
        name = str(assessment.get("name") or "")
        values: list[float] = []
        for student in students:
            for score in student.get("scores", []):
                same_id = assessment_id and int(score.get("assessment_id") or 0) == assessment_id
                same_name = name and str(score.get("assessment_name") or "") == name
                if not (same_id or same_name):
                    continue
                value = _grade(score.get("grade"))
                if value is not None:
                    values.append(value)
                break
        average = round(mean(values), 2) if values else None
        assessment["average"] = average
        recalculated.append(
            {
                "name": name,
                "source_average": source_averages.get(name),
                "calculated_average": average,
            }
        )
    if recalculated:
        course["activity_averages"] = recalculated


def filtered_nuclei(report_id: int) -> dict[str, Any]:
    """Filtra solo para reportes; la pantalla de carga conserva todos los registros crudos."""
    reconcile_all(report_id)
    masters = _master(report_id)
    source_courses: list[dict[str, Any]] = []
    for source_report_id in _project_report_ids(report_id):
        source_courses.extend(
            nuclei_multicampus.get_nuclei(source_report_id).get("courses", [])
        )
    courses: list[dict[str, Any]] = []
    for source_course in source_courses:
        course = dict(source_course)
        course["assessments"] = [dict(item) for item in source_course.get("assessments", [])]
        course["activity_averages"] = [
            dict(item) for item in source_course.get("activity_averages", []) if isinstance(item, dict)
        ]
        students: list[dict[str, Any]] = []
        for source_student in source_course.get("students", []):
            sid = source_student.get("period_student_id")
            master = masters.get(int(sid)) if sid else None
            if _active_for_route(master, ROUTE_COMPLEXIVE):
                final_grade = _grade(source_student.get("final_grade"))
                nucleus_number = int(course.get("nucleus_number") or 0)
                if not _grade_selected(report_id, "NUCLEI", int(sid), final_grade, nucleus_number):
                    continue
                student = dict(source_student)
                student["scores"] = [dict(score) for score in source_student.get("scores", [])]
                student["master_identification"] = master.get("identification") or ""
                student["master_name"] = master.get("full_name") or ""
                student["full_name"] = master.get("full_name") or student.get("full_name") or ""
                student["identification"] = master.get("identification") or student.get("identification") or ""
                student["official_career_name"] = master.get("career_name") or ""
                student["official_modality"] = master.get("modality") or ""
                student["official_graduated"] = bool(master.get("official_graduated"))
                students.append(student)
        course["students"] = students
        official_careers = {
            str(item.get("official_career_name") or "")
            for item in students if item.get("official_career_name")
        }
        if len(official_careers) == 1:
            course["career_name"] = next(iter(official_careers))
        _recalculate_nucleus(course)
        # El curso permanece como evidencia de carga incluso si queda sin población
        # válida; sus métricas se recalculan a cero en lugar de contaminar el reporte.
        courses.append(course)
    return {"courses": courses}


def filtered_projects(report_id: int) -> dict[str, Any]:
    reconcile_all(report_id)
    masters = _master(report_id)
    data = raw_get_projects(report_id)
    source_projects: list[dict[str, Any]] = []
    for source_report_id in _project_report_ids(report_id):
        source_projects.extend(raw_get_projects(source_report_id).get("projects", []))
    projects: list[dict[str, Any]] = []
    omitted_route_conflicts = 0
    for source in source_projects:
        sid = source.get("period_student_id")
        master = masters.get(int(sid)) if sid else None
        if _active_for_route(master, ROUTE_THESIS):
            if not _grade_selected(report_id, "THESIS", int(sid), _grade(source.get("final_grade"))):
                continue
            item = dict(source)
            item["full_name"] = master.get("full_name") or item.get("full_name") or ""
            item["identification"] = master.get("identification") or item.get("identification") or ""
            item["career_name"] = master.get("career_name") or item.get("career_name") or ""
            item["modality"] = master.get("modality") or item.get("modality") or ""
            item["official_graduated"] = bool(master.get("official_graduated"))
            item["official_titulation_completed"] = bool(master.get("official_titulation_completed"))
            projects.append(item)
        else:
            omitted_route_conflicts += 1
    result = dict(data)
    result["projects"] = projects
    approved = 0
    failed = 0
    for item in projects:
        status = str(item.get("final_status") or "").upper()
        grade = _grade(item.get("final_grade"))
        if status == "APROBADO" or (grade is not None and grade >= 7):
            approved += 1
        elif status == "REPROBADO" or (grade is not None and grade < 7):
            failed += 1
    result["summary"] = {
        **(data.get("summary") or {}),
        "total": len(projects),
        "approved": approved,
        "failed": failed,
        "incomplete": max(0, len(projects) - approved - failed),
    }
    result["omitted_route_conflicts"] = omitted_route_conflicts
    return result


def filtered_report_data(report_id: int) -> dict[str, Any]:
    """Complexivo: solo ruta Complexivo y estudiantes habilitados por requisitos."""
    reconcile_all(report_id)
    masters = _master(report_id)
    if _BASE_REPORT_DATA is None:
        raise RuntimeError("La integración del dominio de estudiantes todavía no fue instalada.")
    report = _BASE_REPORT_DATA(report_id)
    target_templates = {
        str(career.get("name") or "").strip().casefold(): dict(career)
        for career in report.get("careers", [])
    }
    source_careers: list[dict[str, Any]] = []
    for source_report_id in _project_report_ids(report_id):
        source_careers.extend(_BASE_REPORT_DATA(source_report_id).get("careers", []))

    grouped_careers: dict[str, dict[str, Any]] = {}
    synthetic_id = -1
    for source_career in source_careers:
        for source in source_career.get("students", []):
            sid = source.get("period_student_id")
            master = masters.get(int(sid)) if sid else None
            if not _active_for_route(master, ROUTE_COMPLEXIVE):
                continue
            if not _grade_selected(report_id, "COMPLEXIVE", int(sid), analytics.final_grade(source)):
                continue
            official_career = str(master.get("career_name") or source_career.get("name") or "Sin carrera")
            key = official_career.strip().casefold()
            if key not in grouped_careers:
                template = dict(target_templates.get(key) or source_career)
                if key not in target_templates:
                    template["id"] = synthetic_id
                    synthetic_id -= 1
                    template["images"] = []
                    template["analyses"] = {}
                template["name"] = official_career
                template["students"] = []
                grouped_careers[key] = template

            item = dict(source)
            item["identification"] = master.get("identification") or item.get("identification") or ""
            item["full_name"] = master.get("full_name") or item.get("full_name") or ""
            item["official_career_name"] = official_career
            item["official_modality"] = master.get("modality") or ""
            item["official_graduated"] = bool(master.get("official_graduated"))
            item["official_titulation_completed"] = bool(master.get("official_titulation_completed"))
            grouped_careers[key]["students"].append(item)

    report["careers"] = sorted(
        grouped_careers.values(),
        key=lambda career: str(career.get("name") or "").casefold(),
    )
    report["student_domain_applied"] = True
    return report


class _IntegrityProcessProxy:
    """Evita alterar process_service global; solo cambia la lectura usada por integridad."""

    def __getattr__(self, name: str) -> Any:
        if name == "get_projects":
            return filtered_projects
        return getattr(_BASE_INTEGRITY_PROCESS_SERVICE, name)


def _dataset_modality_label(report_id: int) -> str:
    with connection() as conn:
        row = conn.execute("SELECT modality FROM reports WHERE id=?", (report_id,)).fetchone()
    return "Online" if row and str(row["modality"]) == "en_linea" else "Presencial"


def _nuclei_consolidated_with_dataset_modality(report_id: int) -> dict[str, Any]:
    if _BASE_NUCLEI_CONSOLIDATED is None:
        raise RuntimeError("La integración de reportes todavía no fue instalada.")
    data = _BASE_NUCLEI_CONSOLIDATED(report_id)
    modality = _dataset_modality_label(report_id)
    for row in data.get("careers", []):
        row["modality"] = modality
    for row in data.get("course_rows", []):
        row["modality"] = modality
    return data


def _integrated_docx_objectives(document: Any, context: Any, report: dict[str, Any]) -> None:
    report_quality._docx_heading(document, context, 1, "Objetivos")
    report_quality._docx_heading(document, context, 2, "Objetivo general")
    report_quality._docx_body(
        document,
        f"Analizar la trayectoria de los estudiantes del período académico "
        f"{report.get('period') or 'analizado'} a partir de la población maestra de "
        "Requisitos y de la evidencia académica asociada a su ruta de titulación.",
    )
    report_quality._docx_heading(document, context, 2, "Objetivos específicos")
    for item in (
        "Verificar el cumplimiento de los requisitos habilitantes registrados para cada estudiante.",
        "Conciliar los resultados de Núcleos con los estudiantes que continúan por la ruta de Examen Complexivo.",
        "Integrar los resultados ordinarios y supletorios del Examen Complexivo al estudiante correspondiente.",
        "Integrar los resultados del Trabajo de Titulación únicamente a los estudiantes asignados a esa ruta.",
        "Identificar discrepancias de identidad, ruta, estado o calificación que requieran subsanación.",
    ):
        report_quality._docx_bullet(document, item)


def _integrated_pdf_objectives(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> None:
    report_quality._pdf_heading(story, context, styles, 1, "Objetivos")
    report_quality._pdf_heading(story, context, styles, 2, "Objetivo general")
    report_quality._pdf_body(
        story,
        styles,
        f"Analizar la trayectoria de los estudiantes del período académico "
        f"{report.get('period') or 'analizado'} a partir de la población maestra de "
        "Requisitos y de la evidencia académica asociada a su ruta de titulación.",
    )
    report_quality._pdf_heading(story, context, styles, 2, "Objetivos específicos")
    for item in (
        "Verificar el cumplimiento de los requisitos habilitantes registrados para cada estudiante.",
        "Conciliar los resultados de Núcleos con los estudiantes que continúan por la ruta de Examen Complexivo.",
        "Integrar los resultados ordinarios y supletorios del Examen Complexivo al estudiante correspondiente.",
        "Integrar los resultados del Trabajo de Titulación únicamente a los estudiantes asignados a esa ruta.",
        "Identificar discrepancias de identidad, ruta, estado o calificación que requieran subsanación.",
    ):
        report_quality._pdf_bullet(story, styles, item)


def _integrated_methodology_paragraphs(report_id: int, report: dict[str, Any]) -> list[str]:
    requirements = report_completion.corrected_requirement_analysis(report_id)
    nuclei = report_decoupled._nucleus_summary(report_id)
    complexive = report_completion._complexive_data(report)["totals"]
    projects = filtered_projects(report_id)["summary"]
    cutoff = (
        report_quality.base.format_date(report.get("cutoff_date"))
        if report.get("cutoff_date")
        else "no registrada"
    )
    return [
        f"La información fue procesada con fecha de corte {cutoff} para el período "
        f"{report.get('period') or 'analizado'}.",
        "Requisitos constituye la población maestra del período. De esta fuente se conserva "
        "la identidad oficial, carrera, modalidad, sede, estado de requisitos y trazabilidad "
        "administrativa de cada estudiante.",
        "Todos los estudiantes parten por la ruta de Examen Complexivo. Los casos que realizan "
        "Trabajo de Titulación se cambian explícitamente a esa ruta y la decisión manual se "
        "conserva en futuras recargas.",
        "Los registros de Núcleos, Examen Complexivo y Trabajo de Titulación se concilian con "
        "el estudiante maestro mediante cédula, correo o nombre normalizado. Las coincidencias "
        "ambiguas o de baja confianza requieren confirmación y no se incorporan a las métricas "
        "de una ruta hasta quedar resueltas.",
        f"La población maestra contiene {requirements['total'] if requirements else 0} registros; "
        f"la ruta de Complexivo presenta {nuclei['courses']} cursos de Núcleos y "
        f"{complexive['registered']} registros de Examen Complexivo; Trabajo de Titulación "
        f"presenta {projects['total']} registros conciliados y habilitados.",
        "Las métricas académicas se calculan después de aplicar la conciliación, la ruta y el "
        "estado del proceso. Los registros retirados, los conflictos de ruta y las evidencias "
        "sin identidad confirmada permanecen visibles para auditoría, pero no contaminan los "
        "resultados de la ruta que no les corresponde.",
    ]


def _wrap_docx_post(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(document: Any, context: Any, report: dict[str, Any]) -> Any:
        original_bullet = report_quality._docx_bullet

        def bullet(document_arg: Any, text: str) -> Any:
            value = _INTEGRATED_SENTENCE if str(text).strip() == _OLD_INDEPENDENCE_SENTENCE else text
            return original_bullet(document_arg, value)

        report_quality._docx_bullet = bullet
        try:
            return original(document, context, report)
        finally:
            report_quality._docx_bullet = original_bullet

    return wrapped


def _wrap_pdf_post(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> Any:
        original_bullet = report_quality._pdf_bullet

        def bullet(story_arg: list[Any], styles_arg: Any, text: str) -> Any:
            value = _INTEGRATED_SENTENCE if str(text).strip() == _OLD_INDEPENDENCE_SENTENCE else text
            return original_bullet(story_arg, styles_arg, value)

        report_quality._pdf_bullet = bullet
        try:
            return original(story, context, styles, report)
        finally:
            report_quality._pdf_bullet = original_bullet

    return wrapped


def install() -> None:
    global _INSTALLED
    global _BASE_REPORT_DATA, _BASE_INTEGRITY_PROCESS_SERVICE, _BASE_NUCLEI_CONSOLIDATED
    global _BASE_DOCX_POST, _BASE_PDF_POST
    if _INSTALLED:
        return

    # Captura las capas vigentes en este punto de prepare(), no las funciones que
    # existían al importar el módulo. Así se preservan los wrappers de calidad.
    _BASE_REPORT_DATA = report_quality._report_data
    _BASE_INTEGRITY_PROCESS_SERVICE = report_integrity_core.process_service
    _BASE_NUCLEI_CONSOLIDATED = report_final_overhaul._nuclei_consolidated
    _BASE_DOCX_POST = report_completion._add_docx_post_sections
    _BASE_PDF_POST = report_completion._add_pdf_post_sections

    # Los servicios de carga/UI siguen usando sus fuentes crudas. Solo las capas
    # de construcción y validación del informe reciben la población reconciliada.
    report_quality._report_data = filtered_report_data
    report_quality.get_nuclei = filtered_nuclei
    report_quality.get_projects = filtered_projects
    nuclei_export.get_nuclei = filtered_nuclei
    report_final_overhaul.get_nuclei = filtered_nuclei
    report_final_overhaul.get_projects = filtered_projects
    report_full_detail.get_nuclei = filtered_nuclei
    report_full_detail.get_projects = filtered_projects

    # Las conclusiones instaladas por report_decoupled deben consumir la misma
    # población filtrada y describir la arquitectura maestra actual.
    report_decoupled.get_nuclei = filtered_nuclei
    report_decoupled.get_projects = filtered_projects
    report_completion._add_docx_objectives = _integrated_docx_objectives
    report_completion._add_pdf_objectives = _integrated_pdf_objectives
    report_completion._methodology_paragraphs = _integrated_methodology_paragraphs
    if _BASE_DOCX_POST is not None:
        report_completion._add_docx_post_sections = _wrap_docx_post(_BASE_DOCX_POST)
    if _BASE_PDF_POST is not None:
        report_completion._add_pdf_post_sections = _wrap_pdf_post(_BASE_PDF_POST)

    # La modalidad pertenece al dataset del período; no se infiere del texto del
    # nombre de la carrera, porque las carreras Online no siempre contienen esa palabra.
    report_final_overhaul._nuclei_consolidated = _nuclei_consolidated_with_dataset_modality

    report_integrity_core.set_raw_nuclei_provider(filtered_nuclei)
    report_integrity_core.process_service = _IntegrityProcessProxy()
    _INSTALLED = True
