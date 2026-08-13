from __future__ import annotations

import re
import unicodedata
from typing import Any

import thesis_independent as thesis
from import_service import clean_cell


ID_RE = re.compile(r"\b(\d{8,13})\b")
CODE_RE = re.compile(
    r"\b((?=[A-Z0-9-]{8,40}\b)(?=[A-Z0-9-]*\d)(?:[A-Z0-9]{1,24}-){2,5}[A-Z0-9]{1,12})\b",
    re.I,
)
CAREER_RE = re.compile(
    r"\b((?:TECNOLOG[IÍ]A(?:\s+(?:SUPERIOR|UNIVERSITARIA))?|"
    r"T[EÉ]CNICO(?:\s+SUPERIOR)?|UNIVERSITARIA|LICENCIATURA|"
    r"INGENIER[IÍ]A)\b[^\n\r]*)",
    re.I,
)
BOUNDARY_RE = re.compile(
    r"(?:Informaci[oó]n\s+Proyecto|Miembros\s+Proyecto|Notas\s+Proyecto|"
    r"Vocal\s*Evaluaci[oó]n\s+Final\s+Proyecto|"
    r"TRABAJO\s+ESCRITO\s+PROYECTO\s+DE\s+TITULACI[oó]N|"
    r"N[ÚU]MERO\s+DE\s+ACTA\s+DE\s+GRADO|DEFENSA\s+DE\s+PROYECTO)",
    re.I,
)
LABEL_RE = re.compile(
    r"\b(?:Nombres?|C[eé]dula|Cedula|C\.?\s*I\.?|Identificaci[oó]n|"
    r"C[oó]digo\s+(?:de\s+)?Carrera|Carrera)\s*:",
    re.I,
)


def _line(value: Any) -> str:
    return " ".join(
        str(value or "")
        .replace("\u00a0", " ")
        .replace("\u200b", "")
        .strip()
        .split()
    )


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _line(value))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()


def _normalize_text(value: Any) -> str:
    return (
        str(value or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u00a0", " ")
        .replace("\u200b", "")
    )


def _identity_section(text: str) -> str:
    """Limita la búsqueda a la cabecera para evitar confundir actas/notas con identidad."""

    match = BOUNDARY_RE.search(text)
    return text[: match.start()] if match else text


def _is_headerish(value: Any) -> bool:
    folded = _fold(value)
    hits = sum(
        marker in folded
        for marker in ("nombres", "cedula", "codigo de carrera", "codigo carrera", "carrera")
    )
    return hits >= 2 or bool(LABEL_RE.search(str(value or "")))


def _looks_like_name(value: Any) -> bool:
    text = _line(value).strip(" :-|")
    if not text or _is_headerish(text) or any(ch.isdigit() for ch in text):
        return False
    folded = _fold(text)
    if any(
        marker in folded
        for marker in ("tecnologia", "tecnico superior", "universitaria", "licenciatura", "ingenieria")
    ):
        return False
    words = [word for word in re.split(r"\s+", text) if any(ch.isalpha() for ch in word)]
    return 2 <= len(words) <= 10 and sum(ch.isalpha() for ch in text) >= 5


def _trim_career(value: Any) -> str:
    text = _line(value).strip(" :-|")
    if not text:
        return ""

    # El copiado desde el sistema puede pegar navegación/secciones al final de la carrera.
    cut = re.search(
        r"\s+(?:Informaci[oó]n\s+Proyecto|Miembros\s+Proyecto|Notas\s+Proyecto|"
        r"Vocal\s*Evaluaci[oó]n\s+Final\s+Proyecto|TRABAJO\s+ESCRITO\b|"
        r"N[ÚU]MERO\s+DE\s+ACTA\b|DEFENSA\s+DE\s+PROYECTO\b)",
        text,
        re.I,
    )
    if cut:
        text = text[: cut.start()]
    return _line(text).strip(" :-|")


def _career_from_value(value: Any) -> str:
    match = CAREER_RE.search(_line(value))
    return _trim_career(match.group(1)) if match else ""


def extract_identity(raw_text: str, overrides: dict[str, Any] | None = None) -> dict[str, str]:
    """Extrae identidad sin depender de una distribución exacta de columnas o saltos."""

    overrides = overrides or {}
    identification = clean_cell(overrides.get("identification"))
    full_name = clean_cell(overrides.get("full_name"))
    career_code = clean_cell(overrides.get("career_code"))
    career_name = clean_cell(overrides.get("career_name"))

    text = _normalize_text(raw_text)
    section = _identity_section(text)
    search_text = section if section.strip() else text
    lines = [(raw_line, _line(raw_line)) for raw_line in search_text.splitlines() if _line(raw_line)]

    # Etiquetas con valor en la misma línea.
    if not identification:
        labelled_id = re.search(
            r"(?:C[eé]dula|Cedula|C\.?\s*I\.?|Identificaci[oó]n)\s*:\s*(\d{8,13})\b",
            search_text,
            re.I,
        )
        if labelled_id:
            identification = labelled_id.group(1)

    if not full_name:
        labelled_name = re.search(
            r"Nombres?\s*:\s*(.*?)\s+(?=(?:C[eé]dula|Cedula|C\.?\s*I\.?|Identificaci[oó]n)\s*:)",
            search_text,
            re.I | re.S,
        )
        if labelled_name and _looks_like_name(labelled_name.group(1)):
            full_name = _line(labelled_name.group(1))

    if not career_name:
        for _raw_line, line in lines:
            labelled_career = re.search(r"\bCarrera\s*:\s*(.+)$", line, re.I)
            if labelled_career:
                candidate = _career_from_value(labelled_career.group(1))
                if candidate:
                    career_name = candidate
                    break

    # Búsqueda independiente por patrones: el encabezado ayuda, pero no es obligatorio.
    id_match = ID_RE.search(search_text)
    if not identification and id_match:
        identification = id_match.group(1)

    code_match = CODE_RE.search(search_text)
    if not career_code and code_match:
        career_code = code_match.group(1).upper()

    # Fila tipo tabla/TSV o fila aplanada: nombre + cédula + código + carrera.
    id_line_index = None
    if identification:
        for index, (_raw_line, line) in enumerate(lines):
            if identification not in line:
                continue
            id_line_index = index
            pos = line.find(identification)
            before = line[:pos].strip(" :-|\t")
            after = line[pos + len(identification) :].strip(" :-|\t")

            if not full_name and _looks_like_name(before):
                full_name = _line(before)

            line_code = CODE_RE.search(after)
            if line_code:
                if not career_code:
                    career_code = line_code.group(1).upper()
                if not career_name:
                    candidate = _career_from_value(after[line_code.end() :])
                    if candidate:
                        career_name = candidate
            elif not career_name:
                candidate = _career_from_value(after)
                if candidate:
                    career_name = candidate
            break

    # Si el navegador copió cada celda en una línea diferente, usa la cercanía entre campos.
    if not full_name and id_line_index is not None:
        for index in range(id_line_index - 1, max(-1, id_line_index - 4), -1):
            candidate = lines[index][1]
            if _looks_like_name(candidate):
                full_name = candidate
                break

    code_line_index = None
    if career_code:
        for index, (_raw_line, line) in enumerate(lines):
            code_pos = line.upper().find(career_code.upper())
            if code_pos < 0:
                continue
            code_line_index = index
            if not career_name:
                tail = line[code_pos + len(career_code) :].strip(" :-|\t")
                candidate = _career_from_value(tail)
                if candidate:
                    career_name = candidate
            break

    if not career_name and code_line_index is not None:
        for index in range(code_line_index + 1, min(len(lines), code_line_index + 4)):
            candidate = _career_from_value(lines[index][1])
            if candidate:
                career_name = candidate
                break

    # Último respaldo: una denominación formal de carrera en cualquier lugar de la cabecera.
    if not career_name:
        for _raw_line, line in lines:
            candidate = _career_from_value(line)
            if candidate:
                career_name = candidate
                break

    # Respaldo para cabeceras totalmente aplanadas.
    if not full_name and identification:
        id_pos = search_text.find(identification)
        before_id = search_text[:id_pos] if id_pos >= 0 else ""
        candidate = before_id.splitlines()[-1] if before_id.splitlines() else before_id
        candidate = LABEL_RE.sub(" ", candidate)
        candidate = _line(candidate).strip(" :-|")
        if _looks_like_name(candidate):
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
