from __future__ import annotations

from typing import Any

import report_integrity_core as integrity


def _format_names(names: list[str]) -> str:
    clean = list(dict.fromkeys(str(name or "").strip() for name in names if str(name or "").strip()))
    if not clean:
        return "—"
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} y {clean[1]}"
    return ", ".join(clean[:-1]) + f" y {clean[-1]}"


def _none(items: list[str]) -> list[str]:
    return items[:2] if items else ["Sin hallazgos críticos cuantificables"]


def factors(report_id: int, report: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """Construye el Ishikawa desde la misma auditoría usada por el informe.

    No intenta demostrar causalidad. Los empates se conservan y las categorías
    sin evidencia se declaran explícitamente sin inventar un tercer hallazgo.
    """
    del report
    audit = integrity.audit_report(report_id, resolve_resources=False)
    if audit["mode"] != "normal":
        empty = ["Sin hallazgos críticos cuantificables"]
        return [
            ("Gestión de datos", empty),
            ("Preparación académica", empty),
            ("Evaluación", empty),
            ("Seguimiento estudiantil", empty),
            ("Planificación y cronogramas", empty),
            ("Gestión tecnológica y administrativa", empty),
        ]

    metrics = audit["metrics"]
    req = metrics["requirements"]
    nuclei = metrics["nuclei"]
    comp = metrics["complexive"]
    thesis = metrics["thesis"]
    schedules = metrics["schedules"]

    data_factors: list[str] = []
    if req["incomplete"]:
        data_factors.append(f"{req['incomplete']} estudiantes con información de requisitos todavía no cerrada")
    if thesis["incomplete"]:
        data_factors.append(f"{thesis['incomplete']} registros incompletos en Trabajo de Titulación")
    if audit["duplicates"]["unresolved_probable"]:
        data_factors.append(f"{audit['duplicates']['unresolved_probable']} duplicados probables pendientes de resolución")

    academic_factors: list[str] = []
    strict = integrity.strict_nuclei(report_id)
    low_courses = [row for row in strict.get("course_rows", []) if row.get("approval") is not None and float(row["approval"]) < 70]
    if low_courses:
        academic_factors.append(f"{len(low_courses)} cursos o núcleos con aprobación menor al 70 %")
    careers = list(nuclei.get("careers", []))
    if careers:
        minimum = min(float(row["approval"]) for row in careers)
        tied = [str(row["career"]) for row in careers if float(row["approval"]) == minimum]
        academic_factors.append(
            f"Menor aprobación en Núcleos: {_format_names(tied)} ({minimum:.2f} %)"
        )

    evaluation_factors: list[str] = []
    if comp["failed"]:
        evaluation_factors.append(f"{comp['failed']} reprobados finales en Examen Complexivo")
    if comp["not_evaluated"]:
        evaluation_factors.append(f"{comp['not_evaluated']} estudiantes no evaluados en Examen Complexivo")
    if thesis["failed"]:
        evaluation_factors.append(f"{thesis['failed']} reprobados en Trabajo de Titulación")

    followup_factors: list[str] = []
    if req["pending"]:
        followup_factors.append(f"{req['pending']} estudiantes con requisitos NO CUMPLE o que requieren corrección")
    if nuclei["unevaluated"]:
        followup_factors.append(f"{nuclei['unevaluated']} registros no evaluados en Núcleos")
    if comp["not_evaluated"]:
        followup_factors.append(f"{comp['not_evaluated']} casos no evaluados del Complexivo requieren clasificación")

    schedule_factors: list[str] = []
    if schedules["pending_evaluation"]:
        schedule_factors.append(f"{schedules['pending_evaluation']} actividades sin evaluación de ejecución")
    if schedules["incomplete_evidence"]:
        schedule_factors.append(f"{schedules['incomplete_evidence']} actividades evaluadas con evidencia incompleta")

    tech_factors: list[str] = []
    rec = audit["reconciliation"]
    if rec["reasons"].get("Duplicado"):
        tech_factors.append(f"{rec['reasons']['Duplicado']} cursos duplicados excluidos en la conciliación")
    exact = int(audit["duplicates"].get("nuclei_exact_omitted") or 0)
    if exact:
        tech_factors.append(f"{exact} filas duplicadas exactas omitidas del Excel de Núcleos")
    if not rec["balanced"]:
        tech_factors.append("La conciliación de cursos importados no cierra matemáticamente")

    return [
        ("Gestión de datos", _none(data_factors)),
        ("Preparación académica", _none(academic_factors)),
        ("Evaluación", _none(evaluation_factors)),
        ("Seguimiento estudiantil", _none(followup_factors)),
        ("Planificación y cronogramas", _none(schedule_factors)),
        ("Gestión tecnológica y administrativa", _none(tech_factors)),
    ]
