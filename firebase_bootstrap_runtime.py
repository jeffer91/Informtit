from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

import app as core
import firebase_sync_runtime as firebase
import period_policy_runtime as period_policy
import period_unified_runtime as unified
from db import connection
from import_service import clean_cell


REPORTS_COLLECTION = "informesTitulacion"
_LOCK = threading.Lock()
_ATTEMPTED = False
_LAST_RESULT: dict[str, Any] = {
    "ok": True,
    "attempted": False,
    "source": "Firebase",
    "periods": 0,
    "reports": 0,
    "students": 0,
    "warnings": [],
}


def _list_remote_reports() -> list[dict[str, Any]]:
    """Lee la misma colección de metadatos que usa GitHub Pages."""
    rows: list[dict[str, Any]] = []
    token = ""
    while True:
        params: dict[str, Any] = {"pageSize": 1000}
        if token:
            params["pageToken"] = token
        payload = firebase._request(
            "GET",
            f"/documents/{REPORTS_COLLECTION}",
            params=params,
            allow_404=True,
        ) or {}
        rows.extend(
            firebase._decode_document(document)
            for document in (payload.get("documents") or [])
        )
        token = clean_cell(payload.get("nextPageToken"))
        if not token:
            break
    return [row for row in rows if row.get("active") is not False]


def _remote_period_id(row: dict[str, Any]) -> str:
    period_id = clean_cell(row.get("periodId") or row.get("firebase_period_id"))
    if period_id:
        return period_id
    period_key = clean_cell(row.get("periodKey"))
    if ":" in period_key:
        candidate = period_key.split(":", 1)[1]
        if period_policy.canonical_period_id(candidate):
            return period_policy.canonical_period_id(candidate)
    return period_policy.canonical_period_id(row.get("period"))


def _remote_kind(row: dict[str, Any], fallback: str = "normal") -> str:
    value = clean_cell(row.get("reportType") or row.get("report_type")).lower()
    return value if value in {"normal", "pvc"} else fallback


def _dedupe_remote_reports(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        period_id = _remote_period_id(row)
        if not period_id:
            continue
        kind = _remote_kind(row, period_policy.classify_period(period_id))
        key = f"{kind}:{period_id}"
        current = deduped.get(key)
        if current is None or clean_cell(row.get("_updateTime")) >= clean_cell(current.get("_updateTime")):
            deduped[key] = row
    return list(deduped.values())


def _table_exists(conn: Any, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def _report_has_real_data(conn: Any, report_id: int) -> bool:
    row = conn.execute(
        "SELECT source_import_id, firebase_synced_at FROM reports WHERE id=?",
        (report_id,),
    ).fetchone()
    if not row:
        return False
    if row["source_import_id"] or clean_cell(row["firebase_synced_at"]):
        return True

    checks = (
        ("requirements_students", "report_id"),
        ("careers", "report_id"),
        ("nucleus_course_instances", "report_id"),
        ("thesis_projects", "report_id"),
        ("schedule_items", "report_id"),
        ("images", "report_id"),
    )
    for table, column in checks:
        if not _table_exists(conn, table):
            continue
        if conn.execute(
            f"SELECT 1 FROM {table} WHERE {column}=? LIMIT 1",
            (report_id,),
        ).fetchone():
            return True
    return False


def _prune_legacy_catalog_shells(remote_period_ids: set[str]) -> int:
    """Elimina solo contenedores vacíos creados por el bootstrap anterior.

    Nunca elimina un período que tenga una sincronización real, una importación o
    contenido académico/local. Así se corrige el exceso de PVC sin arriesgar datos.
    """
    groups: dict[int, list[int]] = defaultdict(list)
    direct: list[int] = []
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, firebase_period_id, period_project_id
            FROM reports
            WHERE COALESCE(firebase_period_id, '') <> ''
            """
        ).fetchall()
        for row in rows:
            period_id = clean_cell(row["firebase_period_id"])
            if not period_id or period_id in remote_period_ids:
                continue
            report_id = int(row["id"])
            if _report_has_real_data(conn, report_id):
                continue
            project_id = int(row["period_project_id"] or 0)
            if project_id:
                groups[project_id].append(report_id)
            else:
                direct.append(report_id)

    removed = 0
    for project_id, report_ids in groups.items():
        with connection() as conn:
            all_members = [
                int(row[0])
                for row in conn.execute(
                    "SELECT id FROM reports WHERE period_project_id=?",
                    (project_id,),
                ).fetchall()
            ]
            if not all_members or any(_report_has_real_data(conn, rid) for rid in all_members):
                continue
        try:
            unified._delete_project(report_ids[0])
            removed += 1
        except Exception:
            continue

    if direct:
        with connection() as conn:
            for report_id in direct:
                if not _report_has_real_data(conn, report_id):
                    conn.execute("DELETE FROM reports WHERE id=?", (report_id,))
                    removed += 1
    return removed


def _apply_remote_metadata(
    row: dict[str, Any],
    sync_result: dict[str, Any],
) -> None:
    report_ids = dict(sync_result.get("report_ids") or {})
    fallback_kind = clean_cell(sync_result.get("report_type")) or "normal"
    kind = _remote_kind(row, fallback_kind)
    period_id = _remote_period_id(row)
    period = clean_cell(row.get("period") or sync_result.get("period"))
    name = clean_cell(row.get("name")) or (
        f"Informe PVC - {period}" if kind == "pvc" else period_policy.automatic_report_name(period)
    )
    version = clean_cell(row.get("version")) or "1.0"
    elaboration_date = clean_cell(row.get("elaborationDate") or row.get("elaboration_date"))
    code_presencial = clean_cell(row.get("codePresencial") or row.get("code_presencial") or row.get("code"))
    code_online = clean_cell(row.get("codeOnline") or row.get("code_online"))

    with connection() as conn:
        for modality, report_id in report_ids.items():
            code = code_presencial
            if modality == "en_linea" and code_online:
                code = code_online
            conn.execute(
                """
                UPDATE reports SET
                    name=?, period=?, code=?, version=?, elaboration_date=?,
                    report_type=?, firebase_period_id=?
                WHERE id=?
                """,
                (
                    name,
                    period,
                    code,
                    version,
                    elaboration_date,
                    kind,
                    period_id,
                    int(report_id),
                ),
            )


def bootstrap_catalog() -> dict[str, Any]:
    """Restaura exactamente los informes publicados y sus fuentes oficiales."""
    periods = firebase.list_periods()
    remote_reports = _dedupe_remote_reports(_list_remote_reports())
    remote_period_ids = {_remote_period_id(row) for row in remote_reports if _remote_period_id(row)}

    # Corrige los contenedores vacíos que la versión anterior creó a partir de
    # todos los documentos de periodos, aunque no existiera un informe publicado.
    removed_shells = _prune_legacy_catalog_shells(remote_period_ids)

    details: list[dict[str, Any]] = []
    warnings: list[str] = []
    students = 0
    synced = 0

    for row in remote_reports:
        period_id = _remote_period_id(row)
        if not period_id:
            warnings.append("Un informe de Firebase no tiene período reconocible.")
            continue
        try:
            sync_result = firebase.sync_period(period_id)
            _apply_remote_metadata(row, sync_result)
            requirements = dict(sync_result.get("requirements") or {})
            students += int(requirements.get("students") or 0)
            synced += 1
            details.append(
                {
                    "periodoId": period_id,
                    "period": sync_result.get("period"),
                    "report_type": _remote_kind(row, clean_cell(sync_result.get("report_type")) or "normal"),
                    "report_ids": sync_result.get("report_ids") or {},
                    "students": int(requirements.get("students") or 0),
                    "presencial": int(requirements.get("presencial") or 0),
                    "en_linea": int(requirements.get("en_linea") or 0),
                    "code": clean_cell(row.get("codePresencial") or row.get("code")),
                }
            )
        except Exception as exc:
            warnings.append(f"{period_id}: {exc}")

    reconciliation = unified.reconcile_projects()
    return {
        "ok": True,
        "attempted": True,
        "source": "Firebase",
        "periods": len(periods),
        "reports": len(remote_reports),
        "synced": synced,
        "students": students,
        "removed_legacy_shells": removed_shells,
        "details": details,
        "warnings": warnings,
        "reconciliation": reconciliation,
        "preserved_local_data": True,
    }


def _bootstrap_once() -> dict[str, Any]:
    global _ATTEMPTED, _LAST_RESULT

    if _ATTEMPTED:
        return dict(_LAST_RESULT)

    with _LOCK:
        if _ATTEMPTED:
            return dict(_LAST_RESULT)
        _ATTEMPTED = True
        try:
            _LAST_RESULT = bootstrap_catalog()
        except Exception as exc:
            _LAST_RESULT = {
                "ok": False,
                "attempted": True,
                "source": "Firebase",
                "periods": 0,
                "reports": 0,
                "students": 0,
                "warnings": [str(exc)],
                "fallback": "local",
                "preserved_local_data": True,
            }
        return dict(_LAST_RESULT)


def install() -> None:
    """Restaura Firebase antes del primer GET /api/reports del escritorio."""
    if getattr(core.InformtitHandler, "_firebase_bootstrap_installed", False):
        return

    previous_get = core.InformtitHandler._handle_api_get

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/reports":
            result = _bootstrap_once()
            if not result.get("ok"):
                print(
                    "[Informtit] Firebase no pudo restaurarse; se conserva SQLite local: "
                    + "; ".join(result.get("warnings") or []),
                    flush=True,
                )
        if path == "/api/firebase/bootstrap-status":
            self._send_json(dict(_LAST_RESULT))
            return
        previous_get(self, path, query)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._firebase_bootstrap_installed = True
