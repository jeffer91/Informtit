from __future__ import annotations

from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth

import report_quality


def _right_top_baselines(top: float, row_height: float) -> tuple[float, float, float]:
    """Devuelve tres líneas seguras dentro de la fila superior derecha."""
    return (
        top - 0.27 * cm,
        top - 0.55 * cm,
        top - 0.83 * cm,
    )


def _draw_fitted_centered(
    canvas: Any,
    text: str,
    center_x: float,
    y: float,
    max_width: float,
    *,
    initial_size: float = 6.3,
    minimum_size: float = 5.1,
    bold: bool = False,
) -> None:
    font = "Helvetica-Bold" if bold else "Helvetica"
    size = initial_size
    while size > minimum_size and stringWidth(text, font, size) > max_width:
        size -= 0.2
    canvas.setFont(font, size)
    canvas.drawCentredString(center_x, y, text)


def draw_header(canvas: Any, report: dict[str, Any], page: int, pages: int) -> None:
    """Encabezado institucional sin texto atravesado por la línea divisoria."""
    base = report_quality.base
    width, height = A4
    x = 1.25 * cm
    top = height - 0.70 * cm
    row = 1.08 * cm
    total = width - 2.5 * cm
    left = 4.35 * cm
    right = 4.15 * cm
    middle = total - left - right
    bottom = top - 2 * row
    divider = top - row
    right_x = x + left + middle
    right_center = right_x + right / 2

    canvas.saveState()
    canvas.setLineWidth(0.7)
    canvas.rect(x, bottom, total, 2 * row)
    canvas.line(x, divider, x + total, divider)
    canvas.line(x + left, bottom, x + left, top)
    canvas.line(right_x, bottom, right_x, top)

    logo = base.image_path(base.image_for(report, base.LOGO))
    if logo:
        canvas.drawImage(
            str(logo),
            x + 0.03 * cm,
            divider + 0.03 * cm,
            width=left - 0.06 * cm,
            height=row - 0.06 * cm,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
    else:
        base.centered(
            canvas,
            "LOGO INSTITUCIONAL NO CARGADO",
            x,
            divider + 0.30 * cm,
            left,
            6.5,
            True,
        )

    base.centered(
        canvas,
        "Unidad Titulación y Eficiencia Terminal",
        x + left,
        divider + 0.32 * cm,
        middle,
        8.2,
    )

    code_y, value_y, version_y = _right_top_baselines(top, row)
    _draw_fitted_centered(canvas, "Código:", right_center, code_y, right - 0.20 * cm, bold=True)
    _draw_fitted_centered(
        canvas,
        str(report.get("code") or "—"),
        right_center,
        value_y,
        right - 0.20 * cm,
        initial_size=6.1,
    )
    _draw_fitted_centered(
        canvas,
        f"Versión: {report.get('version') or '1.0'}",
        right_center,
        version_y,
        right - 0.20 * cm,
        initial_size=6.1,
    )

    base.centered(
        canvas,
        f"Fecha de Elaboración: {base.format_date(report.get('elaboration_date'))}",
        x,
        bottom + 0.30 * cm,
        left,
        6.8,
        False,
        2,
    )
    base.centered(
        canvas,
        base.header_title(report),
        x + left,
        bottom + 0.24 * cm,
        middle,
        6.8,
        True,
    )
    _draw_fitted_centered(
        canvas,
        f"Página {page} de {pages}",
        right_center,
        bottom + 0.43 * cm,
        right - 0.20 * cm,
        initial_size=7.2,
    )

    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(width - 1.35 * cm, 0.65 * cm, f"Página {page} de {pages}")
    canvas.restoreState()


def install() -> None:
    report_quality.base.draw_header = draw_header
