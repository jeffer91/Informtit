from __future__ import annotations

from typing import Any, Callable

import app as core
import institutional_export as institutional
import process_export
import process_routes
from db import connection, utcnow
from process_service import COMPLEXIVE_DEFAULTS, THESIS_DEFAULTS, get_projects


PROVISIONAL_EXPRESSIONS = (
    "deberá completarse",
    "se completará",
    "informtit generará",
    "pendiente de generar",
    "texto provisional",
    "por completar",
    "insertar análisis",
    "la versión final deberá ser revisada",
)


def ensure_optional_schema() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS content_presence (
                report_id INTEGER NOT NULL,
                content_key TEXT NOT NULL,
                included INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(report_id, content_key),
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            );
            """
        )
        report_ids = [
            int(row[0]) for row in conn.execute("SELECT id FROM reports").fetchall()
        ]
        for report_id in report_ids:
            for schedule_type, defaults in (
                ("complexive", COMPLEXIVE_DEFAULTS),
                ("thesis", THESIS_DEFAULTS),
            ):
                key = f"schedule_{schedule_type}"
                exists = conn.execute(
                    "SELECT 1 FROM content_presence WHERE report_id=? AND content_key=?",
                    (report_id, key),
                ).fetchone()
                if exists:
                    continue
                rows = conn.execute(
                    """
                    SELECT phase, activity, start_date, end_date
                    FROM schedule_items
                    WHERE report_id=? AND schedule_type=?
                    ORDER BY sort_order, id
                    """,
                    (report_id, schedule_type),
                ).fetchall()
                current = [tuple(row) for row in rows]
                included = int(bool(current) and current != list(defaults))
                conn.execute(
                    """
                    INSERT INTO content_presence
                    (report_id, content_key, included, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (report_id, key, included, utcnow()),
                )


def set_presence(report_id: int, content_key: str, included: bool) -> None:
    ensure_optional_schema()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO content_presence
            (report_id, content_key, included, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(report_id, content_key) DO UPDATE SET
                included=excluded.included,
                updated_at=excluded.updated_at
            """,
            (report_id, content_key, 1 if included else 0, utcnow()),
        )


def is_present(report_id: int, content_key: str) -> bool:
    ensure_optional_schema()
    with connection() as conn:
        row = conn.execute(
            "SELECT included FROM content_presence WHERE report_id=? AND content_key=?",
            (report_id, content_key),
        ).fetchone()
    return bool(row and row[0])


def _clean_report_loader(original: Callable[[int], dict[str, Any]]) -> Callable[[int], dict[str, Any]]:
    def load(report_id: int) -> dict[str, Any]:
        report = original(report_id)
        cleaned = dict(report)
        cleaned_sections: list[dict[str, Any]] = []
        for section in report.get("sections", []):
            content = str(section.get("content") or "").strip()
            folded = content.casefold()
            if not content:
                continue
            if any(expression in folded for expression in PROVISIONAL_EXPRESSIONS):
                continue
            cleaned_sections.append(section)
        cleaned["sections"] = cleaned_sections
        return cleaned

    return load


def install() -> None:
    """Aplica la regla: lo que no fue cargado no aparece en Word ni PDF."""

    ensure_optional_schema()

    original_replace = process_routes.replace_schedule
    original_reset = process_routes.reset_schedule

    def replace_schedule(report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
        result = original_replace(report_id, schedule_type, entries)
        set_presence(report_id, f"schedule_{schedule_type}", True)
        return result

    def reset_schedule(report_id: int, schedule_type: str) -> dict[str, Any]:
        result = original_reset(report_id, schedule_type)
        set_presence(report_id, f"schedule_{schedule_type}", False)
        return result

    process_routes.replace_schedule = replace_schedule
    process_routes.reset_schedule = reset_schedule

    original_get_schedules = process_export.get_schedules

    def export_schedules(report_id: int) -> dict[str, Any]:
        schedules = original_get_schedules(report_id)
        return {
            "complexive": schedules.get("complexive", [])
            if is_present(report_id, "schedule_complexive")
            else [],
            "thesis": schedules.get("thesis", [])
            if is_present(report_id, "schedule_thesis")
            else [],
        }

    process_export.get_schedules = export_schedules

    original_add_docx_schedule = process_export._add_docx_schedule
    original_pdf_schedule = process_export._pdf_schedule
    original_add_docx_projects = process_export._add_docx_projects
    original_pdf_projects = process_export._pdf_projects

    def add_docx_schedule(document: Any, title: str, rows: list[dict[str, Any]], show_phase: bool) -> None:
        if rows:
            original_add_docx_schedule(document, title, rows, show_phase)

    def pdf_schedule(title: str, rows: list[dict[str, Any]], show_phase: bool, styles: Any) -> list[Any]:
        return original_pdf_schedule(title, rows, show_phase, styles) if rows else []

    def add_docx_projects(document: Any, report_id: int) -> None:
        if get_projects(report_id).get("projects"):
            original_add_docx_projects(document, report_id)

    def pdf_projects(report_id: int, styles: Any) -> list[Any]:
        return original_pdf_projects(report_id, styles) if get_projects(report_id).get("projects") else []

    process_export._add_docx_schedule = add_docx_schedule
    process_export._pdf_schedule = pdf_schedule
    process_export._add_docx_projects = add_docx_projects
    process_export._pdf_projects = pdf_projects

    original_loader = institutional.legacy.load_report_data
    cleaned_loader = _clean_report_loader(original_loader)
    institutional.legacy.load_report_data = cleaned_loader

    original_build_docx = process_export.build_docx
    original_build_pdf = process_export.build_pdf

    def has_optional_content(report_id: int) -> bool:
        schedules = export_schedules(report_id)
        return bool(
            schedules["complexive"]
            or schedules["thesis"]
            or get_projects(report_id).get("projects")
        )

    def build_docx(report_id: int):
        if not has_optional_content(report_id):
            return institutional.build_docx(report_id)
        return original_build_docx(report_id)

    def build_pdf(report_id: int):
        if not has_optional_content(report_id):
            return institutional.build_pdf(report_id)
        return original_build_pdf(report_id)

    process_export.build_docx = build_docx
    process_export.build_pdf = build_pdf
    core.build_docx = build_docx
    core.build_pdf = build_pdf
