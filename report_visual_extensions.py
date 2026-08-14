from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

import report_completion
import report_enhancements as enh
import report_final_overhaul as final
import report_full_detail as full
import report_pdf_polish as polish
import report_quality
from process_service import get_projects


def _short(value: Any, limit: int = 42) -> str:
    text = " ".join(str(value or "").strip().split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _chart_path(report_id: int, name: str) -> Path:
    return enh._chart_path(report_id, "visual_" + name)


def _parse_date(value: Any) -> datetime | None:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _save_requirement_stacked(rows: list[dict[str, Any]], path: Path) -> Path:
    ordered = sorted(rows, key=lambda row: float(row.get("percentage") or 0), reverse=True)
    labels = [_short(row.get("career"), 40) for row in ordered]
    complete = [int(row.get("complete") or 0) for row in ordered]
    pending = [int(row.get("pending") or 0) for row in ordered]
    incomplete = [int(row.get("incomplete") or 0) for row in ordered]
    y = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(10.4, max(4.8, len(labels) * .48 + 1.8)))
    ax.barh(y, complete, label="Cumple integralmente")
    ax.barh(y, pending, left=complete, label="Pendiente")
    left = [a + b for a, b in zip(complete, pending)]
    ax.barh(y, incomplete, left=left, label="Información incompleta")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Estudiantes")
    ax.set_title("Cumplimiento y pendientes de requisitos por carrera")
    ax.legend(fontsize=8)
    ax.grid(axis="x", alpha=.18)
    fig.tight_layout()
    fig.savefig(path, dpi=210, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _add_requirement_visuals(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    data = report_completion.corrected_requirement_analysis(report_id)
    if not data or not data.get("careers"):
        return
    rows = sorted(data["careers"], key=lambda row: float(row.get("percentage") or 0), reverse=True)
    ranking = enh._save_bar(
        [_short(row["career"], 40) for row in rows],
        [float(row["percentage"]) for row in rows],
        "Cumplimiento integral de requisitos por carrera",
        "Cumplimiento (%)",
        _chart_path(report_id, "requirements_career_ranking"),
        100,
    )
    enh._add_pdf_figure(
        story,
        context,
        styles,
        ranking,
        "Cumplimiento integral de requisitos por carrera",
        "Las barras se ordenan de mayor a menor para identificar con rapidez las carreras que requieren mayor regularización.",
    )
    stacked = _save_requirement_stacked(rows, _chart_path(report_id, "requirements_career_status"))
    enh._add_pdf_figure(
        story,
        context,
        styles,
        stacked,
        "Cumplimiento y pendientes de requisitos por carrera",
        "Se muestran cantidades absolutas de estudiantes que cumplen integralmente, mantienen incumplimientos o presentan información incompleta.",
    )


def _save_timeline(report_id: int) -> Path | None:
    schedules = final._schedule_analysis(report_id).get("schedules", {})
    entries: list[tuple[datetime, datetime, str, str]] = []
    for source, rows in (("Núcleos / Complexivo", schedules.get("complexive", [])), ("Trabajo de Titulación", schedules.get("thesis", []))):
        for row in rows:
            start = _parse_date(row.get("start_date"))
            end = _parse_date(row.get("end_date")) or start
            if not start:
                continue
            if end and end < start:
                end = start
            entries.append((start, end or start, _short(row.get("activity") or "Actividad", 34), source))
    if not entries:
        return None
    entries.sort(key=lambda item: (item[0], item[1], item[2]))
    fig, ax = plt.subplots(figsize=(11.4, 7.0))
    y = list(range(len(entries)))
    starts = [mdates.date2num(item[0]) for item in entries]
    widths = [max(1.0, mdates.date2num(item[1]) - mdates.date2num(item[0]) + 1.0) for item in entries]
    ax.barh(y, widths, left=starts, height=.65)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{item[2]} · {item[3]}" for item in entries], fontsize=6.2)
    ax.invert_yaxis()
    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.tick_params(axis="x", rotation=30, labelsize=7)
    ax.set_title("Línea de tiempo general del proceso de titulación")
    ax.set_xlabel("Fecha")
    ax.grid(axis="x", alpha=.2)
    fig.tight_layout()
    path = _chart_path(report_id, "schedule_timeline")
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _add_schedule_timeline(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    path = _save_timeline(report_id)
    if not path:
        return
    enh._add_pdf_figure(
        story,
        context,
        styles,
        path,
        "Línea de tiempo general del proceso de titulación",
        "La visualización integra las actividades de Núcleos/Complexivo y Trabajo de Titulación y permite observar la extensión del proceso más allá del cierre académico cuando el cronograma institucional así lo establece.",
    )


def _add_nuclei_visuals(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    data = polish._filtered_nuclei_data(report_id)
    careers = [row for row in data.get("careers", []) if row.get("average") is not None]
    if careers:
        ordered = sorted(careers, key=lambda row: float(row["average"]), reverse=True)
        chart = enh._save_bar(
            [row["career"] for row in ordered],
            [float(row["average"]) for row in ordered],
            "Promedio académico de Núcleos por carrera",
            "Promedio / 10",
            _chart_path(report_id, "nuclei_average_by_career"),
            10,
        )
        enh._add_pdf_figure(
            story,
            context,
            styles,
            chart,
            "Promedio académico de Núcleos por carrera",
            "El promedio discrimina diferencias de desempeño que pueden no ser visibles cuando varias carreras presentan porcentajes de aprobación cercanos al 100 %.",
        )
    low = sorted(
        [row for row in data.get("course_rows", []) if row.get("average") is not None],
        key=lambda row: float(row["average"]),
    )[:5]
    if low:
        labels = [f"{_short(row['career'], 20)} · {_short(row['nucleus'], 24)} (N={row.get('students') or 0})" for row in low]
        chart = enh._save_bar(
            labels,
            [float(row["average"]) for row in low],
            "Cinco cursos o núcleos con menor promedio",
            "Promedio / 10",
            _chart_path(report_id, "nuclei_low_five"),
            10,
        )
        enh._add_pdf_figure(
            story,
            context,
            styles,
            chart,
            "Cinco cursos o núcleos con menor promedio",
            "Cada etiqueta incorpora N, correspondiente al número de registros del curso, para evitar interpretar del mismo modo resultados con tamaños de grupo diferentes.",
        )


def _save_gap_from_points(points: list[tuple[float, float, str]], title: str, xlabel: str, ylabel: str, path: Path) -> Path:
    gaps = sorted([(label, round(y - x, 2)) for x, y, label in points], key=lambda item: item[1])
    labels = [_short(label, 38) for label, _ in gaps]
    values = [value for _, value in gaps]
    fig, ax = plt.subplots(figsize=(10.2, max(4.8, len(labels) * .48 + 1.8)))
    y = list(range(len(labels)))
    ax.barh(y, values)
    ax.axvline(0, linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Brecha en puntos porcentuales (Complexivo − Núcleos)")
    ax.set_title("Brecha de aprobación entre Núcleos y Examen Complexivo")
    ax.grid(axis="x", alpha=.2)
    for index, value in enumerate(values):
        ax.text(value + (.8 if value >= 0 else -.8), index, f"{value:.2f} pp", va="center", ha="left" if value >= 0 else "right", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=210, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def complexive_component_approval(items: list[dict[str, Any]]) -> tuple[list[str], list[float], list[float]]:
    labels: list[str] = []
    theory_rates: list[float] = []
    practical_rates: list[float] = []
    for item in items:
        rows = item.get("ordinary", {}).get("rows", [])
        theory = [float(row["ordinary_theory"]) for row in rows if row.get("ordinary_theory") is not None]
        practical = [float(row["ordinary_practical"]) for row in rows if row.get("ordinary_practical") is not None]
        labels.append(str(item.get("name") or "Sin carrera"))
        theory_rates.append(round(sum(value >= 70 for value in theory) / len(theory) * 100, 2) if theory else 0.0)
        practical_rates.append(round(sum(value >= 70 for value in practical) / len(practical) * 100, 2) if practical else 0.0)
    return labels, theory_rates, practical_rates


def _add_complexive_visuals(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> None:
    items = full._complexive_rows(report)
    if not items:
        return
    report_id = int(report["id"])
    gain_order = sorted(items, key=lambda item: float(item["final"]["approved_pct"] - item["ordinary"]["approved_pct"]), reverse=True)
    gain = enh._save_bar(
        [item["name"] for item in gain_order],
        [round(float(item["final"]["approved_pct"] - item["ordinary"]["approved_pct"]), 2) for item in gain_order],
        "Incremento de aprobación posterior al supletorio",
        "Incremento (puntos porcentuales)",
        _chart_path(report_id, "complexive_supp_gain"),
    )
    enh._add_pdf_figure(
        story,
        context,
        styles,
        gain,
        "Incremento de aprobación posterior al supletorio por carrera",
        "La ganancia corresponde a la diferencia entre la aprobación final y la aprobación ordinaria; no implica que todo el incremento sea atribuible causalmente al supletorio.",
    )
    labels, theory_rates, practical_rates = complexive_component_approval(items)
    chart = full._save_grouped(
        labels,
        [("Componente teórico aprobado", theory_rates), ("Componente práctico aprobado", practical_rates)],
        "Tasa de aprobación teórica frente a práctica",
        "Aprobación del componente (%)",
        _chart_path(report_id, "complexive_component_approval"),
        100,
    )
    enh._add_pdf_figure(
        story,
        context,
        styles,
        chart,
        "Aprobación del componente teórico frente al práctico por carrera",
        "Cada tasa se calcula únicamente entre estudiantes con calificación disponible en el componente correspondiente; aprobar el Complexivo requiere cumplir individualmente ambos componentes según la regla institucional.",
    )


def cohort_criterion_stats(projects: list[dict[str, Any]], evaluation_type: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for project in projects:
        for row in project.get("scores", []):
            if row.get("evaluation_type") != evaluation_type:
                continue
            maximum = float(row.get("max_score") or 0)
            if maximum <= 0:
                continue
            criterion = " ".join(str(row.get("criterion") or "Criterio").strip().split())
            key = re.sub(r"\s+", " ", criterion.casefold())
            bucket = grouped.setdefault(key, {"criterion": criterion, "ratios": [], "values": [], "maxima": []})
            for field in ("vocal_1", "vocal_2", "vocal_3"):
                if row.get(field) is None:
                    continue
                value = float(row[field])
                bucket["values"].append(value)
                bucket["maxima"].append(maximum)
                bucket["ratios"].append(value / maximum * 100)
    result: list[dict[str, Any]] = []
    for bucket in grouped.values():
        if not bucket["ratios"]:
            continue
        result.append(
            {
                "criterion": bucket["criterion"],
                "percentage": round(mean(bucket["ratios"]), 2),
                "average": round(mean(bucket["values"]), 2),
                "maximum": round(mean(bucket["maxima"]), 2),
                "n": len(bucket["ratios"]),
            }
        )
    return sorted(result, key=lambda row: row["percentage"])


def _save_criterion_chart(rows: list[dict[str, Any]], title: str, path: Path) -> Path:
    labels = [_short(row["criterion"], 44) for row in rows]
    values = [float(row["percentage"]) for row in rows]
    fig, ax = plt.subplots(figsize=(9.8, max(4.4, len(labels) * .58 + 1.5)))
    y = list(range(len(labels)))
    ax.barh(y, values)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Desempeño promedio respecto del puntaje máximo (%)")
    ax.set_title(title)
    ax.grid(axis="x", alpha=.2)
    for index, row in enumerate(rows):
        ax.text(min(float(row["percentage"]) + 1, 98), index, f"{row['percentage']:.2f} %", va="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=210, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _add_project_visuals(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    projects = get_projects(report_id).get("projects", [])
    if not projects:
        return
    scored = [project for project in projects if project.get("final_grade") is not None]
    if scored:
        ordered = sorted(scored, key=lambda project: float(project["final_grade"]), reverse=True)
        final_chart = enh._save_bar(
            [_short(project.get("full_name") or "Estudiante", 38) for project in ordered],
            [float(project["final_grade"]) for project in ordered],
            "Calificación final de los estudiantes",
            "Calificación / 10",
            _chart_path(report_id, "thesis_final_ranking"),
            10,
        )
        enh._add_pdf_figure(
            story,
            context,
            styles,
            final_chart,
            "Calificación final de los estudiantes de Trabajo de Titulación",
            "Ranking descriptivo de las calificaciones finales registradas en el componente.",
        )
    component_projects = [project for project in projects if all(project.get(key) is not None for key in ("written_average", "practical_average", "defense_average"))]
    if component_projects:
        chart = full._save_grouped(
            [_short(project.get("full_name") or "Estudiante", 32) for project in component_projects],
            [
                ("Trabajo escrito", [float(project["written_average"]) for project in component_projects]),
                ("Evaluación práctica", [float(project["practical_average"]) for project in component_projects]),
                ("Defensa", [float(project["defense_average"]) for project in component_projects]),
            ],
            "Trabajo escrito, práctica y defensa por estudiante",
            "Calificación / 10",
            _chart_path(report_id, "thesis_components_cohort"),
            10,
        )
        enh._add_pdf_figure(
            story,
            context,
            styles,
            chart,
            "Trabajo escrito, evaluación práctica y defensa por estudiante",
            "La comparación permite identificar en qué componente se concentra la menor calificación de cada estudiante.",
        )
    for evaluation_type, title, figure_title in (
        ("practical", "Desempeño promedio de criterios de evaluación práctica", "Desempeño promedio por criterio de evaluación práctica"),
        ("defense", "Desempeño promedio de criterios de defensa", "Desempeño promedio por criterio de defensa"),
    ):
        rows = cohort_criterion_stats(projects, evaluation_type)
        if not rows:
            continue
        path = _save_criterion_chart(rows, title, _chart_path(report_id, f"thesis_criteria_{evaluation_type}"))
        enh._add_pdf_figure(
            story,
            context,
            styles,
            path,
            figure_title,
            "Los criterios se normalizan respecto de su puntaje máximo para hacer comparables parámetros con escalas distintas. El resultado representa el promedio de todas las valoraciones de vocales disponibles.",
        )
        weakest = rows[0]
        report_quality._pdf_body(
            story,
            styles,
            f"El criterio con menor desempeño promedio relativo en {('la evaluación práctica' if evaluation_type == 'practical' else 'la defensa')} fue «{weakest['criterion']}», con {report_quality._fmt(weakest['average'])} puntos promedio sobre un máximo medio de {report_quality._fmt(weakest['maximum'])}, equivalente al {report_quality._pct(weakest['percentage'])}. Este resultado resume la cohorte disponible y no corresponde al valor aislado de un solo estudiante.",
        )


def _hallazgo_frequencies(report_id: int, report: dict[str, Any]) -> list[tuple[str, int]]:
    findings: list[tuple[str, int]] = []
    requirements = report_completion.corrected_requirement_analysis(report_id)
    if requirements:
        count = int(requirements.get("pending") or 0) + int(requirements.get("incomplete") or 0)
        if count:
            findings.append(("Requisitos pendientes o incompletos", count))
    nuclei = polish._filtered_nuclei_data(report_id)
    nuclei_count = sum(int(row.get("failed") or 0) + int(row.get("unevaluated") or 0) for row in nuclei.get("careers", []))
    if nuclei_count:
        findings.append(("Registros reprobados/no evaluados en Núcleos", nuclei_count))
    complexive = full._complexive_rows(report)
    complexive_count = sum(int(item["final"].get("failed") or 0) + int(item["final"].get("not_evaluated") or 0) for item in complexive)
    if complexive_count:
        findings.append(("Reprobados/no evaluados en Complexivo", complexive_count))
    projects = get_projects(report_id).get("projects", [])
    thesis_count = sum(project.get("final_grade") is None or float(project.get("final_grade") or 0) < 7 for project in projects)
    if thesis_count:
        findings.append(("No aprobados/incompletos en Trabajo de Titulación", int(thesis_count)))
    schedule = final._schedule_analysis(report_id)
    schedule_count = sum(int(schedule.get(key) or 0) for key in ("pending_evaluation", "not_complied", "delayed", "partial"))
    if schedule_count:
        findings.append(("Desviaciones o actividades sin cierre de cronograma", schedule_count))
    duplicates = sum(len(values) for values in report.get("duplicate_warnings", {}).values())
    zeros = sum(1 for course in nuclei.get("courses", []) for student in course.get("students", []) if student.get("final_grade") is not None and float(student["final_grade"]) == 0)
    quality_count = duplicates + zeros
    if quality_count:
        findings.append(("Incidencias de calidad de datos", quality_count))
    return sorted(findings, key=lambda item: item[1], reverse=True)


def _save_pareto(findings: list[tuple[str, int]], path: Path) -> Path:
    labels = [_short(label, 40) for label, _ in findings]
    values = [int(value) for _, value in findings]
    total = sum(values) or 1
    cumulative: list[float] = []
    running = 0
    for value in values:
        running += value
        cumulative.append(running / total * 100)
    x = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    ax.bar(x, values)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=7.2)
    ax.set_ylabel("Frecuencia de casos/registros")
    ax.set_title("Priorización de hallazgos cuantificados")
    ax.grid(axis="y", alpha=.18)
    ax2 = ax.twinx()
    ax2.plot(x, cumulative, marker="o")
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("Porcentaje acumulado (%)")
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _add_pareto(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> None:
    report_id = int(report["id"])
    findings = _hallazgo_frequencies(report_id, report)
    if not findings:
        return
    path = _save_pareto(findings, _chart_path(report_id, "strategic_pareto"))
    enh._add_pdf_figure(
        story,
        context,
        styles,
        path,
        "Priorización de hallazgos cuantificados del proceso de titulación",
        "La frecuencia consolida incidencias documentadas por módulo para ordenar la atención. Los módulos conservan poblaciones independientes, por lo que el gráfico se interpreta como priorización operativa y no como una población estadística única.",
    )


def _correct_conclusions(base: Any, report_id: int, report: dict[str, Any]) -> list[str]:
    conclusions = list(base(report_id, report))
    projects = get_projects(report_id).get("projects", [])
    if not projects:
        return conclusions
    corrected: list[str] = []
    for item in conclusions:
        if "Trabajo de Titulación registró" in item and "con una sola observación" in item:
            item = item.replace(
                "; con una sola observación, el resultado es individual y no constituye una tendencia institucional.",
                f"; dado que el componente comprende únicamente {len(projects)} estudiantes, los resultados se interpretan descriptivamente y no como una tendencia institucional.",
            )
        corrected.append(item)
    return corrected


def _correct_recommendations(base: Any, report_id: int, report: dict[str, Any]) -> list[dict[str, str]]:
    rows = [dict(row) for row in base(report_id, report)]
    rows = [row for row in rows if not row.get("hallazgo", "").startswith("Menor desempeño relativo en Trabajo de Titulación:")]
    for row in rows:
        indicator = row.get("indicador", "")
        if indicator in {"Aprobación de Núcleos", "Aprobación final", "Efectividad de supletorio"} or indicator.startswith("Promedio teórico") or indicator.startswith("Promedio práctico"):
            row["meta"] = "Superar la línea base del período con una meta institucional justificada"
    projects = get_projects(report_id).get("projects", [])
    criterion_rows = cohort_criterion_stats(projects, "practical") + cohort_criterion_stats(projects, "defense")
    if criterion_rows:
        weakest = min(criterion_rows, key=lambda row: float(row["percentage"]))
        rows.append(
            {
                "hallazgo": f"Menor desempeño promedio relativo en Trabajo de Titulación: {weakest['criterion']} ({weakest['percentage']:.2f} % del máximo)",
                "accion": "Reforzar el criterio identificado durante la preparación de la defensa y verificar su evolución mediante el promedio de las rúbricas de la siguiente cohorte.",
                "responsable": "Tutor y Coordinación de Titulación",
                "indicador": f"Desempeño promedio relativo de {weakest['criterion']}",
                "actual": f"{weakest['percentage']:.2f} % del máximo",
                "meta": "Superar la línea base del período en la siguiente cohorte",
                "plazo": "Próxima cohorte",
                "prioridad": "Media",
                "evidencia": "Rúbricas consolidadas por criterio",
            }
        )
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        key = row.get("hallazgo", "").casefold()
        if key and key not in seen:
            seen.add(key)
            unique.append(row)
    return unique[:12]


def install() -> None:
    if getattr(report_quality, "_visual_extensions_installed", False):
        return

    base_requirements = report_quality._pdf_requirements
    base_schedules = report_quality._pdf_schedules
    base_nuclei = report_quality._pdf_nucleus_results
    base_complexive = report_quality._pdf_complexive
    base_projects = report_quality._pdf_projects
    base_post = report_quality._pdf_post_sections
    base_conclusions = full._conclusions
    base_recommendations = full._recommendations

    def requirements(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
        base_requirements(story, context, styles, report_id)
        _add_requirement_visuals(story, context, styles, report_id)

    def schedules(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
        base_schedules(story, context, styles, report_id)
        _add_schedule_timeline(story, context, styles, report_id)

    def nuclei(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
        base_nuclei(story, context, styles, report_id)
        _add_nuclei_visuals(story, context, styles, report_id)

    def complexive(story: list[Any], context: Any, styles: Any, report: dict[str, Any], temp_paths: list[Path]) -> None:
        original_scatter = full._save_scatter
        original_add = enh._add_pdf_figure

        def add_proxy(story_: list[Any], context_: Any, styles_: Any, path: Path, title: str, note: str) -> None:
            if title == "Dispersión de aprobación de Núcleos y Complexivo":
                title = "Ranking de brecha de aprobación entre Núcleos y Complexivo"
                note = "Brecha calculada como aprobación del Examen Complexivo menos aprobación de Núcleos por carrera; la comparación es descriptiva y no causal."
            original_add(story_, context_, styles_, path, title, note)

        try:
            full._save_scatter = _save_gap_from_points
            enh._add_pdf_figure = add_proxy
            base_complexive(story, context, styles, report, temp_paths)
        finally:
            full._save_scatter = original_scatter
            enh._add_pdf_figure = original_add
        _add_complexive_visuals(story, context, styles, report)

    def projects(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
        base_projects(story, context, styles, report_id)
        _add_project_visuals(story, context, styles, report_id)

    def post(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> None:
        original_heading = report_quality._pdf_heading
        original_add = enh._add_pdf_figure
        injected = {"pareto": False}

        def heading_proxy(story_: list[Any], context_: Any, styles_: Any, level: int, title: str, page_break: bool = False) -> None:
            if level == 1 and title == "Conclusiones" and not injected["pareto"]:
                _add_pareto(story_, context_, styles_, report)
                injected["pareto"] = True
            original_heading(story_, context_, styles_, level, title, page_break)

        def add_proxy(story_: list[Any], context_: Any, styles_: Any, path: Path, title: str, note: str) -> None:
            if title == "Diagrama de Ishikawa de factores observados":
                title = "Diagrama de factores asociados y aspectos por verificar"
                note = "Las categorías organizan hallazgos observados o aspectos que requieren verificación; el diagrama no demuestra causalidad ni identifica por sí solo causas raíz."
            original_add(story_, context_, styles_, path, title, note)

        try:
            report_quality._pdf_heading = heading_proxy
            enh._add_pdf_figure = add_proxy
            base_post(story, context, styles, report)
        finally:
            report_quality._pdf_heading = original_heading
            enh._add_pdf_figure = original_add

    def conclusions(report_id: int, report: dict[str, Any]) -> list[str]:
        return _correct_conclusions(base_conclusions, report_id, report)

    def recommendations(report_id: int, report: dict[str, Any]) -> list[dict[str, str]]:
        return _correct_recommendations(base_recommendations, report_id, report)

    full._conclusions = conclusions
    full._recommendations = recommendations
    report_quality._pdf_requirements = requirements
    report_quality._pdf_schedules = schedules
    report_quality._pdf_nucleus_results = nuclei
    report_quality._pdf_complexive = complexive
    report_quality._pdf_projects = projects
    report_quality._pdf_post_sections = post
    report_quality._visual_extensions_installed = True
