from __future__ import annotations

import re
from typing import Any

import app as core
import import_service
import requirements_store
from db import connection, create_default_sections, utcnow
from import_service import _load_preview, clean_cell


def _robust_modality(career_name: str, career_code: str) -> str:
    """Reconoce variantes habituales de la modalidad en línea."""
    name = import_service.normalize_name(career_name)
    code = str(career_code or "").upper()
    return "en_linea" if (
        "ONLINE" in name
        or "EN LINEA" in name
        or "EN-LINEA" in name
        or "-L-" in code
    ) else "presencial"


def _counterpart_id(conn: Any, active: Any, other_modality: str, period: str) -> int | None:
    old_import_id = active["source_import_id"]
    if old_import_id:
        row = conn.execute(
            """
            SELECT id FROM reports
            WHERE source_import_id=? AND modality=? AND id<>?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (old_import_id, other_modality, active["id"]),
        ).fetchone()
        if row:
            return int(row["id"])

    row = conn.execute(
        """
        SELECT id FROM reports
        WHERE modality=? AND period=? AND name=? AND id<>?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (other_modality, period, active["name"], active["id"]),
    ).fetchone()
    return int(row["id"]) if row else None


def _report_code(payload: dict[str, Any], modality: str, fallback: str) -> str:
    specific = "code_online" if modality == "en_linea" else "code_presencial"
    return clean_cell(payload.get(specific) or payload.get("code") or fallback)


def _upsert_report(
    conn: Any,
    *,
    active: Any,
    report_id: int | None,
    modality: str,
    import_id: int,
    period: str,
    version: str,
    elaboration_date: str,
    code: str,
    now: str,
) -> int:
    if report_id is not None:
        conn.execute(
            """
            UPDATE reports SET
                name=?, period=?, modality=?, code=?, version=?, elaboration_date=?,
                prepared_by=?, prepared_role=?, reviewed_by=?, reviewed_role=?,
                approved_by=?, approved_role=?, status=?, source_import_id=?, updated_at=?
            WHERE id=?
            """,
            (
                active["name"],
                period,
                modality,
                code,
                version,
                elaboration_date,
                active["prepared_by"],
                active["prepared_role"],
                active["reviewed_by"],
                active["reviewed_role"],
                active["approved_by"],
                active["approved_role"],
                active["status"],
                import_id,
                now,
                report_id,
            ),
        )
        return report_id

    cursor = conn.execute(
        """
        INSERT INTO reports
        (name, period, modality, code, version, elaboration_date,
         prepared_by, prepared_role, reviewed_by, reviewed_role,
         approved_by, approved_role, status, source_import_id,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            active["name"],
            period,
            modality,
            code,
            version,
            elaboration_date,
            active["prepared_by"],
            active["prepared_role"],
            active["reviewed_by"],
            active["reviewed_role"],
            active["approved_by"],
            active["approved_role"],
            active["status"],
            import_id,
            now,
            now,
        ),
    )
    new_id = int(cursor.lastrowid)
    create_default_sections(conn, new_id)
    return new_id


def commit_preview_to_pair(token: str, active_report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Carga una sola base y mantiene dos informes hermanos por modalidad."""
    requirements_store.ensure_requirements_schema()
    parsed = _load_preview(token)
    preview = parsed.get("preview") or {}
    records = list(parsed.get("records") or [])
    if not records:
        raise ValueError("El archivo no contiene estudiantes válidos.")

    with connection() as conn:
        active = conn.execute("SELECT * FROM reports WHERE id=?", (active_report_id,)).fetchone()
        if not active:
            raise ValueError("El informe activo no existe.")

        period = clean_cell(payload.get("period") or preview.get("period") or active["period"])
        if not period:
            raise ValueError("Confirme el periodo académico antes de importar.")
        version = clean_cell(payload.get("version") or active["version"] or "1.0")
        elaboration_date = clean_cell(payload.get("elaboration_date") or active["elaboration_date"])
        now = utcnow()

        by_modality = {
            "presencial": [row for row in records if row.get("modality") == "presencial"],
            "en_linea": [row for row in records if row.get("modality") == "en_linea"],
        }
        active_modality = str(active["modality"] or "presencial")
        if not by_modality.get(active_modality):
            label = "en línea" if active_modality == "en_linea" else "presencial"
            raise ValueError(f"El archivo no contiene estudiantes de modalidad {label}.")

        cursor = conn.execute(
            """
            INSERT INTO import_history
            (original_name, period, total_students, presencial_students,
             online_students, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                clean_cell(preview.get("filename") or "requisitos.xls"),
                period,
                len(records),
                len(by_modality["presencial"]),
                len(by_modality["en_linea"]),
                now,
            ),
        )
        import_id = int(cursor.lastrowid)

        report_ids: dict[str, int] = {}
        for modality in ("presencial", "en_linea"):
            modality_records = by_modality[modality]
            if not modality_records:
                continue

            if modality == active_modality:
                target_id = active_report_id
            else:
                target_id = _counterpart_id(conn, active, modality, period)

            target_id = _upsert_report(
                conn,
                active=active,
                report_id=target_id,
                modality=modality,
                import_id=import_id,
                period=period,
                version=version,
                elaboration_date=elaboration_date,
                code=_report_code(payload, modality, str(active["code"] or "")),
                now=now,
            )
            report_ids[modality] = target_id

            conn.execute("DELETE FROM requirements_students WHERE report_id=?", (target_id,))
            for record in modality_records:
                requirements_store._insert_requirement_record(conn, target_id, record, now)

    other_modality = "en_linea" if active_modality == "presencial" else "presencial"
    return {
        "ok": True,
        "report_id": active_report_id,
        "report_ids": report_ids,
        "paired_report_id": report_ids.get(other_modality),
        "modality": active_modality,
        "period": period,
        "students": len(records),
        "active_students": len(by_modality[active_modality]),
        "presencial": len(by_modality["presencial"]),
        "en_linea": len(by_modality["en_linea"]),
        "careers": len({clean_cell(row.get("career_name")) for row in records if row.get("career_name")}),
        "filename": clean_cell(preview.get("filename") or "requisitos.xls"),
    }


def install() -> None:
    if getattr(core.InformtitHandler, "_dual_modality_runtime_installed", False):
        return

    # La detección se usa al analizar el .xls, antes de confirmar la importación.
    import_service._modality = _robust_modality

    previous_write = core.InformtitHandler._handle_api_write

    def dual_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)/imports/([A-Za-z0-9_-]+)/commit", path)
        if match and method == "POST":
            result = commit_preview_to_pair(match.group(2), int(match.group(1)), payload)
            self._send_json(result, 201)
            return
        previous_write(self, method, path, payload)

    core.InformtitHandler._handle_api_write = dual_write
    core.InformtitHandler._dual_modality_runtime_installed = True
