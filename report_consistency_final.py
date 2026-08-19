from __future__ import annotations

import copy
import re
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable

import app as core
import process_service
import report_completion
import report_final_overhaul as final
import report_full_detail as full
import report_pdf_polish as polish
import report_quality
import report_schedule_truth as schedule_truth
import report_structure
import report_visual_extensions as visual
from completion_service import get_schedules_extended
from coordinator_registry import normalize
from optional_content import is_present


INSTITUTION_NAME = "Instituto Superior Tecnológico Quito Metropolitano"

_ORIGINAL_GET_PROJECTS: Callable[[int], dict[str, Any]] | None = None
_ORIGINAL_NUCLEI_CONSOLIDATED: Callable[[int], dict[str, Any]] | None = None
_ORIGINAL_DISPLAY_REPORT: Callable[[dict[str, Any]], dict[str, Any]] | None = None
_ORIGINAL_VALIDATE: Callable[[int], dict[str, Any]] | None = None
_ORIGINAL_BUILD_PDF: Callable[[int], Path] | None = None
_ORIGINAL_PDF_BODY: Callable[..., Any] | None = None
_ORIGINAL_PDF_BULLET: Callable[..., Any] | None = None
_ORIGINAL_PDF_METHODOLOGY: Callable[..., Any] | None = None
_ORIGINAL_PDF_NUCLEI: Callable[..., Any] | None = None
_ORIGINAL_CONCLUSIONS: Callable[..., list[str]] | None = None
_ORIGINAL_RECOMMENDATIONS: Callable[..., list[dict[str, str]]] | None = None

_CURRENT_REPORT_ID: int | None = None


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _is_online(career_name: Any, career_code: Any = "") -> bool:
    key = normalize(career_name)
    code = str(career_code or "").upper()
    return "online" in key or "en linea" in key or "-L-" in code


def _matches_modality(report: dict[str, Any], career_name: Any, career_code: Any = "") -> bool:
    modality = str(report.get("modality") or "").strip().lower()
    if modality == "en_linea":
        return _is_online(career_name, career_code)
    if modality == "presencial":
        return not _is_online(career_name, career_code)
    return True


def _display_report_filtered(report: dict[str, Any]) -> dict[str, Any]:
    if _ORIGINAL_DISPLAY_REPORT is None:
        raise RuntimeError("La capa de consistencia todavía no está instalada.")
    result = _ORIGINAL_DISPLAY_REPORT(report)
    result["careers"] = [
        career
        for career in result.get("careers", [])
        if _matches_modality(result, career.get("name"), career.get("career_code"))
    ]
    return result


def _filtered_projects(report_id: int) -> dict[str, Any]:
    if _ORIGINAL_GET_PROJECTS is None:
        raise RuntimeError("La capa de consistencia todavía no está instalada.")
    raw = copy.deepcopy(_ORIGINAL_GET_PROJECTS(report_id))
    report = report_quality._report_data(report_id)
    projects = [
        project
        for project in raw.get("projects", [])
        if _matches_modality(report, project.get("career_name"), project.get("career_code"))
    ]
    finals = [float(project["final_grade"]) for project in projects if project.get("final_grade") is not None]
    raw["projects"] = projects
    raw["summary"] = {
        "total": len(projects),
        "average_final": round(mean(finals), 2) if finals else None,
        "approved": sum(value >= 7.0 for value in finals),
        "failed": sum(value < 7.0 for value in finals),
    }
    return raw


def _master_nuclei(report_id: int) -> dict[str, Any]:
    if _ORIGINAL_NUCLEI_CONSOLIDATED is None:
        raise RuntimeError("La capa de consistencia todavía no está instalada.")
    report = report_quality._report_data(report_id)
    source = _ORIGINAL_NUCLEI_CONSOLIDATED(report_id)
    courses = [
        course
        for course in source.get("courses", [])
        if polish._allowed_nuclei_career(course.get("career_name"), report)
    ]
    courses.sort(
        key=lambda course: (
            polish._display_career(course.get("career_name")).casefold(),
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
            "career": polish._display_career(raw_career),
            "raw_career": raw_career,
            "modality": "Online" if _is_online(raw_career) else "Presencial",
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
            capproved = sum(_norm(student.get("final_status")).upper() == "APROBADO" for student in course_students)
            cfailed = sum(_norm(student.get("final_status")).upper() == "REPROBADO" for student in course_students)
            cunevaluated = max(0, len(course_students) - capproved - cfailed)
            cevaluated = capproved + cfailed
            cgrades = [float(student["final_grade"]) for student in course_students if student.get("final_grade") is not None]
            course_rows.append(
                {
                    "career": polish._display_career(raw_career),
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


def _format_names(names: list[str]) -> str:
    clean = [name for name in dict.fromkeys(_norm(name) for name in names) if name]
    if not clean:
        return "—"
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} y {clean[1]}"
    return ", ".join(clean[:-1]) + f" y {clean[-1]}"


def _nuclei_extreme_text(report_id: int, *, include_institutional: bool = True) -> str:
    data = _master_nuclei(report_id)
    rows = data.get("careers", [])
    if not rows:
        return ""
    max_value = max(float(row["approval"]) for row in rows)
    min_value = min(float(row["approval"]) for row in rows)
    best = [row["career"] for row in rows if float(row["approval"]) == max_value]
    worst = [row["career"] for row in rows if float(row["approval"]) == min_value]
    prefix = (
        f"La aprobación institucional de Núcleos fue del {report_quality._pct(data['institutional_approval'])}. "
        if include_institutional
        else "En Núcleos, "
    )
    if max_value == min_value:
        return prefix + f"Todas las carreras analizadas registraron el mismo porcentaje de aprobación ({report_quality._pct(max_value)})."
    best_label = _format_names(best)
    worst_label = _format_names(worst)
    best_phrase = "correspondió" if len(best) == 1 else "correspondió conjuntamente"
    worst_phrase = "correspondió" if len(worst) == 1 else "correspondió conjuntamente"
    return (
        prefix
        + f"La mayor aprobación {best_phrase} a {best_label} ({report_quality._pct(max_value)}) y "
        + f"la menor {worst_phrase} a {worst_label} ({report_quality._pct(min_value)})."
    )


def _cohort_weakest(projects: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = visual.cohort_criterion_stats(projects, "practical") + visual.cohort_criterion_stats(projects, "defense")
    return min(rows, key=lambda row: float(row["percentage"])) if rows else None


def _conclusions_fixed(report_id: int, report: dict[str, Any]) -> list[str]:
    if _ORIGINAL_CONCLUSIONS is None:
        return []
    conclusions = list(_ORIGINAL_CONCLUSIONS(report_id, report))
    projects = _filtered_projects(report_id).get("projects", [])
    finals = [float(project["final_grade"]) for project in projects if project.get("final_grade") is not None]
    approved = sum(value >= 7 for value in finals)
    n = len(projects)

    result: list[str] = []
    for item in conclusions:
        if item.startswith("En Núcleos, la mayor aprobación correspondió"):
            item = _nuclei_extreme_text(report_id, include_institutional=False)
        elif item.startswith("Trabajo de Titulación registró") and projects:
            base = (
                f"Trabajo de Titulación registró {n} {'estudiante' if n == 1 else 'estudiantes'}, "
                f"{approved} {'aprobado' if approved == 1 else 'aprobados'} y un promedio final de "
                f"{report_quality._fmt(round(mean(finals), 2) if finals else None)}."
            )
            if n == 1:
                item = base + " El resultado corresponde a un caso individual y no constituye una tendencia institucional."
            elif 2 <= n <= 9:
                item = base + f" Debido al tamaño reducido de la población analizada (n = {n}), los resultados deben interpretarse con cautela y no generalizarse como una tendencia institucional."
            else:
                item = base
        result.append(_sanitize_text(item))
    return result


def _recommendations_fixed(report_id: int, report: dict[str, Any]) -> list[dict[str, str]]:
    if _ORIGINAL_RECOMMENDATIONS is None:
        return []
    rows = [dict(row) for row in _ORIGINAL_RECOMMENDATIONS(report_id, report)]
    nuclei = _master_nuclei(report_id)
    careers = nuclei.get("careers", [])
    if careers:
        min_value = min(float(row["approval"]) for row in careers)
        worst = [row["career"] for row in careers if float(row["approval"]) == min_value]
        for row in rows:
            if row.get("hallazgo", "").startswith("Menor aprobación en Núcleos:"):
                row["hallazgo"] = f"Menor aprobación en Núcleos: {_format_names(worst)} ({str(f'{min_value:.2f}').replace('.', ',')} %)"
                if len(worst) > 1:
                    row["responsable"] = "Coordinaciones de carrera"

    projects = _filtered_projects(report_id).get("projects", [])
    weakest = _cohort_weakest(projects)
    if weakest:
        avg = str(f"{float(weakest['average']):.2f}").replace(".", ",")
        maximum = str(f"{float(weakest['maximum']):.2f}").replace(".", ",")
        percentage = str(f"{float(weakest['percentage']):.2f}").replace(".", ",")
        for row in rows:
            if row.get("hallazgo", "").startswith("Menor desempeño promedio relativo en Trabajo de Titulación:"):
                row["hallazgo"] = f"Menor promedio institucional en Trabajo de Titulación: {weakest['criterion']} ({avg}/{maximum}; {percentage} % del máximo)"
                row["indicador"] = f"Promedio de {weakest['criterion']}"
                row["actual"] = f"{avg}/{maximum}"

    for row in rows:
        for key, value in list(row.items()):
            row[key] = _sanitize_text(value)
    return rows


def _sanitize_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("Instituto Tecnológico Superior Quito Metropolitano", INSTITUTION_NAME)
    text = re.sub(r"\ba el cierre\b", "al cierre", text, flags=re.IGNORECASE)

    replacements = {
        r"\b1 estudiantes\b": "1 estudiante",
        r"\b1 participantes\b": "1 participante",
        r"\b1 aprobados\b": "1 aprobado",
        r"\b1 reprobados\b": "1 reprobado",
        r"\b1 evaluados\b": "1 evaluado",
        r"\b1 registros duplicados\b": "1 registro duplicado",
        r"\b1 posibles duplicidades nominales\b": "1 posible duplicidad nominal",
        r"\b1 posibles registros duplicados identificados\b": "1 posible registro duplicado identificado",
        r"\b1 posibles registros duplicados\b": "1 posible registro duplicado",
        r"\b1 cuentan\b": "1 cuenta",
        r"\b1 lograron\b": "1 logró",
        r"\b1 fueron\b": "1 fue",
        r"\bLos 1 estudiantes\b": "El estudiante",
        r"\blos 1 estudiantes\b": "el estudiante",
        r"\bLa tabla identifica a los 1 estudiantes\b": "La tabla identifica al estudiante",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)

    text = re.sub(r"\bSe identificaron 1 aprobado\b", "Se identificó 1 aprobado", text)
    text = re.sub(r"\bSe identificaron 1 reprobado\b", "Se identificó 1 reprobado", text)
    text = re.sub(r"\bSe registraron 1 participante\b", "Se registró 1 participante", text)
    text = re.sub(r"(?<!\d)(\d+)\.(\d{2})(?=\s*%)", r"\1,\2", text)
    return text


def _pdf_body_fixed(story: list[Any], styles: Any, text: str) -> Any:
    if _ORIGINAL_PDF_BODY is None:
        return None
    if _CURRENT_REPORT_ID is not None and (
        str(text).startswith("La aprobación institucional de Núcleos fue del")
        or str(text).startswith("El mayor porcentaje de aprobación correspondió")
    ):
        text = _nuclei_extreme_text(_CURRENT_REPORT_ID, include_institutional=True)
    return _ORIGINAL_PDF_BODY(story, styles, _sanitize_text(text))


def _pdf_bullet_fixed(story: list[Any], styles: Any, text: str) -> Any:
    if _ORIGINAL_PDF_BULLET is None:
        return None
    return _ORIGINAL_PDF_BULLET(story, styles, _sanitize_text(text))


def _pdf_nuclei_fixed(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    global _CURRENT_REPORT_ID
    if _ORIGINAL_PDF_NUCLEI is None:
        return
    previous = _CURRENT_REPORT_ID
    _CURRENT_REPORT_ID = int(report_id)
    try:
        _ORIGINAL_PDF_NUCLEI(story, context, styles, report_id)
    finally:
        _CURRENT_REPORT_ID = previous


def _pdf_schedules_fixed(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    schedule_truth._pdf_schedules(story, context, styles, report_id)
    visual._add_schedule_timeline(story, context, styles, report_id)


def _pdf_methodology_fixed(story: list[Any], context: Any, styles: Any, report: dict[str, Any], temp_paths: list[Path]) -> None:
    if _ORIGINAL_PDF_METHODOLOGY is None or _ORIGINAL_NUCLEI_CONSOLIDATED is None:
        return
    _ORIGINAL_PDF_METHODOLOGY(story, context, styles, report, temp_paths)
    report_id = int(report["id"])
    raw_count = len(_ORIGINAL_NUCLEI_CONSOLIDATED(report_id).get("courses", []))
    analyzed_count = len(_master_nuclei(report_id).get("courses", []))
    excluded_count = max(0, raw_count - analyzed_count)
    if raw_count:
        report_quality._pdf_body(
            story,
            styles,
            f"Se importaron {raw_count} registros de cursos de Núcleos. Después de aplicar la modalidad del informe y los criterios de exclusión, {analyzed_count} fueron incluidos en el análisis y {excluded_count} fueron excluidos. Los resultados, gráficos, conclusiones y análisis estratégicos utilizan únicamente los {analyzed_count} registros conciliados.",
        )


def _schedule_rows(report_id: int) -> list[dict[str, Any]]:
    schedules = get_schedules_extended(report_id)
    rows: list[dict[str, Any]] = []
    if is_present(report_id, "schedule_complexive"):
        rows.extend(schedules.get("complexive", []))
    if is_present(report_id, "schedule_thesis"):
        rows.extend(schedules.get("thesis", []))
    return rows


def _validation_fixed(report_id: int) -> dict[str, Any]:
    if _ORIGINAL_VALIDATE is None or _ORIGINAL_GET_PROJECTS is None or _ORIGINAL_NUCLEI_CONSOLIDATED is None:
        raise RuntimeError("La capa de consistencia todavía no está instalada.")
    result = dict(_ORIGINAL_VALIDATE(report_id))
    checks = [dict(check) for check in result.get("checks", [])]

    def add(name: str, ok: bool, detail: str, severity: str = "warning") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "severity": severity})

    report = report_quality._report_data(report_id)
    displayed = _display_report_filtered(report)
    mixed_careers = [
        career.get("name") or "Sin carrera"
        for career in displayed.get("careers", [])
        if not _matches_modality(displayed, career.get("name"), career.get("career_code"))
    ]
    add(
        "Modalidad de carreras",
        not mixed_careers,
        "Todas las carreras del informe corresponden a la modalidad seleccionada." if not mixed_careers else "Carreras fuera de modalidad: " + ", ".join(mixed_careers),
        "error",
    )

    projects = _filtered_projects(report_id).get("projects", [])
    mixed_projects = [
        project.get("full_name") or project.get("identification") or "Registro sin nombre"
        for project in projects
        if not _matches_modality(report, project.get("career_name"), project.get("career_code"))
    ]
    add(
        "Modalidad de Trabajo de Titulación",
        not mixed_projects,
        "Todos los registros de Trabajo de Titulación corresponden a la modalidad del informe." if not mixed_projects else "Registros fuera de modalidad: " + ", ".join(mixed_projects),
        "error",
    )

    nuclei = _master_nuclei(report_id)
    mixed_nuclei = [
        course.get("career_name") or "Sin carrera"
        for course in nuclei.get("courses", [])
        if not polish._allowed_nuclei_career(course.get("career_name"), report)
    ]
    add(
        "Modalidad de Núcleos",
        not mixed_nuclei,
        "Todos los cursos de Núcleos analizados corresponden a la modalidad del informe." if not mixed_nuclei else "Cursos fuera de modalidad: " + ", ".join(mixed_nuclei),
        "error",
    )

    raw_nuclei = len(_ORIGINAL_NUCLEI_CONSOLIDATED(report_id).get("courses", []))
    analyzed_nuclei = len(nuclei.get("courses", []))
    add(
        "Conciliación de Núcleos",
        True,
        f"Importados: {raw_nuclei}; analizados: {analyzed_nuclei}; excluidos por modalidad o criterios: {max(0, raw_nuclei - analyzed_nuclei)}.",
    )

    raw_projects = _ORIGINAL_GET_PROJECTS(report_id).get("projects", [])
    excluded_projects = len(raw_projects) - len(projects)
    add(
        "Conciliación de Trabajo de Titulación",
        True,
        f"Registros cargados: {len(raw_projects)}; analizados: {len(projects)}; excluidos por modalidad: {max(0, excluded_projects)}.",
    )

    incomplete_full_compliance: list[str] = []
    for row in _schedule_rows(report_id):
        percentage = row.get("compliance_percentage")
        if percentage is None or float(percentage) < 100:
            continue
        if not row.get("executed_date") or not row.get("execution_status") or not row.get("evidence"):
            incomplete_full_compliance.append(str(row.get("activity") or "Actividad sin nombre"))
    add(
        "Evidencia de cronograma al 100 %",
        not incomplete_full_compliance,
        "Las actividades con 100 % registran fecha ejecutada, estado y evidencia." if not incomplete_full_compliance else "Actividades con 100 % sin respaldo completo: " + ", ".join(incomplete_full_compliance),
        "error",
    )

    add(
        "Código para nombre del PDF",
        bool(_norm(report.get("code"))),
        "El código del informe está disponible para construir el nombre del archivo." if _norm(report.get("code")) else "El informe no tiene código; el archivo usará SIN-CODIGO.",
    )

    errors = [check for check in checks if not check["ok"] and check.get("severity") == "error"]
    warnings = [check for check in checks if not check["ok"] and check.get("severity") != "error"]
    result.update(
        ok=not errors,
        checks=checks,
        errors=errors,
        warnings=warnings,
        nuclei_count=analyzed_nuclei,
        thesis_count=len(projects),
    )
    return result


def _safe_filename_part(value: Any, fallback: str) -> str:
    text = _norm(value) or fallback
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1F]+", "-", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def download_filename(report: dict[str, Any]) -> str:
    code = _safe_filename_part(report.get("code"), "SIN-CODIGO")
    period = _safe_filename_part(report.get("period"), "SIN-PERIODO")
    modality = _safe_filename_part(report_quality.base.modality(report), "SIN-MODALIDAD")
    return f"{code} - Informe Titulación - {period} - {modality}.pdf"


def _build_pdf_named(report_id: int) -> Path:
    if _ORIGINAL_BUILD_PDF is None:
        raise RuntimeError("La capa de consistencia todavía no está instalada.")
    current = Path(_ORIGINAL_BUILD_PDF(report_id))
    report = _display_report_filtered(report_quality._report_data(report_id))
    target = current.with_name(download_filename(report))
    if target == current:
        return current
    if target.exists():
        target.unlink()
    current.replace(target)
    return target


def install() -> None:
    global _ORIGINAL_GET_PROJECTS, _ORIGINAL_NUCLEI_CONSOLIDATED, _ORIGINAL_DISPLAY_REPORT
    global _ORIGINAL_VALIDATE, _ORIGINAL_BUILD_PDF, _ORIGINAL_PDF_BODY, _ORIGINAL_PDF_BULLET
    global _ORIGINAL_PDF_METHODOLOGY, _ORIGINAL_PDF_NUCLEI, _ORIGINAL_CONCLUSIONS, _ORIGINAL_RECOMMENDATIONS

    if getattr(report_quality, "_report_consistency_final_installed", False):
        return

    _ORIGINAL_GET_PROJECTS = process_service.get_projects
    _ORIGINAL_NUCLEI_CONSOLIDATED = final._nuclei_consolidated
    _ORIGINAL_DISPLAY_REPORT = polish._display_report
    _ORIGINAL_VALIDATE = full.validate_pdf_report
    _ORIGINAL_BUILD_PDF = core.build_pdf
    _ORIGINAL_PDF_BODY = report_quality._pdf_body
    _ORIGINAL_PDF_BULLET = report_quality._pdf_bullet
    _ORIGINAL_PDF_METHODOLOGY = report_quality._pdf_methodology
    _ORIGINAL_PDF_NUCLEI = report_quality._pdf_nucleus_results
    _ORIGINAL_CONCLUSIONS = full._conclusions
    _ORIGINAL_RECOMMENDATIONS = full._recommendations

    # Una sola fuente de verdad para Núcleos en resultados, gráficos, Ishikawa,
    # conclusiones y plan de mejora.
    final._nuclei_consolidated = _master_nuclei
    polish._filtered_nuclei_data = _master_nuclei
    full._nuclei_data = _master_nuclei

    # El PDF trabaja únicamente con carreras y proyectos de la modalidad elegida.
    polish._display_report = _display_report_filtered
    process_service.get_projects = _filtered_projects
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith(("report_", "process_")) or module is None:
            continue
        if getattr(module, "get_projects", None) is _ORIGINAL_GET_PROJECTS:
            setattr(module, "get_projects", _filtered_projects)

    # Restaurar el cronograma basado en ejecución real y conservar su línea de tiempo.
    report_quality._pdf_schedules = _pdf_schedules_fixed

    # Conciliación metodológica, empates, redacción y cálculo institucional de rúbricas.
    report_quality._pdf_methodology = _pdf_methodology_fixed
    report_quality._pdf_nucleus_results = _pdf_nuclei_fixed
    report_quality._pdf_body = _pdf_body_fixed
    report_quality._pdf_bullet = _pdf_bullet_fixed
    full._conclusions = _conclusions_fixed
    full._recommendations = _recommendations_fixed

    # Validación ampliada antes de permitir la generación.
    polish.validate_pdf_report = _validation_fixed
    full.validate_pdf_report = _validation_fixed

    # Nombre final: código + Informe Titulación + período + modalidad.
    core.build_pdf = _build_pdf_named
    report_quality.build_pdf = _build_pdf_named
    full.build_pdf = _build_pdf_named
    polish.build_pdf = _build_pdf_named

    report_quality._report_consistency_final_installed = True
