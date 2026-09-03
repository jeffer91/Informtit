from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import app as core
import db
import import_service
import report_service
import dual_modality_runtime
import institutional_export
import requirements_store
from db import connection, create_default_sections, rows_to_dicts, utcnow
from import_service import _load_preview, clean_cell, settings_for_report


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

NORMAL_PERIODS = {(4, 9), (10, 3)}

REPORT_NAME_PREFIX = "Informe Final del Proceso de Titulación"
REPORT_CODE_PREFIX = "UTET-INF-01-PRO-95-"


def automatic_report_name(period: Any) -> str:
    value = clean_cell(period)
    return f"{REPORT_NAME_PREFIX} - {value}" if value else REPORT_NAME_PREFIX


def institutional_code_for_month(value: Any) -> str:
    month = clean_cell(value)
    if not month:
        return ""
    if not re.fullmatch(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])", month):
        raise ValueError("El mes y año del código deben tener formato AAAA-MM.")
    return f"{REPORT_CODE_PREFIX}{month}"


def configure_storage() -> None:
    """Usa la carpeta persistente que Electron entrega a Python."""
    storage = clean_cell(os.environ.get("INFORMTIT_STORAGE_DIR"))
    if not storage:
        return
    path = Path(storage).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)

    db.DATA_DIR = path
    db.DB_PATH = path / "informtit.db"
    import_service.DATA_DIR = path

    uploads = path / "uploads"
    exports = path / "exports"
    core.UPLOAD_DIR = uploads
    report_service.UPLOAD_DIR = uploads
    report_service.EXPORT_DIR = exports
    institutional_export.UPLOAD_DIR = uploads
    institutional_export.EXPORT_DIR = exports


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", text).strip().upper()


def period_months(value: Any) -> tuple[int, int] | None:
    text = clean_cell(value)
    canonical = re.search(
        r"(\d{4})-(\d{1,2})\s*__\s*(\d{4})-(\d{1,2})",
        text,
    )
    if canonical:
        return int(canonical.group(2)), int(canonical.group(4))

    folded = _fold(text)
    names = "|".join(sorted(MONTHS, key=len, reverse=True))
    match = re.search(
        rf"\b({names})\b\s+\d{{4}}\s*(?:-|–|—|A|AL)\s*\b({names})\b\s+\d{{4}}",
        folded,
    )
    if match:
        return MONTHS[match.group(1)], MONTHS[match.group(2)]

    numeric = re.search(
        r"\b(\d{4})[-/](\d{1,2})\b.*?\b(\d{4})[-/](\d{1,2})\b",
        text,
    )
    if numeric:
        return int(numeric.group(2)), int(numeric.group(4))
    return None


def classify_period(value: Any) -> str:
    months = period_months(value)
    return "normal" if months in NORMAL_PERIODS else "pvc"


def canonical_period_id(value: Any) -> str:
    text = clean_cell(value)
    match = re.search(
        r"(\d{4})-(\d{1,2})\s*__\s*(\d{4})-(\d{1,2})",
        text,
    )
    if match:
        return (
            f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"
            f"__{int(match.group(3)):04d}-{int(match.group(4)):02d}"
        )

    folded = _fold(text)
    names = "|".join(sorted(MONTHS, key=len, reverse=True))
    match = re.search(
        rf"\b({names})\b\s+(\d{{4}})\s*(?:-|–|—|A|AL)\s*"
        rf"\b({names})\b\s+(\d{{4}})",
        folded,
    )
    if match:
        return (
            f"{int(match.group(2)):04d}-{MONTHS[match.group(1)]:02d}"
            f"__{int(match.group(4)):04d}-{MONTHS[match.group(3)]:02d}"
        )
    return ""


def period_label(period_id: str, fallback: str = "") -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})__(\d{4})-(\d{2})", clean_cell(period_id))
    if not match:
        return clean_cell(fallback or period_id)
    inverse = {
        1: "Enero",
        2: "Febrero",
        3: "Marzo",
        4: "Abril",
        5: "Mayo",
        6: "Junio",
        7: "Julio",
        8: "Agosto",
        9: "Septiembre",
        10: "Octubre",
        11: "Noviembre",
        12: "Diciembre",
    }
    y1, m1, y2, m2 = map(int, match.groups())
    return f"{inverse[m1]} {y1} - {inverse[m2]} {y2}"


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn: Any, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def ensure_schema() -> None:
    with connection() as conn:
        columns = _columns(conn, "reports")
        additions = {
            "report_type": "TEXT DEFAULT 'normal'",
            "firebase_period_id": "TEXT DEFAULT ''",
            "firebase_synced_at": "TEXT DEFAULT ''",
        }
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE reports ADD COLUMN {name} {definition}")

        rows = conn.execute("SELECT id, period, report_type FROM reports").fetchall()
        for row in rows:
            # El tipo no es una preferencia manual: por contrato institucional,
            # Abril-Septiembre y Octubre-Marzo son regulares; cualquier otro
            # rango es PVC/Artículo Académico. Recalcular evita que bases antiguas
            # con el valor DEFAULT 'normal' clasifiquen mal un período PVC.
            current = clean_cell(row["report_type"]).lower()
            months = period_months(row["period"])
            if months is None:
                # Etiquetas técnicas/antiguas sin rango reconocible no deben
                # convertirse a PVC por accidente.
                expected = current if current in {"normal", "pvc"} else "normal"
            else:
                expected = "normal" if months in NORMAL_PERIODS else "pvc"
            if current != expected:
                conn.execute(
                    "UPDATE reports SET report_type=? WHERE id=?",
                    (expected, int(row["id"])),
                )


def _report_kind(row: Any) -> str:
    try:
        explicit = clean_cell(row["report_type"])
    except (IndexError, KeyError, TypeError):
        explicit = ""
    return explicit if explicit in {"normal", "pvc"} else classify_period(row["period"])


def ensure_normal_pairs() -> dict[str, Any]:
    """Crea pares Presencial/Online solo para los períodos académicos regulares."""
    ensure_schema()
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
            if _report_kind(active) != "normal":
                continue
            active_modality = str(active["modality"] or "presencial")
            other_modality = "en_linea" if active_modality == "presencial" else "presencial"
            period = clean_cell(active["period"])
            counterpart = dual_modality_runtime._counterpart_id(
                conn, active, other_modality, period
            )
            if counterpart is not None:
                continue
            new_id = dual_modality_runtime._upsert_report(
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
            conn.execute(
                "UPDATE reports SET report_type='normal' WHERE id=?",
                (new_id,),
            )
            created.append(new_id)
    return {"ok": True, "created": created, "count": len(created)}


def prepare_dual_policy() -> None:
    """Evita que el runtime antiguo cree un hermano Online para PVC."""
    ensure_schema()
    dual_modality_runtime.ensure_report_pairs = ensure_normal_pairs


def _commit_pvc(
    token: str,
    active_report_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    requirements_store.ensure_requirements_schema()
    ensure_schema()
    parsed = _load_preview(token)
    preview = parsed.get("preview") or {}
    records = list(parsed.get("records") or [])
    if not records:
        raise ValueError("El archivo no contiene estudiantes válidos.")

    with connection() as conn:
        active = conn.execute(
            "SELECT * FROM reports WHERE id=?",
            (active_report_id,),
        ).fetchone()
        if not active:
            raise ValueError("El informe activo no existe.")

        period = clean_cell(
            payload.get("period") or preview.get("period") or active["period"]
        )
        version = clean_cell(payload.get("version") or active["version"] or "1.0")
        elaboration_date = clean_cell(
            payload.get("elaboration_date") or active["elaboration_date"]
        )
        code = clean_cell(
            payload.get("code")
            or payload.get("code_presencial")
            or active["code"]
        )
        now = utcnow()

        cursor = conn.execute(
            """
            INSERT INTO import_history
            (original_name, period, total_students, presencial_students,
             online_students, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (
                clean_cell(preview.get("filename") or "requisitos.xls"),
                period,
                len(records),
                len(records),
                now,
            ),
        )
        import_id = int(cursor.lastrowid)

        conn.execute(
            """
            UPDATE reports SET
                period=?, modality='presencial', code=?, version=?,
                elaboration_date=?, source_import_id=?, report_type='pvc',
                firebase_period_id=COALESCE(NULLIF(firebase_period_id, ''), ?),
                updated_at=?
            WHERE id=?
            """,
            (
                period,
                code,
                version,
                elaboration_date,
                import_id,
                canonical_period_id(period),
                now,
                active_report_id,
            ),
        )
        conn.execute(
            "DELETE FROM requirements_students WHERE report_id=?",
            (active_report_id,),
        )
        for record in records:
            normalized = dict(record)
            normalized["modality"] = "presencial"
            requirements_store._insert_requirement_record(
                conn, active_report_id, normalized, now
            )

    return {
        "ok": True,
        "report_id": active_report_id,
        "report_ids": {"pvc": active_report_id},
        "paired_report_id": None,
        "report_type": "pvc",
        "modality": "pvc",
        "period": period,
        "students": len(records),
        "presencial": len(records),
        "en_linea": 0,
        "filename": clean_cell(preview.get("filename") or "requisitos.xls"),
    }


def _report_counts(conn: Any, report_id: int) -> tuple[int, int]:
    careers = int(
        conn.execute(
            "SELECT COUNT(*) FROM careers WHERE report_id=?",
            (report_id,),
        ).fetchone()[0]
    )
    if _table_exists(conn, "requirements_students"):
        students = int(
            conn.execute(
                "SELECT COUNT(*) FROM requirements_students WHERE report_id=?",
                (report_id,),
            ).fetchone()[0]
        )
        if students:
            return careers, students
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


def visible_reports() -> list[dict[str, Any]]:
    ensure_schema()
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM reports ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        )
        visible: list[dict[str, Any]] = []
        pvc_seen: set[str] = set()
        for report in rows:
            kind = report.get("report_type") or classify_period(report.get("period"))
            report["report_type"] = kind
            if kind == "pvc":
                key = (
                    clean_cell(report.get("firebase_period_id"))
                    or canonical_period_id(report.get("period"))
                    or _fold(report.get("period"))
                )
                if key in pvc_seen:
                    continue
                pvc_seen.add(key)
            careers, students = _report_counts(conn, int(report["id"]))
            report["career_count"] = careers
            report["student_count"] = students
            visible.append(report)
    return visible


def _create_manual_reports(payload: dict[str, Any]) -> dict[str, Any]:
    period = clean_cell(payload.get("period"))
    if not period:
        raise ValueError("El periodo académico es obligatorio.")
    name = automatic_report_name(period)
    explicit_kind = clean_cell(payload.get("report_type")).lower()
    kind = explicit_kind if explicit_kind in {"normal", "pvc"} else classify_period(period)
    requested = clean_cell(payload.get("modality")) or "presencial"
    if requested not in {"presencial", "en_linea"}:
        requested = "presencial"

    modalities = ["presencial"] if kind == "pvc" else ["presencial", "en_linea"]
    settings = settings_for_report()
    now = utcnow()
    ids: dict[str, int] = {}

    with connection() as conn:
        for modality in modalities:
            selected_code_month = clean_cell(payload.get("code_month"))
            code = (
                institutional_code_for_month(selected_code_month)
                if selected_code_month
                else clean_cell(
                    payload.get("code_online")
                    if modality == "en_linea"
                    else payload.get("code_presencial")
                ) or clean_cell(payload.get("code"))
            )
            cursor = conn.execute(
                """
                INSERT INTO reports
                (name, period, modality, code, version, elaboration_date,
                 prepared_by, prepared_role, reviewed_by, reviewed_role,
                 approved_by, approved_role, status, created_at, updated_at,
                 report_type, firebase_period_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'borrador', ?, ?, ?, ?)
                """,
                (
                    name,
                    period,
                    modality,
                    code,
                    clean_cell(payload.get("version") or "1.0"),
                    clean_cell(payload.get("elaboration_date")),
                    clean_cell(payload.get("prepared_by") or settings["prepared_by"]),
                    clean_cell(payload.get("prepared_role") or settings["prepared_role"]),
                    clean_cell(payload.get("reviewed_by") or settings["reviewed_by"]),
                    clean_cell(payload.get("reviewed_role") or settings["reviewed_role"]),
                    clean_cell(payload.get("approved_by") or settings["approved_by"]),
                    clean_cell(payload.get("approved_role") or settings["approved_role"]),
                    now,
                    now,
                    kind,
                    canonical_period_id(period),
                ),
            )
            report_id = int(cursor.lastrowid)
            create_default_sections(conn, report_id)
            ids[modality if kind == "normal" else "pvc"] = report_id

    active_key = requested if kind == "normal" else "pvc"
    return {
        "ok": True,
        "report_id": ids.get(active_key) or next(iter(ids.values())),
        "report_ids": ids,
        "report_type": kind,
    }


def _decorate_report(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not report:
        return report
    report["report_type"] = report.get("report_type") or classify_period(report.get("period"))
    report["display_modality"] = (
        "PVC"
        if report["report_type"] == "pvc"
        else ("Online" if report.get("modality") == "en_linea" else "Presencial")
    )
    return report


def install() -> None:
    ensure_schema()
    if getattr(core.InformtitHandler, "_period_policy_installed", False):
        return

    old_modality = institutional_export.modality

    def export_modality(report: dict[str, Any]) -> str:
        if (report.get("report_type") or classify_period(report.get("period"))) == "pvc":
            return "PVC"
        return old_modality(report)

    institutional_export.modality = export_modality

    previous_get = core.InformtitHandler._handle_api_get
    previous_write = core.InformtitHandler._handle_api_write

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/reports":
            self._send_json({"ok": True, "reports": visible_reports()})
            return

        previous_get(self, path, query)

    def handle_write(
        self: Any,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> None:
        if method == "POST" and path == "/api/reports":
            self._send_json(_create_manual_reports(payload), 201)
            return

        import_match = re.fullmatch(
            r"/api/reports/(\d+)/imports/([A-Za-z0-9_-]+)/commit",
            path,
        )
        if import_match and method == "POST":
            parsed = _load_preview(import_match.group(2))
            preview = parsed.get("preview") or {}
            with connection() as conn:
                active = conn.execute(
                    "SELECT period, report_type FROM reports WHERE id=?",
                    (int(import_match.group(1)),),
                ).fetchone()
            period = clean_cell(
                payload.get("period")
                or preview.get("period")
                or (active["period"] if active else "")
            )
            active_kind = _report_kind(active) if active else classify_period(period)
            if active_kind == "pvc":
                result = _commit_pvc(
                    import_match.group(2),
                    int(import_match.group(1)),
                    payload,
                )
                self._send_json(result, 201)
                return

        update_match = re.fullmatch(r"/api/reports/(\d+)", path)
        if update_match and method == "PUT":
            report_id = int(update_match.group(1))
            with connection() as conn:
                before = conn.execute(
                    "SELECT period, report_type FROM reports WHERE id=?",
                    (report_id,),
                ).fetchone()
            if before and _report_kind(before) == "pvc":
                payload = dict(payload)
                payload["modality"] = "presencial"

        previous_write(self, method, path, payload)

        if update_match and method == "PUT":
            report_id = int(update_match.group(1))
            with connection() as conn:
                row = conn.execute(
                    "SELECT period, report_type FROM reports WHERE id=?",
                    (report_id,),
                ).fetchone()
                if row:
                    kind = _report_kind(row)
                    conn.execute(
                        """
                        UPDATE reports SET report_type=?,
                            firebase_period_id=COALESCE(NULLIF(firebase_period_id, ''), ?)
                        WHERE id=?
                        """,
                        (kind, canonical_period_id(row["period"]), report_id),
                    )

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
    core.InformtitHandler._period_policy_installed = True
