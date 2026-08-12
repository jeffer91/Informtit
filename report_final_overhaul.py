from __future__ import annotations

import html
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx.shared import Inches
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

import nuclei_export
import report_completion
import report_enhancements as enh
import report_quality
from analytics import summary
from completion_service import get_schedules_extended
from nuclei_multicampus import get_nuclei
from optional_content import is_present
from process_service import get_projects


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _status(value: Any) -> str:
    return _norm(value).upper()


def _stats(values: list[float]) -> dict[str, float | None]:
    clean = [float(value) for value in values]
    if not clean:
        return {"average": None, "median": None, "minimum": None, "maximum": None, "stdev": None}
    return {
        "average": round(mean(clean), 2),
        "median": round(median(clean), 2),
        "minimum": round(min(clean), 2),
        "maximum": round(max(clean), 2),
        "stdev": round(pstdev(clean), 2) if len(clean) > 1 else 0.0,
    }


def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def _nuclei_consolidated(report_id: int) -> dict[str, Any]:
    courses = get_nuclei(report_id).get("courses", [])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for course in courses:
        grouped[_norm(course.get("career_name")) or "Sin carrera"].append(course)

    rows: list[dict[str, Any]] = []
    course_rows: list[dict[str, Any]] = []
    for career, career_courses in sorted(grouped.items()):
        all_students = [student for course in career_courses for student in course.get("students", [])]
        grades = [float(student["final_grade"]) for student in all_students if student.get("final_grade") is not None]
        approved = sum(_status(student.get("final_status")) == "APROBADO" for student in all_students)
        failed = sum(_status(student.get("final_status")) == "REPROBADO" for student in all_students)
        unevaluated = max(0, len(all_students) - approved - failed)
        evaluated = approved + failed
        stat = _stats(grades)
        modality = "Online" if "ONLINE" in career.upper() else "Presencial"
        rows.append(
            {
                "career": career,
                "modality": modality,
                "courses": len(career_courses),
                "records": len(all_students),
                "evaluated": evaluated,
                "approved": approved,
                "failed": failed,
                "unevaluated": unevaluated,
                **stat,
                "approval": _pct(approved, evaluated),
            }
        )
        for course in career_courses:
            students = course.get("students", [])
            course_approved = sum(_status(student.get("final_status")) == "APROBADO" for student in students)
            course_failed = sum(_status(student.get("final_status")) == "REPROBADO" for student in students)
            course_unevaluated = max(0, len(students) - course_approved - course_failed)
            evaluated_course = course_approved + course_failed
            course_grades = [float(student["final_grade"]) for student in students if student.get("final_grade") is not None]
            course_rows.append(
                {
                    "career": career,
                    "modality": modality,
                    "nucleus": course.get("course_title") or f"Núcleo {course.get('nucleus_number') or '—'}",
                    "teacher": course.get("teacher_name") or "—",
                    "students": len(students),
                    "approved": course_approved,
                    "failed": course_failed,
                    "unevaluated": course_unevaluated,
                    "average": _stats(course_grades)["average"],
                    "approval": _pct(course_approved, evaluated_course),
                    "course": course,
                }
            )
    return {"courses": courses, "careers": rows, "course_rows": course_rows}


def _complexive_consolidated(report: dict[str, Any]) -> dict[str, Any]:
    return report_completion._complexive_data(report)


def _thesis_consolidated(report_id: int) -> dict[str, Any]:
    data = get_projects(report_id)
    projects = data.get("projects", [])
    finals = [float(project["final_grade"]) for project in projects if project.get("final_grade") is not None]
    written = [float(project["written_average"]) for project in projects if project.get("written_average") is not None]
    practical = [float(project["practical_average"]) for project in projects if project.get("practical_average") is not None]
    defense = [float(project["defense_average"]) for project in projects if project.get("defense_average") is not None]
    oral = [float(project["oral_average"]) for project in projects if project.get("oral_average") is not None]
    approved = sum((project.get("final_status") or "").upper() == "APROBADO" or (project.get("final_grade") is not None and float(project["final_grade"]) >= 7) for project in projects)
    failed = sum((project.get("final_status") or "").upper() == "REPROBADO" or (project.get("final_grade") is not None and float(project["final_grade"]) < 7) for project in projects)
    incomplete = max(0, len(projects) - approved - failed)
    return {
        "projects": projects,
        "total": len(projects),
        "approved": approved,
        "failed": failed,
        "incomplete": incomplete,
        "approval": _pct(approved, approved + failed),
        "final": _stats(finals),
        "written_average": round(mean(written), 2) if written else None,
        "practical_average": round(mean(practical), 2) if practical else None,
        "defense_average": round(mean(defense), 2) if defense else None,
        "oral_average": round(mean(oral), 2) if oral else None,
    }


def _schedule_analysis(report_id: int) -> dict[str, Any]:
    schedules = get_schedules_extended(report_id)
    filtered = {
        "complexive": schedules.get("complexive", []) if is_present(report_id, "schedule_complexive") else [],
        "thesis": schedules.get("thesis", []) if is_present(report_id, "schedule_thesis") else [],
    }
    rows = filtered["complexive"] + filtered["thesis"]
    evaluated = [row for row in rows if row.get("execution_status") or row.get("compliance_percentage") is not None or row.get("executed_date")]
    percentages = [float(row["compliance_percentage"]) for row in evaluated if row.get("compliance_percentage") is not None]
    return {
        "schedules": filtered,
        "total": len(rows),
        "evaluated": len(evaluated),
        "average": round(mean(percentages), 2) if percentages else None,
        "pending_evaluation": len(rows) - len(evaluated),
        "not_complied": sum(_status(row.get("execution_status")) == "NO CUMPLIDO" for row in evaluated),
        "delayed": sum("RETRAS" in _status(row.get("execution_status")) for row in evaluated),
        "partial": sum("PARCIAL" in _status(row.get("execution_status")) for row in evaluated),
    }


def _docx_nuclei(document: Any, context: Any, report_id: int) -> None:
    data = _nuclei_consolidated(report_id)
    rows = data["careers"]
    if not rows:
        return
    report_quality._docx_heading(document, context, 1, "Resultados de los Núcleos Estructurantes")
    report_quality._docx_body(document, "El cuerpo principal presenta resultados consolidados por carrera. Los listados nominales de estudiantes se trasladan a los anexos para mantener una lectura institucional centrada en indicadores, comparaciones y decisiones.")
    report_quality._docx_heading(document, context, 2, "Consolidado institucional por carrera")
    report_quality._docx_caption(document, context.table_caption("Resultados consolidados de Núcleos Estructurantes por carrera"))
    enh._docx_table_pretty(
        document,
        ["Carrera", "Modalidad", "Cursos", "Registros", "Evaluados", "APR", "REP", "No eval.", "Promedio", "Mediana", "Mín.", "Máx.", "Desv.", "% APR"],
        [[row["career"], row["modality"], row["courses"], row["records"], row["evaluated"], row["approved"], row["failed"], row["unevaluated"], report_quality._fmt(row["average"]), report_quality._fmt(row["median"]), report_quality._fmt(row["minimum"]), report_quality._fmt(row["maximum"]), report_quality._fmt(row["stdev"]), report_quality._pct(row["approval"])] for row in rows],
        [1.65, .55, .40, .48, .48, .38, .38, .48, .52, .48, .42, .42, .42, .55],
    )
    best = max(rows, key=lambda row: row["approval"])
    worst = min(rows, key=lambda row: row["approval"])
    institutional_approved = sum(row["approved"] for row in rows)
    institutional_evaluated = sum(row["evaluated"] for row in rows)
    institutional_rate = _pct(institutional_approved, institutional_evaluated)
    report_quality._docx_body(document, f"La aprobación institucional de Núcleos fue del {report_quality._pct(institutional_rate)} entre los registros evaluados. El mayor porcentaje correspondió a {best['career']} ({report_quality._pct(best['approval'])}) y el menor a {worst['career']} ({report_quality._pct(worst['approval'])}), con una brecha de {report_quality._pct(round(best['approval'] - worst['approval'], 2))} puntos porcentuales. Esta diferencia permite priorizar la revisión académica de los cursos con menor desempeño, sin asumir causalidad a partir de una comparación descriptiva.")

    chart = enh._save_bar([row["career"] for row in sorted(rows, key=lambda item: item["approval"], reverse=True)], [row["approval"] for row in sorted(rows, key=lambda item: item["approval"], reverse=True)], "Aprobación de Núcleos por carrera", "Aprobación (%)", enh._chart_path(report_id, "nuclei_careers_final"), 100)
    enh._add_docx_figure(document, context, chart, "Aprobación de Núcleos por carrera", f"Elaboración propia a partir de {institutional_evaluated} registros evaluados.")

    report_quality._docx_heading(document, context, 2, "Consolidado por materia o núcleo")
    report_quality._docx_body(document, "La siguiente tabla permite identificar materias o núcleos con resultados relativos más altos o bajos. El estado académico utilizado corresponde al campo oficial importado desde el archivo consolidado.")
    report_quality._docx_caption(document, context.table_caption("Resultados por materia o núcleo"))
    enh._docx_table_pretty(
        document,
        ["Carrera", "Materia / núcleo", "Docente", "Reg.", "APR", "REP", "No eval.", "Promedio", "% APR"],
        [[row["career"], row["nucleus"], row["teacher"], row["students"], row["approved"], row["failed"], row["unevaluated"], report_quality._fmt(row["average"]), report_quality._pct(row["approval"])] for row in data["course_rows"]],
        [1.45, 1.45, 1.15, .42, .38, .38, .48, .52, .55],
    )


def _pdf_nuclei(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    data = _nuclei_consolidated(report_id)
    rows = data["careers"]
    if not rows:
        return
    report_quality._pdf_heading(story, context, styles, 1, "Resultados de los Núcleos Estructurantes")
    report_quality._pdf_body(story, styles, "El cuerpo principal presenta resultados consolidados por carrera; los listados nominales se trasladan a los anexos.")
    report_quality._pdf_heading(story, context, styles, 2, "Consolidado institucional por carrera")
    pdf_rows = [[Paragraph(html.escape(str(row["career"])), styles["TableCell"]), row["modality"], row["courses"], row["records"], row["evaluated"], row["approved"], row["failed"], row["unevaluated"], report_quality._fmt(row["average"]), report_quality._fmt(row["median"]), report_quality._fmt(row["minimum"]), report_quality._fmt(row["maximum"]), report_quality._fmt(row["stdev"]), report_quality._pct(row["approval"])] for row in rows]
    report_quality._pdf_caption(story, styles, context.table_caption("Resultados consolidados de Núcleos Estructurantes por carrera"))
    story += [enh._pdf_table_pretty(["Carrera", "Mod.", "Cursos", "Reg.", "Eval.", "APR", "REP", "N/E", "Prom.", "Med.", "Mín.", "Máx.", "Desv.", "% APR"], pdf_rows, [3.5*cm,1.3*cm,1.0*cm,1.0*cm,1.0*cm,.9*cm,.9*cm,.9*cm,1.1*cm,1.1*cm,1.0*cm,1.0*cm,1.0*cm,1.2*cm]), Spacer(1,.15*cm)]
    best = max(rows, key=lambda row: row["approval"])
    worst = min(rows, key=lambda row: row["approval"])
    report_quality._pdf_body(story, styles, f"El mayor porcentaje de aprobación correspondió a {best['career']} ({report_quality._pct(best['approval'])}) y el menor a {worst['career']} ({report_quality._pct(worst['approval'])}). La brecha descriptiva fue de {report_quality._pct(round(best['approval']-worst['approval'],2))} puntos porcentuales.")


def _docx_complexive(document: Any, context: Any, report: dict[str, Any]) -> None:
    data = _complexive_consolidated(report)
    rows = data["rows"]
    if not rows:
        return
    report_quality._docx_heading(document, context, 1, "Resultados del Examen Complexivo")
    report_quality._docx_body(document, "Los resultados se presentan de forma consolidada por carrera para facilitar la comparación institucional. Los resultados nominales de estudiantes se incluyen en los anexos.")
    report_quality._docx_caption(document, context.table_caption("Resultados consolidados del Examen Complexivo por carrera"))
    enh._docx_table_pretty(document, ["Carrera", "Registrados", "APR ordinario", "Supletorio", "Recuperados", "APR final", "REP final", "No eval.", "% APR final"], [[row["career"], row["registered"], row["ordinary_approved"], row["supplementary"], row["recovered"], row["final_approved"], row["final_failed"], row["not_evaluated"], report_quality._pct(row["approval_percentage"])] for row in rows], [2.2,.55,.65,.58,.58,.55,.55,.55,.7])
    totals = data["totals"]
    effectiveness = _pct(totals.get("recovered", 0), totals.get("supplementary", 0))
    report_quality._docx_body(document, f"El Examen Complexivo registró {totals['registered']} estudiantes, con {totals['final_approved']} aprobados, {totals['final_failed']} reprobados y {totals['not_evaluated']} no evaluados. La aprobación final fue del {report_quality._pct(totals['approval_percentage'])}. De {totals['supplementary']} registros en fase supletoria, {totals['recovered']} lograron recuperación, equivalente a una efectividad descriptiva del {report_quality._pct(effectiveness)}.")
    ordered = sorted(rows, key=lambda row: row["approval_percentage"], reverse=True)
    chart = enh._save_bar([row["career"] for row in ordered], [row["approval_percentage"] for row in ordered], "Aprobación final del Examen Complexivo", "Aprobación (%)", enh._chart_path(int(report["id"]), "complexive_ranking_final"), 100)
    enh._add_docx_figure(document, context, chart, "Ranking final de aprobación por carrera", f"Elaboración propia con base en {totals['registered']} registros de Examen Complexivo.")


def _pdf_complexive(story: list[Any], context: Any, styles: Any, report: dict[str, Any], temp_paths: list[Path]) -> None:
    data = _complexive_consolidated(report)
    rows = data["rows"]
    if not rows:
        return
    report_quality._pdf_heading(story, context, styles, 1, "Resultados del Examen Complexivo")
    report_quality._pdf_body(story, styles, "Los resultados se presentan de forma consolidada por carrera; los listados nominales se incluyen en los anexos.")
    pdf_rows = [[Paragraph(html.escape(str(row["career"])), styles["TableCell"]), row["registered"], row["ordinary_approved"], row["supplementary"], row["recovered"], row["final_approved"], row["final_failed"], row["not_evaluated"], report_quality._pct(row["approval_percentage"])] for row in rows]
    report_quality._pdf_caption(story, styles, context.table_caption("Resultados consolidados del Examen Complexivo por carrera"))
    story += [enh._pdf_table_pretty(["Carrera", "Reg.", "APR ord.", "Sup.", "Recup.", "APR final", "REP final", "N/E", "% APR"], pdf_rows, [5.2*cm,1.5*cm,1.8*cm,1.4*cm,1.6*cm,1.7*cm,1.7*cm,1.4*cm,1.8*cm]), Spacer(1,.18*cm)]
    totals = data["totals"]
    report_quality._pdf_body(story, styles, f"La aprobación final fue del {report_quality._pct(totals['approval_percentage'])}; se registraron {totals['final_approved']} aprobados, {totals['final_failed']} reprobados y {totals['not_evaluated']} no evaluados.")


def _docx_projects(document: Any, context: Any, report_id: int) -> None:
    data = _thesis_consolidated(report_id)
    projects = data["projects"]
    if not projects:
        return
    report_quality._docx_heading(document, context, 1, "Resultados del Trabajo de Titulación")
    report_quality._docx_body(document, f"Se analizaron {data['total']} registros de Trabajo de Titulación. La calificación final se calcula con 60 % del promedio del trabajo escrito y 40 % del promedio de la defensa oral, conforme a la configuración predeterminada del proceso.")
    report_quality._docx_caption(document, context.table_caption("Resultados consolidados del Trabajo de Titulación"))
    enh._docx_table_pretty(document, ["Estudiante", "Carrera", "Trabajo escrito", "Práctica", "Defensa", "Promedio oral", "Final", "Estado"], [[project.get("full_name") or "—", project.get("career_name") or "—", report_quality._fmt(project.get("written_average")), report_quality._fmt(project.get("practical_average")), report_quality._fmt(project.get("defense_average")), report_quality._fmt(project.get("oral_average")), report_quality._fmt(project.get("final_grade")), project.get("final_status") or ("APROBADO" if (project.get("final_grade") or 0) >= 7 else "REPROBADO")] for project in projects], [1.45,1.35,.65,.62,.62,.65,.55,.65])
    report_quality._docx_body(document, f"Se registraron {data['approved']} aprobados, {data['failed']} reprobados y {data['incomplete']} registros incompletos. La aprobación entre los casos con calificación final fue del {report_quality._pct(data['approval'])}. El promedio general fue {report_quality._fmt(data['final']['average'])}, con mediana {report_quality._fmt(data['final']['median'])}, mínimo {report_quality._fmt(data['final']['minimum'])}, máximo {report_quality._fmt(data['final']['maximum'])} y desviación estándar {report_quality._fmt(data['final']['stdev'])}.")
    if len(projects) == 1:
        report_quality._docx_body(document, "Los resultados corresponden a un único estudiante, por lo que el análisis es individual y no permite establecer una tendencia general de la carrera o del período.")
    weakest = min((("Trabajo escrito", data["written_average"]), ("Evaluación práctica", data["practical_average"]), ("Evaluación de defensa", data["defense_average"]), ("Promedio oral", data["oral_average"])), key=lambda item: float(item[1]) if item[1] is not None else 999)
    if weakest[1] is not None:
        report_quality._docx_body(document, f"El componente con menor promedio agregado fue {weakest[0]}, con {report_quality._fmt(weakest[1])}. Este resultado orienta la revisión del componente, pero por sí solo no permite atribuir una causa del desempeño final.")


def _pdf_projects(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    data = _thesis_consolidated(report_id)
    projects = data["projects"]
    if not projects:
        return
    report_quality._pdf_heading(story, context, styles, 1, "Resultados del Trabajo de Titulación")
    report_quality._pdf_body(story, styles, f"Se analizaron {data['total']} registros. La nota final se calcula con 60 % del trabajo escrito y 40 % de la defensa oral.")
    rows = [[Paragraph(html.escape(str(project.get("full_name") or "—")), styles["TableCell"]), Paragraph(html.escape(str(project.get("career_name") or "—")), styles["TableCell"]), report_quality._fmt(project.get("written_average")), report_quality._fmt(project.get("practical_average")), report_quality._fmt(project.get("defense_average")), report_quality._fmt(project.get("oral_average")), report_quality._fmt(project.get("final_grade")), project.get("final_status") or "—"] for project in projects]
    report_quality._pdf_caption(story, styles, context.table_caption("Resultados consolidados del Trabajo de Titulación"))
    story += [enh._pdf_table_pretty(["Estudiante", "Carrera", "Escrito", "Práctica", "Defensa", "Oral", "Final", "Estado"], rows, [4.2*cm,3.8*cm,1.7*cm,1.7*cm,1.7*cm,1.6*cm,1.5*cm,1.8*cm]), Spacer(1,.15*cm)]
    report_quality._pdf_body(story, styles, f"Aprobados: {data['approved']}; reprobados: {data['failed']}; incompletos: {data['incomplete']}; aprobación: {report_quality._pct(data['approval'])}; promedio final: {report_quality._fmt(data['final']['average'])}.")
    if len(projects) == 1:
        report_quality._pdf_body(story, styles, "Los resultados corresponden a un único estudiante, por lo que el análisis es individual y no permite establecer una tendencia general de la carrera o del período.")


def _ishikawa_factors(report_id: int, report: dict[str, Any]) -> list[tuple[str, list[str]]]:
    req = report_completion.corrected_requirement_analysis(report_id)
    nuclei = _nuclei_consolidated(report_id)
    complexive = _complexive_consolidated(report)
    thesis = _thesis_consolidated(report_id)
    schedules = _schedule_analysis(report_id)

    data_factors: list[str] = []
    if req and req.get("incomplete"):
        data_factors.append(f"{req['incomplete']} registros de requisitos con información incompleta")
    if thesis["incomplete"]:
        data_factors.append(f"{thesis['incomplete']} trabajos con información incompleta")
    if not data_factors:
        data_factors.append("Sin hallazgos críticos registrados")

    academic_factors: list[str] = []
    low_courses = [row for row in nuclei["course_rows"] if row["approval"] < 70]
    if low_courses:
        academic_factors.append(f"{len(low_courses)} materias o núcleos con aprobación menor al 70 %")
    if nuclei["careers"]:
        worst = min(nuclei["careers"], key=lambda row: row["approval"])
        academic_factors.append(f"Menor aprobación en Núcleos: {worst['career']} ({worst['approval']:.2f} %)")
    if not academic_factors:
        academic_factors.append("Sin hallazgos críticos registrados")

    totals = complexive["totals"]
    evaluation_factors = []
    if totals.get("final_failed"):
        evaluation_factors.append(f"{totals['final_failed']} reprobados finales en Examen Complexivo")
    if totals.get("not_evaluated"):
        evaluation_factors.append(f"{totals['not_evaluated']} estudiantes no evaluados en Complexivo")
    if thesis["projects"] and thesis["practical_average"] is not None and thesis["defense_average"] is not None:
        lower = "práctica" if thesis["practical_average"] < thesis["defense_average"] else "defensa"
        evaluation_factors.append(f"Menor promedio en Trabajo de Titulación: evaluación {lower}")
    if not evaluation_factors:
        evaluation_factors.append("Sin hallazgos críticos registrados")

    followup_factors = []
    if req and req.get("pending"):
        followup_factors.append(f"{req['pending']} estudiantes con requisitos pendientes")
    if totals.get("not_evaluated"):
        followup_factors.append(f"{totals['not_evaluated']} casos no evaluados requieren seguimiento")
    if not followup_factors:
        followup_factors.append("Sin hallazgos críticos registrados")

    schedule_factors = []
    if schedules["pending_evaluation"]:
        schedule_factors.append(f"{schedules['pending_evaluation']} actividades sin evaluación de ejecución")
    if schedules["delayed"]:
        schedule_factors.append(f"{schedules['delayed']} actividades con retraso registrado")
    if not schedule_factors:
        schedule_factors.append("Sin hallazgos críticos registrados")

    tech_factors = []
    import_summary = None
    try:
        from nuclei_excel_import import get_excel_import_summary
        import_summary = get_excel_import_summary(report_id)
    except Exception:
        import_summary = None
    if import_summary and import_summary.get("duplicate_rows"):
        tech_factors.append(f"{import_summary['duplicate_rows']} filas duplicadas omitidas en el Excel de Núcleos")
    if import_summary and import_summary.get("skipped_rows"):
        tech_factors.append(f"{import_summary['skipped_rows']} filas no aplicables omitidas en la carga")
    if not tech_factors:
        tech_factors.append("Sin hallazgos críticos registrados")

    return [
        ("Gestión de datos", data_factors[:2]),
        ("Preparación académica", academic_factors[:2]),
        ("Evaluación", evaluation_factors[:2]),
        ("Seguimiento estudiantil", followup_factors[:2]),
        ("Planificación y cronogramas", schedule_factors[:2]),
        ("Gestión tecnológica y administrativa", tech_factors[:2]),
    ]


def _ishikawa(report_id: int, report: dict[str, Any]) -> Path:
    path = enh._chart_path(report_id, "ishikawa_final")
    categories = _ishikawa_factors(report_id, report)
    fig, ax = plt.subplots(figsize=(12.5, 7.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    spine_y = 0.50
    ax.plot([0.08, 0.84], [spine_y, spine_y], linewidth=2.5, color="#244A73")
    ax.annotate("Resultados que requieren\npriorización de mejora", xy=(0.84, spine_y), xytext=(0.96, spine_y), ha="center", va="center", fontsize=10.5, fontweight="bold", arrowprops=dict(arrowstyle="-|>", color="#244A73", lw=2))
    xs = [0.25, 0.47, 0.69]
    for index, (title, factors) in enumerate(categories):
        top = index < 3
        x = xs[index % 3]
        endpoint = (x - 0.09, 0.82 if top else 0.18)
        ax.plot([x, endpoint[0]], [spine_y, endpoint[1]], linewidth=1.6, color="#607D94")
        content = title + "\n" + "\n".join(f"• {factor}" for factor in factors)
        ax.text(endpoint[0], 0.88 if top else 0.12, content, ha="center", va="top" if top else "bottom", fontsize=8.4, wrap=True, bbox=dict(boxstyle="round,pad=0.55", facecolor="#F7F9FB", edgecolor="#B7C3CE"))
    ax.text(0.5, 0.025, "Los elementos representan hallazgos observados o factores que requieren verificación; el diagrama no establece causalidad.", ha="center", fontsize=8.2, color="#526575")
    fig.tight_layout(pad=0.5)
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _ishikawa_analysis(report_id: int, report: dict[str, Any]) -> list[str]:
    categories = _ishikawa_factors(report_id, report)
    paragraphs = [
        "El diagrama organiza los hallazgos en seis categorías para facilitar la priorización institucional. Los elementos incluidos se derivan de los datos disponibles; cuando la información no permite verificar un problema, la categoría se presenta sin hallazgos críticos en lugar de inventar una causa.",
    ]
    for title, factors in categories:
        paragraphs.append(f"{title}: " + "; ".join(factors) + ". La interpretación de estos factores debe complementarse con la revisión documental y académica correspondiente antes de establecer relaciones causales o responsables específicos.")
    paragraphs.append("La prioridad de intervención debe concentrarse primero en los hallazgos cuantificados que afectan cobertura, cumplimiento o aprobación; en segundo lugar, en los registros incompletos que limitan la interpretación; y finalmente en los factores que requieren verificación adicional. Esta secuencia permite orientar acciones académicas, administrativas y tecnológicas sin exceder la evidencia disponible.")
    return paragraphs


def _conclusions(report_id: int, report: dict[str, Any]) -> list[str]:
    conclusions: list[str] = []
    req = report_completion.corrected_requirement_analysis(report_id)
    if req:
        conclusions.append(f"De {req['total']} estudiantes registrados en Requisitos, {req['complete']} cumplieron integralmente, equivalente al {report_quality._pct(req['percentage'])}; {req['pending']} presentaron al menos un incumplimiento y {req['incomplete']} información incompleta.")
        if req.get("requirements"):
            lowest = min(req["requirements"], key=lambda row: row["percentage"])
            conclusions.append(f"El requisito con menor cumplimiento fue {lowest['label']}, con {report_quality._pct(lowest['percentage'])}; este resultado concentra una prioridad administrativa verificable para la regularización de casos pendientes.")
    schedules = _schedule_analysis(report_id)
    if schedules["total"]:
        if schedules["evaluated"]:
            conclusions.append(f"De {schedules['total']} actividades de cronograma, {schedules['evaluated']} cuentan con información de ejecución; el cumplimiento promedio registrado es {report_quality._pct(schedules['average']) if schedules['average'] is not None else 'no calculable'} y {schedules['pending_evaluation']} actividades permanecen sin evaluación de ejecución.")
        else:
            conclusions.append(f"Las {schedules['total']} actividades planificadas no disponen todavía de datos suficientes de ejecución para calcular un porcentaje real de cumplimiento; por tanto, no se asigna automáticamente un 100 %.")
    nuclei = _nuclei_consolidated(report_id)
    if nuclei["careers"]:
        total_eval = sum(row["evaluated"] for row in nuclei["careers"])
        total_apr = sum(row["approved"] for row in nuclei["careers"])
        worst = min(nuclei["careers"], key=lambda row: row["approval"])
        conclusions.append(f"Núcleos Estructurantes registró {len(nuclei['courses'])} materias o grupos y {total_eval} registros evaluados, con una aprobación institucional del {report_quality._pct(_pct(total_apr,total_eval))}.")
        conclusions.append(f"La carrera con menor aprobación en Núcleos fue {worst['career']}, con {report_quality._pct(worst['approval'])}; este resultado identifica un foco de revisión académica, pero no demuestra por sí solo la causa de la diferencia.")
    complexive = _complexive_consolidated(report)
    totals = complexive["totals"]
    if totals.get("registered"):
        conclusions.append(f"El Examen Complexivo registró {totals['registered']} estudiantes y alcanzó una aprobación final del {report_quality._pct(totals['approval_percentage'])}, con {totals['final_failed']} reprobados y {totals['not_evaluated']} no evaluados.")
        effectiveness = _pct(totals.get("recovered",0), totals.get("supplementary",0))
        conclusions.append(f"La fase supletoria registró {totals.get('supplementary',0)} participantes y {totals.get('recovered',0)} recuperados, equivalente a una efectividad descriptiva del {report_quality._pct(effectiveness)}.")
    thesis = _thesis_consolidated(report_id)
    if thesis["total"]:
        conclusions.append(f"Trabajo de Titulación registró {thesis['total']} estudiantes: {thesis['approved']} aprobados, {thesis['failed']} reprobados y {thesis['incomplete']} registros incompletos; el promedio final fue {report_quality._fmt(thesis['final']['average'])}.")
        if thesis["total"] == 1:
            conclusions.append("El análisis de Trabajo de Titulación corresponde a un único estudiante, por lo que sus resultados son individuales y no permiten inferir una tendencia general de carrera o período.")
    while len(conclusions) < 8:
        conclusions.append("La calidad de las decisiones institucionales depende de mantener consistencia entre registros, estados académicos, cálculos, evidencias y documentos de respaldo; los datos incompletos deben tratarse como limitaciones y no como resultados negativos automáticos.")
    return conclusions[:12]


def _recommendations(report_id: int, report: dict[str, Any]) -> list[dict[str, str]]:
    req = report_completion.corrected_requirement_analysis(report_id)
    nuclei = _nuclei_consolidated(report_id)
    complexive = _complexive_consolidated(report)
    thesis = _thesis_consolidated(report_id)
    schedules = _schedule_analysis(report_id)
    rows: list[dict[str, str]] = []

    def add(hallazgo: str, accion: str, responsable: str, indicador: str, actual: str, meta: str, plazo: str, prioridad: str, evidencia: str) -> None:
        rows.append({"hallazgo": hallazgo, "accion": accion, "responsable": responsable, "indicador": indicador, "actual": actual, "meta": meta, "plazo": plazo, "prioridad": prioridad, "evidencia": evidencia})

    if req and req["pending"]:
        add(f"{req['pending']} estudiantes con requisitos pendientes", "Ejecutar una jornada de regularización focalizada en los requisitos con menor cumplimiento y registrar el cierre de cada caso.", "Coordinación de Titulación y áreas responsables", "Casos pendientes de requisitos", str(req["pending"]), "0 pendientes al cierre", "Antes del siguiente cierre de requisitos", "Alta", "Matriz de regularización y respaldos")
    if req and req["incomplete"]:
        add(f"{req['incomplete']} registros con información incompleta", "Completar y validar los campos faltantes antes de utilizar los registros en indicadores institucionales.", "Coordinación de Titulación", "Registros incompletos", str(req["incomplete"]), "0 registros incompletos", "15 días", "Alta", "Matriz depurada")
    if nuclei["careers"]:
        worst = min(nuclei["careers"], key=lambda row: row["approval"])
        add(f"Menor aprobación en Núcleos: {worst['career']} ({worst['approval']:.2f} %)", "Revisar materias con menor aprobación y programar refuerzo previo a la siguiente evaluación, utilizando los resultados por curso como evidencia de priorización.", "Coordinación de carrera", "Aprobación de Núcleos", f"{worst['approval']:.2f} %", f"> {min(100, worst['approval'] + 10):.2f} %", "Siguiente período", "Alta", "Plan de refuerzo y reporte comparativo")
    totals = complexive["totals"]
    if totals.get("final_failed"):
        add(f"{totals['final_failed']} reprobados finales en Examen Complexivo", "Analizar por carrera y componente los casos reprobados y ejecutar refuerzo específico antes del siguiente examen.", "Coordinaciones de carrera", "Reprobados finales", str(totals["final_failed"]), "Reducir al menos 20 %", "Siguiente convocatoria", "Alta", "Informe de refuerzo y resultados")
    if totals.get("not_evaluated"):
        add(f"{totals['not_evaluated']} estudiantes no evaluados", "Clasificar la causa de no evaluación y definir una acción de regularización individual para cada caso.", "Coordinación de Titulación", "Casos no evaluados con seguimiento", str(totals["not_evaluated"]), "100 % clasificados", "30 días", "Alta", "Matriz de seguimiento")
    if totals.get("supplementary"):
        effectiveness = _pct(totals.get("recovered",0), totals.get("supplementary",0))
        add(f"Efectividad de supletorio: {effectiveness:.2f} %", "Revisar los componentes que originaron supletorio y reforzar contenidos antes de la recuperación.", "Coordinaciones de carrera", "Efectividad del supletorio", f"{effectiveness:.2f} %", f"> {min(100, effectiveness + 10):.2f} %", "Siguiente supletorio", "Media", "Resultados comparativos de supletorio")
    if schedules["pending_evaluation"]:
        add(f"{schedules['pending_evaluation']} actividades sin evaluación de ejecución", "Registrar fechas reales, estado, porcentaje, evidencia y observación para cerrar el control del cronograma con datos verificables.", "Responsables de cada fase", "Actividades con ejecución documentada", f"{schedules['evaluated']}/{schedules['total']}", f"{schedules['total']}/{schedules['total']}", "Antes de emitir el informe definitivo", "Alta", "Evidencias y cronograma actualizado")
    if thesis["incomplete"]:
        add(f"{thesis['incomplete']} registros incompletos de Trabajo de Titulación", "Completar acta, vocales o calificaciones faltantes y validar nuevamente las fórmulas antes de emitir resultados.", "Coordinación de Titulación", "Registros completos", str(thesis["total"]-thesis["incomplete"]), str(thesis["total"]), "Antes del cierre", "Alta", "Actas y rúbricas completas")
    while len(rows) < 8:
        add("Necesidad de seguimiento entre períodos", "Comparar los mismos indicadores en el siguiente período y documentar variaciones para verificar el efecto de las acciones implementadas.", "Coordinación de Titulación", "Indicadores comparados", "Sin línea histórica consolidada", "Comparación disponible", "Siguiente período", "Media", "Informe comparativo")
    return rows[:12]


def _docx_post(document: Any, context: Any, report: dict[str, Any]) -> None:
    report_id = int(report["id"])
    report_quality._docx_heading(document, context, 1, "Resumen ejecutivo de resultados")
    req = report_completion.corrected_requirement_analysis(report_id)
    nuclei = _nuclei_consolidated(report_id)
    complexive = _complexive_consolidated(report)
    thesis = _thesis_consolidated(report_id)
    schedules = _schedule_analysis(report_id)
    indicator_rows = []
    if req:
        indicator_rows += [["Registros de Requisitos", req["total"]], ["Cumplimiento integral de Requisitos", report_quality._pct(req["percentage"])]]
    if nuclei["careers"]:
        eval_n = sum(row["evaluated"] for row in nuclei["careers"]); apr_n = sum(row["approved"] for row in nuclei["careers"])
        indicator_rows += [["Materias / grupos de Núcleos", len(nuclei["courses"])], ["Aprobación general de Núcleos", report_quality._pct(_pct(apr_n,eval_n))]]
    totals = complexive["totals"]
    if totals.get("registered"):
        indicator_rows += [["Estudiantes de Examen Complexivo", totals["registered"]], ["Aprobación final de Complexivo", report_quality._pct(totals["approval_percentage"])]]
    if thesis["total"]:
        indicator_rows += [["Estudiantes de Trabajo de Titulación", thesis["total"]], ["Aprobación en Trabajo de Titulación", report_quality._pct(thesis["approval"])]]
    if schedules["total"]:
        indicator_rows += [["Actividades de cronograma evaluadas", f"{schedules['evaluated']} de {schedules['total']}"]]
    report_quality._docx_body(document, "El resumen integra los principales resultados ya presentados en las secciones anteriores. Cada indicador conserva la población propia de su módulo y se interpreta sin asumir relaciones automáticas entre estudiantes de componentes distintos.")
    if indicator_rows:
        report_quality._docx_caption(document, context.table_caption("Indicadores principales del período"))
        enh._docx_table_pretty(document, ["Indicador", "Resultado"], indicator_rows, [4.7,1.6])

    report_quality._docx_heading(document, context, 1, "Análisis estratégico de resultados")
    report_quality._docx_body(document, "El análisis estratégico sintetiza hallazgos cuantificados, limitaciones de información y factores que requieren revisión para orientar la toma de decisiones institucionales.")
    fish = _ishikawa(report_id, report)
    enh._add_docx_figure(document, context, fish, "Diagrama de Ishikawa de factores observados", "Síntesis elaborada únicamente con hallazgos disponibles en los datos; los factores no demostrados se presentan como aspectos que requieren verificación.")
    report_quality._docx_heading(document, context, 2, "Análisis del diagrama de Ishikawa")
    for paragraph in _ishikawa_analysis(report_id, report):
        report_quality._docx_body(document, paragraph)

    report_quality._docx_heading(document, context, 1, "Conclusiones")
    for item in _conclusions(report_id, report):
        report_quality._docx_bullet(document, item)

    recommendations = _recommendations(report_id, report)
    report_quality._docx_heading(document, context, 1, "Recomendaciones")
    for item in recommendations:
        report_quality._docx_bullet(document, f"{item['hallazgo']}: {item['accion']} Responsable sugerido: {item['responsable']}. Indicador: {item['indicador']}. Meta: {item['meta']}. Plazo: {item['plazo']}. Prioridad: {item['prioridad']}.")

    report_quality._docx_heading(document, context, 1, "Plan de mejora")
    report_quality._docx_caption(document, context.table_caption("Matriz de acciones de mejora"))
    enh._docx_table_pretty(document, ["N.º", "Hallazgo", "Acción", "Responsable", "Indicador", "Valor actual", "Meta", "Plazo", "Prioridad", "Evidencia esperada"], [[index, item["hallazgo"], item["accion"], item["responsable"], item["indicador"], item["actual"], item["meta"], item["plazo"], item["prioridad"], item["evidencia"]] for index,item in enumerate(recommendations,1)], [.35,1.0,1.35,.95,.85,.65,.65,.7,.5,.9])

    enh._docx_references(document, context)
    _docx_annexes(document, context, report)


def _pdf_post(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> None:
    report_id = int(report["id"])
    report_quality._pdf_heading(story, context, styles, 1, "Resumen ejecutivo de resultados")
    report_quality._pdf_body(story, styles, "El resumen integra los principales resultados de cada componente sin asumir correspondencia automática entre sus poblaciones.")
    report_quality._pdf_heading(story, context, styles, 1, "Análisis estratégico de resultados")
    fish = _ishikawa(report_id, report)
    enh._add_pdf_figure(story, context, styles, fish, "Diagrama de Ishikawa de factores observados", "Síntesis elaborada con los hallazgos disponibles; no establece causalidad.")
    report_quality._pdf_heading(story, context, styles, 2, "Análisis del diagrama de Ishikawa")
    for paragraph in _ishikawa_analysis(report_id, report):
        report_quality._pdf_body(story, styles, paragraph)
    report_quality._pdf_heading(story, context, styles, 1, "Conclusiones")
    for item in _conclusions(report_id, report):
        report_quality._pdf_bullet(story, styles, item)
    recommendations = _recommendations(report_id, report)
    report_quality._pdf_heading(story, context, styles, 1, "Recomendaciones")
    for item in recommendations:
        report_quality._pdf_bullet(story, styles, f"{item['hallazgo']}: {item['accion']} Responsable sugerido: {item['responsable']}. Indicador: {item['indicador']}. Meta: {item['meta']}. Plazo: {item['plazo']}. Prioridad: {item['prioridad']}.")
    report_quality._pdf_heading(story, context, styles, 1, "Plan de mejora")
    rows = [[index, Paragraph(html.escape(item["hallazgo"]), styles["TableCell"]), Paragraph(html.escape(item["accion"]), styles["TableCell"]), Paragraph(html.escape(item["responsable"]), styles["TableCell"]), item["indicador"], item["actual"], item["meta"], item["plazo"], item["prioridad"]] for index,item in enumerate(recommendations,1)]
    report_quality._pdf_caption(story, styles, context.table_caption("Matriz de acciones de mejora"))
    story += [enh._pdf_table_pretty(["N.º","Hallazgo","Acción","Responsable","Indicador","Actual","Meta","Plazo","Prioridad"], rows, [.8*cm,3.0*cm,4.1*cm,2.8*cm,2.2*cm,1.4*cm,1.4*cm,2.0*cm,1.4*cm]), Spacer(1,.2*cm)]
    enh._pdf_references(story, context, styles)
    _pdf_annexes(story, context, styles, report)


def _docx_annexes(document: Any, context: Any, report: dict[str, Any]) -> None:
    report_id = int(report["id"])
    nuclei = _nuclei_consolidated(report_id)
    complexive = [career for career in report.get("careers", []) if report_quality._has_notes(career)]
    thesis = _thesis_consolidated(report_id)["projects"]
    if not nuclei["courses"] and not complexive and not thesis:
        return
    report_quality._docx_heading(document, context, 1, "Anexos")
    if nuclei["courses"]:
        report_quality._docx_heading(document, context, 2, "Anexo A. Resultados individuales de Núcleos Estructurantes")
        for course in nuclei["courses"]:
            report_quality._docx_heading(document, context, 3, f"{course.get('career_name')} – {course.get('course_title') or 'Núcleo'}")
            report_quality._docx_caption(document, context.table_caption(f"Listado individual de {course.get('course_title') or 'Núcleo'}"))
            nuclei_export._docx_score_table(document, course)
    if complexive:
        report_quality._docx_heading(document, context, 2, "Anexo B. Resultados individuales del Examen Complexivo")
        for career in complexive:
            data = summary(career["students"], "consolidado")
            report_quality._docx_heading(document, context, 3, str(career["name"]))
            report_quality._docx_caption(document, context.table_caption(f"Resultado individual consolidado de {career['name']}"))
            report_quality._docx_phase_table(document, career, "consolidado", data)
    if thesis:
        report_quality._docx_heading(document, context, 2, "Anexo C. Resultados detallados del Trabajo de Titulación")
        for project in thesis:
            report_quality._docx_heading(document, context, 3, project.get("full_name") or "Estudiante")
            enh._docx_table_pretty(document, ["Dato", "Resultado"], [["Cédula", project.get("identification") or "—"], ["Código de carrera", project.get("career_code") or "—"], ["Carrera", project.get("career_name") or "—"], ["Acta", project.get("act_number") or "—"], ["Fecha", project.get("act_date") or "—"], ["Trabajo escrito", report_quality._fmt(project.get("written_average"))], ["Evaluación práctica", report_quality._fmt(project.get("practical_average"))], ["Evaluación de defensa", report_quality._fmt(project.get("defense_average"))], ["Promedio oral", report_quality._fmt(project.get("oral_average"))], ["Calificación final", report_quality._fmt(project.get("final_grade"))], ["Estado", project.get("final_status") or "—"]], [2.4,3.9])
            for evaluation_type, title in (("practical","Evaluación práctica"),("defense","Evaluación de la defensa")):
                scores = [row for row in project.get("scores", []) if row.get("evaluation_type") == evaluation_type]
                if scores:
                    report_quality._docx_caption(document, context.table_caption(f"{title} de {project.get('full_name') or 'estudiante'}"))
                    enh._docx_table_pretty(document, ["Criterio","Máximo","Vocal 1","Vocal 2","Vocal 3"], [[row.get("criterion"),report_quality._fmt(row.get("max_score")),report_quality._fmt(row.get("vocal_1")),report_quality._fmt(row.get("vocal_2")),report_quality._fmt(row.get("vocal_3"))] for row in scores], [2.7,.7,.9,.9,.9])


def _pdf_annexes(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> None:
    report_id = int(report["id"])
    nuclei = _nuclei_consolidated(report_id)
    thesis = _thesis_consolidated(report_id)["projects"]
    if not nuclei["courses"] and not thesis:
        return
    report_quality._pdf_heading(story, context, styles, 1, "Anexos")
    if nuclei["courses"]:
        report_quality._pdf_heading(story, context, styles, 2, "Anexo A. Resultados individuales de Núcleos Estructurantes")
        for course in nuclei["courses"]:
            report_quality._pdf_heading(story, context, styles, 3, f"{course.get('career_name')} – {course.get('course_title') or 'Núcleo'}")
            story += [nuclei_export._pdf_score_table(course, styles), Spacer(1,.18*cm)]
    if thesis:
        report_quality._pdf_heading(story, context, styles, 2, "Anexo C. Resultados detallados del Trabajo de Titulación")
        for project in thesis:
            report_quality._pdf_heading(story, context, styles, 3, project.get("full_name") or "Estudiante")
            rows = [["Cédula", project.get("identification") or "—"], ["Carrera", project.get("career_name") or "—"], ["Acta", project.get("act_number") or "—"], ["Trabajo escrito", report_quality._fmt(project.get("written_average"))], ["Práctica", report_quality._fmt(project.get("practical_average"))], ["Defensa", report_quality._fmt(project.get("defense_average"))], ["Oral", report_quality._fmt(project.get("oral_average"))], ["Final", report_quality._fmt(project.get("final_grade"))], ["Estado", project.get("final_status") or "—"]]
            story += [enh._pdf_table_pretty(["Dato","Resultado"], rows, [7.0*cm,9.0*cm]), Spacer(1,.15*cm)]


def install() -> None:
    if getattr(report_quality, "_final_overhaul_installed", False):
        return
    report_quality._docx_nucleus_results = _docx_nuclei
    report_quality._pdf_nucleus_results = _pdf_nuclei
    report_quality._docx_complexive = _docx_complexive
    report_quality._pdf_complexive = _pdf_complexive
    report_quality._docx_projects = _docx_projects
    report_quality._pdf_projects = _pdf_projects
    report_quality._docx_post_sections = _docx_post
    report_quality._pdf_post_sections = _pdf_post
    report_quality._final_overhaul_installed = True
