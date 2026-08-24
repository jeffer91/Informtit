from __future__ import annotations

from collections import Counter
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
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "UTF-8"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "UTF-16"

    try:
        return data.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        pass

    # Algunos exportadores de Excel guardan texto UTF-16 sin BOM. Solo se
    # intenta si la distribución de bytes NUL realmente parece UTF-16.
    sample = data[:8192]
    if sample:
        even_nulls = sum(sample[index] == 0 for index in range(0, len(sample), 2))
        odd_nulls = sum(sample[index] == 0 for index in range(1, len(sample), 2))
        even_slots = max(1, (len(sample) + 1) // 2)
        odd_slots = max(1, len(sample) // 2)
        if odd_nulls / odd_slots > 0.25:
            try:
                return data.decode("utf-16-le"), "UTF-16 LE"
            except UnicodeDecodeError:
                pass
        if even_nulls / even_slots > 0.25:
            try:
                return data.decode("utf-16-be"), "UTF-16 BE"
            except UnicodeDecodeError:
                pass

    try:
        return data.decode("cp1252"), "Windows-1252"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "Latin-1"


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


def _build_parsed(
    rows: list[list[Any]],
    *,
    filename: str,
    file_type: str,
    encoding: str,
) -> dict[str, Any]:
    if not rows:
        raise ValueError("No se encontraron filas tabulares en el archivo.")

    records, meta = _records_from_rows_fixed(rows)
    identification_counts = Counter(row["identification"] for row in records if row["identification"])
    email_counts = Counter(row["email"] for row in records if row["email"])
    career_counts: dict[str, Counter[str]] = {"presencial": Counter(), "en_linea": Counter()}
    for row in records:
        career_counts[row["modality"]][row["career_name"]] += 1

    preview = {
        "filename": filename,
        "file_type": file_type,
        "encoding": encoding,
        "period": import_service._extract_period(filename),
        "total": len(records),
        "presencial": sum(row["modality"] == "presencial" for row in records),
        "en_linea": sum(row["modality"] == "en_linea" for row in records),
        "careers_total": len({row["career_name"] for row in records}),
        "careers": {
            modality: [
                {"name": name, "students": count}
                for name, count in sorted(career_counts[modality].items())
            ]
            for modality in ("presencial", "en_linea")
        },
        "campuses": dict(sorted(Counter(row["campus"] for row in records if row["campus"]).items())),
        "schedules": dict(sorted(Counter(row["schedule"] for row in records if row["schedule"]).items())),
        "duplicate_identifications": [key for key, count in identification_counts.items() if count > 1],
        "duplicate_emails": [key for key, count in email_counts.items() if count > 1],
        "missing_institutional_email": sum(not row["email"] for row in records),
        **meta,
    }
    return {"records": records, "preview": preview}


def _parse_roster_bytes_fixed(data: bytes, filename: str = "requisitos") -> dict[str, Any]:
    if not data:
        raise ValueError("El archivo está vacío.")
    if len(data) > robust.MAX_IMPORT_BYTES:
        raise ValueError("El archivo supera el límite permitido de 20 MB.")

    if data.startswith(robust.OLE_SIGNATURE):
        return _build_parsed(
            robust._rows_from_xls_binary(data),
            filename=filename,
            file_type="Excel 97-2003 binario (.xls)",
            encoding="Binario",
        )

    if data.startswith(robust.ZIP_SIGNATURE):
        return _build_parsed(
            robust._rows_from_xlsx(data),
            filename=filename,
            file_type="Excel moderno (.xlsx)",
            encoding="Binario",
        )

    text, encoding = _decode_text_fixed(data)
    probe = text.lstrip().lower()

    if "<table" in probe[:1024 * 1024]:
        parser = robust._HtmlRowsParser()
        parser.feed(text)
        rows = parser.rows
        file_type = "HTML antiguo compatible con Excel"
    elif probe.startswith("<") and any(marker in probe[:20000] for marker in ("<workbook", ":workbook", "<worksheet", ":worksheet")):
        rows = robust._rows_from_spreadsheetml(text)
        file_type = "Excel XML / SpreadsheetML"
    else:
        rows, file_type = robust._rows_from_delimited(text)

    return _build_parsed(rows, filename=filename, file_type=file_type, encoding=encoding)


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
    robust.parse_roster_bytes = _parse_roster_bytes_fixed
    import_service.parse_roster_bytes = _parse_roster_bytes_fixed
    _INSTALLED = True
