from __future__ import annotations

import re

import dual_modality_runtime as dual
import import_service


_INSTALLED = False


def classify_modality(career_name: str, career_code: str) -> str:
    name = import_service.normalize_name(career_name)
    code = str(career_code or "").upper().strip()

    online_name = any(
        signal in name
        for signal in (
            "ONLINE",
            "EN LINEA",
            "VIRTUAL",
            "A DISTANCIA",
            "DISTANCIA",
            "MODALIDAD L",
        )
    )
    online_code = (
        "-L-" in code
        or bool(re.search(r"(?:^|[-_/])L(?:[-_/]|$)", code))
        or "ONLINE" in code
    )
    if online_name or online_code:
        return "en_linea"

    presencial_name = "PRESENCIAL" in name
    presencial_code = "-P-" in code or bool(re.search(r"(?:^|[-_/])P(?:[-_/]|$)", code))
    if presencial_name or presencial_code:
        return "presencial"

    # Si la fuente antigua no trae marca explícita se conserva la convención
    # histórica de Informtit: la carrera se considera Presencial, pero el parser
    # robusto la expone como modalidad de confianza baja en la previsualización.
    return "presencial"


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    dual._robust_modality = classify_modality
    import_service._modality = classify_modality
    _INSTALLED = True
