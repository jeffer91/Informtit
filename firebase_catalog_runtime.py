from __future__ import annotations

import period_policy_runtime
from db import connection


def install() -> None:
    """Hace que el panel cuente carreras/estudiantes desde Requisitos sincronizados."""
    if getattr(period_policy_runtime, "_firebase_catalog_installed", False):
        return

    previous = period_policy_runtime.visible_reports

    def visible_reports():
        reports = previous()
        with connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='requirements_students'"
            ).fetchone()
            if not exists:
                return reports
            for report in reports:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS students,
                           COUNT(DISTINCT NULLIF(TRIM(career_name), '')) AS careers
                    FROM requirements_students
                    WHERE report_id=?
                    """,
                    (int(report["id"]),),
                ).fetchone()
                if row and int(row["students"] or 0) > 0:
                    report["student_count"] = int(row["students"] or 0)
                    report["career_count"] = int(row["careers"] or 0)
        return reports

    period_policy_runtime.visible_reports = visible_reports
    period_policy_runtime._firebase_catalog_installed = True
