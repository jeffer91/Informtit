from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable

import completion_service
import nuclei_excel_import
import process_service
import report_completion
import report_full_detail as full
import report_quality
import report_integrity_core as integrity
from db import connection


_BASE_VALIDATE: Callable[[int], dict[str, Any]] | None = None
_BASE_EXECUTIVE_DATA: Callable[[int], dict[str, Any]] | None = None
_BASE_CONCLUSIONS: Callable[[int, dict[str, Any]], list[str]] | None = None
_BASE_REPLACE_SCHEDULE: Callable[..., dict[str, Any]] | None = None
_BASE_REPLACE_SCHEDULE_EXTENDED: Callable[..., dict[str, Any]] | None = None
_BASE_IMPORT_NUCLEI_EXCEL: Callable[..., dict[str, Any]] | None = None


def configure(
    *,
    validate: Callable[[int], dict[str, Any]],
    executive_data: Callable[[int], dict[str, Any]],
    conclusions: Callable[[int, dict[str, Any]], list[str]],
    replace_schedule: Callable[..., dict[str, Any]],
    replace_schedule_extended: Callable[..., dict[str, Any]],
    import_nuclei_excel: Callable[..., dict[str, Any]],
) -> None:
    global _BASE_VALIDATE, _BASE_EXECUTIVE_DATA, _BASE_CONCLUSIONS
    global _BASE_REPLACE_SCHEDULE, _BASE_REPLACE_SCHEDULE_EXTENDED, _BASE_IMPORT_NUCLEI_EXCEL
    _BASE_VALIDATE = validate
    _BASE_EXECUTIVE_DATA = executive_data
    _BASE_CONCLUSIONS = conclusions
    _BASE_REPLACE_SCHEDULE = replace_schedule
    _BASE_REPLACE_SCHEDULE_EXTENDED = replace_schedule_extended
    _BASE_IMPORT_NUCLEI_EXCEL = import_nuclei_excel


def strict_course_detail(
    course: dict[str, Any],
    career_row: dict[str, Any] | None,
    institutional_average: float | None,
    institutional_approval: float,
) -> dict[str, Any]:
    students = list(course.get("students", []))
    approved = sum(integrity.nucleus_state(student) == "approved" for student in students)
    failed = sum(integrity.nucleus_state(student) == "failed" for student in students)
    evaluated = approved + failed
    grades = integrity.evaluated_grades(students)
    zeros = sum(
        integrity.nucleus_state(student) in {"approved", "failed"}
        and integrity.number(student.get("final_grade")) == 0
        for student in students
    )
    return {
        "records": len(students),
        "evaluated": evaluated,
        "approved": approved,
        "failed": failed,
        "unevaluated": len(students) - evaluated,
        "approval": full._pct(approved, evaluated),
        "approval_denominator_type": "EVALUADOS",
        "zeros": zeros,
        **integrity.stats(grades),
        "career_average": career_row.get("average") if career_row else None,
        "career_approval": career_row.get("approval") if career_row else None,
        "institutional_average": institutional_average,
        "institutional_approval": institutional_approval,
    }


def _schedule_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return integrity.schedule_key(row)


def schedule_summary_strict(report_id: int) -> dict[str, Any]:
    data = completion_service.get_schedules_extended(report_id)
    rows = list(data.get("complexive", [])) + list(data.get("thesis", []))
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    duplicates = 0
    for row in rows:
        try:
            key = _schedule_key(row)
        except ValueError:
            unique.append(row)
            continue
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(row)
    evaluated = [
        row for row in unique
        if row.get("execution_status")
        or row.get("compliance_percentage") is not None
        or row.get("executed_date")
    ]
    incomplete = [
        row for row in evaluated
        if not row.get("executed_date")
        or not row.get("execution_status")
        or not row.get("evidence")
    ]
    return {
        "rows": unique,
        "total": len(unique),
        "evaluated": len(evaluated),
        "pending_evaluation": len(unique) - len(evaluated),
        "duplicates": duplicates,
        "incomplete_evidence": len(incomplete),
    }


def cleanup_existing_schedule_duplicates() -> int:
    completion_service.ensure_completion_schema()
    deleted = 0
    with connection() as conn:
        rows = conn.execute("SELECT * FROM schedule_items ORDER BY report_id, sort_order, id").fetchall()
        groups: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
        for row in rows:
            try:
                key = (int(row["report_id"]), *_schedule_key(dict(row)))
            except ValueError:
                continue
            groups[key].append(row)

        for items in groups.values():
            if len(items) < 2:
                continue

            def evidence_score(row: Any) -> tuple[int, int]:
                score = sum(
                    bool(row[key])
                    for key in ("executed_date", "execution_status", "evidence", "observation")
                )
                score += int(row["compliance_percentage"] is not None)
                return score, int(row["id"])

            keep = max(items, key=evidence_score)
            for row in items:
                if int(row["id"]) == int(keep["id"]):
                    continue
                conn.execute("DELETE FROM schedule_items WHERE id=?", (int(row["id"]),))
                deleted += 1

        reports = [int(row[0]) for row in conn.execute("SELECT DISTINCT report_id FROM schedule_items").fetchall()]
        for report_id in reports:
            current = conn.execute(
                "SELECT id FROM schedule_items WHERE report_id=? ORDER BY start_date, end_date, id",
                (report_id,),
            ).fetchall()
            for order, row in enumerate(current, start=1):
                conn.execute("UPDATE schedule_items SET sort_order=? WHERE id=?", (order, int(row["id"])))
    return deleted


def replace_schedule_deduped(report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    if _BASE_REPLACE_SCHEDULE is None:
        raise RuntimeError("Integridad no configurada.")
    unique, duplicates = integrity.dedupe_schedule_entries(entries)
    result = dict(_BASE_REPLACE_SCHEDULE(report_id, schedule_type, unique))
    result["duplicates_omitted"] = duplicates
    return result


def replace_schedule_extended_deduped(report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    if _BASE_REPLACE_SCHEDULE_EXTENDED is None:
        raise RuntimeError("Integridad no configurada.")
    unique, duplicates = integrity.dedupe_schedule_entries(entries)
    result = dict(_BASE_REPLACE_SCHEDULE_EXTENDED(report_id, schedule_type, unique))
    result["duplicates_omitted"] = duplicates
    return result


def import_nuclei_audited(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if _BASE_IMPORT_NUCLEI_EXCEL is None:
        raise RuntimeError("Integridad no configurada.")
    records, _ = nuclei_excel_import.parse_excel_payload(payload)
    entries = integrity.nuclei_duplicate_entries(records)
    result = dict(_BASE_IMPORT_NUCLEI_EXCEL(report_id, payload))
    integrity.write_duplicate_logs(report_id, "Núcleos", entries)
    summary = dict(result.get("summary") or {})
    summary["duplicate_exact"] = sum(item["duplicate_type"] == "DUPLICADO EXACTO" for item in entries)
    summary["duplicate_probable"] = sum(item["duplicate_type"] == "DUPLICADO PROBABLE" for item in entries)
    result["summary"] = summary
    return result


def executive_data_integrity(report_id: int) -> dict[str, Any]:
    if _BASE_EXECUTIVE_DATA is None:
        return {}
    data = dict(_BASE_EXECUTIVE_DATA(report_id))
    metrics = integrity.report_metrics(report_id)
    data["reportMetrics"] = metrics
    req = metrics["requirements"]
    nuc = metrics["nuclei"]
    comp = metrics["complexive"]
    thesis = metrics["thesis"]
    schedules = metrics["schedules"]
    data["indicators"] = [
        ("Estudiantes registrados", req["registered"]),
        ("Cumplieron requisitos", req["complete"]),
        ("Registros evaluados en Núcleos", nuc["evaluated"]),
        ("No evaluados en Núcleos", nuc["unevaluated"]),
        ("Aprobados finales en Complexivo", comp["approved"]),
        ("Reprobados finales en Complexivo", comp["failed"]),
        ("No evaluados en Complexivo", comp["not_evaluated"]),
        ("Estudiantes en Trabajo de Titulación", thesis["total"]),
        ("Aprobados en Trabajo de Titulación", thesis["approved"]),
        ("Actividades planificadas", schedules["total"]),
        ("Actividades con ejecución registrada", schedules["evaluated"]),
        ("Actividades sin evaluar", schedules["pending_evaluation"]),
    ]
    return data


def automatic_actions_integrity(data: dict[str, Any]) -> list[dict[str, str]]:
    report = data.get("report") or {}
    report_id = int(report.get("id") or 0)
    if not report_id:
        return []
    audit = integrity.audit_report(report_id, resolve_resources=False)
    if audit["mode"] == "no_population":
        return []
    metrics = audit["metrics"]
    actions: list[dict[str, str]] = []

    def add(finding: str, action: str, responsible: str, indicator: str, evidence: str) -> None:
        actions.append({
            "finding": finding,
            "action": action,
            "responsible": responsible,
            "due_date": "",
            "indicator": indicator,
            "evidence": evidence,
            "status": "Pendiente",
        })

    req = metrics["requirements"]
    if req["pending"] or req["incomplete"]:
        add(
            f"Existen {req['pending']} casos con requisitos NO CUMPLE y {req['incomplete']} con información incompleta.",
            "Completar, corregir o clasificar los requisitos pendientes antes del cierre.",
            "Áreas responsables de requisitos",
            "Casos de requisitos pendientes o incompletos",
            "Matriz de requisitos",
        )

    nuc = metrics["nuclei"]
    if nuc["unevaluated"]:
        add(
            f"Núcleos registra {nuc['unevaluated']} casos no evaluados.",
            "Clasificar individualmente cada caso como ausencia, retiro, pendiente académico u otra novedad documentada.",
            "Coordinaciones de carrera",
            "Casos no evaluados clasificados",
            "Consolidado de Núcleos",
        )

    comp = metrics["complexive"]
    if comp["not_evaluated"]:
        add(
            f"El Examen Complexivo registra {comp['not_evaluated']} estudiantes no evaluados.",
            "Clasificar y documentar individualmente la causa de cada caso antes del cierre.",
            "Coordinaciones de carrera",
            "Casos no evaluados clasificados",
            "Consolidado del Examen Complexivo",
        )

    complexive_metric = metrics["indicators"]["complexive_approval"]
    approval = complexive_metric.get("result")
    if comp["registered"] and approval is not None and float(approval) < 70:
        approval_text = f"{float(approval):.2f}".replace(".", ",")
        add(
            f"La aprobación institucional del Examen Complexivo fue {approval_text} %, por debajo del umbral del 70 %.",
            "Implementar refuerzo académico focalizado y seguimiento temprano de los componentes con menor desempeño.",
            "Coordinaciones de carrera y docentes responsables",
            "Aprobación final del Examen Complexivo",
            "Plan de refuerzo y reporte comparativo",
        )

    schedules = metrics["schedules"]
    if schedules["pending_evaluation"] or schedules["incomplete_evidence"]:
        add(
            f"El cronograma mantiene {schedules['pending_evaluation']} actividades sin evaluar y {schedules['incomplete_evidence']} con evidencia incompleta.",
            "Completar fecha ejecutada, estado, porcentaje, evidencia y observación de cada actividad.",
            "Responsables de cada actividad",
            "Actividades con ejecución documentada",
            "Matriz de cronogramas",
        )
    return actions


def _format_names(names: list[str]) -> str:
    clean = list(dict.fromkeys(str(name or "").strip() for name in names if str(name or "").strip()))
    if not clean:
        return "—"
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} y {clean[1]}"
    return ", ".join(clean[:-1]) + f" y {clean[-1]}"


def complexive_tie_text(report: dict[str, Any]) -> str:
    rows = list(report_completion._complexive_data(report).get("rows", []))
    if not rows:
        return ""
    maximum = max(float(row["approval_percentage"]) for row in rows)
    minimum = min(float(row["approval_percentage"]) for row in rows)
    best = [row["career"] for row in rows if float(row["approval_percentage"]) == maximum]
    worst = [row["career"] for row in rows if float(row["approval_percentage"]) == minimum]
    if maximum == minimum:
        return f"Todas las carreras del Examen Complexivo registraron la misma aprobación final ({report_quality._pct(maximum)})."
    best_phrase = "correspondió a" if len(best) == 1 else "correspondió conjuntamente a"
    worst_phrase = "correspondió a" if len(worst) == 1 else "correspondió conjuntamente a"
    return (
        f"La mayor aprobación final {best_phrase} {_format_names(best)} ({report_quality._pct(maximum)}) y "
        f"la menor {worst_phrase} {_format_names(worst)} ({report_quality._pct(minimum)}). "
        f"La brecha descriptiva entre ambos extremos fue de {report_quality._pct(round(maximum - minimum, 2))} puntos porcentuales."
    )


def conclusions_integrity(report_id: int, report: dict[str, Any]) -> list[str]:
    if _BASE_CONCLUSIONS is None:
        return []
    audit = integrity.audit_report(report_id, resolve_resources=False)
    if audit["mode"] == "no_population":
        return ["No se identificaron hallazgos cuantificables con la información disponible."]
    tie_text = complexive_tie_text(report)
    result: list[str] = []
    for row in _BASE_CONCLUSIONS(report_id, report):
        text = str(row)
        if tie_text and "mayor aprobación final" in text and "Complexivo" in text:
            text = tie_text
        result.append(text)
    return result


def _normalized_old_validation(report_id: int) -> dict[str, Any]:
    if _BASE_VALIDATE is None:
        return {"ok": True, "checks": [], "errors": [], "warnings": []}
    result = dict(_BASE_VALIDATE(report_id))
    structural = {
        "Carrera excluida",
        "Modalidad de carreras",
        "Modalidad de Trabajo de Titulación",
        "Modalidad de Núcleos",
        "Conclusiones no duplicadas",
        "Recomendaciones no duplicadas",
    }
    checks = [dict(item) for item in result.get("checks", [])]
    for item in checks:
        if not item.get("ok") and item.get("name") not in structural:
            item["severity"] = "warning"
    result["checks"] = checks
    result["errors"] = [item for item in checks if not item.get("ok") and item.get("severity") == "error"]
    result["warnings"] = [item for item in checks if not item.get("ok") and item.get("severity") != "error"]
    result["ok"] = not result["errors"]
    return result


def validation_integrity(report_id: int) -> dict[str, Any]:
    audit = integrity.audit_report(report_id)
    result = (
        {"ok": True, "checks": [], "errors": [], "warnings": []}
        if audit["mode"] == "no_population"
        else _normalized_old_validation(report_id)
    )
    checks = [dict(item) for item in result.get("checks", [])]
    for item in audit["controls"]:
        checks.append({
            "name": item["name"],
            "ok": item["status"] == "ok",
            "detail": item["detail"],
            "severity": "error" if item["status"] == "error" and item["blocking"] else "warning",
            "audit_status": item["status"],
        })
    errors = [item for item in checks if not item.get("ok") and item.get("severity") == "error"]
    warnings = [item for item in checks if not item.get("ok") and item.get("severity") != "error"]
    result.update(
        ok=not errors and audit["can_generate_pdf"],
        checks=checks,
        errors=errors,
        warnings=warnings,
        audit=audit,
        report_state=audit["state"],
    )
    return result
