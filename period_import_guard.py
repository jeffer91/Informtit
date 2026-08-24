from __future__ import annotations

from typing import Any

import dual_modality_runtime as dual
import import_service
import period_unified_runtime as unified


_INSTALLED = False


def validate_dual_preview(token: str) -> dict[str, int]:
    """Valida la población recalculando la modalidad desde la fuente.

    La previsualización puede haber sido creada por una versión anterior de la
    aplicación. Por eso esta guarda no confía en ``row['modality']``: vuelve a
    clasificar con NombreCarrera + CodigoCarrera inmediatamente antes del commit.
    """
    parsed = import_service._load_preview(token)
    records = list(parsed.get("records") or [])
    if not records:
        raise ValueError("El archivo no contiene estudiantes válidos.")

    counts = dual.modality_counts(records)
    missing = [
        "Presencial" if modality == "presencial" else "Online"
        for modality, total in counts.items()
        if total == 0
    ]
    if missing:
        raise ValueError(
            "Error de población por modalidad: el archivo no contiene registros "
            + " y ".join(missing)
            + ". Para un período regular deben existir datos Presencial y Online. "
            "Revise NombreCarrera/CodigoCarrera antes de importar."
        )
    return counts


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    # Refuerza tanto la previsualización nueva como tokens creados antes de esta
    # versión. La clasificación final se repite además dentro del commit.
    import_service._modality = dual._robust_modality
    unified.validate_dual_preview = validate_dual_preview
    _INSTALLED = True
