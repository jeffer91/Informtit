from __future__ import annotations

from typing import Any

import import_service
import robust_import_runtime as robust


_INSTALLED = False


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return import_service.clean_cell(value)


def _decode_text_fixed(data: bytes) -> tuple[str, str]:
    attempts = (
        ("utf-8-sig", "UTF-8"),
        ("utf-16", "UTF-16"),
        ("utf-16-le", "UTF-16 LE"),
        ("utf-16-be", "UTF-16 BE"),
        ("cp1252", "Windows-1252"),
        ("latin-1", "Latin-1"),
    )
    for encoding, label in attempts:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        # Evita aceptar UTF-16 incorrecto sin BOM cuando produce una cadena
        # llena de caracteres NUL.
        if text and text.count("\x00") > max(2, len(text) // 20):
            continue
        return text, label
    raise ValueError("No se pudo determinar la codificación del archivo de origen.")


def _records_from_rows_fixed(rows: list[list[Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    header_index, header_map, original_headers = robust._find_header(rows)
    records: list[dict[str, Any]] = []
    ambiguous: list[dict[str, str]] = []

    for source_row in rows[header_index + 1 :]:
        canonical: dict[str, str] = {}
        for column, key in header_map.items():
            value = source_row[column] if column < len(source_row) else ""
            canonical[key] = _cell_text(value)

        identification = canonical.get("identification", "")
        full_name = canonical.get("full_name", "")
        career_name = canonical.get("career_name", "")
        if not identification and not full_name:
            continue
        if not full_name or not career_name:
            continue

        career_code = canonical.get("career_code", "")
        modality, confidence, reason = robust._modality_details(career_name, career_code)
        if confidence == "baja":
            ambiguous.append(
                {
                    "identification": identification,
                    "student": full_name,
                    "career": career_name,
                    "career_code": career_code,
                    "inferred": modality,
                    "reason": reason,
                }
            )

        records.append(
            {
                "identification": identification,
                "full_name": full_name,
                "career_code": career_code,
                "career_name": career_name,
                "modality": modality,
                "modality_confidence": confidence,
                "modality_reason": reason,
                "schedule": canonical.get("schedule", ""),
                "academic_status": canonical.get("academic_status", ""),
                "documentation_status": canonical.get("documentation_status", ""),
                "financial_status": canonical.get("financial_status", ""),
                "titulation_status": canonical.get("titulation_status", ""),
                "practices_linkage_status": canonical.get("practices_linkage_status", ""),
                "linkage_status": canonical.get("linkage_status", ""),
                "graduate_followup_status": canonical.get("graduate_followup_status", ""),
                "english_status": canonical.get("english_status", ""),
                "data_update_status": canonical.get("data_update_status", ""),
                "personal_email": canonical.get("personal_email", ""),
                "email": canonical.get("email", "").lower(),
                "phone": canonical.get("phone", ""),
                "campus": canonical.get("campus", ""),
                "titulation_approval": canonical.get("titulation_approval", ""),
                "complexive_approval": canonical.get("complexive_approval", ""),
            }
        )

    if not records:
        raise ValueError("El archivo fue reconocido, pero no contiene estudiantes válidos después de normalizar las columnas.")

    return records, {
        "header_row": header_index + 1,
        "columns_recognized": len(set(header_map.values())),
        "columns_source": len(original_headers),
        "ambiguous_modality": len(ambiguous),
        "ambiguous_examples": ambiguous[:10],
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    robust._ALIAS_TO_CANONICAL = {
        robust._normalize_header(alias): canonical
        for canonical, aliases in robust.HEADER_ALIASES.items()
        for alias in aliases
        if robust._normalize_header(alias)
    }
    robust._decode_text = _decode_text_fixed
    robust._records_from_rows = _records_from_rows_fixed
    _INSTALLED = True
