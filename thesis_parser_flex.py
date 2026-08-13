from __future__ import annotations

import re
from typing import Any

import thesis_independent as thesis
from import_service import clean_cell


ID_RE = re.compile(r"\b(\d{8,13})\b")
CODE_RE = re.compile(r"\b([A-Z0-9]{5,24}(?:-[A-Z0-9]{1,8}){2,4})\b", re.I)
CAREER_RE = re.compile(r"\b(?:TECNOLOG[IÍ]A|T[EÉ]CNICO|UNIVERSITARIA|LICENCIATURA|INGENIER[IÍ]A)\b.*$", re.I)


def _line(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").strip().split())


def extract_identity(raw_text: str, overrides: dict[str, Any] | None = None) -> dict[str, str]:
    overrides = overrides or {}
    identification = clean_cell(overrides.get("identification"))
    full_name = clean_cell(overrides.get("full_name"))
    career_code = clean_cell(overrides.get("career_code"))
    career_name = clean_cell(overrides.get("career_name"))
    text = str(raw_text or "")

    id_match = ID_RE.search(text)
    if not identification and id_match:
        identification = id_match.group(1)

    if identification:
        for raw_line in text.splitlines():
            if identification not in raw_line:
                continue
            line = _line(raw_line)
            pos = line.find(identification)
            before = line[:pos].strip(" :-")
            after = line[pos + len(identification):].strip(" :-")
            if before and not full_name and "cedula" not in before.casefold() and "cédula" not in before.casefold():
                full_name = before
            code_match = CODE_RE.search(after)
            if code_match:
                if not career_code:
                    career_code = code_match.group(1).upper()
                if not career_name:
                    career_name = _line(after[code_match.end():]).strip(" :-")
            elif not career_name:
                career_match = CAREER_RE.search(after)
                if career_match:
                    career_name = _line(career_match.group(0)).strip(" :-")
            break

    if not career_code:
        code_match = CODE_RE.search(text)
        if code_match:
            career_code = code_match.group(1).upper()

    if not career_name and career_code:
        match = re.search(re.escape(career_code) + r"[ \t]+([^\n\r]+)", text, re.I)
        if match:
            career_name = _line(match.group(1)).strip(" :-")

    if not full_name and identification:
        match = re.search(r"(?m)^([^\n]+?)\s+" + re.escape(identification) + r"\b", text)
        if match:
            candidate = _line(match.group(1)).strip(" :-")
            if "nombres" not in candidate.casefold() and "cedula" not in candidate.casefold() and "cédula" not in candidate.casefold():
                full_name = candidate

    return {
        "identification": clean_cell(identification),
        "full_name": clean_cell(full_name),
        "career_code": clean_cell(career_code),
        "career_name": clean_cell(career_name),
    }


def install() -> None:
    if getattr(thesis, "_flex_identity_parser_installed", False):
        return
    thesis._extract_identity = extract_identity
    thesis._flex_identity_parser_installed = True
