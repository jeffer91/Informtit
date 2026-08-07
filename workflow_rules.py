from __future__ import annotations

from typing import Any


PRE_NUCLEUS_REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("academic_status", "Académico"),
    ("documentation_status", "Documentación"),
    ("english_status", "Inglés"),
    ("financial_status", "Financiero"),
    ("data_update_status", "Actualización de datos"),
    ("graduate_followup_status", "Seguimiento a graduados"),
    ("practices_linkage_status", "Prácticas"),
    ("linkage_status", "Vinculación"),
)

# Estos campos pertenecen a etapas posteriores y nunca deben utilizarse
# como requisitos de ingreso a Núcleos.
POST_NUCLEUS_FIELDS: tuple[tuple[str, str], ...] = (
    ("titulation_status", "Titulación"),
    ("complexive_approval", "Aprobación Complexivo/Proyecto"),
    ("titulation_approval", "Aprobación de Titulación"),
)


def status(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").strip().split()).upper()


def complies(value: Any) -> bool:
    return status(value) == "CUMPLE"


def prerequisite_state(student: dict[str, Any]) -> dict[str, Any]:
    pending: list[str] = []
    blank: list[str] = []
    for key, label in PRE_NUCLEUS_REQUIREMENTS:
        value = status(student.get(key))
        if value == "NO CUMPLE":
            pending.append(label)
        elif value != "CUMPLE":
            blank.append(label)
    complete = not pending and not blank
    return {
        "complete": complete,
        "pending": pending,
        "blank": blank,
        "missing": pending + blank,
    }


def eligible_for_nuclei(student: dict[str, Any]) -> bool:
    return prerequisite_state(student)["complete"]


def downstream_state(student: dict[str, Any]) -> dict[str, bool]:
    return {
        # El campo Titulación se marca después de aprobar los núcleos y es
        # una comprobación administrativa, no un requisito previo.
        "titulation_marked": complies(student.get("titulation_status")),
        # AprobacionComplexivoProyecto se marca después de aprobar la
        # evaluación (Complexivo o Proyecto).
        "complexive_project_approved": complies(student.get("complexive_approval")),
        # AprobacionTitulacion se marca cuando los títulos ya fueron subidos.
        "titles_uploaded": complies(student.get("titulation_approval")),
    }
