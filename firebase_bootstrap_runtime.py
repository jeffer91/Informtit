from __future__ import annotations

import threading
from typing import Any

import app as core
import firebase_sync_runtime as firebase
import period_policy_runtime as period_policy
import period_unified_runtime as unified
from db import connection, create_default_sections, utcnow
from import_service import clean_cell, settings_for_report


_LOCK = threading.Lock()
_ATTEMPTED = False
_LAST_RESULT: dict[str, Any] = {
    "ok": True,
    "attempted": False,
    "source": "Firebase",
    "periods": 0,
    "created": 0,
    "updated": 0,
    "warnings": [],
}


def _catalog_name(kind: str, label: str) -> str:
    if kind == "pvc":
        return f"Informe PVC - {label}" if label else "Informe PVC"
    return period_policy.automatic_report_name(label)


def _ensure_catalog_period(period: dict[str, Any]) -> dict[str, Any]:
    """Crea únicamente el contenedor local del período oficial.

    Esta operación no toca Requisitos, notas, cronogramas ni evidencias. Tampoco
    cambia firebase_synced_at: ese campo continúa representando una sincronización
    académica completa ejecutada por el usuario.
    """

    period_policy.ensure_schema()
    period_id = clean_cell(period.get("periodoId") or period.get("_id"))
    if not period_id:
        raise ValueError("Firebase devolvió un período sin identificador.")

    kind = period_policy.classify_period(period_id)
    label = clean_cell(period.get("label")) or period_policy.period_label(period_id)
    wanted = ["presencial"] if kind == "pvc" else ["presencial", "en_linea"]
    settings = settings_for_report()
    now = utcnow()
    created = 0
    updated = 0
    report_ids: dict[str, int] = {}

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM reports
            WHERE firebase_period_id=? OR period=?
            ORDER BY updated_at DESC, id DESC
            """,
            (period_id, label),
        ).fetchall()

        for modality in wanted:
            local_modality = "presencial" if kind == "pvc" else modality
            row = next(
                (
                    item
                    for item in rows
                    if (
                        kind == "pvc"
                        and (
                            clean_cell(item["report_type"]) == "pvc"
                            or period_policy.classify_period(item["period"]) == "pvc"
                        )
                    )
                    or (
                        kind == "normal"
                        and clean_cell(item["modality"]) == modality
                        and clean_cell(item["report_type"]) in {"", "normal"}
                    )
                ),
                None,
            )

            if row:
                report_id = int(row["id"])
                current = (
                    clean_cell(row["period"]),
                    clean_cell(row["modality"]),
                    clean_cell(row["report_type"]),
                    clean_cell(row["firebase_period_id"]),
                )
                expected = (label, local_modality, kind, period_id)
                if current != expected:
                    conn.execute(
                        """
                        UPDATE reports
                        SET period=?, modality=?, report_type=?, firebase_period_id=?
                        WHERE id=?
                        """,
                        (*expected, report_id),
                    )
                    updated += 1
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO reports
                    (name, period, modality, code, version, elaboration_date,
                     prepared_by, prepared_role, reviewed_by, reviewed_role,
                     approved_by, approved_role, status, created_at, updated_at,
                     report_type, firebase_period_id, firebase_synced_at)
                    VALUES (?, ?, ?, '', '1.0', '', ?, ?, ?, ?, ?, ?,
                            'borrador', ?, ?, ?, ?, '')
                    """,
                    (
                        _catalog_name(kind, label),
                        label,
                        local_modality,
                        settings["prepared_by"],
                        settings["prepared_role"],
                        settings["reviewed_by"],
                        settings["reviewed_role"],
                        settings["approved_by"],
                        settings["approved_role"],
                        now,
                        now,
                        kind,
                        period_id,
                    ),
                )
                report_id = int(cursor.lastrowid)
                create_default_sections(conn, report_id)
                created += 1
                rows = conn.execute(
                    "SELECT * FROM reports WHERE firebase_period_id=? ORDER BY id",
                    (period_id,),
                ).fetchall()

            report_ids["pvc" if kind == "pvc" else modality] = report_id

    return {
        "periodoId": period_id,
        "period": label,
        "report_type": kind,
        "report_ids": report_ids,
        "created": created,
        "updated": updated,
    }


def bootstrap_catalog() -> dict[str, Any]:
    """Replica el catálogo de períodos Firebase sin reemplazar trabajo local."""

    periods = firebase.list_periods()
    details: list[dict[str, Any]] = []
    warnings: list[str] = []
    created = 0
    updated = 0

    for period in periods:
        try:
            result = _ensure_catalog_period(period)
            details.append(result)
            created += int(result.get("created") or 0)
            updated += int(result.get("updated") or 0)
        except Exception as exc:
            period_id = clean_cell(period.get("periodoId") or period.get("_id")) or "sin-id"
            warnings.append(f"{period_id}: {exc}")

    reconciliation: dict[str, Any] = {"ok": True, "skipped": True}
    if created or updated:
        reconciliation = unified.reconcile_projects()

    return {
        "ok": True,
        "attempted": True,
        "source": "Firebase",
        "periods": len(periods),
        "created": created,
        "updated": updated,
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
            # Informtit debe seguir abriendo sin Internet. En ese caso conserva
            # íntegramente SQLite y el botón Sincronizar Firebase queda disponible.
            _LAST_RESULT = {
                "ok": False,
                "attempted": True,
                "source": "Firebase",
                "periods": 0,
                "created": 0,
                "updated": 0,
                "warnings": [str(exc)],
                "fallback": "local",
                "preserved_local_data": True,
            }
        return dict(_LAST_RESULT)


def install() -> None:
    """Carga el catálogo Firebase antes del primer GET /api/reports."""

    if getattr(core.InformtitHandler, "_firebase_bootstrap_installed", False):
        return

    previous_get = core.InformtitHandler._handle_api_get

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/reports":
            result = _bootstrap_once()
            if not result.get("ok"):
                print(
                    "[Informtit] No se pudo restaurar el catálogo Firebase; "
                    "se mantiene el respaldo local: "
                    + "; ".join(result.get("warnings") or []),
                    flush=True,
                )
        if path == "/api/firebase/bootstrap-status":
            self._send_json(dict(_LAST_RESULT))
            return
        previous_get(self, path, query)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._firebase_bootstrap_installed = True
