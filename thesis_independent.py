from __future__ import annotations

import re
from statistics import mean
from typing import Any

from db import connection, utcnow
from import_service import clean_cell
import process_service as legacy


def _clean_identity(payload: dict[str, Any], raw_text: str) -> tuple[str, str, str]:
    identification = clean_cell(payload.get("identification"))
    if not identification:
        match = re.search(r"(?:C[eé]dula|Cedula)\s*:?\s*(\d{8,13})", raw_text, re.IGNORECASE)
        identification = match.group(1) if match else ""
    full_name = clean_cell(payload.get("full_name"))
    career_name = clean_cell(payload.get("career_name"))
    if not identification:
        raise ValueError("Ingrese la cédula del estudiante para este Trabajo de Titulación.")
    if not full_name:
        raise ValueError("Ingrese el nombre del estudiante para este Trabajo de Titulación.")
    if not career_name:
        raise ValueError("Ingrese la carrera del estudiante para este Trabajo de Titulación.")
    return identification, full_name, career_name


def parse_project_text(report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Guarda Trabajo de Titulación sin consultar Requisitos ni Examen Complexivo."""

    raw_text = str(payload.get("text") or "").strip()
    if not raw_text:
        raise ValueError("Pegue la información del Trabajo de Titulación.")
    identification, full_name, career_name = _clean_identity(payload, raw_text)
    career_code = clean_cell(payload.get("career_code"))

    tutor = legacy._field_number(raw_text, r"CALIFICACI[ÓO]N\s+TUTOR")
    reader = legacy._field_number(raw_text, r"CALIFICACI[ÓO]N\s+LECTOR")
    source_written = legacy._field_number(raw_text, r"PROMEDIO\s+TRABAJO\s+ESCRITO")
    written_values = [value for value in (tutor, reader) if value is not None]
    written = source_written if source_written is not None else round(mean(written_values), 2) if written_values else None

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

    vocal_1 = legacy._field_text(raw_text, r"PRIMER\s+VOCAL", r"SEGUNDO\s+VOCAL")
    vocal_2 = legacy._field_text(raw_text, r"SEGUNDO\s+VOCAL", r"TERCER\s+VOCAL")
    vocal_3 = legacy._field_text(raw_text, r"TERCER\s+VOCAL", r"EVALUACI[ÓO]N\s+PRACTICA")

    practical_scores = legacy._score_block(
        raw_text,
        "EVALUACIÓN PRACTICA",
        "EVALUACIÓN DE LA DEFENSA",
        legacy.PRACTICAL_CRITERIA,
    )
    defense_scores = legacy._score_block(
        raw_text,
        "EVALUACIÓN DE LA DEFENSA",
        "1. PROMEDIO TRABAJO ESCRITO",
        legacy.DEFENSE_CRITERIA,
    )
    practical_average = legacy._evaluation_average(practical_scores)
    defense_average = legacy._evaluation_average(defense_scores)
    oral_average = (
        round((practical_average + defense_average) / 2, 2)
        if practical_average is not None and defense_average is not None
        else None
    )
    final_grade = (
        round(written * 0.60 + oral_average * 0.40, 2)
        if written is not None and oral_average is not None
        else None
    )
    source_final = legacy._field_number(
        raw_text,
        r"CALIFICACION\s+FINAL\s+DEL\s+PROYECTO\s+DE\s+TITULACION[^:]*",
    )
    difference = (
        round(final_grade - source_final, 2)
        if final_grade is not None and source_final is not None
        else None
    )

    now = utcnow()
    with connection() as conn:
        report = conn.execute("SELECT id FROM reports WHERE id=?", (report_id,)).fetchone()
        if not report:
            raise ValueError("El informe no existe.")
        conn.execute(
            """
            INSERT INTO thesis_projects
            (report_id, student_id, identification, full_name, career_code, career_name,
             act_number, act_date, tutor_grade, reader_grade, written_average,
             vocal_1, vocal_2, vocal_3, practical_average, defense_average,
             oral_average, final_grade, source_final_grade, source_difference,
             raw_text, created_at, updated_at)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_id, identification) DO UPDATE SET
                student_id=NULL,
                full_name=excluded.full_name,
                career_code=excluded.career_code,
                career_name=excluded.career_name,
                act_number=excluded.act_number,
                act_date=excluded.act_date,
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
                updated_at=excluded.updated_at
            """,
            (
                report_id,
                identification,
                full_name,
                career_code,
                career_name,
                act_number_match.group(1) if act_number_match else "",
                act_date_match.group(1) if act_date_match else "",
                tutor,
                reader,
                written,
                vocal_1,
                vocal_2,
                vocal_3,
                practical_average,
                defense_average,
                oral_average,
                final_grade,
                source_final,
                difference,
                raw_text,
                now,
                now,
            ),
        )
        project_id = int(
            conn.execute(
                "SELECT id FROM thesis_projects WHERE report_id=? AND identification=?",
                (report_id, identification),
            ).fetchone()[0]
        )
        conn.execute("DELETE FROM thesis_scores WHERE project_id=?", (project_id,))
        for evaluation_type, rows in (
            ("practical", practical_scores),
            ("defense", defense_scores),
        ):
            for order, row in enumerate(rows, start=1):
                conn.execute(
                    """
                    INSERT INTO thesis_scores
                    (project_id, evaluation_type, criterion, max_score, vocal_1,
                     vocal_2, vocal_3, sort_order)
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
    return {"ok": True, "project_id": project_id, "final_grade": final_grade}
