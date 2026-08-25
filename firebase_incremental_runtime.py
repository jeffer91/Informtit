from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

import firebase_sync_runtime as firebase_sync
from db import connection, utcnow
from import_service import clean_cell


_INSTALLED = False
_BASE_WRITE_DOCUMENT: Callable[[str, str, dict[str, Any]], Any] | None = None


def ensure_schema() -> None:
    with connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS firebase_sync_hashes (
                project_id TEXT NOT NULL,
                collection_name TEXT NOT NULL,
                document_id TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                synced_at TEXT NOT NULL,
                PRIMARY KEY(project_id, collection_name, document_id)
            )
            """
        )


def _stable_payload(data: dict[str, Any]) -> dict[str, Any]:
    # updatedAt es metadato de transporte. Si fuera parte del hash, cada clic en
    # Sincronizar convertiría un documento idéntico en un cambio artificial.
    return {
        key: value
        for key, value in data.items()
        if key != "updatedAt" and not str(key).startswith("_")
    }


def _payload_hash(data: dict[str, Any]) -> str:
    encoded = json.dumps(
        _stable_payload(data),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _known_hash(collection: str, document_id: str) -> str:
    ensure_schema()
    with connection() as conn:
        row = conn.execute(
            """
            SELECT payload_hash FROM firebase_sync_hashes
            WHERE project_id=? AND collection_name=? AND document_id=?
            """,
            (firebase_sync.PROJECT_ID, collection, document_id),
        ).fetchone()
    return str(row[0]) if row else ""


def _remember_hash(collection: str, document_id: str, payload_hash: str) -> None:
    ensure_schema()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO firebase_sync_hashes
            (project_id, collection_name, document_id, payload_hash, synced_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id, collection_name, document_id) DO UPDATE SET
                payload_hash=excluded.payload_hash,
                synced_at=excluded.synced_at
            """,
            (
                firebase_sync.PROJECT_ID,
                collection,
                document_id,
                payload_hash,
                utcnow(),
            ),
        )


def write_document_incremental(
    collection: str,
    document_id: str,
    data: dict[str, Any],
) -> bool:
    if _BASE_WRITE_DOCUMENT is None:
        raise RuntimeError("Sincronización incremental no configurada.")

    current_hash = _payload_hash(data)
    if _known_hash(collection, document_id) == current_hash:
        return False

    _BASE_WRITE_DOCUMENT(collection, document_id, data)
    _remember_hash(collection, document_id, current_hash)
    return True


def push_new_collections_incremental(
    period_id: str,
    kind: str,
    report_ids: dict[str, int],
) -> tuple[dict[str, int], list[str]]:
    written = {name: 0 for name in firebase_sync.WRITABLE_COLLECTIONS}
    warnings: list[str] = []

    for key, report_id in report_ids.items():
        modality = "presencial" if key in {"pvc", "presencial"} else "en_linea"
        group = firebase_sync._group_label(kind, modality)
        items = {
            "nucleos": firebase_sync._local_nuclei(report_id, period_id, group),
            "complexivo": firebase_sync._local_complexive(report_id, period_id, group),
            "titulacion": firebase_sync._local_thesis(report_id, period_id, group),
        }
        schedule = firebase_sync._local_schedule(report_id, period_id, group)
        items["cronogramas"] = [schedule] if schedule else []

        for collection, documents in items.items():
            for doc_id, data in documents:
                try:
                    changed = write_document_incremental(collection, doc_id, data)
                    if changed:
                        written[collection] += 1
                except Exception as exc:
                    message = f"{collection}: {clean_cell(exc)}"
                    if message not in warnings:
                        warnings.append(message)
                    break

    return written, warnings


def install() -> None:
    global _INSTALLED, _BASE_WRITE_DOCUMENT
    if _INSTALLED:
        return

    ensure_schema()
    _BASE_WRITE_DOCUMENT = firebase_sync.write_document
    firebase_sync.write_document = write_document_incremental
    firebase_sync._push_new_collections = push_new_collections_incremental
    firebase_sync._incremental_sync_installed = True
    _INSTALLED = True
