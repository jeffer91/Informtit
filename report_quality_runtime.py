from __future__ import annotations

from docx.shared import Cm
from reportlab.lib.styles import ParagraphStyle

import report_quality


def install() -> None:
    original_configure_docx = report_quality._configure_docx
    original_pdf_styles = report_quality._pdf_styles

    def configure_docx(document):
        original_configure_docx(document)
        # La sangría se aplica en los párrafos del cuerpo, no en la portada.
        document.styles["Normal"].paragraph_format.first_line_indent = Cm(0)

    def pdf_styles():
        styles = original_pdf_styles()
        if "NucleusCell" not in styles:
            styles.add(
                ParagraphStyle(
                    "NucleusCell",
                    parent=styles["TableCell"],
                    fontSize=6,
                    leading=7,
                )
            )
        return styles

    report_quality._configure_docx = configure_docx
    report_quality._pdf_styles = pdf_styles
