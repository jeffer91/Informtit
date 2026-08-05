from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from db import connection, rows_to_dicts, utcnow
from import_service import _load_preview, clean_cell, ensure_schema


REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("academic_status", "Académico"),
    ("documentation_status", "Documentación"),
    ("financial_status", "Financiero"),
    ("titulation_status", "Titulación"),
    ("practices_linkage_status", "Prácticas y vinculación"),
    ("linkage_status", "Vinculación"),
    ("graduate_followup_status", "Seguimiento a graduados"),
    ("english_status", "Inglés"),
    ("data_update_status", "Actualización de datos"),
    ("titulation_approval", "Aprobación de titulación"),
    ("complexive_approval", "Aprobación complexivo/proyecto"),
)


def _status(value: Any) -> str:
    return clean_cell(value).upper()


def get_report_roster(report_id: int) -> dict[str, Any]:
    ensure_schema()
    with connection() as conn:
        report = conn.execute(
            "SELECT id, name, period, modality, source_import_id FROM reports WHERE id=?",
            (report_id,),
        ).fetchone()
        if not report:
            raise ValueError("El informe no existe.")

        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT s.*, c.name AS career_name, c.career_code AS report_career_code
                FROM students s
                JOIN careers c ON c.id=s.career_id
                WHERE c.report_id=?
                ORDER BY c.sort_order, c.name, s.full_name
                """,
                (report_id,),
            ).fetchall()
        )

    requirement_summary: list[dict[str, Any]] = []
    for key, label in REQUIREMENTS:
        values = [_status(row.get(key)) for row in rows]
        requirement_summary.append(
            {
                "key": key,
                "label": label,
                "complies": sum(value == "CUMPLE" for value in values),
                "does_not_comply": sum(value == "NO CUMPLE" for value in values),
                "blank": sum(not value for value in values),
                "total": len(values),
            }
        )

    complete = 0
    pending = 0
    notes_loaded = 0
    for row in rows:
        pending_keys = [
            key for key, _label in REQUIREMENTS if _status(row.get(key)) == "NO CUMPLE"
        ]
        blank_keys = [key for key, _label in REQUIREMENTS if not _status(row.get(key))]
        row["pending_requirements"] = pending_keys
        row["blank_requirements"] = blank_keys
        row["requirements_complete"] = not pending_keys and not blank_keys
        row["notes_loaded"] = bool(
            row.get("notes_matched")
            or row.get("ordinary_theory") is not None
            or row.get("ordinary_practical") is not None
            or row.get("source_total_course") is not None
        )
        complete += int(row["requirements_complete"])
        pending += int(not row["requirements_complete"])
        notes_loaded += int(row["notes_loaded"])

    career_counter = Counter(row["career_name"] for row in rows)
    campus_counter = Counter(row.get("campus") or "Sin sede" for row in rows)
    schedule_counter = Counter(row.get("schedule") or "Sin jornada" for row in rows)

    return {
        "ok": True,
        "report": dict(report),
        "summary": {
            "students": len(rows),
            "careers": len(career_counter),
            "requirements_complete": complete,
            "requirements_pending": pending,
            "notes_loaded": notes_loaded,
            "notes_pending": max(0, len(rows) - notes_loaded),
            "is_imported": bool(report["source_import_id"])
            or any(row.get("imported_from_roster") for row in rows),
        },
        "careers": [
            {"name": name, "students": count}
            for name, count in sorted(career_counter.items())
        ],
        "campuses": [
            {"name": name, "students": count}
            for name, count in sorted(campus_counter.items())
        ],
        "schedules": [
            {"name": name, "students": count}
            for name, count in sorted(schedule_counter.items())
        ],
        "requirements": requirement_summary,
        "students": rows,
    }


def commit_preview_to_report(
    token: str, report_id: int, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_schema()
    parsed = _load_preview(token)
    preview = parsed["preview"]
    records = parsed["records"]

    with connection() as conn:
        report = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        if not report:
            raise ValueError("El informe activo no existe.")

        modality = report["modality"]
        selected = [record for record in records if record["modality"] == modality]
        if not selected:
            label = "en línea" if modality == "en_linea" else "presencial"
            raise ValueError(f"El archivo no contiene estudiantes de modalidad {label}.")

        now = utcnow()
        period = clean_cell(payload.get("period") or preview.get("period") or report["period"])
        version = clean_cell(payload.get("version") or report["version"] or "1.0")
        elaboration_date = clean_cell(
            payload.get("elaboration_date") or report["elaboration_date"]
        )
        code = clean_cell(payload.get("code") or report["code"])

        cursor = conn.execute(
            """
            INSERT INTO import_history
            (original_name, period, total_students, presencial_students,
             online_students, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                preview["filename"],
                period,
                len(selected),
                len(selected) if modality == "presencial" else 0,
                len(selected) if modality == "en_linea" else 0,
                now,
            ),
        )
        import_id = int(cursor.lastrowid)

        conn.execute("DELETE FROM careers WHERE report_id=?", (report_id,))
        conn.execute(
            """
            UPDATE reports SET period=?, version=?, elaboration_date=?, code=?,
                source_import_id=?, updated_at=?
            WHERE id=?
            """,
            (period, version, elaboration_date, code, import_id, now, report_id),
        )

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in selected:
            grouped[record["career_name"]].append(record)

        for sort_order, career_name in enumerate(sorted(grouped), start=1):
            career_records = grouped[career_name]
            codes = sorted(
                {
                    record["career_code"]
                    for record in career_records
                    if record["career_code"]
                }
            )
            cursor = conn.execute(
                """
                INSERT INTO careers
                (report_id, name, sort_order, created_at, career_code)
                VALUES (?, ?, ?, ?, ?)
                """,
                (report_id, career_name, sort_order, now, " / ".join(codes)),
            )
            career_id = int(cursor.lastrowid)

            for record in career_records:
                conn.execute(
                    """
                    INSERT INTO students
                    (career_id, full_name, email, created_at, updated_at,
                     identification, career_code, schedule, academic_status,
                     documentation_status, financial_status, titulation_status,
                     practices_linkage_status, linkage_status,
                     graduate_followup_status, english_status,
                     data_update_status, personal_email, phone, campus,
                     titulation_approval, complexive_approval,
                     imported_from_roster, notes_matched, match_method)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, 1, 0, '')
                    """,
                    (
                        career_id,
                        record["full_name"],
                        record["email"] or None,
                        now,
                        now,
                        record["identification"],
                        record["career_code"],
                        record["schedule"],
                        record["academic_status"],
                        record["documentation_status"],
                        record["financial_status"],
                        record["titulation_status"],
                        record["practices_linkage_status"],
                        record["linkage_status"],
                        record["graduate_followup_status"],
                        record["english_status"],
                        record["data_update_status"],
                        record["personal_email"],
                        record["phone"],
                        record["campus"],
                        record["titulation_approval"],
                        record["complexive_approval"],
                    ),
                )

    return {
        "ok": True,
        "report_id": report_id,
        "modality": modality,
        "period": period,
        "students": len(selected),
        "careers": len(grouped),
        "filename": preview["filename"],
    }
