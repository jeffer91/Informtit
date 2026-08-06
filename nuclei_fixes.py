from __future__ import annotations

import re
from typing import Any

import nuclei_service


_ORIGINAL_PARSE_PARTICIPANTS = nuclei_service.parse_participants_text


def clean_name(value: str) -> str:
    """Elimina el estado anexado por Moodle sin cortar nombres completos."""

    text = nuclei_service._line(value)
    text = re.sub(
        r"Matriculaci[oó]n de usuarios suspendida.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def clean_participant_initials(value: str, email: str) -> str:
    """Quita prefijos como RA+ROSA o MP+MELISSA de la lista de participantes.

    Moodle concatena las iniciales del avatar con el primer nombre cuando se
    copia la tabla. La eliminación solo se aplica cuando el prefijo coincide
    con los dos primeros caracteres del correo y, después de retirarlo, el
    nombre conserva la inicial esperada. Así se evita cortar nombres reales.
    """

    text = clean_name(value)
    parts = text.split()
    local = str(email or "").split("@", 1)[0].upper()
    if not parts or len(local) < 2:
        return text

    token = parts[0]
    prefix = local[:2]
    if (
        token.startswith(prefix)
        and len(token) >= len(prefix) + 4
        and token[len(prefix) : len(prefix) + 1] == prefix[:1]
    ):
        parts[0] = token[len(prefix) :]
        return " ".join(parts)
    return text


def parse_participants_text(
    raw_text: str,
    grade_students: list[dict[str, Any]],
) -> list[dict[str, str]]:
    participants = _ORIGINAL_PARSE_PARTICIPANTS(raw_text, grade_students)
    graded_emails = {
        str(student.get("email") or "").lower()
        for student in grade_students
        if student.get("email")
    }
    for participant in participants:
        email = str(participant.get("email") or "").lower()
        # Los estudiantes con notas ya reciben el nombre limpio del
        # calificador. Esta corrección se necesita principalmente para el
        # docente y para participantes sin calificación.
        if email not in graded_emails:
            participant["full_name"] = clean_participant_initials(
                participant.get("full_name") or "",
                email,
            )
    return participants


def install() -> None:
    if getattr(nuclei_service, "_nuclei_name_fixes_installed", False):
        return
    nuclei_service._clean_name = clean_name
    nuclei_service.parse_participants_text = parse_participants_text
    nuclei_service._nuclei_name_fixes_installed = True
