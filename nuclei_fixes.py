from __future__ import annotations

import re

import nuclei_service


def clean_name(value: str) -> str:
    """Elimina únicamente el estado anexado por Moodle, sin cortar nombres."""

    text = nuclei_service._line(value)
    text = re.sub(
        r"Matriculaci[oó]n de usuarios suspendida.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def install() -> None:
    nuclei_service._clean_name = clean_name
