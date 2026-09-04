from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import quote

import completion_routes
import completion_service
import firebase_sync_runtime as firebase_sync
import process_routes
import process_service
from db import connection, utcnow
from import_service import clean_cell


_INSTALLED = False
_BASE_SEED: Callable[..., None] | None = None
_BASE_GET_EXTENDED: Callable[[int], dict[str, Any]] | None = None
_BASE_REPLACE_EXTENDED: Callable[[int, str, list[dict[str, Any]]], dict[str, Any]] | None = None

MONTHS = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

KNOWN_COMPLEXIVE: dict[str, list[tuple[str, str, str, str]]] = {
    "2025-10__2026-03": [
        ("", "Núcleo 1", "30/03/2026", "02/04/2026"),
        ("", "Núcleo 2", "06/04/2026", "09/04/2026"),
        ("", "Núcleo 3", "10/04/2026", "14/04/2026"),
        ("", "Núcleo 4", "15/04/2026", "18/04/2026"),
        ("", "Examen Complexivo", "20/04/2026", "24/04/2026"),
        ("", "Supletorio", "04/05/2026", "04/05/2026"),
    ],
    "2026-04__2026-09": [
        ("", "Fin de clases", "25/09/2026", "26/09/2026"),
        ("", "Semana Requisitos", "28/09/2026", "02/10/2026"),
        ("", "Núcleo 1", "05/10/2026", "08/10/2026"),
        ("", "Núcleo 2", "12/10/2026", "15/10/2026"),
        ("", "Núcleo 3", "16/10/2026", "20/10/2026"),
        ("", "Núcleo 4", "21/10/2026", "24/10/2026"),
        ("", "Notas de núcleos", "26/10/2026", "27/10/2026"),
        ("", "Examen Complexivo", "28/10/2026", "31/10/2026"),
        ("", "Supletorio", "09/11/2026", "11/11/2026"),
    ],
}


def _fold(value: Any) -> str:
    text = clean_cell(value).upper()
    return (
        text.replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
        .replace("Ü", "U")
        .replace("Ñ", "N")
    )


def canonical_period_id(value: Any) -> str:
    text = clean_cell(value)
    if re.fullmatch(r"\d{4}-\d{2}__\d{4}-\d{2}", text):
        return text

    normalized = _fold(text).replace("–", "-").replace("—", "-")
    names = "|".join(sorted(MONTHS, key=len, reverse=True))
    match = re.search(
        rf"\b({names})\b\s+(\d{{4}}).*?\b({names})\b\s+(\d{{4}})",
        normalized,
    )
    if not match:
        return ""
    return (
        f"{match.group(2)}-{MONTHS[match.group(1)]:02d}__"
        f"{match.group(4)}-{MONTHS[match.group(3)]:02d}"
    )


def _report_context(report_id: int) -> dict[str, str]:
    with connection() as conn:
        columns = _columns(conn, "reports")
        fields = ["period"]
        if "firebase_period_id" in columns:
            fields.append("firebase_period_id")
        row = conn.execute(
            f"SELECT {', '.join(fields)} FROM reports WHERE id=?",
            (int(report_id),),
        ).fetchone()
    if not row:
        return {"period": "", "period_id": ""}
    period = clean_cell(row["period"])
    firebase_period = clean_cell(row["firebase_period_id"]) if "firebase_period_id" in row.keys() else ""
    return {
        "period": period,
        "period_id": canonical_period_id(firebase_period) or canonical_period_id(period),
    }


def _table_exists(conn: Any, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _matches_defaults(rows: list[Any], defaults: list[tuple[str, str, str, str]]) -> bool:
    current = [
        (
            str(row["phase"] or ""),
            str(row["activity"] or ""),
            str(row["start_date"] or ""),
            str(row["end_date"] or ""),
        )
        for row in rows
    ]
    return current == list(defaults)


def _has_execution(rows: list[Any], columns: set[str]) -> bool:
    execution_fields = {
        "executed_date",
        "execution_status",
        "compliance_percentage",
        "evidence",
        "observation",
    }
    if not execution_fields.issubset(columns):
        return False
    return any(
        str(row["executed_date"] or "").strip()
        or str(row["execution_status"] or "").strip()
        or row["compliance_percentage"] is not None
        or str(row["evidence"] or "").strip()
        or str(row["observation"] or "").strip()
        for row in rows
    )


def cleanup_untouched_defaults() -> int:
    """Quita semillas históricas equivocadas, pero conserva el período al que sí pertenecen."""
    deleted = 0
    with connection() as conn:
        if not _table_exists(conn, "schedule_items"):
            return 0
        columns = _columns(conn, "schedule_items")
        select_columns = ["phase", "activity", "start_date", "end_date"]
        for optional in (
            "executed_date",
            "execution_status",
            "compliance_percentage",
            "evidence",
            "observation",
        ):
            if optional in columns:
                select_columns.append(optional)

        report_rows = conn.execute("SELECT id, period FROM reports ORDER BY id").fetchall()
        defaults_by_type = {
            "complexive": process_service.COMPLEXIVE_DEFAULTS,
            "thesis": process_service.THESIS_DEFAULTS,
        }
        for report in report_rows:
            report_id = int(report["id"])
            period_id = canonical_period_id(report["period"])
            for schedule_type, defaults in defaults_by_type.items():
                rows = conn.execute(
                    f"""
                    SELECT {', '.join(select_columns)} FROM schedule_items
                    WHERE report_id=? AND schedule_type=?
                    ORDER BY sort_order, id
                    """,
                    (report_id, schedule_type),
                ).fetchall()
                if not rows or not _matches_defaults(rows, defaults) or _has_execution(rows, columns):
                    continue

                # El antiguo COMPLEXIVE_DEFAULTS es exactamente el cronograma
                # oficial de Octubre 2025 a Marzo 2026, por lo que allí sí se conserva.
                if schedule_type == "complexive" and period_id == "2025-10__2026-03":
                    continue

                cursor = conn.execute(
                    "DELETE FROM schedule_items WHERE report_id=? AND schedule_type=?",
                    (report_id, schedule_type),
                )
                deleted += int(cursor.rowcount or 0)
                if _table_exists(conn, "content_presence"):
                    conn.execute(
                        """
                        INSERT INTO content_presence
                        (report_id, content_key, included, updated_at)
                        VALUES (?, ?, 0, ?)
                        ON CONFLICT(report_id, content_key) DO UPDATE SET
                            included=0, updated_at=excluded.updated_at
                        """,
                        (report_id, f"schedule_{schedule_type}", utcnow()),
                    )
    return deleted


def seed_schedules_without_legacy_defaults(
    conn: Any,
    report_id: int,
    force: bool = False,
) -> None:
    """No aplica fechas globales: la semilla se decide por el período del informe."""
    return


def _template_entries(period_id: str) -> list[dict[str, Any]]:
    return [
        {
            "phase": phase,
            "activity": activity,
            "start_date": start,
            "end_date": end,
            "executed_date": "",
            "execution_status": "",
            "compliance_percentage": None,
            "evidence": "",
            "observation": "",
        }
        for phase, activity, start, end in KNOWN_COMPLEXIVE.get(period_id, [])
    ]


def _remote_document(period_id: str) -> dict[str, Any] | None:
    if not period_id:
        return None
    payload = firebase_sync._request(
        "GET",
        f"/documents/cronogramas/{quote(period_id, safe='')}",
        allow_404=True,
    )
    return firebase_sync._decode_document(payload) if payload else None


def _publish_remote(report_id: int, schedules: dict[str, Any] | None = None) -> tuple[bool, str]:
    context = _report_context(report_id)
    period_id = context["period_id"]
    if not period_id:
        return False, "No se pudo reconocer el período para publicar el cronograma."
    if schedules is None:
        if _BASE_GET_EXTENDED is None:
            return False, "El servicio de cronogramas todavía no está inicializado."
        schedules = _BASE_GET_EXTENDED(report_id)

    data = {
        "periodoId": period_id,
        "periodo": context["period"] or period_id,
        "version": 2,
        "complexive": schedules.get("complexive", []),
        "thesis": schedules.get("thesis", []),
        "updatedAt": utcnow(),
        "source": "Informtit",
    }
    fields = {
        str(key): firebase_sync._value_to_firestore(value)
        for key, value in data.items()
    }
    try:
        firebase_sync._request(
            "PATCH",
            f"/documents/cronogramas/{quote(period_id, safe='')}",
            body={"fields": fields},
        )
        return True, ""
    except Exception as exc:  # La base local sigue siendo caché si Firebase no responde.
        return False, clean_cell(exc)


def _restore_remote_type(report_id: int, schedule_type: str, entries: Any) -> bool:
    if _BASE_REPLACE_EXTENDED is None or not isinstance(entries, list) or not entries:
        return False
    try:
        _BASE_REPLACE_EXTENDED(report_id, schedule_type, entries)
        return True
    except Exception:
        return False


def get_schedules_smart(report_id: int) -> dict[str, Any]:
    """Firebase es la fuente compartida; SQLite conserva una copia de trabajo local."""
    if _BASE_GET_EXTENDED is None or _BASE_REPLACE_EXTENDED is None:
        return {"complexive": [], "thesis": []}

    schedules = _BASE_GET_EXTENDED(report_id)
    context = _report_context(report_id)
    period_id = context["period_id"]
    remote: dict[str, Any] | None = None
    remote_error = ""

    if period_id:
        try:
            remote = _remote_document(period_id)
        except Exception as exc:
            remote_error = clean_cell(exc)

    changed = False
    if remote:
        if not schedules.get("complexive"):
            changed = _restore_remote_type(report_id, "complexive", remote.get("complexive") or remote.get("actividades")) or changed
        if not schedules.get("thesis"):
            changed = _restore_remote_type(report_id, "thesis", remote.get("thesis")) or changed
    elif not schedules.get("complexive") and period_id in KNOWN_COMPLEXIVE:
        _BASE_REPLACE_EXTENDED(report_id, "complexive", _template_entries(period_id))
        changed = True

    if changed:
        schedules = _BASE_GET_EXTENDED(report_id)

    # Si el período conocido aún no existe en Firebase, se crea una sola vez
    # usando el mismo documento para Presencial y Online.
    if period_id and remote is None and schedules.get("complexive"):
        saved, warning = _publish_remote(report_id, schedules)
        remote_error = remote_error or warning
    else:
        saved = remote is not None

    schedules["_meta"] = {
        "period_id": period_id,
        "source": "Firebase UTET" if saved else "SQLite / plantilla institucional",
        "firebase_saved": bool(saved),
        "warning": remote_error,
        "intelligent_template": period_id in KNOWN_COMPLEXIVE,
    }
    return schedules


def replace_schedule_smart(
    report_id: int,
    schedule_type: str,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    if _BASE_REPLACE_EXTENDED is None or _BASE_GET_EXTENDED is None:
        raise ValueError("El servicio de cronogramas todavía no está inicializado.")
    result = _BASE_REPLACE_EXTENDED(report_id, schedule_type, entries)
    schedules = _BASE_GET_EXTENDED(report_id)
    saved, warning = _publish_remote(report_id, schedules)
    result["firebase_saved"] = saved
    if warning:
        result["warning"] = (
            "El cronograma quedó guardado localmente, pero Firebase no confirmó la publicación. "
            + warning
        )
    return result


def reset_schedule_smart(report_id: int, schedule_type: str) -> dict[str, Any]:
    if schedule_type not in {"complexive", "thesis"}:
        raise ValueError("Tipo de cronograma no válido.")
    if _BASE_REPLACE_EXTENDED is None or _BASE_GET_EXTENDED is None:
        raise ValueError("El servicio de cronogramas todavía no está inicializado.")

    context = _report_context(report_id)
    if schedule_type == "complexive":
        entries = _template_entries(context["period_id"])
        if not entries:
            raise ValueError(
                "Este período todavía no tiene un cronograma institucional conocido. "
                "Ingrese las actividades manualmente o pegue la tabla oficial."
            )
        result = _BASE_REPLACE_EXTENDED(report_id, schedule_type, entries)
    else:
        with connection() as conn:
            conn.execute(
                "DELETE FROM schedule_items WHERE report_id=? AND schedule_type=?",
                (int(report_id), schedule_type),
            )
        result = {"ok": True, "count": 0}

    saved, warning = _publish_remote(report_id, _BASE_GET_EXTENDED(report_id))
    result["firebase_saved"] = saved
    if warning:
        result["warning"] = warning
    return result


def parse_schedule_text_smart(text: str, schedule_type: str) -> list[dict[str, str]]:
    """Entiende tablas Markdown/Excel pegadas, CSV simple y texto con una o dos fechas."""
    current_phase = ""
    entries: list[dict[str, str]] = []
    date_re = re.compile(r"\b(?:\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})\b")

    for raw_line in str(text or "").splitlines():
        line = clean_cell(raw_line).strip("|")
        if not line or re.fullmatch(r"[-:|\s]+", line):
            continue
        if schedule_type == "thesis" and re.match(r"^Fase\s+\d+", line, re.IGNORECASE):
            if not date_re.search(line):
                current_phase = clean_cell(line.replace("|", " "))
                continue

        dates = date_re.findall(line)
        if not dates:
            continue
        activity = clean_cell(line[: line.find(dates[0])].replace("|", " ").replace(";", " "))
        activity = re.sub(
            r"^(Actividad|Cronograma\s+\d+\s*:?)\s*",
            "",
            activity,
            flags=re.IGNORECASE,
        ).strip(" ,-;")
        if not activity or re.search(r"fecha\s*(inicio|fin)", activity, re.IGNORECASE):
            continue

        start_date = process_service._valid_date(dates[0])
        end_date = process_service._valid_date(dates[1] if len(dates) > 1 else dates[0])
        entries.append(
            {
                "phase": current_phase if schedule_type == "thesis" else "",
                "activity": activity,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    if not entries:
        raise ValueError(
            "No se detectaron actividades. Pegue una tabla con Actividad, Fecha inicio y Fecha fin."
        )
    return entries


def install() -> None:
    global _INSTALLED, _BASE_SEED, _BASE_GET_EXTENDED, _BASE_REPLACE_EXTENDED
    if _INSTALLED:
        return

    _BASE_SEED = process_service.seed_schedules
    _BASE_GET_EXTENDED = completion_routes.get_schedules_extended
    _BASE_REPLACE_EXTENDED = completion_routes.replace_schedule_extended

    cleanup_untouched_defaults()

    # Ninguna fecha se hereda globalmente. La app reconoce el período y usa
    # únicamente su cronograma oficial conocido.
    process_service.seed_schedules = seed_schedules_without_legacy_defaults
    completion_service.seed_schedules = seed_schedules_without_legacy_defaults

    # Parser tolerante a Markdown, CSV/texto y fechas de un solo día.
    process_service.parse_schedule_text = parse_schedule_text_smart
    process_routes.parse_schedule_text = parse_schedule_text_smart

    # Las rutas instaladas después consultan estas referencias globales en tiempo de ejecución.
    completion_routes.get_schedules_extended = get_schedules_smart
    completion_routes.replace_schedule_extended = replace_schedule_smart
    process_service.reset_schedule = reset_schedule_smart
    process_routes.reset_schedule = reset_schedule_smart

    process_service._legacy_schedule_defaults_disabled = True
    process_service._smart_period_schedules_enabled = True
    _INSTALLED = True
