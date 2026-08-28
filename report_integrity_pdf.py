from __future__ import annotations

import html
import re
import threading
from pathlib import Path
from typing import Any, Callable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import report_consistency_final as consistency
import report_full_detail as full
import report_integrity_core as integrity
import report_integrity_hooks as hooks
import report_quality
import pdf_progress_runtime


_LOCAL = threading.local()
_BASE_BUILD_PDF: Callable[[int], Path] | None = None
_BASE_DISPLAY_REPORT: Callable[[dict[str, Any]], dict[str, Any]] | None = None
_BASE_COVER_PDF: Callable[[dict[str, Any], Any], list[Any]] | None = None
_BASE_PDF_BODY: Callable[..., Any] | None = None
_BASE_PDF_BULLET: Callable[..., Any] | None = None
_BASE_PDF_METHODOLOGY: Callable[..., Any] | None = None
_BASE_PDF_POST_SECTIONS: Callable[..., Any] | None = None


def configure(
    *,
    build_pdf: Callable[[int], Path],
    display_report: Callable[[dict[str, Any]], dict[str, Any]],
    cover_pdf: Callable[[dict[str, Any], Any], list[Any]],
    pdf_body: Callable[..., Any],
    pdf_bullet: Callable[..., Any],
    pdf_methodology: Callable[..., Any],
    pdf_post_sections: Callable[..., Any],
) -> None:
    global _BASE_BUILD_PDF, _BASE_DISPLAY_REPORT, _BASE_COVER_PDF
    global _BASE_PDF_BODY, _BASE_PDF_BULLET, _BASE_PDF_METHODOLOGY, _BASE_PDF_POST_SECTIONS
    _BASE_BUILD_PDF = build_pdf
    _BASE_DISPLAY_REPORT = display_report
    _BASE_COVER_PDF = cover_pdf
    _BASE_PDF_BODY = pdf_body
    _BASE_PDF_BULLET = pdf_bullet
    _BASE_PDF_METHODOLOGY = pdf_methodology
    _BASE_PDF_POST_SECTIONS = pdf_post_sections


def current_audit() -> dict[str, Any] | None:
    return getattr(_LOCAL, "audit", None)


def current_audit_for(report_id: int) -> dict[str, Any] | None:
    audit = current_audit()
    if not isinstance(audit, dict):
        return None
    if int(audit.get("report_id") or 0) != int(report_id):
        return None
    return audit


def display_report_integrity(report: dict[str, Any]) -> dict[str, Any]:
    result = _BASE_DISPLAY_REPORT(report) if _BASE_DISPLAY_REPORT is not None else dict(report)
    report_id = int(result.get("id") or report.get("id") or 0)
    if report_id:
        audit = integrity.audit_report(report_id, resolve_resources=False)
        result["name"] = audit["document_title"]
        result["emission_status"] = audit["state"]
        result["is_final"] = audit["final_ready"]
    return result


def header_title(report: dict[str, Any]) -> str:
    title = str(report.get("name") or "Informe de Titulación").rstrip(".")
    return f"{title}. {report.get('period', '')} - Modalidad {report_quality.base.modality(report)}"


def cover_pdf_integrity(report: dict[str, Any], styles: Any) -> list[Any]:
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


def _replace_complexive_extreme(text: str) -> str:
    report_id = getattr(_LOCAL, "report_id", None)
    if not report_id or "mayor aprobación" not in text.lower():
        return text
    report = report_quality._report_data(int(report_id))
    tie = hooks.complexive_tie_text(report)
    if not tie:
        return text
    patterns = (
        r"La mayor aprobación final correspondió.*?puntos porcentuales\.",
        r"La mayor aprobación correspondió.*?puntos porcentuales\.",
        r"La mayor aprobación final del Complexivo fue.*?puntos porcentuales\.",
    )
    for pattern in patterns:
        replaced = re.sub(pattern, tie, text, count=1, flags=re.IGNORECASE)
        if replaced != text:
            return replaced
    return text


def stateful_text(value: Any) -> str:
    text = _replace_complexive_extreme(str(value or ""))
    audit = current_audit()
    if not audit or audit.get("final_ready"):
        return text
    title = str(audit.get("document_title") or "Informe Preliminar del Proceso de Titulación")
    text = re.sub(
        r"Informe\s+Final\s+(?:Del|del)\s+Proceso\s+(?:De|de)\s+Titulaci[oó]n\. ?",
        title + ". ",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\binforme final\b", "informe preliminar", text, flags=re.IGNORECASE)


def pdf_body_integrity(story: list[Any], styles: Any, text: str) -> Any:
    if _BASE_PDF_BODY is None:
        return None
    return _BASE_PDF_BODY(story, styles, stateful_text(text))


def pdf_bullet_integrity(story: list[Any], styles: Any, text: str) -> Any:
    if _BASE_PDF_BULLET is None:
        return None
    return _BASE_PDF_BULLET(story, styles, stateful_text(text))


def _reconciliation_section(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    audit = current_audit_for(report_id)
    data = (audit or {}).get("reconciliation") or integrity.reconciliation(report_id)
    report_quality._pdf_heading(story, context, styles, 2, "Conciliación de datos importados")
    report_quality._pdf_body(
        story,
        styles,
        f"Antes de calcular indicadores se verificó la igualdad: {data['imported']} cursos importados = "
        f"{data['included']} incluidos + {data['excluded']} excluidos. "
        + ("La conciliación es correcta." if data["balanced"] else "ERROR DE CONCILIACIÓN: la igualdad no se cumple."),
    )
    rows = [["Motivo", "Cantidad"]]
    rows.extend([[reason, count] for reason, count in data["reasons"].items()])
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
        f"Control del Excel de Núcleos: {source['source_rows']} filas fuente, {source['duplicate_rows']} duplicados exactos omitidos y {source['skipped_rows']} filas no aplicables omitidas.",
    )


def pdf_methodology_integrity(story: list[Any], context: Any, styles: Any, report: dict[str, Any], temp_paths: list[Path]) -> None:
    if _BASE_PDF_METHODOLOGY is None:
        return
    _BASE_PDF_METHODOLOGY(story, context, styles, report, temp_paths)
    _reconciliation_section(story, context, styles, int(report["id"]))


def _metric_rows(audit: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
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
        f"{comparison['difference']:.2f} pp".replace(".", ",") if comparison["comparable"] else "No comparable",
        "Correcto" if comparison["comparable"] else comparison["reason"],
    ])
    return rows


def _paragraph_rows(rows: list[list[Any]], styles: Any) -> list[list[Any]]:
    return [
        [Paragraph(html.escape(str(value)), styles["TableCell"]) for value in row]
        for row in rows
    ]


def formula_traceability(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    audit = current_audit_for(report_id) or integrity.audit_report(report_id, resolve_resources=False)
    report_quality._pdf_heading(story, context, styles, 1, "Trazabilidad de fórmulas e indicadores")
    report_quality._pdf_body(
        story,
        styles,
        "Cada porcentaje conserva numerador, denominador y tipo de denominador. Las brechas se calculan solo cuando ambos indicadores usan poblaciones conceptualmente comparables.",
    )
    body = _paragraph_rows(_metric_rows(audit), styles)
    table = Table(
        [["Indicador", "Fórmula", "Tipo de denominador", "Resultado", "Validación"]] + body,
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
    ]))
    story += [table, Spacer(1, 0.22 * cm)]

    report_quality._pdf_heading(story, context, styles, 2, "Validaciones matemáticas")
    balances = _paragraph_rows([
        [item["name"], item["formula"], "Correcto" if item["ok"] else "ERROR DE CONSISTENCIA"]
        for item in audit["formulas"]
    ], styles)
    balance_table = Table(
        [["Control", "Comprobación", "Estado"]] + balances,
        colWidths=[6.4 * cm, 6.0 * cm, 4.2 * cm],
        repeatRows=1,
    )
    balance_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#AAB7C4")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#244A73")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [balance_table, Spacer(1, 0.25 * cm)]


def pdf_post_sections_integrity(story: list[Any], context: Any, styles: Any, report: dict[str, Any]) -> None:
    if _BASE_PDF_POST_SECTIONS is None:
        return
    _BASE_PDF_POST_SECTIONS(story, context, styles, report)
    formula_traceability(story, context, styles, int(report["id"]))


def build_no_population_pdf(report_id: int, audit: dict[str, Any]) -> Path:
    report_quality.base.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = display_report_integrity(report_quality._report_data(report_id))
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


def build_pdf_integrity(report_id: int) -> Path:
    if _BASE_BUILD_PDF is None:
        raise RuntimeError("Integridad PDF no configurada.")

    # Un solo preflight completo por generación. El generador base vuelve a llamar
    # validate_pdf_report por diseño; prime_validation hace que esa segunda llamada
    # reutilice exactamente el mismo resultado en este hilo.
    validation = (
        pdf_progress_runtime.consume_preflight(report_id, "normal")
        or hooks.validation_integrity(report_id)
    )
    audit = validation.get("audit") or integrity.audit_report(report_id)
    errors = list(validation.get("errors") or [])
    if errors or not audit["can_generate_pdf"]:
        details = "; ".join(
            str(item.get("detail") or item.get("name") or "Error de validación")
            for item in (errors or audit["blocking_errors"])
        ) or "El informe contiene errores bloqueantes."
        raise ValueError("No se puede generar el PDF: " + details)

    previous_audit = current_audit()
    previous_report = getattr(_LOCAL, "report_id", None)
    _LOCAL.audit = audit
    _LOCAL.report_id = report_id
    hooks.prime_validation(report_id, validation)
    try:
        if audit["mode"] == "no_population":
            return build_no_population_pdf(report_id, audit)
        return Path(_BASE_BUILD_PDF(report_id))
    finally:
        hooks.clear_primed_validation()
        _LOCAL.audit = previous_audit
        _LOCAL.report_id = previous_report
