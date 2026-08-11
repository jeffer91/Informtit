from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from statistics import mean
from typing import Any

from coordinator_registry import find_coordinator, normalize
from db import connection, rows_to_dicts, utcnow
from nuclei_catalog import catalog_for_career
from nuclei_multicampus import ensure_multicampus_schema


REQUIRED_HEADERS = (
    "nombre_carrera",
    "nombre_profesor",
    "nombre_estudiante",
    "materia",
    "nota_final",
    "estado",
    "trabajoTitulacion",
)

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _line(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").strip().split())


def _header_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize(value))


def _column_index(reference: str) -> int:
    match = re.match(r"([A-Z]+)", str(reference or "").upper())
    if not match:
        return 0
    value = 0
    for character in match.group(1):
        value = value * 26 + (ord(character) - 64)
    return value - 1


def _xlsx_rows(data: bytes) -> list[list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("El archivo no es un Excel .xlsx válido.") from exc

    with archive:
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
            raise ValueError("El archivo no contiene una estructura de Excel compatible.")

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{{{_MAIN_NS}}}si"):
                shared_strings.append(
                    "".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t"))
                )

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        first_sheet = workbook.find(f".//{{{_MAIN_NS}}}sheet")
        if first_sheet is None:
            raise ValueError("El Excel no contiene hojas de cálculo.")
        relation_id = first_sheet.attrib.get(f"{{{_OFFICE_REL_NS}}}id", "")

        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = ""
        for relation in relations.findall(f"{{{_PACKAGE_REL_NS}}}Relationship"):
            if relation.attrib.get("Id") == relation_id:
                target = relation.attrib.get("Target", "")
                break
        if not target:
            raise ValueError("No se pudo localizar la primera hoja del Excel.")

        if target.startswith("/"):
            sheet_path = target.lstrip("/")
        elif target.startswith("xl/"):
            sheet_path = target
        else:
            sheet_path = "xl/" + target.lstrip("./")
        if sheet_path not in names:
            raise ValueError("No se pudo leer la hoja de datos del Excel.")

        root = ET.fromstring(archive.read(sheet_path))
        result: list[list[str]] = []
        for row in root.findall(f".//{{{_MAIN_NS}}}sheetData/{{{_MAIN_NS}}}row"):
            values: dict[int, str] = {}
            max_index = -1
            for cell in row.findall(f"{{{_MAIN_NS}}}c"):
                index = _column_index(cell.attrib.get("r", ""))
                max_index = max(max_index, index)
                cell_type = cell.attrib.get("t", "")
                if cell_type == "inlineStr":
                    text = "".join(
                        node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t")
                    )
                else:
                    value_node = cell.find(f"{{{_MAIN_NS}}}v")
                    raw = value_node.text if value_node is not None else ""
                    if cell_type == "s" and raw:
                        try:
                            text = shared_strings[int(raw)]
                        except (ValueError, IndexError):
                            text = raw
                    elif cell_type == "b":
                        text = "TRUE" if raw == "1" else "FALSE"
                    else:
                        text = raw
                values[index] = _line(text)
            if max_index >= 0:
                result.append([values.get(index, "") for index in range(max_index + 1)])
        return result


def _decode_upload(payload: dict[str, Any]) -> tuple[bytes, str]:
    filename = _line(payload.get("filename")) or "nucleos.xlsx"
    data_url = str(payload.get("data_url") or "")
    if not data_url or "," not in data_url:
        raise ValueError("Seleccione el archivo Excel de Núcleos.")
    header, encoded = data_url.split(",", 1)
    if ";base64" not in header:
        raise ValueError("El archivo debe enviarse codificado en base64.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("No se pudo decodificar el archivo Excel.") from exc
    if not data:
        raise ValueError("El archivo Excel está vacío.")
    return data, filename


def _records_from_rows(rows: list[list[str]]) -> list[dict[str, str]]:
    header_index = next((index for index, row in enumerate(rows) if any(_line(cell) for cell in row)), None)
    if header_index is None:
        raise ValueError("El Excel no contiene datos.")

    header_row = rows[header_index]
    positions = {_header_key(value): index for index, value in enumerate(header_row) if _line(value)}
    required_positions: dict[str, int] = {}
    missing: list[str] = []
    for header in REQUIRED_HEADERS:
        key = _header_key(header)
        if key not in positions:
            missing.append(header)
        else:
            required_positions[header] = positions[key]
    if missing:
        raise ValueError("Faltan columnas obligatorias: " + ", ".join(missing) + ".")

    records: list[dict[str, str]] = []
    for row in rows[header_index + 1 :]:
        record = {
            header: _line(row[position] if position < len(row) else "")
            for header, position in required_positions.items()
        }
        if not any(record.values()):
            continue
        if not record["nombre_carrera"] or not record["nombre_estudiante"] or not record["materia"]:
            continue
        records.append(record)
    if not records:
        raise ValueError("No se encontraron registros válidos de Núcleos en el Excel.")
    return records


def parse_excel_payload(payload: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    data, filename = _decode_upload(payload)
    rows = _xlsx_rows(data)
    return _records_from_rows(rows), filename


def _grade(value: Any) -> float | None:
    text = _line(value)
    if not text or normalize(text) in {"null", "none", "sin nota", "no evaluado"}:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _status(value: Any, grade: float | None) -> str:
    text = normalize(value)
    if text in {"apr", "aprobado", "aprobada"}:
        return "Aprobado"
    if text in {"rep", "reprobado", "reprobada", "suspenso"}:
        return "Reprobado"
    if text in {"", "null", "none", "no evaluado", "sin nota"}:
        return "No evaluado"
    if grade is None:
        return "No evaluado"
    return "Aprobado" if grade >= 7 else "Reprobado"


def _subject_number_map(records: list[dict[str, str]]) -> dict[tuple[str, str], int]:
    by_career: dict[str, list[str]] = defaultdict(list)
    for record in records:
        career = record["nombre_carrera"]
        subject = record["materia"]
        if subject not in by_career[career]:
            by_career[career].append(subject)

    mapping: dict[tuple[str, str], int] = {}
    stopwords = {"t", "nucleo", "nucleo", "de", "del", "la", "el", "y", "en", "para"}
    for career, subjects in by_career.items():
        catalog = catalog_for_career(career)
        used_by_subject: dict[str, int] = {}
        for subject in subjects:
            match = re.search(r"n[úu]cleo\s*(\d+)", subject, re.IGNORECASE)
            if match:
                used_by_subject[subject] = int(match.group(1))

        if catalog:
            for subject in subjects:
                if subject in used_by_subject:
                    continue
                subject_norm = normalize(subject)
                subject_tokens = {token for token in subject_norm.split() if token not in stopwords}
                best_number = None
                best_score = 0.0
                for nucleus in catalog.get("nuclei", []):
                    guide_norm = normalize(nucleus.get("guide"))
                    if guide_norm and guide_norm in subject_norm:
                        best_number = int(nucleus["number"])
                        best_score = 1.0
                        break
                    guide_tokens = {token for token in guide_norm.split() if token not in stopwords}
                    if not guide_tokens:
                        continue
                    score = len(subject_tokens & guide_tokens) / len(guide_tokens)
                    if score > best_score:
                        best_score = score
                        best_number = int(nucleus["number"])
                if best_number is not None and best_score >= 0.55:
                    used_by_subject[subject] = best_number

        next_number = 1
        for subject in subjects:
            if subject not in used_by_subject:
                while next_number in used_by_subject.values():
                    next_number += 1
                used_by_subject[subject] = next_number
                next_number += 1
            mapping[(career, subject)] = used_by_subject[subject]
    return mapping


def ensure_excel_schema() -> None:
    ensure_multicampus_schema()
    with connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nucleus_excel_imports (
                report_id INTEGER PRIMARY KEY,
                filename TEXT DEFAULT '',
                source_rows INTEGER DEFAULT 0,
                imported_rows INTEGER DEFAULT 0,
                duplicate_rows INTEGER DEFAULT 0,
                skipped_rows INTEGER DEFAULT 0,
                careers INTEGER DEFAULT 0,
                students INTEGER DEFAULT 0,
                courses INTEGER DEFAULT 0,
                imported_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            )
            """
        )


def _student_key(career: str, subject: str, teacher: str, student: str) -> str:
    digest = hashlib.sha1(
        "|".join(map(normalize, (career, subject, teacher, student))).encode("utf-8")
    ).hexdigest()[:24]
    return f"{digest}@excel.local"


def import_nuclei_excel(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_excel_schema()
    source_records, filename = parse_excel_payload(payload)
    source_rows = len(source_records)

    exact_seen: set[tuple[str, ...]] = set()
    records: list[dict[str, str]] = []
    duplicate_rows = 0
    skipped_rows = 0
    for record in source_records:
        option = normalize(record.get("trabajoTitulacion"))
        if option and option != "examen complexivo":
            skipped_rows += 1
            continue
        signature = tuple(record.get(header, "") for header in REQUIRED_HEADERS)
        if signature in exact_seen:
            duplicate_rows += 1
            continue
        exact_seen.add(signature)
        records.append(record)

    if not records:
        raise ValueError("El Excel no contiene registros de Examen Complexivo para importar como Núcleos.")

    number_map = _subject_number_map(records)
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for record in records:
        key = (record["nombre_carrera"], record["materia"], record["nombre_profesor"])
        groups[key].append(record)

    now = utcnow()
    with connection() as conn:
        conn.execute("DELETE FROM nucleus_course_instances WHERE report_id=?", (report_id,))

        for (career, subject, teacher), group_rows in groups.items():
            nucleus_number = number_map[(career, subject)]
            coordinator = find_coordinator(career)
            course_key = "excel|" + "|".join(
                [normalize(career), str(nucleus_number), normalize(subject), normalize(teacher)]
            )

            by_student: dict[str, dict[str, Any]] = {}
            for row in group_rows:
                student_name = row["nombre_estudiante"]
                grade = _grade(row.get("nota_final"))
                status = _status(row.get("estado"), grade)
                by_student[normalize(student_name)] = {
                    "full_name": student_name,
                    "grade": grade,
                    "status": status,
                }
            students = list(by_student.values())
            numeric = [student["grade"] for student in students if student["grade"] is not None]
            approved = sum(student["status"] == "Aprobado" for student in students)
            failed = sum(student["status"] == "Reprobado" for student in students)
            unevaluated = sum(student["status"] == "No evaluado" for student in students)
            average = round(mean(numeric), 2) if numeric else None

            cursor = conn.execute(
                """
                INSERT INTO nucleus_course_instances
                (report_id, career_name, nucleus_number, campus, module_code, period_label,
                 group_code, schedule, course_key, course_title, teacher_name, teacher_candidates,
                 coordinator_name, coordinator_program, coordinator_telegram, participant_students,
                 graded_students, matched_students, missing_grades, extra_grades, course_average,
                 approved_count, failed_count, unevaluated_count, activity_averages, raw_grades,
                 raw_participants, created_at, updated_at)
                VALUES (?, ?, ?, '', '', '', '', '', ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, '[]', ?, '', ?, ?)
                """,
                (
                    report_id,
                    career,
                    nucleus_number,
                    course_key,
                    subject,
                    teacher,
                    coordinator.get("coordinator", ""),
                    coordinator.get("program", ""),
                    coordinator.get("telegram", ""),
                    len(students),
                    len(numeric),
                    len(students),
                    average,
                    approved,
                    failed,
                    unevaluated,
                    f"Excel consolidado: {filename}",
                    now,
                    now,
                ),
            )
            course_id = int(cursor.lastrowid)
            for student in students:
                conn.execute(
                    """
                    INSERT INTO nucleus_instance_students
                    (course_id, full_name, email, final_grade, final_status, participant_found)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (
                        course_id,
                        student["full_name"],
                        _student_key(career, subject, teacher, student["full_name"]),
                        student["grade"],
                        student["status"],
                    ),
                )

        unique_students = {
            (normalize(record["nombre_carrera"]), normalize(record["nombre_estudiante"]))
            for record in records
        }
        careers = {normalize(record["nombre_carrera"]) for record in records}
        conn.execute(
            """
            INSERT INTO nucleus_excel_imports
            (report_id, filename, source_rows, imported_rows, duplicate_rows, skipped_rows,
             careers, students, courses, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_id) DO UPDATE SET
                filename=excluded.filename,
                source_rows=excluded.source_rows,
                imported_rows=excluded.imported_rows,
                duplicate_rows=excluded.duplicate_rows,
                skipped_rows=excluded.skipped_rows,
                careers=excluded.careers,
                students=excluded.students,
                courses=excluded.courses,
                imported_at=excluded.imported_at
            """,
            (
                report_id,
                filename,
                source_rows,
                len(records),
                duplicate_rows,
                skipped_rows,
                len(careers),
                len(unique_students),
                len(groups),
                now,
            ),
        )

    return {
        "ok": True,
        "summary": {
            "filename": filename,
            "source_rows": source_rows,
            "imported_rows": len(records),
            "duplicate_rows": duplicate_rows,
            "skipped_rows": skipped_rows,
            "careers": len(careers),
            "students": len(unique_students),
            "courses": len(groups),
            "imported_at": now,
        },
    }


def get_excel_import_summary(report_id: int) -> dict[str, Any] | None:
    ensure_excel_schema()
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM nucleus_excel_imports WHERE report_id=?",
            (report_id,),
        ).fetchone()
    if not row:
        return None
    return rows_to_dicts([row])[0]
