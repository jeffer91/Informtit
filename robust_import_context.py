from __future__ import annotations

import re

import import_service
import robust_import_fixes as fixes


_INSTALLED = False


def _base_career_name(value: str) -> str:
    name = import_service.normalize_name(value)
    name = re.sub(r"\b(ONLINE|EN LINEA|VIRTUAL|A DISTANCIA|PRESENCIAL)\b", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    previous_build = fixes._build_parsed

    def build_with_context(rows, *, filename: str, file_type: str, encoding: str):
        parsed = previous_build(rows, filename=filename, file_type=file_type, encoding=encoding)
        records = list(parsed.get("records") or [])

        online_bases = {
            _base_career_name(str(row.get("career_name") or ""))
            for row in records
            if row.get("modality") == "en_linea"
        }

        for row in records:
            if row.get("modality_confidence") != "baja":
                continue
            base = _base_career_name(str(row.get("career_name") or ""))
            if base and base in online_bases:
                row["modality"] = "presencial"
                row["modality_confidence"] = "media"
                row["modality_reason"] = "existe una versión Online diferenciada de la misma carrera en la fuente"

        unresolved = [row for row in records if row.get("modality_confidence") == "baja"]
        preview = parsed.get("preview") or {}
        preview["ambiguous_modality"] = len(unresolved)
        preview["ambiguous_examples"] = [
            {
                "identification": str(row.get("identification") or ""),
                "student": str(row.get("full_name") or ""),
                "career": str(row.get("career_name") or ""),
                "career_code": str(row.get("career_code") or ""),
                "inferred": str(row.get("modality") or ""),
                "reason": str(row.get("modality_reason") or ""),
            }
            for row in unresolved[:10]
        ]
        return parsed

    fixes._build_parsed = build_with_context
    _INSTALLED = True
