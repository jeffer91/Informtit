from __future__ import annotations

import html
import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import app as core
import completion_routes
import completion_service
import nuclei_excel_import
import nuclei_routes
import process_routes
import process_service
import report_completion
import report_consistency_final as consistency
import report_final_overhaul as final
import report_full_detail as full
import report_pdf_polish as polish
import report_quality
import report_integrity_core as integrity
from db import connection


_LOCAL = threading.local()
_BASE_VALIDATE: Callable[[int], dict[str, Any]] | None = None
_BASE_BUILD_PDF: Callable[[int], Path] | None = None
_BASE_DISPLAY_REPORT: Callable[[dict[str, Any]], dict[str, Any]] | None = None
_BASE_COVER_PDF: Callable[[dict[str, Any], Any], list[Any]] | None = None
_BASE_PDF_BODY: Callable[..., Any] | None = None
_BASE_PDF_BULLET: Callable[..., Any] | None = None
_BASE_PDF_METHODOLOGY: Callable[..., Any] | None = None
_BASE_PDF_POST_SECTIONS: Callable[..., Any] | None = None
_BASE_CONCLUSIONS: Callable[[int, dict[str, Any]], list[str]] | None = None
_BASE_EXECUTIVE_DATA: Callable[[int], dict[str, Any]] | None = None
_BASE_REPLACE_SCHEDULE: Callable[..., dict[str, Any]] | None = None
_BASE_REPLACE_SCHEDULE_EXTENDED: Callable[..., dict[str, Any]] | None = None
_BASE_IMPORT_NUCLEI_EXCEL: Callable[..., dict[str, Any]] | None = None


def _format_names(names: list[str]) -> str:
    clean = list(dict.fromkeys(str(name or "").strip() for name in names if str(name or "").strip()))
    if not clean:
        return "—"
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} y {clean[1]}"
    return ", ".join(clean[:-1]) + f" y {clean[-1]}"


def _strict_course_detail(
    course: dict[str, Any],
    career_row: dict[str, Any] | None,
    institutional_average: float | None,
    institutional_approval: float,
) -> dict[str, Any]:
    students = list(course.get("students", []))
    approved = sum(integrity.nucleus_state(student) == "approved" for student in students)
    failed = sum(integrity.nucleus_state(student) == "failed" for student in students)
    evaluated = approved + failed
    unevaluated = len(students) - evaluated
    grades = integrity.evaluated_grades(students)
    stat = integrity.stats(grades)
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
        "unevaluated": unevaluated,
        "approval": full._pct(approved, evaluated),
        "approval_denominator_type": "EVALUADOS",
        "zeros": zeros,
        **stat,
        "career_average": career_row.get("average") if career_row else None,
        "career_approval": career_row.get("approval") if career_row else None,
        "institutional_average": institutional_average,
        "institutional_approval": institutional_approval,
    }


def _cleanup_existing_schedule_duplicates() -> int:
    completion_service.ensure_completion_schema()
    deleted = 0
    with connection() as conn:
        rows = conn.execute("SELECT * FROM schedule_items ORDER BY report_id, sort_order, id").fetchall()
        grouped: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
        for row in rows:
            try:
                key = (
                    int(row["report_id"]),
                    *integrity.schedule_key(dict(row)),
                )
            except ValueError:
                continue
            grouped[key].append(row)

        for items in grouped.values():
            if len(items) < 2:
                continue

            def evidence_score(row: Any) -> tuple[int, int]:
                score = sum(
                    bool(row[key])
                    for key in ("executed_date", "execution_status", "evidence", "observation")
                ) + int(row["compliance_percentage"] is not None)
                return score, int(row["id"])

            keep = max(items, key=evidence_score)
            for row in items:
                if int(row["id"]) == int(keep["id"]):
                    continue
                conn.execute("DELETE FROM schedule_items WHERE id=?", (int(row["id"]),))
                deleted += 1

        report_ids = [int(row[0]) for row in conn.execute("SELECT DISTINCT report_id FROM schedule_items").fetchall()]
        for report_id in report_ids:
            schedule_rows = conn.execute(
                "SELECT id FROM schedule_items WHERE report_id=? ORDER BY schedule_type, start_date, end_date, id",
                (report_id,),
            ).fetchall()
            for order, row in enumerate(schedule_rows, start=1):
                conn.execute("UPDATE schedule_items SET sort_order=? WHERE id=?", (order, int(row["id"])))
    return deleted


def _replace_schedule_deduped(report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    if _BASE_REPLACE_SCHEDULE is None:
        raise RuntimeError("La capa de integridad no está inicializada.")
    unique, duplicates = integrity.dedupe_schedule_entries(entries)
    result = dict(_BASE_REPLACE_SCHEDULE(report_id, schedule_type, unique))
    result["duplicates_omitted"] = duplicates
    return result


def _replace_schedule_extended_deduped(report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    if _BASE_REPLACE_SCHEDULE_EXTENDED is None:
        raise RuntimeError("La capa de integridad no está inicializada.")
    unique, duplicates = integrity.dedupe_schedule_entries(entries)
    result = dict(_BASE_REPLACE_SCHEDULE_EXTENDED(report_id, schedule_type, unique))
    result["duplicates_omitted"] = duplicates
    return result


def _import_nuclei_audited(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if _BASE_IMPORT_NUCLEI_EXCEL is None:
        raise RuntimeError("La capa de integridad no está inicializada.")
    records, _ = nuclei_excel_import.parse_excel_payload(payload)
    duplicate_entries = integrity.nuclei_duplicate_entries(records)
    result = dict(_BASE_IMPORT_NUCLEI_EXCEL(report_id, payload))
    integrity.write_duplicate_logs(report_id, "Núcleos", duplicate_entries)
    summary = dict(result.get("summary") or {})
    summary["duplicate_exact"] = sum(item["duplicate_type"] == "DUPLICADO EXACTO" for item in duplicate_entries)
    summary["duplicate_probable"] = sum(item["duplicate_type"] == "DUPLICADO PROBABLE" for item in duplicate_entries)
    result["summary"] = summary
    return result


def _display_report_integrity(report: dict[str, Any]) -> dict[str, Any]:
    if _BASE_DISPLAY_REPORT is None:
        return dict(report)
    result = _BASE_DISPLAY_REPORT(report)
    report_id = int(result.get("id") or report.get("id") or 0)
    if report_id:
        audit = integrity.audit_report(report_id, resolve_resources=False)
        result["name"] = audit["document_title"]
        result["emission_status"] = audit["state"]
        result["is_final"] = audit["final_ready"]
    return result


def _header_title(report: dict[str, Any]) -> str:
    title = str(report.get("name") or "Informe de Titulación").rstrip(".")
    return f"{title}. {report.get('period', '')} - Modalidad {report_quality.base.modality(report)}"


def _cover_pdf_integrity(report: dict[str, Any], styles: Any) -> list[Any]:
    if _BASE_COVER_PDF is None:
        return []
    story = list(_BASE_COVER_PDF(report, styles))
    desired = str(report.get("name") or "Informe de Titulación").rstrip(".") + "."
    for index, flowable in enumerate(story):
        if not isinstance(flowable, Paragraph):
            continue
        text = flowable.getPlainText()
        if "Informe Final" in text and "Titulación" in text:
            story[index] = Paragraph(html.escape(desired), flowable.style)
            break
    return story


def _current_audit() -> dict[str, Any] | None:
    return getattr(_LOCAL, "audit", None)


def _stateful_text(value: Any) -> str:
    text = str(value or "")
    audit = _current_audit()
    if not audit or audit.get("final_ready"):
        return text
    title = str(audit.get("document_title") or "Informe Preliminar del Proceso de Titulación")
    text = re.sub(
        r"Informe\s+Final\s+(?:Del|del)\s+Proceso\s+De\s+Titulaci[oó]n\. ?",
        title + ". ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\binforme final\b", "informe preliminar", text, flags=re.IGNORECASE)
    return text


def _pdf_body_integrity(story: list[Any], styles: Any, text: str) -> Any:
    if _BASE_PDF_BODY is None:
        return None
    return _BASE_PDF_BODY(story, styles, _stateful_text(text))


def _pdf_bullet_integrity(story: list[Any], styles: Any, text: str) -> Any:
    if _BASE_PDF_BULLET is None:
        return None
    return _BASE_PDF_BULLET(story, styles, _stateful_text(text))


def _reconciliation_table(story: list[Any], styles: Any, report_id: int) -> None:
    data = integrity.reconciliation(report_id)
    report_quality._pdf_heading(story, full.RecordingContext(), styles, 2, "Conciliación de datos importados")
    report_quality._pdf_body(
        story,
        styles,
        f"La conciliación se realiza antes de calcular indicadores: {data['imported']} cursos importados = "
        f"{data['included']} incluidos + {data['excluded']} excluidos. "
        + ("La igualdad fue validada correctamente." if data["balanced"] else "Existe un error de conciliación y el informe no puede emitirse."),
    )
    rows = [["Motivo", "Cantidad"]]
    rows += [[reason, count] for reason, count in data["reasons"].items()]
    rows.append(["Total excluidos", data["excluded"]])
    table = Table(rows, colWidths=[11.5 * cm, 3.2 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AAB7C4")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#244A73")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [table, Spacer(1, 0.2 * cm)]
    source = data["source_quality"]
    report_quality._pdf_body(
        story,
        styles,
        f"Control del archivo fuente de Núcleos: {source['source_rows']} filas válidas detectadas; "
        f"{source['duplicate_rows']} filas duplicadas exactas omitidas y {source['skipped_rows']} filas no aplicables omitidas durante la importación.",
    )


def _pdf_methodology_integrity(story: list[Any], context: Any, styles: Any, report: dict[str, Any], temp_paths: list[Path]) -> None:
    if _BASE_PDF_METHODOLOGY is None:
        return
    _BASE_PDF_METHODOLOGY(story, context, styles, report, temp_paths)
    _reconciliation_table(story, styles, int(report["id"]))


def _metric_rows(audit: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for item in audit["metrics"]["indicators"].values():
        result = "No aplica" if item["result"] is None else f"{item['result']:.2f} %".replace(".", ",")
        rows.append([
            item["name"],
            item["formula"],
            item["denominator_type"],
            result,
            "Correcto" if item["denominator"] > 0 else "No aplica",
        ])
    comparison = audit["metrics"]["comparisons"]["nuclei_vs_complexive"]
    rows.append([
        "Brecha Núcleos vs. Complexivo",
        "Diferencia entre porcentajes",
        "Mismo denominador requerido",
        (f"{comparison['difference']:.2f} pp".replace(".", ",") if comparison["comparable"] else "No comparable"),
        "Correcto" if comparison["comparable"] else comparison["reason"],
    ])
    return rows


def _formula_traceability(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    audit = integrity.audit_report(report_id, resolve_resources=False)
    report_quality._pdf_heading(story, context, styles, 1, "Trazabilidad de fórmulas e indicadores")
    report_quality._pdf_body(
        story,
        styles,
        "Cada porcentaje conserva su numerador, denominador y tipo de denominador. Las brechas se calculan automáticamente solo cuando los indicadores son conceptualmente comparables.",
    )
    rows = [[Paragraph(html.escape(str(value)), styles["TableCell"]) for value in row] for row in _metric_rows(audit)]
    table = Table(
        [["Indicador", "Fórmula", "Tipo de denominador", "Resultado", "Validación"]] + rows,
        colWidths=[4.3 * cm, 3.2 * cm, 3.4 * cm, 2.2 * cm, 4.0 * cm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#AAB7C4")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#244A73")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [table, Spacer(1, 0.22 * cm)]

    report_quality._pdf_heading(story, context, styles, 2, "Validaciones matemáticas")
    balance_rows = [
        [item["name"], item["formula"], "Correcto" if item["ok"] else "ERROR DE CONSISTENCIA"]
        for item in audit["formulas"]
    ]
    balance_table = Table([["Control", "Comprobación", "Estado"]] + balance_rows, colWidths=[6.4 * cm, 6.0 * cm, 4.2 * cm], repeatRows=1)
    balance_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#AAB7C4")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#244A73")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [balance_table, Spacer(1, 0.25 * cm)]


def _pdf_post_sections_integrity(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> None:
    if _BASE_PDF_POST_SECTIONS is None:
        return
    _BASE_PDF_POST_SECTIONS(story, context, styles, report)
    _formula_traceability(story, context, styles, int(report["id"]))


def _executive_data_integrity(report_id: int) -> dict[str, Any]:
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


def _automatic_actions_integrity(data: dict[str, Any]) -> list[dict[str, str]]:
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
    if comp["registered"] and complexive_metric["result"] is not None and complexive_metric["result"] < 70:
        add(
            f"La aprobación institucional del Examen Complexivo fue {str(f'{complexive_metric['result']:.2f}').replace('.', ',')} %, por debajo del umbral del 70 %.",
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


def _complexive_tie_text(report: dict[str, Any]) -> str:
    data = report_completion._complexive_data(report)
    rows = list(data.get("rows", []))
    if not rows:
        return ""
    maximum = max(float(row["approval_percentage"]) for row in rows)
    minimum = min(float(row["approval_percentage"]) for row in rows)
    best = [row["career"] for row in rows if float(row["approval_percentage"]) == maximum]
    worst = [row["career"] for row in rows if float(row["approval_percentage"]) == minimum]
    if maximum == minimum:
        return f"Todas las carreras del Examen Complexivo registraron la misma aprobación final ({report_quality._pct(maximum)})."
    best_label = _format_names(best)
    worst_label = _format_names(worst)
    best_phrase = "correspondió a" if len(best) == 1 else "correspondió conjuntamente a"
    worst_phrase = "correspondió a" if len(worst) == 1 else "correspondió conjuntamente a"
    return (
        f"La mayor aprobación final {best_phrase} {best_label} ({report_quality._pct(maximum)}) y "
        f"la menor {worst_phrase} {worst_label} ({report_quality._pct(minimum)}). "
        f"La brecha descriptiva entre ambos extremos fue de {report_quality._pct(round(maximum - minimum, 2))} puntos porcentuales."
    )


def _conclusions_integrity(report_id: int, report: dict[str, Any]) -> list[str]:
    if _BASE_CONCLUSIONS is None:
        return []
    audit = integrity.audit_report(report_id, resolve_resources=False)
    if audit["mode"] == "no_population":
        return ["No se identificaron hallazgos cuantificables con la información disponible."]
    rows = list(_BASE_CONCLUSIONS(report_id, report))
    tie_text = _complexive_tie_text(report)
    result: list[str] = []
    for row in rows:
        text = str(row)
        if tie_text and ("mayor aprobación final del Complexivo" in text or "mayor aprobación final" in text and "Complexivo" in text):
            text = tie_text
        result.append(_stateful_text(text))
    return result


def _normalize_old_validation(report_id: int) -> dict[str, Any]:
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


def _validation_integrity(report_id: int) -> dict[str, Any]:
    audit = integrity.audit_report(report_id)
    result = {"ok": True, "checks": [], "errors": [], "warnings": []} if audit["mode"] == "no_population" else _normalize_old_validation(report_id)
    checks = [dict(item) for item in result.get("checks", [])]
    for item in audit["controls"]:
        severity = "error" if item["status"] == "error" and item["blocking"] else "warning"
        checks.append({
            "name": item["name"],
            "ok": item["status"] == "ok",
            "detail": item["detail"],
            "severity": severity,
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


def _build_no_population_pdf(report_id: int, audit: dict[str, Any]) -> Path:
    report_quality.base.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = _display_report_integrity(report_quality._report_data(report_id))
    output = report_quality.base.EXPORT_DIR / consistency.download_filename(report)
    styles = report_quality._pdf_styles()
    story = list(report_quality.base.cover_pdf(report, styles))
    context = full.RecordingContext()
    report_quality._pdf_heading(story, context, styles, 1, "Disponibilidad de información")
    report_quality._pdf_body(
        story,
        styles,
        f"No se identificaron registros correspondientes a la modalidad {report_quality.base.modality(report)} para el período {report.get('period') or 'analizado'}. La fuente de requisitos fue localizada y confirma una población de 0 registros para esta modalidad; por tanto, la ausencia se clasifica como SIN POBLACIÓN y no como un error de carga.",
    )
    rows = [
        ["Población encontrada", "0"],
        ["Requisitos", "No aplica"],
        ["Núcleos", "No aplica"],
        ["Examen Complexivo", "No aplica"],
        ["Trabajo de Titulación", "No aplica"],
        ["Recomendaciones académicas", "No aplica"],
    ]
    table = Table([["Componente", "Resultado"]] + rows, colWidths=[9.8 * cm, 6.0 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AAB7C4")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#244A73")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [table, Spacer(1, 0.3 * cm)]
    source = audit["source"]
    report_quality._pdf_body(
        story,
        styles,
        f"Archivo fuente: {source.get('filename') or 'fuente institucional registrada'}. Registros totales en la fuente: {source['source_total']}; Presencial: {source['source_presencial']}; Online: {source['source_online']}.",
    )
    report_quality._pdf_heading(story, context, styles, 1, "Conclusión")
    report_quality._pdf_body(story, styles, "No se identificaron hallazgos cuantificables con la información disponible.")

    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=1.45 * cm,
        leftMargin=1.45 * cm,
        topMargin=3.55 * cm,
        bottomMargin=1.35 * cm,
        title=report["name"],
    )
    document.build(
        story,
        canvasmaker=lambda *args, **kwargs: report_quality.base.NumberedCanvas(*args, report=report, **kwargs),
    )
    return output


def _build_pdf_integrity(report_id: int) -> Path:
    if _BASE_BUILD_PDF is None:
        raise RuntimeError("La capa de integridad no está inicializada.")
    audit = integrity.audit_report(report_id)
    if not audit["can_generate_pdf"]:
        details = "; ".join(item["detail"] for item in audit["blocking_errors"]) or "El informe contiene errores bloqueantes."
        raise ValueError("No se puede generar el PDF: " + details)
    previous = _current_audit()
    _LOCAL.audit = audit
    try:
        if audit["mode"] == "no_population":
            return _build_no_population_pdf(report_id, audit)
        return Path(_BASE_BUILD_PDF(report_id))
    finally:
        _LOCAL.audit = previous


def install() -> None:
    global _BASE_VALIDATE, _BASE_BUILD_PDF, _BASE_DISPLAY_REPORT, _BASE_COVER_PDF
    global _BASE_PDF_BODY, _BASE_PDF_BULLET, _BASE_PDF_METHODOLOGY, _BASE_PDF_POST_SECTIONS
    global _BASE_CONCLUSIONS, _BASE_EXECUTIVE_DATA, _BASE_REPLACE_SCHEDULE
    global _BASE_REPLACE_SCHEDULE_EXTENDED, _BASE_IMPORT_NUCLEI_EXCEL

    if getattr(report_quality, "_report_integrity_runtime_installed", False):
        return

    raw_provider = consistency._ORIGINAL_NUCLEI_CONSOLIDATED or final._nuclei_consolidated
    integrity.set_raw_nuclei_provider(raw_provider)
    integrity.ensure_integrity_schema()

    _BASE_VALIDATE = full.validate_pdf_report
    _BASE_BUILD_PDF = core.build_pdf
    _BASE_DISPLAY_REPORT = polish._display_report
    _BASE_COVER_PDF = report_quality.base.cover_pdf
    _BASE_PDF_BODY = report_quality._pdf_body
    _BASE_PDF_BULLET = report_quality._pdf_bullet
    _BASE_PDF_METHODOLOGY = report_quality._pdf_methodology
    _BASE_PDF_POST_SECTIONS = report_quality._pdf_post_sections
    _BASE_CONCLUSIONS = full._conclusions
    _BASE_EXECUTIVE_DATA = report_completion._executive_data
    _BASE_REPLACE_SCHEDULE = process_service.replace_schedule
    _BASE_REPLACE_SCHEDULE_EXTENDED = completion_service.replace_schedule_extended
    _BASE_IMPORT_NUCLEI_EXCEL = nuclei_excel_import.import_nuclei_excel

    # 1) No evaluado nunca es una nota estadística, aunque el archivo tenga 0.
    consistency._master_nuclei = integrity.strict_nuclei
    final._nuclei_consolidated = integrity.strict_nuclei
    polish._filtered_nuclei_data = integrity.strict_nuclei
    full._nuclei_data = integrity.strict_nuclei
    full._course_detail = _strict_course_detail

    # 2) Cronogramas: normalización y deduplicación antes de guardar, más limpieza histórica.
    _cleanup_existing_schedule_duplicates()
    process_service.replace_schedule = _replace_schedule_deduped
    process_routes.replace_schedule = _replace_schedule_deduped
    completion_service.replace_schedule_extended = _replace_schedule_extended_deduped
    completion_routes.replace_schedule_extended = _replace_schedule_extended_deduped

    # 3) Auditoría de duplicados en la importación oficial de Núcleos.
    nuclei_excel_import.import_nuclei_excel = _import_nuclei_audited
    nuclei_routes.import_nuclei_excel = _import_nuclei_audited

    # 4) Una sola fuente de métricas para resumen, reglas, conclusiones y trazabilidad.
    report_completion._executive_data = _executive_data_integrity
    report_completion._automatic_actions = _automatic_actions_integrity
    full._conclusions = _conclusions_integrity

    # 5) Documento dinámico: final solo si la auditoría confirma que está listo.
    polish._display_report = _display_report_integrity
    report_quality.base.header_title = _header_title
    report_quality.base.cover_pdf = _cover_pdf_integrity
    report_quality._pdf_body = _pdf_body_integrity
    report_quality._pdf_bullet = _pdf_bullet_integrity
    report_quality._pdf_methodology = _pdf_methodology_integrity
    report_quality._pdf_post_sections = _pdf_post_sections_integrity

    # 6) Auditoría bloqueante antes de PDF y modo corto cuando la fuente confirma población cero.
    polish.validate_pdf_report = _validation_integrity
    full.validate_pdf_report = _validation_integrity
    core.build_pdf = _build_pdf_integrity
    report_quality.build_pdf = _build_pdf_integrity
    full.build_pdf = _build_pdf_integrity
    polish.build_pdf = _build_pdf_integrity

    previous_get = core.InformtitHandler._handle_api_get

    def audit_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)/audit", path)
        if match:
            self._send_json({"ok": True, "audit": integrity.audit_report(int(match.group(1)))})
            return
        previous_get(self, path, query)

    core.InformtitHandler._handle_api_get = audit_get
    report_quality._report_integrity_runtime_installed = True
