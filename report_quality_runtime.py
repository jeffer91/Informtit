from __future__ import annotations

import re

from docx.shared import Cm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm

import report_quality


def _pdf_styles():
    """Construye los estilos sin volver a registrar Heading4, ya incluido por ReportLab."""

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "BodyJustified",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=13.5,
            alignment=TA_JUSTIFY,
            firstLineIndent=1.25 * cm,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "BulletIndented",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            leftIndent=1.25 * cm,
            firstLineIndent=-0.63 * cm,
            bulletIndent=0.62 * cm,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            "FigureCaption",
            parent=styles["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            leading=10.5,
            alignment=TA_CENTER,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "TableCell",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=6.8,
            leading=8,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            "NucleusCell",
            parent=styles["TableCell"],
            fontSize=6,
            leading=7,
        )
    )

    heading4 = styles["Heading4"]
    heading4.fontName = "Helvetica-Bold"
    heading4.fontSize = 10.5
    heading4.leading = 13
    heading4.spaceBefore = 7
    heading4.spaceAfter = 4
    heading4.keepWithNext = True

    for level in (1, 2, 3):
        heading = styles[f"Heading{level}"]
        heading.fontName = "Helvetica-Bold"
        heading.keepWithNext = True
        heading.spaceBefore = 9 if level == 1 else 6
        heading.spaceAfter = 5
    return styles


def _sanitize_analysis(value: str) -> str:
    text = " ".join(str(value or "").split())
    text = re.sub(
        r"resultados\s+de\s+la\s+resultado\s+consolidado",
        "resultados consolidados",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\binformación de 1 estudiantes\b", "información de 1 estudiante", text)
    text = re.sub(r"\bDe los 1 registros\b", "De 1 registro", text)
    text = re.sub(r"\b1 alcanzaron\b", "1 alcanzó", text)
    text = re.sub(
        r"(\d+)\.(\d{2})\s*%",
        lambda match: f"{match.group(1)},{match.group(2)} %",
        text,
    )
    return text


def _phase_after(data):
    total = int(data["total"])
    approved = int(data["approved"])
    failed = int(data["failed"])
    not_evaluated = int(data["not_evaluated"])
    record = report_quality._plural(total, "registro")
    analyzed = "analizado" if total == 1 else "analizados"
    approved_verb = "alcanzó" if approved == 1 else "alcanzaron"
    failed_verb = "no alcanzó" if failed == 1 else "no alcanzaron"
    sentence = (
        f"De {total} {record} {analyzed}, {approved} {approved_verb} la aprobación "
        f"({report_quality._pct(data['approved_pct'])}) y {failed} {failed_verb} la calificación mínima."
    )
    if not_evaluated:
        student = report_quality._plural(not_evaluated, "estudiante")
        verb = "no registró" if not_evaluated == 1 else "no registraron"
        sentence += f" Además, {not_evaluated} {student} {verb} una evaluación completa."
    sentence += f" El promedio registrado fue {report_quality._fmt(data['average_final'])}."
    return sentence


def _is_generated_summary(value: str, position: str) -> bool:
    text = " ".join(str(value or "").split()).casefold()
    if not text:
        return False
    if position == "before":
        return text.startswith("a continuación, se presentan los resultados")
    return bool(
        re.match(r"^de (los )?\d+ registros? analizados?[, ]", text)
        or "alcanzaron la aprobación" in text
        or "promedio registrado fue" in text
    )


def _refresh_generated_analyses(original_loader):
    """Descarta resúmenes automáticos viejos para recalcularlos con las reglas actuales."""

    def load(report_id: int):
        report = original_loader(report_id)
        for career in report.get("careers", []):
            analyses = career.get("analyses") or {}
            for analysis in analyses.values():
                before = str(analysis.get("text_before") or "")
                after = str(analysis.get("text_after") or "")
                if _is_generated_summary(before, "before"):
                    analysis["text_before"] = ""
                if _is_generated_summary(after, "after"):
                    analysis["text_after"] = ""
        return report

    return load


def _without_first_career_page_break(
    original_function,
    heading_name: str,
    level_position: int,
):
    """Evita que el subtítulo de contenido quede solo antes de la primera carrera."""

    def wrapped(*args, **kwargs):
        original_heading = getattr(report_quality, heading_name)
        first_career = True

        def heading(*heading_args, **heading_kwargs):
            nonlocal first_career
            level = (
                heading_args[level_position]
                if len(heading_args) > level_position
                else heading_kwargs.get("level")
            )
            page_break = heading_kwargs.get("page_break", False)
            if level == 3 and page_break and first_career:
                heading_kwargs["page_break"] = False
                first_career = False
            return original_heading(*heading_args, **heading_kwargs)

        setattr(report_quality, heading_name, heading)
        try:
            return original_function(*args, **kwargs)
        finally:
            setattr(report_quality, heading_name, original_heading)

    return wrapped


def install() -> None:
    if getattr(report_quality, "_quality_runtime_installed", False):
        return

    original_configure_docx = report_quality._configure_docx
    original_docx_methodology = report_quality._docx_methodology
    original_pdf_methodology = report_quality._pdf_methodology
    original_report_data = report_quality._report_data

    def configure_docx(document):
        original_configure_docx(document)
        # La portada y las tablas no heredan sangría. Los párrafos de cuerpo
        # reciben 1,25 cm explícitamente mediante _docx_body.
        document.styles["Normal"].paragraph_format.first_line_indent = Cm(0)

    report_quality._configure_docx = configure_docx
    report_quality._pdf_styles = _pdf_styles
    report_quality._sanitize_analysis = _sanitize_analysis
    report_quality._phase_after = _phase_after
    report_quality._report_data = _refresh_generated_analyses(original_report_data)
    report_quality._docx_methodology = _without_first_career_page_break(
        original_docx_methodology,
        "_docx_heading",
        2,
    )
    report_quality._pdf_methodology = _without_first_career_page_break(
        original_pdf_methodology,
        "_pdf_heading",
        3,
    )
    report_quality._quality_runtime_installed = True
