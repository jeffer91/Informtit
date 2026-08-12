from __future__ import annotations

import re
from typing import Any

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer

import app as core
import institutional_export as institutional


def _signature_items_without_upload(
    report: dict[str, Any],
    label: str,
    section: str,
    name: str,
    role: str,
    styles: Any,
) -> list[Any]:
    """Bloque de responsables sin imágenes de firmas o códigos QR."""

    del report, section
    style = ParagraphStyle(
        "ResponsibleBlockPdfOnly",
        parent=styles["BodyText"],
        fontSize=7.2,
        leading=9,
        alignment=TA_CENTER,
    )
    return [
        Paragraph(f"<b>{label}</b>", style),
        Spacer(1, 0.22 * 28.3465),
        Paragraph(f"<b>NOMBRE:</b> {name or '—'}", style),
        Paragraph(f"<b>CARGO:</b> {role or '—'}", style),
    ]


def install() -> None:
    if getattr(core.InformtitHandler, "_pdf_only_runtime_installed", False):
        return

    # La portada conserva responsables y cargos, pero nunca solicita ni inserta
    # imágenes de firmas o QR.
    institutional.signature_items = _signature_items_without_upload

    previous_get = core.InformtitHandler._handle_api_get

    def pdf_only_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        if re.fullmatch(r"/api/reports/\d+/export/docx", path):
            self._send_error_json(
                "La exportación Word está deshabilitada. Genere el informe en PDF.",
                404,
            )
            return
        previous_get(self, path, query)

    core.InformtitHandler._handle_api_get = pdf_only_get
    core.InformtitHandler._pdf_only_runtime_installed = True
