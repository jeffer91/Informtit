from __future__ import annotations

from collections import Counter
from typing import Any

from db import connection, create_default_sections, rows_to_dicts, utcnow
from import_service import _load_preview, clean_cell, ensure_schema, settings_for_report
from workflow_rules import PRE_NUCLEUS_REQUIREMENTS, downstream_state, prerequisite_state


REQUIREMENTS: tuple[tuple[str, str], ...] = PRE_NUCLEUS_REQUIREMENTS

_REQUIREMENT_COLUMNS = (
    "identification",
    "full_name",
    "career_code",
    "career_name",
    "modality",
    "schedule",
    "academic_status",
    "documentation_status",
    "financial_status",
    "titulation_status",
    "practices_linkage_status",
    "linkage_status",
    "graduate_followup_status",
    "english_status",
    "data_update_status",
    "personal_email",
    "email",
    "phone",
    "campus",
    "titulation_approval",
    "complexive_approval",
)


def _status(value: Any) -> str:
    return clean_cell(value).upper()


def ensure_requirements_schema() -> None:
    """Crea el almacenamiento exclusivo del módulo Requisitos y migra bases antiguas."""

    ensure_schema()
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS requirements_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                identification TEXT DEFAULT '',
                full_name TEXT NOT NULL,
                career_code TEXT DEFAULT '',
                career_name TEXT DEFAULT '',
                modality TEXT DEFAULT '',
                schedule TEXT DEFAULT '',
                academic_status TEXT DEFAULT '',
                documentation_status TEXT DEFAULT '',
                financial_status TEXT DEFAULT '',
                titulation_status TEXT DEFAULT '',
                practices_linkage_status TEXT DEFAULT '',
                linkage_status TEXT DEFAULT '',
                graduate_followup_status TEXT DEFAULT '',
                english_status TEXT DEFAULT '',
                data_update_status TEXT DEFAULT '',
                personal_email TEXT DEFAULT '',
                email TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                campus TEXT DEFAULT '',
                titulation_approval TEXT DEFAULT '',
                complexive_approval TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_requirements_report
                ON requirements_students(report_id);
            CREATE INDEX IF NOT EXISTS idx_requirements_identification
                ON requirements_students(report_id, identification);
            """
        )

        report_ids = [int(row[0]) for row in conn.execute("SELECT id FROM reports").fetchall()]
        for report_id in report_ids:
            count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM requirements_students WHERE report_id=?",
                    (report_id,),
                ).fetchone()[0]
            )
            if count:
                continue

            legacy = rows_to_dicts(
                conn.execute(
                    """
                    SELECT s.*, c.name AS career_name,
                           COALESCE(NULLIF(s.career_code, ''), c.career_code, '') AS migrated_career_code,
                           r.modality AS report_modality
                    FROM students s
                    JOIN careers c ON c.id=s.career_id
                    JOIN reports r ON r.id=c.report_id
                    WHERE c.report_id=?
                      AND (
                        COALESCE(s.imported_from_roster, 0)=1 OR
                        COALESCE(s.academic_status, '')<>'' OR
                        COALESCE(s.documentation_status, '')<>'' OR
                        COALESCE(s.financial_status, '')<>'' OR
                        COALESCE(s.practices_linkage_status, '')<>'' OR
                        COALESCE(s.linkage_status, '')<>'' OR
                        COALESCE(s.graduate_followup_status, '')<>'' OR
                        COALESCE(s.english_status, '')<>'' OR
                        COALESCE(s.data_update_status, '')<>''
                      )
                    ORDER BY c.sort_order, c.name, s.full_name
                    """,
                    (report_id,),
                ).fetchall()
            )
            if not legacy:
                continue
            now = utcnow()
            for row in legacy:
                conn.execute(
                    """
                    INSERT INTO requirements_students
                    (report_id, identification, full_name, career_code, career_name,
                     modality, schedule, academic_status, documentation_status,
                     financial_status, titulation_status, practices_linkage_status,
                     linkage_status, graduate_followup_status, english_status,
                     data_update_status, personal_email, email, phone, campus,
                     titulation_approval, complexive_approval, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        row.get("identification") or "",
                        row.get("full_name") or "",
                        row.get("migrated_career_code") or "",
                        row.get("career_name") or "",
                        row.get("report_modality") or "",
                        row.get("schedule") or "",
                        row.get("academic_status") or "",
                        row.get("documentation_status") or "",
                        row.get("financial_status") or "",
                        row.get("titulation_status") or "",
                        row.get("practices_linkage_status") or "",
                        row.get("linkage_status") or "",
                        row.get("graduate_followup_status") or "",
                        row.get("english_status") or "",
                        row.get("data_update_status") or "",
                        row.get("personal_email") or "",
                        row.get("email") or "",
                        row.get("phone") or "",
                        row.get("campus") or "",
                        row.get("titulation_approval") or "",
                        row.get("complexive_approval") or "",
                        now,
                        now,
                    ),
                )


def _insert_requirement_record(conn: Any, report_id: int, record: dict[str, Any], now: str) -> None:
    values = [record.get(column) or "" for column in _REQUIREMENT_COLUMNS]
    conn.execute(
        f"""
        INSERT INTO requirements_students
        (report_id, {', '.join(_REQUIREMENT_COLUMNS)}, created_at, updated_at)
        VALUES (?, {', '.join('?' for _ in _REQUIREMENT_COLUMNS)}, ?, ?)
        """,
        (report_id, *values, now, now),
    )


def get_report_roster(report_id: int) -> dict[str, Any]:
    ensure_requirements_schema()
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
                SELECT * FROM requirements_students
                WHERE report_id=?
                ORDER BY career_name, full_name, id
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
    titulation_marked = 0
    complexive_project_approved = 0
    titles_uploaded = 0
    for row in rows:
        requirement_state = prerequisite_state(row)
        downstream = downstream_state(row)
        row["pending_requirements"] = requirement_state["pending"]
        row["blank_requirements"] = requirement_state["blank"]
        row["requirements_complete"] = requirement_state["complete"]
        row["missing_requirement_labels"] = requirement_state["missing"]
        row.update(downstream)
        row["notes_loaded"] = False
        row["report_career_code"] = row.get("career_code") or ""
        complete += int(row["requirements_complete"])
        pending += int(not row["requirements_complete"])
        titulation_marked += int(downstream["titulation_marked"])
        complexive_project_approved += int(downstream["complexive_project_approved"])
        titles_uploaded += int(downstream["titles_uploaded"])

    career_counter = Counter(row.get("career_name") or "Sin carrera" for row in rows)
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
            "titulation_marked": titulation_marked,
            "complexive_project_approved": complexive_project_approved,
            "titles_uploaded": titles_uploaded,
            "notes_loaded": 0,
            "notes_pending": 0,
            "is_imported": bool(report["source_import_id"]) or bool(rows),
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


def commit_preview_to_report(token: str, report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_requirements_schema()
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
        elaboration_date = clean_cell(payload.get("elaboration_date") or report["elaboration_date"])
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
        conn.execute("DELETE FROM requirements_students WHERE report_id=?", (report_id,))
        conn.execute(
            """
            UPDATE reports SET period=?, version=?, elaboration_date=?, code=?,
                source_import_id=?, updated_at=?
            WHERE id=?
            """,
            (period, version, elaboration_date, code, import_id, now, report_id),
        )
        for record in selected:
            _insert_requirement_record(conn, report_id, record, now)

    return {
        "ok": True,
        "report_id": report_id,
        "modality": modality,
        "period": period,
        "students": len(selected),
        "careers": len({record["career_name"] for record in selected}),
        "filename": preview["filename"],
    }


def commit_preview(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Crea uno o dos informes cargando únicamente el módulo Requisitos."""

    ensure_requirements_schema()
    parsed = _load_preview(token)
    preview = parsed["preview"]
    records = parsed["records"]
    period = clean_cell(payload.get("period") or preview.get("period"))
    if not period:
        raise ValueError("Confirme el periodo académico antes de importar.")
    report_name = clean_cell(payload.get("report_name") or "Informe Final del Proceso de Titulación")
    version = clean_cell(payload.get("version") or "1.0")
    elaboration_date = clean_cell(payload.get("elaboration_date"))
    settings = settings_for_report()
    now = utcnow()

    report_ids: dict[str, int] = {}
    with connection() as conn:
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
                preview["total"],
                preview["presencial"],
                preview["en_linea"],
                now,
            ),
        )
        import_id = int(cursor.lastrowid)

        for modality in ("presencial", "en_linea"):
            modality_records = [record for record in records if record["modality"] == modality]
            if not modality_records:
                continue
            code_key = "code_online" if modality == "en_linea" else "code_presencial"
            code = clean_cell(payload.get(code_key, ""))
            cursor = conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, code, version, elaboration_date,
                 prepared_by, prepared_role, reviewed_by, reviewed_role,
                 approved_by, approved_role, status, source_import_id,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'borrador', ?, ?, ?)
                """,
                (
                    report_name,
                    period,
                    modality,
                    code,
                    version,
                    elaboration_date,
                    settings["prepared_by"],
                    settings["prepared_role"],
                    settings["reviewed_by"],
                    settings["reviewed_role"],
                    settings["approved_by"],
                    settings["approved_role"],
                    import_id,
                    now,
                    now,
                ),
            )
            report_id = int(cursor.lastrowid)
            report_ids[modality] = report_id
            create_default_sections(conn, report_id)
            for record in modality_records:
                _insert_requirement_record(conn, report_id, record, now)

    return {
        "ok": True,
        "report_ids": report_ids,
        "period": period,
        "total": preview["total"],
        "presencial": preview["presencial"],
        "en_linea": preview["en_linea"],
    }
