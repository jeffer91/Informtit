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


def _reclassify_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recalcula la modalidad desde la carrera y el código antes de guardar.

    No se confía ciegamente en el campo ``modality`` almacenado en una
    previsualización anterior. Así, un registro con código ``-L-`` o carrera
    ONLINE siempre termina en el dataset Online aunque la previsualización haya
    sido creada por una versión antigua del parser.
    """
    result: list[dict[str, Any]] = []
    for item in records:
        row = dict(item)
        row["modality"] = _robust_modality(
            str(row.get("career_name") or ""),
            str(row.get("career_code") or ""),
        )
        result.append(row)
    return result


def modality_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    classified = _reclassify_records(records)
    return {
        "presencial": sum(row.get("modality") == "presencial" for row in classified),
        "en_linea": sum(row.get("modality") == "en_linea" for row in classified),
    }


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
    import_id: int | None,
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


def ensure_report_pairs() -> dict[str, Any]:
    """Garantiza que todo informe tenga su hermano Presencial/Online."""
    now = utcnow()
    created: list[int] = []

    with connection() as conn:
        reports = conn.execute(
            """
            SELECT * FROM reports
            WHERE modality IN ('presencial', 'en_linea')
            ORDER BY id
            """
        ).fetchall()

        for active in reports:
            active_modality = str(active["modality"] or "presencial")
            other_modality = "en_linea" if active_modality == "presencial" else "presencial"
            period = clean_cell(active["period"])
            counterpart = _counterpart_id(conn, active, other_modality, period)
            if counterpart is not None:
                continue

            new_id = _upsert_report(
                conn,
                active=active,
                report_id=None,
                modality=other_modality,
                import_id=active["source_import_id"],
                period=period,
                version=clean_cell(active["version"] or "1.0"),
                elaboration_date=clean_cell(active["elaboration_date"]),
                code=clean_cell(active["code"]),
                now=now,
            )
            created.append(new_id)

    return {"ok": True, "created": created, "count": len(created)}


def commit_preview_to_pair(token: str, active_report_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Carga una sola base y actualiza los datasets Presencial y Online.

    La modalidad se vuelve a calcular en el momento del commit y se verifica que
    el número realmente guardado coincida con el número detectado. Una importación
    no puede terminar silenciosamente con Online=0 cuando la fuente contiene
    carreras ONLINE o códigos -L-.
    """
    requirements_store.ensure_requirements_schema()
    parsed = _load_preview(token)
    preview = parsed.get("preview") or {}
    records = _reclassify_records(list(parsed.get("records") or []))
    if not records:
        raise ValueError("El archivo no contiene estudiantes válidos.")

    by_modality = {
        "presencial": [row for row in records if row.get("modality") == "presencial"],
        "en_linea": [row for row in records if row.get("modality") == "en_linea"],
    }

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
        active_modality = str(active["modality"] or "presencial")

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
        persisted: dict[str, int] = {}
        for modality in ("presencial", "en_linea"):
            modality_records = by_modality[modality]

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

            saved = int(
                conn.execute(
                    "SELECT COUNT(*) FROM requirements_students WHERE report_id=?",
                    (target_id,),
                ).fetchone()[0]
            )
            expected = len(modality_records)
            persisted[modality] = saved
            if saved != expected:
                label = "Online" if modality == "en_linea" else "Presencial"
                raise ValueError(
                    f"Error de importación {label}: se detectaron {expected} estudiantes "
                    f"pero se guardaron {saved}. La operación fue cancelada para evitar datos incompletos."
                )

        if persisted["presencial"] + persisted["en_linea"] != len(records):
            raise ValueError(
                "Error de conciliación de la importación: Presencial + Online no coincide con el total del archivo."
            )

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
        "persisted_presencial": persisted["presencial"],
        "persisted_en_linea": persisted["en_linea"],
        "careers": len({clean_cell(row.get("career_name")) for row in records if row.get("career_name")}),
        "filename": clean_cell(preview.get("filename") or "requisitos.xls"),
    }


def install() -> None:
    if getattr(core.InformtitHandler, "_dual_modality_runtime_installed", False):
        import_service._modality = _robust_modality
        ensure_report_pairs()
        return

    # La detección se usa al analizar el .xls y se repite al confirmar la carga.
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
    ensure_report_pairs()
