from __future__ import annotations

import html
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus.tableofcontents import TableOfContents

import app as core
import nuclei_excel_report
import report_completion
import report_enhancements as enh
import report_final_overhaul as final
import report_quality
import report_structure
from analytics import summary
from nuclei_multicampus import get_nuclei
from process_service import get_projects


TARGET_NUCLEI = 106
TARGET_COMPLEXIVE_CAREERS = 10


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _status(value: Any) -> str:
    return _norm(value).upper()


def _pct(num: float | int, den: float | int) -> float:
    return round(float(num) / float(den) * 100, 2) if den else 0.0


def _stats(values: list[float]) -> dict[str, float | None]:
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not clean:
        return {"average": None, "median": None, "minimum": None, "maximum": None, "stdev": None}
    return {
        "average": round(mean(clean), 2),
        "median": round(median(clean), 2),
        "minimum": round(min(clean), 2),
        "maximum": round(max(clean), 2),
        "stdev": round(pstdev(clean), 2) if len(clean) > 1 else 0.0,
    }


def _career_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _norm(value)).encode("ascii", "ignore").decode("ascii").upper()
    for token in (
        "TECNOLOGIA SUPERIOR EN ",
        "TECNICO SUPERIOR EN ",
        "UNIVERSITARIA EN ",
        " ONLINE",
        " PRESENCIAL",
    ):
        text = text.replace(token, "")
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def _short(value: Any, limit: int = 46) -> str:
    text = _norm(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _p(text: Any, styles: Any) -> Paragraph:
    return Paragraph(html.escape(str(text if text not in (None, "") else "—")), styles["TableCell"])


def _table(headers: list[str], rows: list[list[Any]], widths: list[float], styles: Any, font_size: float = 7.2) -> Table:
    values: list[list[Any]] = []
    for row in rows:
        current: list[Any] = []
        for value in row:
            current.append(value if isinstance(value, Paragraph) else _p(value, styles))
        values.append(current)
    table = Table([headers] + values, colWidths=widths, repeatRows=1, hAlign="CENTER")
    commands: list[tuple[Any, ...]] = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AAB7C4")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#244A73")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    for row_idx in range(2, len(rows) + 1, 2):
        commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#F4F7FA")))
    table.setStyle(TableStyle(commands))
    return table


def _chart_path(report_id: int, name: str) -> Path:
    return enh._chart_path(report_id, "full_" + name)


def _save_grouped(labels: list[str], series: list[tuple[str, list[float]]], title: str, ylabel: str, path: Path, maximum: float | None = None) -> Path:
    fig, ax = plt.subplots(figsize=(10.8, max(4.8, len(labels) * 0.42 + 2.0)))
    n = max(1, len(series))
    width = 0.78 / n
    positions = list(range(len(labels)))
    for idx, (name, values) in enumerate(series):
        offset = (idx - (n - 1) / 2) * width
        ax.barh([p + offset for p in positions], values, height=width * 0.9, label=name)
    ax.set_yticks(positions)
    ax.set_yticklabels([_short(v, 38) for v in labels], fontsize=7.6)
    ax.invert_yaxis()
    ax.set_xlabel(ylabel)
    ax.set_title(title)
    if maximum is not None:
        ax.set_xlim(0, maximum)
    ax.legend(fontsize=8)
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def _save_stacked(labels: list[str], approved: list[float], failed: list[float], pending: list[float], title: str, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10.8, max(4.8, len(labels) * 0.42 + 2.0)))
    y = list(range(len(labels)))
    ax.barh(y, approved, label="Aprobados")
    ax.barh(y, failed, left=approved, label="Reprobados")
    left2 = [a + b for a, b in zip(approved, failed)]
    ax.barh(y, pending, left=left2, label="No evaluados")
    ax.set_yticks(y)
    ax.set_yticklabels([_short(v, 38) for v in labels], fontsize=7.5)
    ax.invert_yaxis()
    ax.set_title(title)
    ax.set_xlabel("Número de registros")
    ax.legend(fontsize=8)
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def _save_scatter(points: list[tuple[float, float, str]], title: str, xlabel: str, ylabel: str, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8.8, 6.2))
    for x, y, label in points:
        ax.scatter([x], [y], s=48)
        ax.annotate(_short(label, 24), (x, y), xytext=(4, 4), textcoords="offset points", fontsize=7.2)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=210, bbox_inches="tight")
    plt.close(fig)
    return path


def _save_heatmap(careers: list[str], courses: list[dict[str, Any]], path: Path) -> Path | None:
    if not careers or not courses:
        return None
    subjects = sorted({_short(row["nucleus"], 32) for row in courses})
    if len(subjects) > 28:
        subjects = subjects[:28]
    matrix: list[list[float]] = []
    for career in careers:
        values = []
        for subject in subjects:
            matches = [row for row in courses if row["career"] == career and _short(row["nucleus"], 32) == subject and row.get("average") is not None]
            values.append(round(mean(float(row["average"]) for row in matches), 2) if matches else float("nan"))
        matrix.append(values)
    fig_w = max(10, len(subjects) * 0.42 + 4)
    fig_h = max(5, len(careers) * 0.42 + 2)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    image = ax.imshow(matrix, aspect="auto", interpolation="nearest")
    ax.set_yticks(range(len(careers)))
    ax.set_yticklabels([_short(c, 35) for c in careers], fontsize=7)
    ax.set_xticks(range(len(subjects)))
    ax.set_xticklabels(subjects, rotation=65, ha="right", fontsize=6.2)
    ax.set_title("Mapa de calor del promedio por carrera y núcleo/materia")
    fig.colorbar(image, ax=ax, label="Promedio")
    fig.tight_layout()
    fig.savefig(path, dpi=210, bbox_inches="tight")
    plt.close(fig)
    return path


def _nuclei_data(report_id: int) -> dict[str, Any]:
    data = final._nuclei_consolidated(report_id)
    career_lookup = {row["career"]: row for row in data["careers"]}
    institutional_values = [float(student["final_grade"]) for course in data["courses"] for student in course.get("students", []) if student.get("final_grade") is not None]
    institutional_stats = _stats(institutional_values)
    total_evaluated = sum(row["evaluated"] for row in data["careers"])
    total_approved = sum(row["approved"] for row in data["careers"])
    data["career_lookup"] = career_lookup
    data["institutional_stats"] = institutional_stats
    data["institutional_approval"] = _pct(total_approved, total_evaluated)
    return data


def _course_detail(course: dict[str, Any], career_row: dict[str, Any] | None, institutional_average: float | None, institutional_approval: float) -> dict[str, Any]:
    students = course.get("students", [])
    approved = sum(_status(s.get("final_status")) == "APROBADO" for s in students)
    failed = sum(_status(s.get("final_status")) == "REPROBADO" for s in students)
    pending = max(0, len(students) - approved - failed)
    evaluated = approved + failed
    grades = [float(s["final_grade"]) for s in students if s.get("final_grade") is not None]
    stat = _stats(grades)
    zeros = sum(float(s.get("final_grade") or -1) == 0 for s in students if s.get("final_grade") is not None)
    approval = _pct(approved, evaluated)
    career_average = career_row.get("average") if career_row else None
    career_approval = career_row.get("approval") if career_row else None
    return {
        "records": len(students), "evaluated": evaluated, "approved": approved, "failed": failed,
        "unevaluated": pending, "approval": approval, "zeros": zeros, **stat,
        "career_average": career_average, "career_approval": career_approval,
        "institutional_average": institutional_average, "institutional_approval": institutional_approval,
    }


def _course_analysis_text(course: dict[str, Any], detail: dict[str, Any]) -> str:
    avg = detail["average"]
    cavg = detail["career_average"]
    iavg = detail["institutional_average"]
    parts = [
        f"El curso registra {detail['records']} estudiantes, de los cuales {detail['evaluated']} cuentan con estado evaluado. "
        f"Se identificaron {detail['approved']} aprobados, {detail['failed']} reprobados y {detail['unevaluated']} no evaluados, con una aprobación del {report_quality._pct(detail['approval'])}.",
        f"El promedio fue {report_quality._fmt(avg)}, la mediana {report_quality._fmt(detail['median'])}, la nota mínima {report_quality._fmt(detail['minimum'])}, la máxima {report_quality._fmt(detail['maximum'])} y la desviación estándar {report_quality._fmt(detail['stdev'])}.",
    ]
    if avg is not None and cavg is not None:
        diff = round(float(avg) - float(cavg), 2)
        relation = "por encima" if diff > 0 else "por debajo" if diff < 0 else "en el mismo nivel"
        parts.append(f"El promedio del curso se ubicó {relation} del promedio de su carrera ({report_quality._fmt(cavg)}), con una diferencia descriptiva de {report_quality._fmt(abs(diff))} puntos.")
    if avg is not None and iavg is not None:
        diff = round(float(avg) - float(iavg), 2)
        relation = "por encima" if diff > 0 else "por debajo" if diff < 0 else "en el mismo nivel"
        parts.append(f"Frente al promedio institucional de Núcleos ({report_quality._fmt(iavg)}), el resultado se ubicó {relation}, con una diferencia descriptiva de {report_quality._fmt(abs(diff))} puntos.")
    if detail["zeros"]:
        parts.append(f"Se registraron {detail['zeros']} calificaciones iguales a cero; estos casos deben revisarse para distinguir una nota académica válida de una ausencia o novedad de registro.")
    if detail["failed"] or detail["unevaluated"] or detail["approval"] < detail["institutional_approval"]:
        parts.append("El resultado requiere seguimiento académico o administrativo, priorizando los casos reprobados, no evaluados y las diferencias frente al comportamiento institucional.")
    else:
        parts.append("No se observa una necesidad prioritaria de seguimiento por desempeño en este curso; corresponde mantener el monitoreo ordinario del siguiente período.")
    return " ".join(parts)


def _pdf_nuclei(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    data = _nuclei_data(report_id)
    rows = data["careers"]
    courses = data["courses"]
    if not rows:
        return

    report_quality._pdf_heading(story, context, styles, 1, "Resultados de los Núcleos Estructurantes")
    report_quality._pdf_body(story, styles, f"La sección conserva el detalle de los {len(courses)} cursos o núcleos cargados y añade consolidados institucionales para facilitar la comparación. Las tablas consolidadas complementan, pero no sustituyen, los resultados individuales.")

    report_quality._pdf_heading(story, context, styles, 2, "Consolidado institucional por carrera")
    report_quality._pdf_body(story, styles, "El consolidado resume por carrera el número de cursos, registros, estudiantes evaluados, estados académicos y estadísticos descriptivos obtenidos a partir de las notas finales importadas.")
    table_rows = [[row["career"], row["modality"], row["courses"], row["records"], row["evaluated"], row["approved"], row["failed"], row["unevaluated"], report_quality._fmt(row["average"]), report_quality._fmt(row["median"]), report_quality._fmt(row["stdev"]), report_quality._pct(row["approval"])] for row in rows]
    report_quality._pdf_caption(story, styles, context.table_caption("Consolidado institucional de Núcleos por carrera"))
    story += [_table(["Carrera", "Mod.", "Cursos", "Reg.", "Eval.", "APR", "REP", "N/E", "Prom.", "Med.", "Desv.", "% APR"], table_rows, [3.5*cm,1.25*cm,.95*cm,.95*cm,.95*cm,.85*cm,.85*cm,.85*cm,1.05*cm,1.05*cm,1.05*cm,1.15*cm], styles, 6.6), Spacer(1,.15*cm)]
    best = max(rows, key=lambda r: r["approval"])
    worst = min(rows, key=lambda r: r["approval"])
    report_quality._pdf_body(story, styles, f"La aprobación institucional de Núcleos fue del {report_quality._pct(data['institutional_approval'])}. La mayor aprobación se observó en {best['career']} ({report_quality._pct(best['approval'])}) y la menor en {worst['career']} ({report_quality._pct(worst['approval'])}), con una brecha descriptiva de {report_quality._pct(round(best['approval'] - worst['approval'], 2))} puntos porcentuales.")

    report_quality._pdf_heading(story, context, styles, 2, "Comparación entre carreras")
    ordered_apr = sorted(rows, key=lambda r: r["approval"], reverse=True)
    ordered_avg = sorted(rows, key=lambda r: float(r["average"]) if r["average"] is not None else -999, reverse=True)
    ranking_rows = [[idx, row["career"], report_quality._pct(row["approval"]), report_quality._fmt(row["average"]), "Sobre promedio institucional" if row["average"] is not None and data["institutional_stats"]["average"] is not None and row["average"] >= data["institutional_stats"]["average"] else "Bajo promedio institucional"] for idx, row in enumerate(ordered_apr, 1)]
    report_quality._pdf_caption(story, styles, context.table_caption("Ranking de carreras por aprobación y promedio de Núcleos"))
    story += [_table(["Puesto", "Carrera", "% aprobación", "Promedio", "Lectura comparativa"], ranking_rows, [1.2*cm,7.0*cm,2.6*cm,2.2*cm,4.2*cm], styles), Spacer(1,.12*cm)]
    approval_chart = enh._save_bar([r["career"] for r in ordered_apr], [r["approval"] for r in ordered_apr], "Aprobación de Núcleos por carrera", "Aprobación (%)", _chart_path(report_id, "nuclei_approval"), 100)
    enh._add_pdf_figure(story, context, styles, approval_chart, "Aprobación de Núcleos por carrera", "Elaboración propia a partir del estado académico oficial del Excel consolidado.")
    avg_chart = enh._save_bar([r["career"] for r in ordered_avg], [float(r["average"] or 0) for r in ordered_avg], "Promedio de Núcleos por carrera", "Promedio", _chart_path(report_id, "nuclei_average"), 10)
    enh._add_pdf_figure(story, context, styles, avg_chart, "Promedio de Núcleos por carrera", "Elaboración propia a partir de las notas finales numéricas disponibles.")
    status_chart = _save_stacked([r["career"] for r in rows], [r["approved"] for r in rows], [r["failed"] for r in rows], [r["unevaluated"] for r in rows], "Aprobados, reprobados y no evaluados en Núcleos", _chart_path(report_id, "nuclei_status"))
    enh._add_pdf_figure(story, context, styles, status_chart, "Aprobados, reprobados y no evaluados en Núcleos por carrera", "Los estados corresponden al campo oficial importado.")

    report_quality._pdf_heading(story, context, styles, 2, "Comparación presencial y online")
    modality_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        modality_groups[row["modality"]].append(row)
    modality_rows = []
    for modality, group in sorted(modality_groups.items()):
        evals = sum(r["evaluated"] for r in group)
        approved = sum(r["approved"] for r in group)
        averages = [float(r["average"]) for r in group if r["average"] is not None]
        modality_rows.append([modality, len(group), evals, approved, report_quality._pct(_pct(approved, evals)), report_quality._fmt(round(mean(averages),2) if averages else None)])
    report_quality._pdf_caption(story, styles, context.table_caption("Comparación de Núcleos por modalidad"))
    story += [_table(["Modalidad", "Carreras", "Evaluados", "Aprobados", "% aprobación", "Promedio"], modality_rows, [3.0*cm,2.2*cm,2.6*cm,2.6*cm,3.0*cm,2.8*cm], styles), Spacer(1,.12*cm)]
    if len(modality_rows) > 1:
        mod_chart = _save_grouped([str(r[0]) for r in modality_rows], [("Aprobación (%)", [float(str(r[4]).replace(" %","").replace(",",".")) for r in modality_rows]), ("Promedio x10", [float(str(r[5]).replace(",",".")) * 10 if r[5] != "—" else 0 for r in modality_rows])], "Comparación presencial y online en Núcleos", "Escala comparativa", _chart_path(report_id, "nuclei_modality"), 100)
        enh._add_pdf_figure(story, context, styles, mod_chart, "Comparación de resultados de Núcleos por modalidad", "El promedio se representa multiplicado por diez únicamente para visualizar ambas métricas en una escala común.")

    report_quality._pdf_heading(story, context, styles, 2, "Núcleos con menor desempeño y dispersión")
    course_rows = data["course_rows"]
    low_avg = sorted([r for r in course_rows if r["average"] is not None], key=lambda r: float(r["average"]))[:5]
    high_fail = sorted(course_rows, key=lambda r: (r["failed"], r["unevaluated"]), reverse=True)[:5]
    low_rows = [[r["career"], r["nucleus"], r["teacher"], report_quality._fmt(r["average"]), r["failed"], r["unevaluated"], report_quality._pct(r["approval"])] for r in low_avg]
    report_quality._pdf_caption(story, styles, context.table_caption("Cinco núcleos o materias con menor promedio"))
    story += [_table(["Carrera", "Núcleo / materia", "Docente", "Prom.", "REP", "N/E", "% APR"], low_rows, [3.1*cm,4.6*cm,3.5*cm,1.4*cm,1.2*cm,1.2*cm,1.8*cm], styles), Spacer(1,.12*cm)]
    fail_rows = [[r["career"], r["nucleus"], r["failed"], r["unevaluated"], report_quality._pct(r["approval"])] for r in high_fail]
    report_quality._pdf_caption(story, styles, context.table_caption("Cinco núcleos o materias con mayor número de reprobados"))
    story += [_table(["Carrera", "Núcleo / materia", "Reprobados", "No evaluados", "% aprobación"], fail_rows, [4.0*cm,6.2*cm,2.2*cm,2.4*cm,2.4*cm], styles), Spacer(1,.12*cm)]
    if low_avg:
        low_chart = enh._save_bar([f"{r['career']} · {r['nucleus']}" for r in low_avg], [float(r["average"] or 0) for r in low_avg], "Ranking de núcleos con menor promedio", "Promedio", _chart_path(report_id, "nuclei_low"), 10)
        enh._add_pdf_figure(story, context, styles, low_chart, "Núcleos con menor promedio", "El ranking identifica resultados que requieren revisión académica; no atribuye causalidad.")
    heat = _save_heatmap([r["career"] for r in rows], course_rows, _chart_path(report_id, "nuclei_heatmap"))
    if heat:
        enh._add_pdf_figure(story, context, styles, heat, "Mapa de calor de promedios de Núcleos", "Visualización descriptiva de promedios disponibles por carrera y núcleo/materia.")

    zeros = sum(1 for course in courses for s in course.get("students", []) if s.get("final_grade") is not None and float(s["final_grade"]) == 0)
    high_dispersion = sorted([r for r in rows if r.get("stdev") is not None], key=lambda r: float(r["stdev"]), reverse=True)[:3]
    report_quality._pdf_body(story, styles, f"Se identificaron {zeros} registros con nota cero. La desviación estándar institucional fue {report_quality._fmt(data['institutional_stats']['stdev'])}. Las mayores dispersiones por carrera se observaron en " + ", ".join(f"{r['career']} ({report_quality._fmt(r['stdev'])})" for r in high_dispersion) + ". La comparación entre media y mediana debe interpretarse como un indicador descriptivo de asimetría o presencia potencial de resultados atípicos, sin reemplazar la revisión de los registros individuales.")

    report_quality._pdf_heading(story, context, styles, 2, "Resultados individuales de los cursos o núcleos")
    report_quality._pdf_body(story, styles, f"A continuación se conserva una subsección completa para cada uno de los {len(courses)} cursos o núcleos registrados. Cada resultado incluye contexto, tabla nominal, indicadores descriptivos y un análisis específico.")
    inst_avg = data["institutional_stats"]["average"]
    for index, course in enumerate(courses, 1):
        career = _norm(course.get("career_name")) or "Sin carrera"
        title = _norm(course.get("course_title")) or f"Núcleo {course.get('nucleus_number') or '—'}"
        teacher = _norm(course.get("teacher_name")) or "No registrado"
        modality = "Online" if "ONLINE" in career.upper() else "Presencial"
        detail = _course_detail(course, data["career_lookup"].get(career), inst_avg, data["institutional_approval"])
        report_quality._pdf_heading(story, context, styles, 3, f"Resultado individual {index:03d}. {career} – {title}", page_break=True)
        report_quality._pdf_body(story, styles, f"La subsección presenta el resultado del curso «{title}» de {career}, modalidad {modality}, impartido por {teacher}. La tabla conserva todos los registros nominales importados y su estado académico oficial.")
        student_rows = [[s.get("full_name") or "—", report_quality._fmt(s.get("final_grade")), s.get("final_status") or "No evaluado"] for s in course.get("students", [])]
        report_quality._pdf_caption(story, styles, context.table_caption(f"Resultados individuales de {title} – {career}"))
        story += [_table(["Estudiante", "Nota final", "Estado académico"], student_rows, [10.2*cm,2.7*cm,4.2*cm], styles, 7.4), Spacer(1,.12*cm)]
        metric_rows = [
            ["Registros importados", detail["records"], "Evaluados", detail["evaluated"]],
            ["Aprobados", detail["approved"], "Reprobados", detail["failed"]],
            ["No evaluados", detail["unevaluated"], "% aprobación", report_quality._pct(detail["approval"])],
            ["Promedio", report_quality._fmt(detail["average"]), "Mediana", report_quality._fmt(detail["median"])],
            ["Nota mínima", report_quality._fmt(detail["minimum"]), "Nota máxima", report_quality._fmt(detail["maximum"])],
            ["Desviación estándar", report_quality._fmt(detail["stdev"]), "Notas cero", detail["zeros"]],
        ]
        report_quality._pdf_caption(story, styles, context.table_caption(f"Indicadores descriptivos de {title} – {career}"))
        story += [_table(["Indicador", "Resultado", "Indicador", "Resultado"], metric_rows, [4.3*cm,2.2*cm,4.3*cm,2.2*cm], styles), Spacer(1,.12*cm)]
        report_quality._pdf_body(story, styles, _course_analysis_text(course, detail))


def _complexive_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for career in report.get("careers", []):
        if not report_quality._has_notes(career):
            continue
        ordinary = summary(career["students"], "ordinario")
        supplementary = summary(career["students"], "supletorio")
        consolidated = summary(career["students"], "consolidado")
        theory = [float(r["ordinary_theory"]) for r in ordinary["rows"] if r.get("ordinary_theory") is not None]
        practical = [float(r["ordinary_practical"]) for r in ordinary["rows"] if r.get("ordinary_practical") is not None]
        recovered = sum(r["supplementary_participant"] and r["ordinary_status"] != "Aprobado" and r["final_status"] == "Aprobado" for r in consolidated["rows"])
        result.append({
            "career": career, "name": career["name"], "ordinary": ordinary, "supplementary": supplementary, "final": consolidated,
            "theory_average": round(mean(theory),2) if theory else None, "practical_average": round(mean(practical),2) if practical else None,
            "recovered": recovered, "effectiveness": _pct(recovered, supplementary["total"]),
        })
    return result


def _complexive_phase_analysis(item: dict[str, Any], phase: str) -> str:
    data = item[phase]
    if phase == "ordinary":
        return (f"En la evaluación ordinaria de {item['name']} participaron {data['total']} estudiantes. Se registraron {data['approved']} aprobados, {data['failed']} reprobados y {data['not_evaluated']} no evaluados, con una aprobación del {report_quality._pct(data['approved_pct'])}. El promedio teórico fue {report_quality._fmt(item['theory_average'])}, el promedio práctico {report_quality._fmt(item['practical_average'])} y el promedio final {report_quality._fmt(data['average_final'])}.")
    if phase == "supplementary":
        return (f"La fase supletoria registró {data['total']} participantes. {item['recovered']} lograron recuperar su condición académica, equivalente a una efectividad descriptiva del {report_quality._pct(item['effectiveness'])}. Los casos no recuperados deben analizarse por componente y estudiante, sin asumir una causa única a partir de la calificación.")
    return (f"El resultado consolidado de {item['name']} registra {data['approved']} aprobados finales, {data['failed']} reprobados y {data['not_evaluated']} no evaluados. La aprobación final fue del {report_quality._pct(data['approved_pct'])} y el promedio final fue {report_quality._fmt(data['average_final'])}. La diferencia frente a la aprobación ordinaria fue de {report_quality._pct(round(data['approved_pct'] - item['ordinary']['approved_pct'],2))} puntos porcentuales.")


def _pdf_complexive(story: list[Any], context: Any, styles: Any, report: dict[str, Any], temp_paths: list[Path]) -> None:
    items = _complexive_rows(report)
    if not items:
        return
    report_id = int(report["id"])
    report_quality._pdf_heading(story, context, styles, 1, "Resultados del Examen Complexivo")
    report_quality._pdf_body(story, styles, f"La sección conserva el detalle completo de las {len(items)} carreras con resultados de Examen Complexivo. Para cada carrera se presentan la evaluación ordinaria, el supletorio cuando corresponde, el consolidado final y los gráficos comparativos; el consolidado institucional se incorpora después de los resultados individuales.")

    for idx, item in enumerate(items, 1):
        career = item["career"]
        name = item["name"]
        report_quality._pdf_heading(story, context, styles, 2, f"{name}", page_break=idx > 1)
        warnings = report.get("duplicate_warnings", {}).get(int(career["id"]), [])
        if warnings:
            report_quality._pdf_body(story, styles, "Control de calidad: existen posibles registros duplicados o variantes de nombre que requieren verificación: " + "; ".join(warnings) + ".")

        ordinary = item["ordinary"]
        report_quality._pdf_heading(story, context, styles, 3, "Evaluación ordinaria")
        report_quality._pdf_body(story, styles, f"La evaluación ordinaria constituye la primera medición del Examen Complexivo para {name}. La tabla presenta las notas teórica y práctica, la calificación final y el estado de cada estudiante.")
        report_quality._pdf_caption(story, styles, context.table_caption(f"Evaluación ordinaria de {name}"))
        story += [report_quality._pdf_phase_table(ordinary, "ordinario", styles), Spacer(1,.12*cm)]
        report_quality._pdf_body(story, styles, _complexive_phase_analysis(item, "ordinary"))

        supplementary = item["supplementary"]
        report_quality._pdf_heading(story, context, styles, 3, "Evaluación supletoria")
        if supplementary["rows"]:
            report_quality._pdf_body(story, styles, f"La tabla identifica a los {supplementary['total']} estudiantes que registraron participación supletoria, el componente recuperado, las notas correspondientes y el estado final alcanzado.")
            report_quality._pdf_caption(story, styles, context.table_caption(f"Evaluación supletoria de {name}"))
            story += [report_quality._pdf_phase_table(supplementary, "supletorio", styles), Spacer(1,.12*cm)]
            report_quality._pdf_body(story, styles, _complexive_phase_analysis(item, "supplementary"))
        else:
            report_quality._pdf_body(story, styles, "No se registraron participantes en evaluación supletoria para esta carrera; por ello no se genera una tabla vacía.")

        consolidated = item["final"]
        report_quality._pdf_heading(story, context, styles, 3, "Resultado consolidado")
        report_quality._pdf_body(story, styles, "El consolidado integra el resultado ordinario y, cuando corresponde, la recuperación supletoria, mostrando el estado final de cada estudiante.")
        report_quality._pdf_caption(story, styles, context.table_caption(f"Resultado consolidado del Examen Complexivo de {name}"))
        story += [report_quality._pdf_phase_table(consolidated, "consolidado", styles), Spacer(1,.12*cm)]
        report_quality._pdf_body(story, styles, _complexive_phase_analysis(item, "final"))

        status_path = _chart_path(report_id, f"complexive_{idx}_status")
        fig, ax = plt.subplots(figsize=(7.6,4.5)); labels=["Aprobados","Reprobados","No evaluados"]; values=[consolidated["approved"],consolidated["failed"],consolidated["not_evaluated"]]; ax.bar(labels,values); ax.set_title(f"Estado final · {name}"); ax.set_ylabel("Estudiantes");
        for i,v in enumerate(values): ax.text(i,v+0.1,str(v),ha="center",fontsize=8)
        fig.tight_layout(); fig.savefig(status_path,dpi=190,bbox_inches="tight"); plt.close(fig)
        enh._add_pdf_figure(story, context, styles, status_path, f"Aprobados, reprobados y no evaluados de {name}", "Resultados consolidados del Examen Complexivo.")

        comp_path = _chart_path(report_id, f"complexive_{idx}_components")
        fig, ax = plt.subplots(figsize=(6.8,4.4)); comp_labels=["Teórico","Práctico"]; comp_values=[float(item["theory_average"] or 0),float(item["practical_average"] or 0)]; ax.bar(comp_labels,comp_values); ax.set_ylim(0,100); ax.set_title(f"Promedio teórico y práctico · {name}"); ax.set_ylabel("Promedio / 100");
        for i,v in enumerate(comp_values): ax.text(i,v+1,f"{v:.2f}",ha="center",fontsize=8)
        fig.tight_layout(); fig.savefig(comp_path,dpi=190,bbox_inches="tight"); plt.close(fig)
        enh._add_pdf_figure(story, context, styles, comp_path, f"Promedio teórico frente a práctico de {name}", "Comparación descriptiva de los componentes ordinarios disponibles.")

        approval_path = _chart_path(report_id, f"complexive_{idx}_approval")
        fig, ax = plt.subplots(figsize=(6.8,4.4)); av=[ordinary["approved_pct"],consolidated["approved_pct"]]; ax.bar(["Ordinaria","Final"],av); ax.set_ylim(0,100); ax.set_title(f"Aprobación ordinaria y final · {name}"); ax.set_ylabel("Aprobación (%)");
        for i,v in enumerate(av): ax.text(i,v+1,f"{v:.2f}%",ha="center",fontsize=8)
        fig.tight_layout(); fig.savefig(approval_path,dpi=190,bbox_inches="tight"); plt.close(fig)
        enh._add_pdf_figure(story, context, styles, approval_path, f"Aprobación ordinaria frente a aprobación final de {name}", "La diferencia refleja el cambio descriptivo posterior al proceso supletorio cuando existió.")

        if supplementary["total"]:
            supp_path = _chart_path(report_id, f"complexive_{idx}_supp")
            fig, ax = plt.subplots(figsize=(6.8,4.4)); sv=[supplementary["total"],item["recovered"]]; ax.bar(["Participantes","Recuperados"],sv); ax.set_title(f"Supletorio · {name}"); ax.set_ylabel("Estudiantes");
            for i,v in enumerate(sv): ax.text(i,v+0.1,str(v),ha="center",fontsize=8)
            fig.tight_layout(); fig.savefig(supp_path,dpi=190,bbox_inches="tight"); plt.close(fig)
            enh._add_pdf_figure(story, context, styles, supp_path, f"Participantes y recuperados mediante supletorio de {name}", f"La efectividad descriptiva del supletorio fue {report_quality._pct(item['effectiveness'])}.")

    report_quality._pdf_heading(story, context, styles, 2, "Consolidado institucional del Examen Complexivo")
    institutional_rows=[]
    for item in items:
        institutional_rows.append([item["name"],item["final"]["total"],item["ordinary"]["approved"],item["supplementary"]["total"],item["recovered"],item["final"]["approved"],item["final"]["failed"],item["final"]["not_evaluated"],report_quality._pct(item["final"]["approved_pct"]),report_quality._fmt(item["theory_average"]),report_quality._fmt(item["practical_average"])])
    report_quality._pdf_caption(story, styles, context.table_caption("Consolidado institucional del Examen Complexivo por carrera"))
    story += [_table(["Carrera","Reg.","APR ord.","Sup.","Recup.","APR final","REP","N/E","% APR","Prom. teo.","Prom. prác."], institutional_rows, [3.8*cm,1.0*cm,1.2*cm,1.0*cm,1.1*cm,1.2*cm,.9*cm,.9*cm,1.2*cm,1.3*cm,1.3*cm], styles, 6.4), Spacer(1,.12*cm)]
    total_reg=sum(i["final"]["total"] for i in items); total_apr=sum(i["final"]["approved"] for i in items); total_rep=sum(i["final"]["failed"] for i in items); total_ne=sum(i["final"]["not_evaluated"] for i in items); total_sup=sum(i["supplementary"]["total"] for i in items); total_rec=sum(i["recovered"] for i in items)
    inst_approval=_pct(total_apr,total_reg); inst_eff=_pct(total_rec,total_sup)
    best=max(items,key=lambda i:i["final"]["approved_pct"]); worst=min(items,key=lambda i:i["final"]["approved_pct"])
    report_quality._pdf_body(story, styles, f"El consolidado institucional registra {total_reg} estudiantes, {total_apr} aprobados finales, {total_rep} reprobados y {total_ne} no evaluados. La aprobación final fue del {report_quality._pct(inst_approval)}. La mayor aprobación correspondió a {best['name']} ({report_quality._pct(best['final']['approved_pct'])}) y la menor a {worst['name']} ({report_quality._pct(worst['final']['approved_pct'])}), con una brecha de {report_quality._pct(round(best['final']['approved_pct']-worst['final']['approved_pct'],2))} puntos porcentuales. El supletorio registró {total_sup} participantes y {total_rec} recuperados, con una efectividad del {report_quality._pct(inst_eff)}.")

    ordered=sorted(items,key=lambda i:i["final"]["approved_pct"],reverse=True)
    charts=[
        (enh._save_bar([i["name"] for i in ordered],[i["final"]["approved_pct"] for i in ordered],"Ranking de aprobación final del Examen Complexivo","Aprobación (%)",_chart_path(report_id,"complexive_ranking"),100),"Ranking de aprobación final por carrera"),
        (_save_stacked([i["name"] for i in items],[i["final"]["approved"] for i in items],[i["final"]["failed"] for i in items],[i["final"]["not_evaluated"] for i in items],"Aprobados, reprobados y no evaluados por carrera",_chart_path(report_id,"complexive_status_all")),"Aprobados, reprobados y no evaluados por carrera"),
        (_save_grouped([i["name"] for i in items],[("Aprobación ordinaria",[i["ordinary"]["approved_pct"] for i in items]),("Aprobación final",[i["final"]["approved_pct"] for i in items])],"Aprobación ordinaria frente a final","Aprobación (%)",_chart_path(report_id,"complexive_ord_final"),100),"Aprobación ordinaria frente a aprobación final"),
        (_save_grouped([i["name"] for i in items],[("Participantes",[i["supplementary"]["total"] for i in items]),("Recuperados",[i["recovered"] for i in items])],"Participación y recuperación en supletorio","Estudiantes",_chart_path(report_id,"complexive_supp_all")),"Participantes en supletorio frente a recuperados"),
        (enh._save_bar([i["name"] for i in sorted(items,key=lambda x:x["effectiveness"],reverse=True)],[i["effectiveness"] for i in sorted(items,key=lambda x:x["effectiveness"],reverse=True)],"Efectividad del supletorio por carrera","Efectividad (%)",_chart_path(report_id,"complexive_eff"),100),"Efectividad del supletorio por carrera"),
        (_save_grouped([i["name"] for i in items],[("Teórico",[float(i["theory_average"] or 0) for i in items]),("Práctico",[float(i["practical_average"] or 0) for i in items])],"Promedio teórico frente a práctico","Promedio / 100",_chart_path(report_id,"complexive_components_all"),100),"Promedio teórico frente a práctico por carrera"),
        (enh._save_bar([i["name"] for i in sorted(items,key=lambda x:x["final"]["not_evaluated"],reverse=True)],[i["final"]["not_evaluated"] for i in sorted(items,key=lambda x:x["final"]["not_evaluated"],reverse=True)],"Estudiantes no evaluados por carrera","No evaluados",_chart_path(report_id,"complexive_ne")),"Estudiantes no evaluados por carrera"),
    ]
    for path,title in charts:
        enh._add_pdf_figure(story, context, styles, path, title, "Elaboración propia con base en los resultados consolidados del Examen Complexivo.")

    nuclei = _nuclei_data(report_id)
    nuclei_map={_career_key(r["career"]):r for r in nuclei["careers"]}
    compare=[]
    points=[]
    for item in items:
        nr=nuclei_map.get(_career_key(item["name"]))
        if not nr: continue
        compare.append([item["name"],report_quality._fmt(nr["average"]),report_quality._pct(nr["approval"]),report_quality._fmt(item["final"]["average_final"]),report_quality._pct(item["final"]["approved_pct"]),report_quality._pct(round(item["final"]["approved_pct"]-nr["approval"],2))])
        points.append((float(nr["approval"]),float(item["final"]["approved_pct"]),item["name"]))
    if compare:
        report_quality._pdf_heading(story, context, styles, 2, "Comparación descriptiva entre Núcleos y Examen Complexivo")
        report_quality._pdf_body(story, styles, "La comparación se realiza únicamente a nivel agregado por carrera. Las poblaciones de ambos módulos son independientes y, por tanto, las diferencias observadas no se interpretan como relaciones causales ni como seguimiento automático de los mismos estudiantes.")
        report_quality._pdf_caption(story, styles, context.table_caption("Comparación de resultados de Núcleos y Examen Complexivo por carrera"))
        story += [_table(["Carrera","Prom. Núcleos","% APR Núcleos","Prom. Complexivo","% APR Complexivo","Diferencia APR"],compare,[5.1*cm,2.2*cm,2.4*cm,2.4*cm,2.5*cm,2.3*cm],styles),Spacer(1,.12*cm)]
        grp=_save_grouped([r[0] for r in compare],[("Núcleos",[float(str(r[2]).replace(" %","").replace(",",".")) for r in compare]),("Complexivo",[float(str(r[4]).replace(" %","").replace(",",".")) for r in compare])],"Aprobación en Núcleos y Examen Complexivo","Aprobación (%)",_chart_path(report_id,"nuclei_complexive_bar"),100)
        enh._add_pdf_figure(story,context,styles,grp,"Comparación de aprobación entre Núcleos y Examen Complexivo","Se observa una diferencia descriptiva por carrera; la figura no establece causalidad.")
        scatter=_save_scatter(points,"Relación descriptiva entre aprobación de Núcleos y Complexivo","Aprobación en Núcleos (%)","Aprobación en Complexivo (%)",_chart_path(report_id,"nuclei_complexive_scatter"))
        enh._add_pdf_figure(story,context,styles,scatter,"Dispersión de aprobación de Núcleos y Complexivo","Los puntos representan carreras y requieren revisión académica cuando existe una separación amplia entre ambos resultados.")


def _project_status(project: dict[str, Any]) -> str:
    if project.get("final_status"):
        return str(project["final_status"])
    return "APROBADO" if project.get("final_grade") is not None and float(project["final_grade"]) >= 7 else "REPROBADO"


def _project_weakest(project: dict[str, Any]) -> tuple[str, float, float] | None:
    candidates=[]
    for row in project.get("scores",[]):
        values=[float(row[k]) for k in ("vocal_1","vocal_2","vocal_3") if row.get(k) is not None]
        if not values or not row.get("max_score"): continue
        avg=round(mean(values),2); ratio=avg/float(row["max_score"])
        candidates.append((row.get("criterion") or "Criterio",avg,float(row["max_score"]),ratio))
    if not candidates: return None
    name,avg,max_score,_=min(candidates,key=lambda x:x[3])
    return str(name),avg,max_score


def _pdf_projects(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    projects=get_projects(report_id).get("projects",[])
    if not projects: return
    report_quality._pdf_heading(story,context,styles,1,"Resultados del Trabajo de Titulación")
    report_quality._pdf_body(story,styles,f"Se registraron {len(projects)} estudiantes en Trabajo de Titulación. La sección conserva el detalle individual, la rúbrica de evaluación, la verificación de fórmulas y el análisis de cada registro.")
    consolidated=[[p.get("full_name") or "—",p.get("career_name") or "—",report_quality._fmt(p.get("written_average")),report_quality._fmt(p.get("practical_average")),report_quality._fmt(p.get("defense_average")),report_quality._fmt(p.get("oral_average")),report_quality._fmt(p.get("final_grade")),_project_status(p)] for p in projects]
    report_quality._pdf_caption(story,styles,context.table_caption("Consolidado de resultados del Trabajo de Titulación"))
    story += [_table(["Estudiante","Carrera","Escrito","Práctica","Defensa","Oral","Final","Estado"],consolidated,[4.0*cm,3.7*cm,1.7*cm,1.7*cm,1.7*cm,1.6*cm,1.5*cm,1.9*cm],styles,6.7),Spacer(1,.12*cm)]
    if len(projects)==1:
        report_quality._pdf_body(story,styles,"Los resultados corresponden a un único estudiante, por lo que el análisis es individual y no permite establecer una tendencia general de la carrera o del período.")
    for idx,p in enumerate(projects,1):
        name=p.get("full_name") or "Estudiante"
        report_quality._pdf_heading(story,context,styles,2,f"{name}",page_break=True)
        info=[
            ["Estudiante",name,"Identificación",p.get("identification") or "—"],
            ["Código de carrera",p.get("career_code") or "—","Carrera",p.get("career_name") or "—"],
            ["Número de acta",p.get("act_number") or "—","Fecha del acta",p.get("act_date") or "—"],
            ["Primer vocal",p.get("vocal_1") or "—","Segundo vocal",p.get("vocal_2") or "—"],
            ["Tercer vocal",p.get("vocal_3") or "—","Estado",_project_status(p)],
        ]
        report_quality._pdf_body(story,styles,"La información general identifica al estudiante, la carrera, el acta de grado y los integrantes del tribunal registrados en la fuente de Trabajo de Titulación.")
        report_quality._pdf_caption(story,styles,context.table_caption(f"Información general del Trabajo de Titulación de {name}"))
        story += [_table(["Dato","Resultado","Dato","Resultado"],info,[3.1*cm,5.4*cm,3.1*cm,5.4*cm],styles),Spacer(1,.12*cm)]

        written=[["Calificación tutor",report_quality._fmt(p.get("tutor_grade"))],["Calificación lector",report_quality._fmt(p.get("reader_grade"))],["Promedio trabajo escrito",report_quality._fmt(p.get("written_average"))]]
        report_quality._pdf_body(story,styles,"El trabajo escrito se obtiene a partir de las calificaciones del tutor y del lector. La tabla permite comprobar el promedio utilizado en el cálculo final.")
        report_quality._pdf_caption(story,styles,context.table_caption(f"Calificaciones del trabajo escrito de {name}"))
        story += [_table(["Componente","Calificación"],written,[9*cm,5*cm],styles),Spacer(1,.12*cm)]

        for evaluation_type,title in (("practical","Evaluación práctica"),("defense","Evaluación de la defensa")):
            scores=[r for r in p.get("scores",[]) if r.get("evaluation_type")==evaluation_type]
            if not scores: continue
            rows=[[r.get("criterion") or "—",report_quality._fmt(r.get("max_score")),report_quality._fmt(r.get("vocal_1")),report_quality._fmt(r.get("vocal_2")),report_quality._fmt(r.get("vocal_3"))] for r in scores]
            report_quality._pdf_body(story,styles,f"La {title.lower()} conserva la valoración por parámetro y por cada uno de los tres vocales, permitiendo identificar diferencias internas antes de calcular el promedio del componente.")
            report_quality._pdf_caption(story,styles,context.table_caption(f"{title} por vocal y parámetro de {name}"))
            story += [_table(["Parámetro","Máximo","Primer vocal","Segundo vocal","Tercer vocal"],rows,[6.2*cm,2.1*cm,2.6*cm,2.6*cm,2.6*cm],styles),Spacer(1,.12*cm)]

        summary_rows=[
            ["Promedio trabajo escrito",report_quality._fmt(p.get("written_average"))],
            ["Promedio evaluación práctica",report_quality._fmt(p.get("practical_average"))],
            ["Promedio evaluación defensa",report_quality._fmt(p.get("defense_average"))],
            ["Promedio defensa oral",report_quality._fmt(p.get("oral_average"))],
            ["Calificación final",report_quality._fmt(p.get("final_grade"))],
        ]
        report_quality._pdf_caption(story,styles,context.table_caption(f"Consolidado de calificaciones de {name}"))
        story += [_table(["Componente","Resultado"],summary_rows,[10*cm,4*cm],styles),Spacer(1,.12*cm)]
        expected_written=round(mean([float(v) for v in (p.get("tutor_grade"),p.get("reader_grade")) if v is not None]),2) if p.get("tutor_grade") is not None or p.get("reader_grade") is not None else None
        expected_oral=round((float(p["practical_average"])+float(p["defense_average"]))/2,2) if p.get("practical_average") is not None and p.get("defense_average") is not None else None
        expected_final=round(float(p["written_average"])*.60+float(p["oral_average"])*.40,2) if p.get("written_average") is not None and p.get("oral_average") is not None else None
        verification=[
            ["Trabajo escrito = (Tutor + Lector) / 2",report_quality._fmt(expected_written),report_quality._fmt(p.get("written_average")),"Correcto" if expected_written==p.get("written_average") else "Revisar"],
            ["Oral = (Práctica + Defensa) / 2",report_quality._fmt(expected_oral),report_quality._fmt(p.get("oral_average")),"Correcto" if expected_oral==p.get("oral_average") else "Revisar"],
            ["Final = Escrito × 60 % + Oral × 40 %",report_quality._fmt(expected_final),report_quality._fmt(p.get("final_grade")),"Correcto" if expected_final==p.get("final_grade") else "Revisar"],
        ]
        report_quality._pdf_caption(story,styles,context.table_caption(f"Verificación de fórmulas de {name}"))
        story += [_table(["Fórmula","Resultado calculado","Resultado registrado","Validación"],verification,[7.3*cm,3.1*cm,3.1*cm,3.0*cm],styles),Spacer(1,.12*cm)]
        weak=_project_weakest(p)
        analysis=f"El estudiante obtuvo {report_quality._fmt(p.get('written_average'))} en el trabajo escrito, {report_quality._fmt(p.get('practical_average'))} en la evaluación práctica, {report_quality._fmt(p.get('defense_average'))} en la defensa, {report_quality._fmt(p.get('oral_average'))} como promedio oral y {report_quality._fmt(p.get('final_grade'))} como calificación final, con estado {_project_status(p)}."
        if weak:
            analysis += f" El parámetro de menor desempeño relativo fue «{weak[0]}», con promedio {report_quality._fmt(weak[1])} sobre un máximo de {report_quality._fmt(weak[2])}."
        if len(projects)==1:
            analysis += " Este resultado debe interpretarse exclusivamente a nivel individual y no como tendencia de la carrera o del período."
        report_quality._pdf_body(story,styles,analysis)
        chart=_chart_path(report_id,f"thesis_{idx}")
        labels=["Trabajo escrito","Práctica","Defensa","Promedio oral","Nota final"]; vals=[float(p.get("written_average") or 0),float(p.get("practical_average") or 0),float(p.get("defense_average") or 0),float(p.get("oral_average") or 0),float(p.get("final_grade") or 0)]
        fig,ax=plt.subplots(figsize=(8.2,4.8)); ax.bar(labels,vals); ax.set_ylim(0,10); ax.set_ylabel("Calificación / 10"); ax.set_title(f"Componentes del Trabajo de Titulación · {_short(name,40)}"); ax.tick_params(axis="x",rotation=15)
        for i,v in enumerate(vals): ax.text(i,v+.15,f"{v:.2f}",ha="center",fontsize=8)
        fig.tight_layout(); fig.savefig(chart,dpi=200,bbox_inches="tight"); plt.close(fig)
        enh._add_pdf_figure(story,context,styles,chart,f"Resultados del Trabajo de Titulación de {name}","Comparación de los componentes utilizados en el cálculo de la calificación final.")


def _overall_component_averages(report: dict[str, Any]) -> tuple[float | None,float | None]:
    theory=[]; practical=[]
    for item in _complexive_rows(report):
        for row in item["ordinary"]["rows"]:
            if row.get("ordinary_theory") is not None: theory.append(float(row["ordinary_theory"]))
            if row.get("ordinary_practical") is not None: practical.append(float(row["ordinary_practical"]))
    return (round(mean(theory),2) if theory else None, round(mean(practical),2) if practical else None)


def _unique(items: list[str], limit: int = 12) -> list[str]:
    seen=set(); result=[]
    for item in items:
        key=" ".join(item.casefold().split())
        if key and key not in seen:
            seen.add(key); result.append(item)
    return result[:limit]


def _conclusions(report_id: int, report: dict[str, Any]) -> list[str]:
    out=[]
    req=report_completion.corrected_requirement_analysis(report_id)
    if req:
        out.append(f"Requisitos registró {req['total']} estudiantes; {req['complete']} cumplieron integralmente ({report_quality._pct(req['percentage'])}), {req['pending']} presentaron incumplimientos y {req['incomplete']} información incompleta.")
        if req.get("requirements"):
            low=min(req["requirements"],key=lambda r:r["percentage"]); out.append(f"El requisito con menor cumplimiento fue {low['label']}, con {report_quality._pct(low['percentage'])} y {low['does_not_comply']} registros marcados como no cumple.")
    sch=final._schedule_analysis(report_id)
    if sch["total"]:
        out.append(f"El cronograma contiene {sch['total']} actividades; {sch['evaluated']} cuentan con datos de ejecución y {sch['pending_evaluation']} permanecen sin evaluación, por lo que el cumplimiento no se completa automáticamente cuando falta evidencia real.")
    nuclei=_nuclei_data(report_id)
    if nuclei["careers"]:
        evals=sum(r["evaluated"] for r in nuclei["careers"]); apr=sum(r["approved"] for r in nuclei["careers"]); best=max(nuclei["careers"],key=lambda r:r["approval"]); worst=min(nuclei["careers"],key=lambda r:r["approval"])
        out.append(f"Núcleos conserva {len(nuclei['courses'])} cursos o materias y {evals} registros evaluados, con una aprobación institucional de {report_quality._pct(_pct(apr,evals))} y promedio institucional de {report_quality._fmt(nuclei['institutional_stats']['average'])}.")
        out.append(f"En Núcleos, la mayor aprobación correspondió a {best['career']} ({report_quality._pct(best['approval'])}) y la menor a {worst['career']} ({report_quality._pct(worst['approval'])}), con una brecha de {report_quality._pct(round(best['approval']-worst['approval'],2))} puntos porcentuales.")
        mod=defaultdict(list)
        for r in nuclei["careers"]: mod[r["modality"]].append(r)
        if len(mod)>1:
            vals=[]
            for name,rs in mod.items(): vals.append((name,_pct(sum(r["approved"] for r in rs),sum(r["evaluated"] for r in rs))))
            out.append("La comparación por modalidad en Núcleos registró " + " y ".join(f"{name} {report_quality._pct(value)} de aprobación" for name,value in vals) + "; la diferencia es descriptiva y requiere considerar la composición de cada población.")
    complexive=_complexive_rows(report)
    if complexive:
        total=sum(i["final"]["total"] for i in complexive); apr=sum(i["final"]["approved"] for i in complexive); rep=sum(i["final"]["failed"] for i in complexive); ne=sum(i["final"]["not_evaluated"] for i in complexive); best=max(complexive,key=lambda i:i["final"]["approved_pct"]); worst=min(complexive,key=lambda i:i["final"]["approved_pct"])
        out.append(f"El Examen Complexivo registró {total} estudiantes, {apr} aprobados finales, {rep} reprobados y {ne} no evaluados, con una aprobación institucional del {report_quality._pct(_pct(apr,total))}.")
        out.append(f"La mayor aprobación final del Complexivo fue {best['name']} con {report_quality._pct(best['final']['approved_pct'])}, mientras que {worst['name']} registró {report_quality._pct(worst['final']['approved_pct'])}; la brecha fue de {report_quality._pct(round(best['final']['approved_pct']-worst['final']['approved_pct'],2))} puntos porcentuales.")
        sup=sum(i["supplementary"]["total"] for i in complexive); rec=sum(i["recovered"] for i in complexive); out.append(f"El supletorio contó con {sup} participantes y {rec} recuperados, equivalente a una efectividad institucional del {report_quality._pct(_pct(rec,sup))}; este mecanismo mejoró el resultado final sin compensar automáticamente componentes no aprobados.")
        theo,prac=_overall_component_averages(report); diff=round(abs(float(theo or 0)-float(prac or 0)),2); lower="teórico" if (theo or 0)<(prac or 0) else "práctico"; out.append(f"El promedio teórico institucional del Complexivo fue {report_quality._fmt(theo)} y el práctico {report_quality._fmt(prac)}, con una diferencia de {report_quality._fmt(diff)} puntos; el componente {lower} presentó el menor promedio agregado.")
        out.append(f"Los {ne} estudiantes no evaluados representan {report_quality._pct(_pct(ne,total))} de los registros del Complexivo y requieren clasificación individual de la novedad antes del cierre definitivo.")
    projects=get_projects(report_id).get("projects",[])
    if projects:
        finals=[float(p["final_grade"]) for p in projects if p.get("final_grade") is not None]; approved=sum(v>=7 for v in finals); out.append(f"Trabajo de Titulación registró {len(projects)} estudiantes, {approved} aprobados y un promedio final de {report_quality._fmt(round(mean(finals),2) if finals else None)}; con una sola observación, el resultado es individual y no constituye una tendencia institucional.")
    duplicates=sum(len(v) for v in report.get("duplicate_warnings",{}).values()); zero=sum(1 for c in nuclei.get("courses",[]) for s in c.get("students",[]) if s.get("final_grade") is not None and float(s["final_grade"])==0)
    out.append(f"El control de calidad identificó {duplicates} posibles duplicidades nominales en Complexivo y {zero} notas iguales a cero en Núcleos; ambos tipos de registro deben verificarse en la fuente antes de interpretar una anomalía como desempeño académico.")
    return _unique(out,12)


def _recommendations(report_id: int, report: dict[str, Any]) -> list[dict[str,str]]:
    rows=[]
    def add(h,a,r,i,v,m,p,pri,e): rows.append({"hallazgo":h,"accion":a,"responsable":r,"indicador":i,"actual":v,"meta":m,"plazo":p,"prioridad":pri,"evidencia":e})
    req=report_completion.corrected_requirement_analysis(report_id)
    if req and req["pending"]: add(f"{req['pending']} estudiantes con requisitos pendientes","Regularizar los requisitos marcados como NO CUMPLE mediante seguimiento por responsable y fecha de cierre.","Coordinación de Titulación y áreas responsables","Casos pendientes",str(req["pending"]),"0","Antes del siguiente cierre","Alta","Matriz de regularización")
    nuclei=_nuclei_data(report_id)
    if nuclei["careers"]:
        worst=min(nuclei["careers"],key=lambda r:r["approval"]); add(f"Menor aprobación en Núcleos: {worst['career']} ({worst['approval']:.2f} %)","Revisar los cinco cursos con menor promedio y definir refuerzo focalizado previo a la siguiente evaluación.","Coordinación de carrera","Aprobación de Núcleos",f"{worst['approval']:.2f} %",f"> {min(100,worst['approval']+10):.2f} %","Siguiente período","Alta","Plan de refuerzo")
    items=_complexive_rows(report); bykey={_career_key(i["name"]):i for i in items}
    for wanted in ("REDES Y TELECOMUNICACIONES","DESARROLLO DE SOFTWARE","CONTABILIDAD"):
        item=next((i for k,i in bykey.items() if wanted in k),None)
        if item:
            rate=item["final"]["approved_pct"]; add(f"{item['name']} registra {rate:.2f} % de aprobación final","Analizar resultados ordinarios, componente teórico/práctico y casos de supletorio para definir un plan específico de mejora por carrera.","Coordinación de carrera","Aprobación final",f"{rate:.2f} %",f"> {min(100,rate+10):.2f} %","Siguiente convocatoria","Alta" if rate<70 else "Media","Informe de carrera y plan de acción")
    if items:
        ne=sum(i["final"]["not_evaluated"] for i in items); sup=sum(i["supplementary"]["total"] for i in items); rec=sum(i["recovered"] for i in items); theo,prac=_overall_component_averages(report)
        if ne: add(f"{ne} estudiantes no evaluados en Complexivo","Clasificar la causa de cada caso y cerrar documentalmente ausencia, retiro, novedad o evaluación pendiente.","Coordinación de Titulación","No evaluados",str(ne),"0 sin clasificación","30 días","Alta","Matriz de novedades")
        lower="teórico" if (theo or 0)<(prac or 0) else "práctico"; current=min(v for v in (theo,prac) if v is not None) if any(v is not None for v in (theo,prac)) else None
        if current is not None: add(f"El componente {lower} presenta el menor promedio agregado ({current:.2f})",f"Implementar refuerzo específico en el componente {lower} y verificar el cambio en la siguiente convocatoria.","Coordinaciones de carrera",f"Promedio {lower}",f"{current:.2f}",f"> {min(100,current+5):.2f}","Siguiente convocatoria","Media","Resultados comparativos")
        if sup: add(f"Efectividad institucional del supletorio: {_pct(rec,sup):.2f} %","Revisar por carrera los componentes que originan supletorio y reforzar contenidos antes de la recuperación.","Coordinaciones de carrera","Efectividad de supletorio",f"{_pct(rec,sup):.2f} %",f"> {min(100,_pct(rec,sup)+10):.2f} %","Siguiente supletorio","Media","Reporte de supletorio")
    duplicates=sum(len(v) for v in report.get("duplicate_warnings",{}).values())
    add(f"{duplicates} posibles registros duplicados identificados" if duplicates else "Control preventivo de duplicados","Validar cédula, correo y nombre antes de consolidar resultados y corregir la fuente cuando se detecte una duplicidad.","Coordinación de Titulación","Duplicados sin resolver",str(duplicates),"0","Antes del cierre","Media","Registro de depuración")
    projects=get_projects(report_id).get("projects",[])
    if projects:
        weak=[]
        for p in projects:
            w=_project_weakest(p)
            if w: weak.append(w)
        if weak:
            target=min(weak,key=lambda x:x[1]/x[2]); add(f"Menor desempeño relativo en Trabajo de Titulación: {target[0]} ({target[1]:.2f}/{target[2]:.2f})","Reforzar el parámetro identificado durante la preparación de la defensa y verificarlo en próximas rúbricas.","Tutor y Coordinación de Titulación",f"Promedio de {target[0]}",f"{target[1]:.2f}/{target[2]:.2f}","Mejorar al menos 10 %","Próxima cohorte","Media","Rúbricas comparativas")
    sch=final._schedule_analysis(report_id)
    if sch["pending_evaluation"]: add(f"{sch['pending_evaluation']} actividades sin evaluación de ejecución","Completar fecha ejecutada, estado, porcentaje, evidencia y observación antes del cierre del informe.","Responsables de cada fase","Actividades documentadas",f"{sch['evaluated']}/{sch['total']}",f"{sch['total']}/{sch['total']}","Antes de emitir versión final","Alta","Cronograma y evidencias")
    add("Falta una línea comparativa formal entre períodos","Mantener los mismos indicadores y comparar el siguiente período para evaluar variaciones y el efecto de las acciones implementadas.","Coordinación de Titulación","Indicadores comparables","1 período analizado","2 períodos comparables","Siguiente período","Media","Informe comparativo")
    unique=[]; seen=set()
    for row in rows:
        key=row["hallazgo"].casefold()
        if key not in seen: seen.add(key); unique.append(row)
    return unique[:12]


def _strengths_criticals_actions(report_id: int, report: dict[str, Any]) -> tuple[list[str],list[str],list[str]]:
    strengths=[]; critical=[]; actions=[]
    req=report_completion.corrected_requirement_analysis(report_id)
    if req: strengths.append(f"Cumplimiento integral de requisitos: {report_quality._pct(req['percentage'])} ({req['complete']} de {req['total']}).") if req["percentage"]>=80 else critical.append(f"Cumplimiento integral de requisitos: {report_quality._pct(req['percentage'])}, con {req['pending']+req['incomplete']} casos por regularizar.")
    n=_nuclei_data(report_id)
    if n["careers"]:
        strengths.append(f"Núcleos: {len(n['courses'])} cursos conservados y {report_quality._pct(n['institutional_approval'])} de aprobación institucional.") if n["institutional_approval"]>=70 else critical.append(f"Aprobación institucional de Núcleos: {report_quality._pct(n['institutional_approval'])}.")
        worst=min(n["careers"],key=lambda r:r["approval"]); critical.append(f"Menor aprobación de Núcleos: {worst['career']} con {report_quality._pct(worst['approval'])}.")
    c=_complexive_rows(report)
    if c:
        total=sum(i["final"]["total"] for i in c); apr=sum(i["final"]["approved"] for i in c); ne=sum(i["final"]["not_evaluated"] for i in c); rate=_pct(apr,total)
        strengths.append(f"Aprobación final del Examen Complexivo: {report_quality._pct(rate)} ({apr} aprobados).") if rate>=70 else critical.append(f"Aprobación final del Examen Complexivo: {report_quality._pct(rate)}.")
        if ne: critical.append(f"{ne} estudiantes del Complexivo constan como no evaluados.")
        sup=sum(i["supplementary"]["total"] for i in c); rec=sum(i["recovered"] for i in c)
        if sup: strengths.append(f"El supletorio recuperó {rec} de {sup} participantes ({report_quality._pct(_pct(rec,sup))}).")
    p=get_projects(report_id).get("projects",[])
    if p: strengths.append(f"Trabajo de Titulación registra {len(p)} caso(s) con detalle de acta, rúbrica y cálculo final.")
    recs=_recommendations(report_id,report); actions=[f"{r['accion']} Indicador: {r['indicador']}; meta: {r['meta']}." for r in recs[:3]]
    while len(strengths)<3: strengths.append("Se mantiene trazabilidad de los datos disponibles mediante tablas numeradas y análisis por componente.")
    while len(critical)<3: critical.append("No se registró un tercer resultado crítico cuantificado; se mantiene seguimiento preventivo de calidad de datos.")
    while len(actions)<3: actions.append("Mantener el seguimiento de indicadores y documentar los cambios en el siguiente corte institucional.")
    return _unique(strengths,3),_unique(critical,3),_unique(actions,3)


def _ishikawa_rows(report_id: int, report: dict[str, Any]) -> list[list[str]]:
    actions={
        "Gestión de datos":"Depurar registros, completar campos y validar duplicidades antes del cierre.",
        "Preparación académica":"Priorizar refuerzo en carreras y cursos con menor desempeño.",
        "Evaluación":"Revisar componentes con mayor reprobación y casos no evaluados.",
        "Seguimiento estudiantil":"Cerrar individualmente requisitos, ausencias y novedades pendientes.",
        "Planificación y cronogramas":"Documentar ejecución real, evidencia y porcentaje de cumplimiento.",
        "Gestión tecnológica y administrativa":"Corregir incidencias de importación y conservar trazabilidad de la fuente.",
    }
    risk={"Gestión de datos":"Calidad de datos","Preparación académica":"Académico","Evaluación":"Académico","Seguimiento estudiantil":"Seguimiento","Planificación y cronogramas":"Gestión","Gestión tecnológica y administrativa":"Operativo"}
    rows=[]
    for category,factors in final._ishikawa_factors(report_id,report):
        for factor in factors:
            empty="Sin hallazgos críticos" in factor
            rows.append([category,factor,factor,"Baja" if empty else "Alta","Preventivo" if empty else risk.get(category,"Gestión"),"Sí" if not empty else "No prioritaria",actions.get(category,"Verificar el hallazgo y definir una acción específica.")])
    return rows


class RecordingContext(report_quality.ExportContext):
    def __init__(self) -> None:
        super().__init__([0,0,0,0])
        self.table_titles: list[str] = []
        self.figure_titles: list[str] = []

    def table_caption(self, title: str) -> str:
        text=super().table_caption(title); self.table_titles.append(text); return text

    def figure_caption(self, title: str) -> str:
        text=super().figure_caption(title); self.figure_titles.append(text); return text


def _pdf_post(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> None:
    report_id=int(report["id"]); req=report_completion.corrected_requirement_analysis(report_id); nuclei=_nuclei_data(report_id); complexive=_complexive_rows(report); projects=get_projects(report_id).get("projects",[]); sch=final._schedule_analysis(report_id)
    report_quality._pdf_heading(story,context,styles,1,"Resumen ejecutivo de resultados")
    report_quality._pdf_body(story,styles,"El resumen ejecutivo integra los principales indicadores después de presentar el detalle de Requisitos, cronogramas, Núcleos, Examen Complexivo y Trabajo de Titulación. Cada indicador conserva la población propia de su módulo.")
    indicators=[]
    if req: indicators += [["Registros de requisitos",req["total"]],["Cumplimiento integral",report_quality._pct(req["percentage"])],["Requisitos pendientes",req["pending"]]]
    if sch["total"]: indicators += [["Actividades planificadas",sch["total"]],["Actividades con ejecución registrada",sch["evaluated"]],["Actividades sin evaluar",sch["pending_evaluation"]]]
    if nuclei["careers"]:
        evals=sum(r["evaluated"] for r in nuclei["careers"]); apr=sum(r["approved"] for r in nuclei["careers"]); records=sum(r["records"] for r in nuclei["careers"]); indicators += [["Cursos de Núcleos",len(nuclei["courses"])],["Registros de Núcleos",records],["Estudiantes/registros evaluados en Núcleos",evals],["Aprobación institucional de Núcleos",report_quality._pct(_pct(apr,evals))]]
    if complexive:
        reg=sum(i["final"]["total"] for i in complexive); apr=sum(i["final"]["approved"] for i in complexive); rep=sum(i["final"]["failed"] for i in complexive); ne=sum(i["final"]["not_evaluated"] for i in complexive); sup=sum(i["supplementary"]["total"] for i in complexive); rec=sum(i["recovered"] for i in complexive); indicators += [["Registrados en Examen Complexivo",reg],["Aprobados finales",apr],["Reprobados finales",rep],["No evaluados",ne],["Aprobación final",report_quality._pct(_pct(apr,reg))],["Participantes en supletorio",sup],["Recuperados",rec],["Efectividad del supletorio",report_quality._pct(_pct(rec,sup))]]
    if projects:
        finals=[float(p["final_grade"]) for p in projects if p.get("final_grade") is not None]; indicators += [["Estudiantes en Trabajo de Titulación",len(projects)],["Aprobación en Trabajo de Titulación",report_quality._pct(_pct(sum(v>=7 for v in finals),len(finals)))]]
    report_quality._pdf_caption(story,styles,context.table_caption("Indicadores principales del período")); story += [_table(["Indicador","Resultado"],indicators,[11.5*cm,4.5*cm],styles,7.6),Spacer(1,.15*cm)]
    strengths,critical,actions=_strengths_criticals_actions(report_id,report)
    report_quality._pdf_heading(story,context,styles,2,"Fortalezas principales")
    for item in strengths: report_quality._pdf_bullet(story,styles,item)
    report_quality._pdf_heading(story,context,styles,2,"Resultados críticos")
    for item in critical: report_quality._pdf_bullet(story,styles,item)
    report_quality._pdf_heading(story,context,styles,2,"Acciones prioritarias")
    for item in actions: report_quality._pdf_bullet(story,styles,item)
    dashboard_labels=[]; dashboard_values=[]
    if req: dashboard_labels.append("Requisitos"); dashboard_values.append(req["percentage"])
    if nuclei["careers"]: dashboard_labels.append("Núcleos"); dashboard_values.append(nuclei["institutional_approval"])
    if complexive:
        reg=sum(i["final"]["total"] for i in complexive); apr=sum(i["final"]["approved"] for i in complexive); dashboard_labels.append("Complexivo"); dashboard_values.append(_pct(apr,reg))
    if projects:
        finals=[float(p["final_grade"]) for p in projects if p.get("final_grade") is not None]; dashboard_labels.append("Trabajo titulación"); dashboard_values.append(_pct(sum(v>=7 for v in finals),len(finals)))
    if dashboard_labels:
        path=enh._save_bar(dashboard_labels,dashboard_values,"Tablero de indicadores principales","Resultado (%)",_chart_path(report_id,"executive_dashboard"),100); enh._add_pdf_figure(story,context,styles,path,"Tablero visual de indicadores principales","Los porcentajes representan indicadores de poblaciones independientes y no deben sumarse entre sí.")

    report_quality._pdf_heading(story,context,styles,1,"Análisis estratégico de resultados")
    report_quality._pdf_body(story,styles,"El análisis estratégico organiza hallazgos cuantificados y factores que requieren verificación. El diagrama de Ishikawa se utiliza como herramienta de síntesis y no como demostración causal.")
    fish=final._ishikawa(report_id,report); enh._add_pdf_figure(story,context,styles,fish,"Diagrama de Ishikawa de factores observados","Las seis categorías sintetizan hallazgos o aspectos que requieren verificación; el análisis detallado se desarrolla a continuación.")
    for paragraph in final._ishikawa_analysis(report_id,report): report_quality._pdf_body(story,styles,paragraph)
    ish_rows=_ishikawa_rows(report_id,report); report_quality._pdf_caption(story,styles,context.table_caption("Matriz de análisis del diagrama de Ishikawa")); story += [_table(["Categoría","Hallazgo","Evidencia estadística","Prioridad","Tipo de riesgo","Verificación","Acción sugerida"],ish_rows,[2.6*cm,3.4*cm,3.4*cm,1.4*cm,1.8*cm,1.8*cm,3.4*cm],styles,6.2),Spacer(1,.15*cm)]

    report_quality._pdf_heading(story,context,styles,1,"Conclusiones")
    for idx,item in enumerate(_conclusions(report_id,report),1): report_quality._pdf_bullet(story,styles,f"{idx}. {item}")
    recommendations=_recommendations(report_id,report)
    report_quality._pdf_heading(story,context,styles,1,"Recomendaciones")
    for idx,item in enumerate(recommendations,1): report_quality._pdf_bullet(story,styles,f"{idx}. {item['hallazgo']}: {item['accion']} Responsable: {item['responsable']}. Indicador: {item['indicador']}. Valor actual: {item['actual']}. Meta: {item['meta']}. Plazo: {item['plazo']}. Prioridad: {item['prioridad']}.")
    report_quality._pdf_heading(story,context,styles,1,"Plan de mejora")
    report_quality._pdf_body(story,styles,"La matriz separa hallazgo, acción, responsable, indicador, valor actual, meta, plazo y prioridad. Se divide en bloques para conservar legibilidad y repetir los encabezados en cada continuación.")
    chunks=[recommendations[i:i+4] for i in range(0,len(recommendations),4)] or [[]]
    for chunk_idx,chunk in enumerate(chunks,1):
        if chunk_idx>1:
            story.append(Spacer(1,.08*cm))
        rows=[[idx+(chunk_idx-1)*4,r["hallazgo"],r["accion"],r["responsable"],r["indicador"],r["actual"],r["meta"],r["plazo"],r["prioridad"]] for idx,r in enumerate(chunk,1)]
        report_quality._pdf_caption(story,styles,context.table_caption("Matriz de acciones de mejora" + (f" – continuación {chunk_idx}" if chunk_idx>1 else "")))
        story += [_table(["N.º","Hallazgo","Acción","Responsable","Indicador","Actual","Meta","Plazo","Prior."],rows,[.7*cm,2.4*cm,3.3*cm,2.3*cm,2.1*cm,1.5*cm,1.5*cm,1.8*cm,1.3*cm],styles,6.1),Spacer(1,.12*cm)]
    enh._pdf_references(story,context,styles)


def validate_pdf_report(report_id: int) -> dict[str, Any]:
    report=report_quality._report_data(report_id); nuclei=_nuclei_data(report_id); complexive=_complexive_rows(report); projects=get_projects(report_id).get("projects",[])
    checks=[]
    def add(name:str,ok:bool,detail:str,severity:str="warning"): checks.append({"name":name,"ok":ok,"detail":detail,"severity":severity})
    add("Núcleos registrados",len(nuclei["courses"])==TARGET_NUCLEI,f"Se detectaron {len(nuclei['courses'])} cursos/núcleos; para el informe base se esperan {TARGET_NUCLEI}.")
    add("Carreras con Complexivo",len(complexive)==TARGET_COMPLEXIVE_CAREERS,f"Se detectaron {len(complexive)} carreras con resultados; para el informe base se esperan {TARGET_COMPLEXIVE_CAREERS}.")
    missing_ord=[i["name"] for i in complexive if not i["ordinary"]["rows"]]; add("Evaluaciones ordinarias",not missing_ord,"Todas las carreras tienen evaluación ordinaria." if not missing_ord else "Sin evaluación ordinaria: "+", ".join(missing_ord),"error")
    missing_final=[i["name"] for i in complexive if not i["final"]["rows"]]; add("Consolidados finales",not missing_final,"Todas las carreras tienen consolidado final." if not missing_final else "Sin consolidado: "+", ".join(missing_final),"error")
    add("Trabajo de Titulación",bool(projects),f"Se detectaron {len(projects)} registros de Trabajo de Titulación.","warning")
    conclusions=_conclusions(report_id,report); add("Conclusiones no duplicadas",len(conclusions)==len(set(c.casefold() for c in conclusions)),f"Se generaron {len(conclusions)} conclusiones diferentes.","error")
    recs=_recommendations(report_id,report); add("Recomendaciones no duplicadas",len(recs)==len(set(r['hallazgo'].casefold() for r in recs)),f"Se generaron {len(recs)} recomendaciones diferentes.","error")
    duplicates=sum(len(v) for v in report.get("duplicate_warnings",{}).values()); add("Control de duplicados",duplicates==0,f"Se detectaron {duplicates} posibles duplicidades nominales para revisión.")
    errors=[c for c in checks if not c["ok"] and c["severity"]=="error"]
    warnings=[c for c in checks if not c["ok"] and c["severity"]!="error"]
    return {"ok":not errors,"checks":checks,"errors":errors,"warnings":warnings,"nuclei_count":len(nuclei["courses"]),"complexive_careers":len(complexive),"thesis_count":len(projects)}


def _index_block(title: str, entries: list[str], styles: Any) -> list[Any]:
    story=[Paragraph(title,styles["Title"]),Spacer(1,.2*cm)]
    if not entries:
        story.append(Paragraph("No se generaron elementos para este índice.",styles["BodyJustified"]))
    else:
        for entry in entries:
            story.append(Paragraph(html.escape(entry),styles["BodyText"]))
    story.append(PageBreak())
    return story


def build_pdf(report_id: int) -> Path:
    validation=validate_pdf_report(report_id)
    if validation["errors"]:
        raise ValueError("No se puede generar el PDF: " + "; ".join(item["detail"] for item in validation["errors"]))
    report_structure.ensure_structure_schema(); report_quality.base.EXPORT_DIR.mkdir(parents=True,exist_ok=True); report=report_quality._report_data(report_id); output=report_quality.base.EXPORT_DIR/f"informtit_{report_id}.pdf"; styles=report_quality._pdf_styles(); context=RecordingContext(); content=[]; temp_paths=[]
    report_quality._pdf_heading(content,context,styles,1,"Introducción")
    for paragraph in report_structure.introduction(report,report_id): report_quality._pdf_body(content,styles,paragraph)
    report_quality._pdf_legal(content,context,styles,report); report_quality._pdf_regulation(content,context,styles,report); report_quality._pdf_methodology(content,context,styles,report,temp_paths); report_quality._pdf_requirements(content,context,styles,report_id); report_quality._pdf_schedules(content,context,styles,report_id); report_quality._pdf_nucleus_results(content,context,styles,report_id); report_quality._pdf_complexive(content,context,styles,report,temp_paths); report_quality._pdf_projects(content,context,styles,report_id); report_quality._pdf_post_sections(content,context,styles,report)
    images=report_quality._additional_images(report)
    if images:
        report_quality._pdf_heading(content,context,styles,1,"Anexos de evidencias")
        for image in images:
            path=report_quality.base.image_path(image)
            if not path: continue
            title=str(image.get("title") or image.get("original_name") or "Evidencia"); report_quality._pdf_caption(content,styles,context.figure_caption(title)); content += [report_quality.base.fit_image(path,16.5*cm,20*cm),Spacer(1,.1*cm)]; report_quality._pdf_caption(content,styles,f"Nota. {image.get('source') or 'Fuente institucional'}.")
    prefix=list(report_quality.base.cover_pdf(report,styles)); prefix.append(Paragraph("ÍNDICE GENERAL",styles["Title"])); toc=TableOfContents(); toc.levelStyles=[ParagraphStyle("TOC1F",fontName="Helvetica-Bold",fontSize=10,leading=14,spaceBefore=4),ParagraphStyle("TOC2F",fontName="Helvetica",fontSize=9,leading=12,leftIndent=14),ParagraphStyle("TOC3F",fontName="Helvetica",fontSize=8,leading=11,leftIndent=28)]; prefix += [toc,PageBreak()]; prefix += _index_block("ÍNDICE DE TABLAS",context.table_titles,styles); prefix += _index_block("ÍNDICE DE FIGURAS",context.figure_titles,styles); story=prefix+content
    document=report_structure.TocDocTemplate(str(output),pagesize=A4,rightMargin=1.45*cm,leftMargin=1.45*cm,topMargin=3.4*cm,bottomMargin=1.35*cm,title=report["name"])
    try: document.multiBuild(story,canvasmaker=lambda *args,**kwargs: report_quality.base.NumberedCanvas(*args,report=report,**kwargs))
    finally:
        for path in temp_paths: path.unlink(missing_ok=True)
    return output


def install() -> None:
    if getattr(report_quality,"_full_detail_pdf_installed",False): return
    report_quality._pdf_nucleus_results=_pdf_nuclei
    report_quality._pdf_complexive=_pdf_complexive
    report_quality._pdf_projects=_pdf_projects
    report_quality._pdf_post_sections=_pdf_post
    report_quality.build_pdf=build_pdf
    core.build_pdf=build_pdf
    report_quality._full_detail_pdf_installed=True
