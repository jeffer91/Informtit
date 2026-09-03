from __future__ import annotations

import json
import re
from statistics import mean
from typing import Any

from db import connection, utcnow
from import_service import clean_cell
import process_service as legacy


PASS_GRADE = 7.0
TOLERANCE = 0.05


def _line(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").strip().split())


def _number(value: Any) -> float | None:
    text = _line(value)
    if not text or text in {"-", "—", "–", "NULL", "null", "None"}:
        return None
    try:
        return float(text.replace(".", "").replace(",", ".") if "," in text else text)
    except (TypeError, ValueError):
        return None


def _table_columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_thesis_schema() -> None:
    legacy.ensure_process_schema()
    with connection() as conn:
        columns = _table_columns(conn, "thesis_projects")
        additions = {
            "project_title": "TEXT DEFAULT ''",
            "modality": "TEXT DEFAULT ''",
            "final_status": "TEXT DEFAULT 'INCOMPLETO'",
            "validation_json": "TEXT DEFAULT '{}'",
            "lowest_component": "TEXT DEFAULT ''",
            "lowest_parameter": "TEXT DEFAULT ''",
            "tutor_name": "TEXT DEFAULT ''",
            "reader_name": "TEXT DEFAULT ''",
        }
        for column, definition in additions.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE thesis_projects ADD COLUMN {column} {definition}")


def _split_blocks(raw_text: str) -> list[str]:
    text = str(raw_text or "").strip()
    if not text:
        return []
    starts = [match.start() for match in re.finditer(r"(?im)^\s*Nombres?\s*:", text)]
    if len(starts) <= 1:
        return [text]
    blocks: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        block = text[start:end].strip()
        if block:
            blocks.append(block)
    return blocks or [text]


def _extract_identity(raw_text: str, overrides: dict[str, Any] | None = None) -> dict[str, str]:
    overrides = overrides or {}
    identification = clean_cell(overrides.get("identification"))
    full_name = clean_cell(overrides.get("full_name"))
    career_code = clean_cell(overrides.get("career_code"))
    career_name = clean_cell(overrides.get("career_name"))

    id_match = re.search(r"\b(\d{8,13})\b", raw_text)
    code_match = re.search(r"\b([A-Z0-9]{6,24}-P-\d{3,8})\b", raw_text, re.IGNORECASE)
    if not identification and id_match:
        identification = id_match.group(1)
    if not career_code and code_match:
        career_code = code_match.group(1).upper()

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if identification:
        for raw_line in lines:
            if identification not in raw_line:
                continue
            line = _line(raw_line)
            id_pos = line.find(identification)
            before = line[:id_pos].strip(" \t:-")
            after = line[id_pos + len(identification) :].strip()
            if before and not full_name and "cedula" not in before.lower() and "cédula" not in before.lower():
                full_name = before
            if career_code and career_code in after:
                _, tail = after.split(career_code, 1)
                if tail.strip(" \t:-") and not career_name:
                    career_name = tail.strip(" \t:-")
            elif code_match and code_match.group(1) in after:
                _, tail = after.split(code_match.group(1), 1)
                if tail.strip(" \t:-") and not career_name:
                    career_name = tail.strip(" \t:-")
            break

    if not full_name:
        match = re.search(
            r"Nombres?\s*:\s*(?:Cedula|C[eé]dula)\s*:\s*(?:C[oó]digo\s+de\s+Carrera)\s*:\s*Carrera\s*:\s*\n\s*([^\n\t]+?)\s+(\d{8,13})\b",
            raw_text,
            re.IGNORECASE,
        )
        if match:
            full_name = _line(match.group(1))

    if not career_name and career_code:
        match = re.search(re.escape(career_code) + r"\s+([^\n]+)", raw_text, re.IGNORECASE)
        if match:
            career_name = _line(match.group(1))

    return {
        "identification": identification,
        "full_name": full_name,
        "career_code": career_code,
        "career_name": career_name,
    }


def _between(text: str, start_pattern: str, end_pattern: str) -> str:
    match = re.search(
        start_pattern + r"\s*:?\s*(.*?)\s*(?=" + end_pattern + r")",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    return _line(match.group(1)) if match else ""


def _field_number(text: str, label_pattern: str) -> float | None:
    match = re.search(
        label_pattern + r"[^\n:]*:?\s*([0-9]+(?:[.,][0-9]+)?)",
        text,
        re.IGNORECASE,
    )
    return _number(match.group(1)) if match else None


def _field_text(text: str, label_pattern: str) -> str:
    match = re.search(label_pattern + r"\s*:?\s*([^\n]+)", text, re.IGNORECASE)
    return _line(match.group(1)) if match else ""


def _score_rows(raw_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    practical = legacy._score_block(
        raw_text,
        "EVALUACIÓN PRACTICA",
        "EVALUACIÓN DE LA DEFENSA",
        legacy.PRACTICAL_CRITERIA,
    )
    defense = legacy._score_block(
        raw_text,
        "EVALUACIÓN DE LA DEFENSA",
        "1. PROMEDIO TRABAJO ESCRITO",
        legacy.DEFENSE_CRITERIA,
    )
    return practical, defense


def _normalize_scores(rows: Any, criteria: list[tuple[str, float]]) -> list[dict[str, Any]]:
    source = rows if isinstance(rows, list) else []
    normalized: list[dict[str, Any]] = []
    for index, (criterion, maximum) in enumerate(criteria):
        row = source[index] if index < len(source) and isinstance(source[index], dict) else {}
        normalized.append(
            {
                "criterion": clean_cell(row.get("criterion")) or criterion,
                "max_score": _number(row.get("max_score")) if _number(row.get("max_score")) is not None else maximum,
                "vocal_1": _number(row.get("vocal_1")),
                "vocal_2": _number(row.get("vocal_2")),
                "vocal_3": _number(row.get("vocal_3")),
            }
        )
    return normalized


def _vocal_totals(scores: list[dict[str, Any]]) -> list[float | None]:
    totals: list[float | None] = []
    for vocal in ("vocal_1", "vocal_2", "vocal_3"):
        values = [row.get(vocal) for row in scores]
        totals.append(round(sum(float(value) for value in values), 2) if values and all(value is not None for value in values) else None)
    return totals


def _complete_average(values: list[float | None]) -> float | None:
    return round(mean(float(value) for value in values), 2) if values and all(value is not None for value in values) else None


def _lowest_parameter(practical: list[dict[str, Any]], defense: list[dict[str, Any]]) -> tuple[str, str]:
    candidates: list[tuple[float, str, str]] = []
    for component, rows in (("Evaluación práctica", practical), ("Evaluación de defensa", defense)):
        for row in rows:
            maximum = _number(row.get("max_score"))
            grades = [_number(row.get(key)) for key in ("vocal_1", "vocal_2", "vocal_3")]
            valid = [grade for grade in grades if grade is not None]
            if maximum and valid:
                ratio = mean(valid) / maximum
                candidates.append((ratio, component, clean_cell(row.get("criterion"))))
    if not candidates:
        return "", ""
    _, component, parameter = min(candidates, key=lambda item: item[0])
    return component, parameter


def _calculate(project: dict[str, Any]) -> dict[str, Any]:
    tutor = _number(project.get("tutor_grade"))
    reader = _number(project.get("reader_grade"))
    practical = _normalize_scores(project.get("practical_scores"), legacy.PRACTICAL_CRITERIA)
    defense = _normalize_scores(project.get("defense_scores"), legacy.DEFENSE_CRITERIA)

    written = round((tutor + reader) / 2, 2) if tutor is not None and reader is not None else None
    practical_totals = _vocal_totals(practical)
    defense_totals = _vocal_totals(defense)
    practical_average = _complete_average(practical_totals)
    defense_average = _complete_average(defense_totals)
    oral_average = (
        round((practical_average + defense_average) / 2, 2)
        if practical_average is not None and defense_average is not None
        else None
    )
    final_grade = (
        round((written * 0.60) + (oral_average * 0.40), 2)
        if written is not None and oral_average is not None
        else None
    )
    final_status = "APROBADO" if final_grade is not None and final_grade >= PASS_GRADE else "REPROBADO" if final_grade is not None else "INCOMPLETO"
    lowest_component, lowest_parameter = _lowest_parameter(practical, defense)
    return {
        **project,
        "tutor_grade": tutor,
        "reader_grade": reader,
        "practical_scores": practical,
        "defense_scores": defense,
        "written_average": written,
        "practical_vocal_totals": practical_totals,
        "defense_vocal_totals": defense_totals,
        "practical_average": practical_average,
        "defense_average": defense_average,
        "oral_average": oral_average,
        "final_grade": final_grade,
        "final_status": final_status,
        "lowest_component": lowest_component,
        "lowest_parameter": lowest_parameter,
    }


def _source_values(raw_text: str) -> dict[str, float | None]:
    return {
        "written_average": _field_number(raw_text, r"PROMEDIO\s+TRABAJO\s+ESCRITO"),
        "practical_average": _field_number(raw_text, r"PROMEDIO\s+EVALUACION\s+PRACTICA"),
        "defense_average": _field_number(raw_text, r"PROMEDIO\s+EVALUACION\s+DEFENSA"),
        "oral_average": _field_number(raw_text, r"PROMEDIO\s+DEFENSA\s+ORAL\s+DEL\s+PROYECTO\s+DE\s+TITULACION"),
        "final_grade": _field_number(raw_text, r"CALIFICACION\s+FINAL\s+DEL\s+PROYECTO\s+DE\s+TITULACION"),
    }


def _validate(report_id: int, project: dict[str, Any], existing_project_id: int | None = None) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    if not clean_cell(project.get("identification")):
        errors.append("No se detectó la identificación del estudiante.")
    if not clean_cell(project.get("full_name")):
        errors.append("No se detectó el nombre del estudiante.")
    if not clean_cell(project.get("career_name")):
        errors.append("No se detectó la carrera del estudiante.")
    if not clean_cell(project.get("career_code")):
        warnings.append("No se detectó el código de carrera.")
    if not clean_cell(project.get("act_number")):
        warnings.append("No se detectó el número de acta de grado.")
    if not clean_cell(project.get("act_date")):
        warnings.append("La fecha del acta está vacía.")
    if any(not clean_cell(project.get(key)) for key in ("vocal_1", "vocal_2", "vocal_3")):
        warnings.append("Falta confirmar uno o más vocales de la defensa.")

    for label in ("tutor_grade", "reader_grade"):
        value = _number(project.get(label))
        if value is None:
            warnings.append(f"Falta la calificación de {'tutor' if label == 'tutor_grade' else 'lector'}.")
        elif not 0 <= value <= 10:
            errors.append(f"La calificación de {'tutor' if label == 'tutor_grade' else 'lector'} debe estar entre 0 y 10.")

    for component, scores in (("práctica", project.get("practical_scores", [])), ("defensa", project.get("defense_scores", []))):
        for row in scores:
            maximum = _number(row.get("max_score")) or 0
            for vocal_key, vocal_label in (("vocal_1", "primer vocal"), ("vocal_2", "segundo vocal"), ("vocal_3", "tercer vocal")):
                value = _number(row.get(vocal_key))
                if value is None:
                    warnings.append(f"Falta {component}: {row.get('criterion')} ({vocal_label}).")
                elif value < 0 or value > maximum:
                    errors.append(f"{component.capitalize()} – {row.get('criterion')} ({vocal_label}) debe estar entre 0 y {maximum:g}.")

    sources = project.get("source_values") or {}
    for key, label in (
        ("written_average", "promedio del trabajo escrito"),
        ("practical_average", "promedio de evaluación práctica"),
        ("defense_average", "promedio de defensa"),
        ("oral_average", "promedio oral"),
        ("final_grade", "calificación final"),
    ):
        source = _number(sources.get(key))
        calculated = _number(project.get(key))
        if source is not None and calculated is not None and abs(source - calculated) > TOLERANCE:
            warnings.append(
                f"El {label} pegado ({source:.2f}) no coincide con el cálculo ({calculated:.2f}). Se utilizará el valor calculado."
            )

    identification = clean_cell(project.get("identification"))
    act_number = clean_cell(project.get("act_number"))
    with connection() as conn:
        if identification:
            params: list[Any] = [report_id, identification]
            query = "SELECT id FROM thesis_projects WHERE report_id=? AND identification=?"
            if existing_project_id:
                query += " AND id<>?"
                params.append(existing_project_id)
            duplicate = conn.execute(query, tuple(params)).fetchone()
            if duplicate:
                warnings.append("El estudiante ya se encuentra registrado; al guardar se actualizará su registro.")
        if act_number:
            params = [report_id, act_number]
            query = "SELECT id, identification FROM thesis_projects WHERE report_id=? AND act_number=?"
            if existing_project_id:
                query += " AND id<>?"
                params.append(existing_project_id)
            duplicate_act = conn.execute(query, tuple(params)).fetchone()
            if duplicate_act and clean_cell(duplicate_act["identification"]) != identification:
                errors.append("El número de acta ya está asignado a otro estudiante en este informe.")

    if project.get("final_grade") is not None:
        info.append(
            f"Calificación final calculada: {project['final_grade']:.2f} ({project['final_status']})."
        )
    if project.get("lowest_parameter"):
        info.append(
            f"El parámetro de menor desempeño relativo es «{project['lowest_parameter']}» en {project['lowest_component']}."
        )
    return {"errors": errors, "warnings": warnings, "info": info}


def _parse_block(report_id: int, raw_text: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    identity = _extract_identity(raw_text, overrides)
    act_number_match = re.search(
        r"N[ÚU]MERO\s+DE\s+ACTA\s+DE\s+GRADO\s*:?\s*([A-Za-z0-9-]+)",
        raw_text,
        re.IGNORECASE,
    )
    act_date_match = re.search(
        r"FECHA\s+ACTA\s+DE\s+GRADO\s*:?\s*(\d{2}/\d{2}/\d{4})",
        raw_text,
        re.IGNORECASE,
    )
    practical, defense = _score_rows(raw_text)
    project = {
        **identity,
        "project_title": _field_text(raw_text, r"T[ÍI]TULO\s+(?:DEL\s+)?PROYECTO"),
        "modality": _field_text(raw_text, r"MODALIDAD"),
        "act_number": act_number_match.group(1) if act_number_match else "",
        "act_date": act_date_match.group(1) if act_date_match else "",
        "tutor_name": _field_text(raw_text, r"NOMBRE\s+(?:DEL\s+)?TUTOR"),
        "reader_name": _field_text(raw_text, r"NOMBRE\s+(?:DEL\s+)?LECTOR"),
        "tutor_grade": legacy._field_number(raw_text, r"CALIFICACI[ÓO]N\s+TUTOR"),
        "reader_grade": legacy._field_number(raw_text, r"CALIFICACI[ÓO]N\s+LECTOR"),
        "vocal_1": _between(raw_text, r"PRIMER\s+VOCAL", r"SEGUNDO\s+VOCAL"),
        "vocal_2": _between(raw_text, r"SEGUNDO\s+VOCAL", r"TERCER\s+VOCAL"),
        "vocal_3": _between(raw_text, r"TERCER\s+VOCAL", r"EVALUACI[ÓO]N\s+PRACTICA"),
        "practical_scores": practical,
        "defense_scores": defense,
        "source_values": _source_values(raw_text),
        "raw_text": raw_text,
    }
    if overrides:
        for key in (
            "identification", "full_name", "career_code", "career_name", "project_title", "modality",
            "act_number", "act_date", "tutor_name", "reader_name", "tutor_grade", "reader_grade", "vocal_1", "vocal_2", "vocal_3",
        ):
            if key in overrides and overrides.get(key) not in (None, ""):
                project[key] = overrides.get(key)
    project = _calculate(project)
    project["validation"] = _validate(report_id, project)
    return project


def analyze_project_text(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_thesis_schema()
    raw_text = str(payload.get("text") or "").strip()
    if not raw_text:
        raise ValueError("Pegue la información del Trabajo de Titulación.")
    blocks = _split_blocks(raw_text)
    projects = [_parse_block(report_id, block, payload if len(blocks) == 1 else None) for block in blocks]
    return {
        "ok": True,
        "projects": projects,
        "count": len(projects),
        "has_errors": any(project["validation"]["errors"] for project in projects),
        "has_warnings": any(project["validation"]["warnings"] for project in projects),
    }


def _structured_project(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    project = {
        "identification": clean_cell(payload.get("identification")),
        "full_name": clean_cell(payload.get("full_name")),
        "career_code": clean_cell(payload.get("career_code")),
        "career_name": clean_cell(payload.get("career_name")),
        "project_title": clean_cell(payload.get("project_title")),
        "modality": clean_cell(payload.get("modality")),
        "act_number": clean_cell(payload.get("act_number")),
        "act_date": clean_cell(payload.get("act_date")),
        "tutor_name": clean_cell(payload.get("tutor_name")),
        "reader_name": clean_cell(payload.get("reader_name")),
        "tutor_grade": _number(payload.get("tutor_grade")),
        "reader_grade": _number(payload.get("reader_grade")),
        "vocal_1": clean_cell(payload.get("vocal_1")),
        "vocal_2": clean_cell(payload.get("vocal_2")),
        "vocal_3": clean_cell(payload.get("vocal_3")),
        "practical_scores": _normalize_scores(payload.get("practical_scores"), legacy.PRACTICAL_CRITERIA),
        "defense_scores": _normalize_scores(payload.get("defense_scores"), legacy.DEFENSE_CRITERIA),
        "source_values": payload.get("source_values") if isinstance(payload.get("source_values"), dict) else {},
        "raw_text": str(payload.get("raw_text") or ""),
    }
    project = _calculate(project)
    project["validation"] = _validate(report_id, project, int(payload.get("id") or 0) or None)
    return project


def save_project_data(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_thesis_schema()
    items = payload.get("projects") if isinstance(payload.get("projects"), list) else [payload]
    if not items:
        raise ValueError("No existen registros de Trabajo de Titulación para guardar.")
    saved: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        project = _structured_project(report_id, item)
        if project["validation"]["errors"]:
            raise ValueError("No se puede guardar: " + " ".join(project["validation"]["errors"]))
        if not project["identification"] or not project["full_name"] or not project["career_name"]:
            raise ValueError("Identificación, estudiante y carrera son obligatorios.")

        now = utcnow()
        with connection() as conn:
            report = conn.execute("SELECT id FROM reports WHERE id=?", (report_id,)).fetchone()
            if not report:
                raise ValueError("El informe no existe.")
            conn.execute(
                """
                INSERT INTO thesis_projects
                (report_id, student_id, identification, full_name, career_code, career_name,
                 act_number, act_date, tutor_name, reader_name, tutor_grade, reader_grade, written_average,
                 vocal_1, vocal_2, vocal_3, practical_average, defense_average,
                 oral_average, final_grade, source_final_grade, source_difference,
                 raw_text, created_at, updated_at, project_title, modality, final_status,
                 validation_json, lowest_component, lowest_parameter)
                VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id, identification) DO UPDATE SET
                    student_id=NULL,
                    full_name=excluded.full_name,
                    career_code=excluded.career_code,
                    career_name=excluded.career_name,
                    act_number=excluded.act_number,
                    act_date=excluded.act_date,
                    tutor_name=excluded.tutor_name,
                    reader_name=excluded.reader_name,
                    tutor_grade=excluded.tutor_grade,
                    reader_grade=excluded.reader_grade,
                    written_average=excluded.written_average,
                    vocal_1=excluded.vocal_1,
                    vocal_2=excluded.vocal_2,
                    vocal_3=excluded.vocal_3,
                    practical_average=excluded.practical_average,
                    defense_average=excluded.defense_average,
                    oral_average=excluded.oral_average,
                    final_grade=excluded.final_grade,
                    source_final_grade=excluded.source_final_grade,
                    source_difference=excluded.source_difference,
                    raw_text=excluded.raw_text,
                    project_title=excluded.project_title,
                    modality=excluded.modality,
                    final_status=excluded.final_status,
                    validation_json=excluded.validation_json,
                    lowest_component=excluded.lowest_component,
                    lowest_parameter=excluded.lowest_parameter,
                    updated_at=excluded.updated_at
                """,
                (
                    report_id,
                    project["identification"],
                    project["full_name"],
                    project["career_code"],
                    project["career_name"],
                    project["act_number"],
                    project["act_date"],
                    project["tutor_name"],
                    project["reader_name"],
                    project["tutor_grade"],
                    project["reader_grade"],
                    project["written_average"],
                    project["vocal_1"],
                    project["vocal_2"],
                    project["vocal_3"],
                    project["practical_average"],
                    project["defense_average"],
                    project["oral_average"],
                    project["final_grade"],
                    _number(project.get("source_values", {}).get("final_grade")),
                    round(project["final_grade"] - _number(project.get("source_values", {}).get("final_grade")), 2)
                    if project["final_grade"] is not None and _number(project.get("source_values", {}).get("final_grade")) is not None
                    else None,
                    project["raw_text"],
                    now,
                    now,
                    project["project_title"],
                    project["modality"],
                    project["final_status"],
                    json.dumps(project["validation"], ensure_ascii=False),
                    project["lowest_component"],
                    project["lowest_parameter"],
                ),
            )
            project_id = int(
                conn.execute(
                    "SELECT id FROM thesis_projects WHERE report_id=? AND identification=?",
                    (report_id, project["identification"]),
                ).fetchone()[0]
            )
            conn.execute("DELETE FROM thesis_scores WHERE project_id=?", (project_id,))
            for evaluation_type, rows in (("practical", project["practical_scores"]), ("defense", project["defense_scores"])):
                for order, row in enumerate(rows, start=1):
                    conn.execute(
                        """
                        INSERT INTO thesis_scores
                        (project_id, evaluation_type, criterion, max_score, vocal_1, vocal_2, vocal_3, sort_order)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            project_id,
                            evaluation_type,
                            row["criterion"],
                            row["max_score"],
                            row["vocal_1"],
                            row["vocal_2"],
                            row["vocal_3"],
                            order,
                        ),
                    )
        saved.append({"project_id": project_id, "identification": project["identification"], "final_grade": project["final_grade"], "final_status": project["final_status"]})
    return {"ok": True, "saved": saved, "count": len(saved), "final_grade": saved[0]["final_grade"] if len(saved) == 1 else None}


def parse_project_text(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Compatibilidad: analiza y guarda. La interfaz nueva usa analizar y guardar por separado."""
    analysis = analyze_project_text(report_id, payload)
    if analysis["has_errors"]:
        errors = [error for project in analysis["projects"] for error in project["validation"]["errors"]]
        raise ValueError("No se puede guardar: " + " ".join(errors))
    return save_project_data(report_id, {"projects": analysis["projects"]})
