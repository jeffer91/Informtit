from __future__ import annotations

import report_completion


REFERENCE_LIST = (
    "Constitución de la República del Ecuador.",
    "Ley Orgánica de Educación Superior.",
    "Reglamento de Régimen Académico, Resolución RPC-SE-08-No.023-2022.",
    "Reglamento de la Unidad de Titulación y Eficiencia Terminal, código UTET-REG-25, versión 2.0.",
    "Manual de Procesos de la Unidad de Titulación y Eficiencia Terminal, versión 2.",
    "Guías institucionales de integración curricular y registros académicos cargados en Informtit.",
)


def install() -> None:
    report_completion._REFERENCE_LIST = REFERENCE_LIST
