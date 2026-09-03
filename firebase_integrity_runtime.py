from __future__ import annotations

from typing import Any

import firebase_sync_runtime as firebase_sync
import period_policy_runtime as period_policy
from db import connection, rows_to_dicts, utcnow
from import_service import clean_cell


def _table_exists(conn: Any, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def _count(conn: Any, table: str, report_id: int) -> int:
    if not _table_exists(conn, table):
        return 0
    try:
        return int(
            conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE report_id=?",
                (report_id,),
            ).fetchone()[0]
        )
    except Exception:
        return 0


def _executed_schedule_count(conn: Any, report_id: int) -> int:
    """Cuenta únicamente cronograma con ejecución real, no filas semilla."""
    if not _table_exists(conn, "schedule_items"):
        return 0
    columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(schedule_items)").fetchall()
    }
    required = {
        "executed_date",
        "execution_status",
        "compliance_percentage",
        "evidence",
        "observation",
    }
    if not required.issubset(columns):
        return 0
    return int(
        conn.execute(
            """
            SELECT COUNT(*) FROM schedule_items
            WHERE report_id=? AND (
                COALESCE(executed_date,'')<>'' OR
                COALESCE(execution_status,'')<>'' OR
                compliance_percentage IS NOT NULL OR
                COALESCE(evidence,'')<>'' OR
                COALESCE(observation,'')<>''
            )
            """,
            (report_id,),
        ).fetchone()[0]
    )


def _report_score(conn: Any, report_id: int) -> int:
    """Prioriza el informe PVC que realmente contiene trabajo del usuario."""
    requirements = _count(conn, "requirements_students", report_id)
    nuclei = _count(conn, "nucleus_courses", report_id)
    thesis = _count(conn, "thesis_projects", report_id)
    schedules = _executed_schedule_count(conn, report_id)
    careers = _count(conn, "careers", report_id)

    students = 0
    if _table_exists(conn, "students") and _table_exists(conn, "careers"):
        students = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM students s
                JOIN careers c ON c.id=s.career_id
                WHERE c.report_id=?
                """,
                (report_id,),
            ).fetchone()[0]
        )

    # La población pesa más que los metadatos; los demás módulos desempatan.
    # Las filas automáticas del cronograma ya no pueden hacer ganar un PVC vacío.
    return (
        requirements * 1000
        + students * 500
        + nuclei * 100
        + thesis * 100
        + schedules * 20
        + careers
    )


def _counts_for_report(conn: Any, report_id: int) -> tuple[int, int]:
    requirements = _count(conn, "requirements_students", report_id)
    if requirements:
        careers = int(
            conn.execute(
                """
                SELECT COUNT(DISTINCT NULLIF(TRIM(career_name), ''))
                FROM requirements_students WHERE report_id=?
                """,
                (report_id,),
            ).fetchone()[0]
        )
        return careers, requirements

    careers = _count(conn, "careers", report_id)
    students = 0
    if _table_exists(conn, "students") and _table_exists(conn, "careers"):
        students = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM students s
                JOIN careers c ON c.id=s.career_id
                WHERE c.report_id=?
                """,
                (report_id,),
            ).fetchone()[0]
        )
    return careers, students


def _visible_reports() -> list[dict[str, Any]]:
    """Oculta duplicados PVC sin esconder por accidente el informe con datos."""
    period_policy.ensure_schema()
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM reports ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        )
        normal: list[dict[str, Any]] = []
        pvc_groups: dict[str, list[dict[str, Any]]] = {}

        for report in rows:
            kind = clean_cell(report.get("report_type")) or period_policy.classify_period(
                report.get("period")
            )
            report["report_type"] = kind
            if kind != "pvc":
                normal.append(report)
                continue
            key = (
                clean_cell(report.get("firebase_period_id"))
                or period_policy.canonical_period_id(report.get("period"))
                or period_policy._fold(report.get("period"))
            )
            pvc_groups.setdefault(key, []).append(report)

        selected: list[dict[str, Any]] = list(normal)
        for group in pvc_groups.values():
            best = max(
                group,
                key=lambda item: (
                    _report_score(conn, int(item["id"])),
                    clean_cell(item.get("updated_at")),
                    int(item["id"]),
                ),
            )
            selected.append(best)

        for report in selected:
            careers, students = _counts_for_report(conn, int(report["id"]))
            report["career_count"] = careers
            report["student_count"] = students

    selected.sort(
        key=lambda item: (clean_cell(item.get("updated_at")), int(item.get("id") or 0)),
        reverse=True,
    )
    return selected


def _best_pvc_report(period_id: str, label: str) -> int | None:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM reports
            WHERE firebase_period_id=? OR period=?
            """,
            (period_id, label),
        ).fetchall()
        candidates = [
            row
            for row in rows
            if (
                clean_cell(row["report_type"]) == "pvc"
                or period_policy.classify_period(row["period"]) == "pvc"
            )
        ]
        if not candidates:
            return None
        best = max(
            candidates,
            key=lambda row: (
                _report_score(conn, int(row["id"])),
                clean_cell(row["updated_at"]),
                int(row["id"]),
            ),
        )
        return int(best["id"])


def _explicit_study_modality(enrollment: dict[str, Any]) -> str:
    for key in (
        "modalidadEstudio",
        "modalidadAcademica",
        "modalidadCarrera",
        "modalidadOferta",
        "modalidad",
    ):
        value = clean_cell(enrollment.get(key))
        folded = period_policy._fold(value)
        if any(token in folded for token in ("ONLINE", "EN LINEA", "VIRTUAL")):
            return value
        if any(token in folded for token in ("PRESENCIAL", "PRESENTIAL")):
            return value
    return ""


def install() -> None:
    if getattr(firebase_sync, "_integrity_runtime_installed", False):
        return

    # `notas` forma parte del esquema oficial existente. Informtit puede leerla
    # cuando se necesite, pero queda expresamente fuera de cualquier escritura.
    firebase_sync.READ_ONLY_COLLECTIONS.add("notas")
    firebase_sync.ALL_ALLOWED_COLLECTIONS.add("notas")

    # Reemplaza la deduplicación antigua: un hermano PVC vacío nunca debe ocultar
    # el informe histórico que sí contiene estudiantes o módulos cargados.
    period_policy.visible_reports = _visible_reports

    original_ensure_reports = firebase_sync._ensure_reports
    # El serializador _local_nuclei pertenecía al flujo legado de restauración.
    # Si ya fue retirado, conservamos la capa de integridad sin reintroducirlo.
    original_local_nuclei = getattr(firebase_sync, "_local_nuclei", None)
    original_make_requirement = firebase_sync._make_requirement_record
    original_list_periods = firebase_sync.list_periods

    def ensure_reports(
        period_id: str,
        period: dict[str, Any],
    ) -> tuple[str, str, dict[str, int]]:
        kind, label, report_ids = original_ensure_reports(period_id, period)
        if kind != "pvc":
            return kind, label, report_ids

        best_id = _best_pvc_report(period_id, label)
        if best_id is None:
            return kind, label, report_ids

        now = utcnow()
        with connection() as conn:
            conn.execute(
                """
                UPDATE reports SET period=?, modality='presencial', report_type='pvc',
                    firebase_period_id=?, firebase_synced_at=?, updated_at=?
                WHERE id=?
                """,
                (label, period_id, now, now, best_id),
            )
        return kind, label, {"pvc": best_id}

    def make_requirement_record(
        cedula: str,
        student: dict[str, Any],
        enrollment: dict[str, Any],
        requirement: dict[str, Any],
        career_catalog: dict[str, dict[str, Any]],
        kind: str,
    ) -> dict[str, Any]:
        row = original_make_requirement(
            cedula,
            student,
            enrollment,
            requirement,
            career_catalog,
            kind,
        )
        if kind == "normal":
            explicit = _explicit_study_modality(enrollment)
            if explicit:
                row["modality"] = firebase_sync._modality(
                    explicit,
                    row.get("career_name", ""),
                    row.get("career_code", ""),
                )
        return row

    def list_periods() -> list[dict[str, Any]]:
        # Un periodo marcado explícitamente como inactivo no debe aparecer en el
        # selector de sincronización; los registros sin ese campo se conservan.
        return [
            item
            for item in original_list_periods()
            if item.get("activo") is not False
        ]

    firebase_sync._ensure_reports = ensure_reports
    if original_local_nuclei is not None:
        def local_nuclei(
            report_id: int,
            period_id: str,
            group: str,
        ) -> list[tuple[str, dict[str, Any]]]:
            documents = original_local_nuclei(report_id, period_id, group)
            output: list[tuple[str, dict[str, Any]]] = []
            prefix = f"{period_id}__"
            group_key = clean_cell(group).upper() or "PRESENCIAL"
            for document_id, data in documents:
                remainder = (
                    document_id[len(prefix) :]
                    if document_id.startswith(prefix)
                    else document_id
                )
                if not remainder.startswith(f"{group_key}__"):
                    document_id = f"{period_id}__{group_key}__{remainder}"
                output.append((document_id, data))
            return output

        firebase_sync._local_nuclei = local_nuclei
    firebase_sync._make_requirement_record = make_requirement_record
    firebase_sync.list_periods = list_periods
    firebase_sync._integrity_runtime_installed = True
