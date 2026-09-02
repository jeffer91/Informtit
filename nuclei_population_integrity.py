from __future__ import annotations

from collections import defaultdict
from typing import Any

from nuclei_excel_import import get_excel_import_summary
from student_domain_bridge import reconcile_all
from student_domain_read_model import consolidated_students
from student_domain_service import (
    PROCESS_ACTIVE,
    ROUTE_COMPLEXIVE,
)


def _coverage(matched: int, expected: int) -> float | None:
    if expected <= 0:
        return None
    return round(matched / expected * 100, 2)


def reconcile_population(report_id: int, *, refresh: bool = True) -> dict[str, Any]:
    """Concilia la población maestra con los registros de Núcleos.

    La fuente de verdad para saber quién DEBE aparecer en Núcleos es
    Requisitos -> period_students -> ruta COMPLEXIVO -> estado ACTIVO.
    Los cursos importados solo aportan las notas/evidencias académicas.
    """
    reconciliation = {
        "ok": True,
        "nuclei": {"matched": 0, "pending": 0, "conflicts": 0, "route_conflicts": 0},
    }
    if refresh:
        # reconcile_all sincroniza Requisitos una sola vez y reutiliza la misma
        # población/index para todos los módulos.
        reconciliation = reconcile_all(report_id)

    domain = consolidated_students(report_id, sync=False)
    students = list(domain.get("students") or [])

    expected = [
        student
        for student in students
        if str(student.get("route") or "").upper() == ROUTE_COMPLEXIVE
        and str(student.get("process_status") or "").upper() == PROCESS_ACTIVE
    ]
    matched = [student for student in expected if bool(student.get("has_nuclei"))]
    missing = [student for student in expected if not bool(student.get("has_nuclei"))]

    unexpected = [
        student
        for student in students
        if bool(student.get("has_nuclei"))
        and student not in expected
    ]

    by_career: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "career": "",
            "expected": 0,
            "with_nuclei": 0,
            "missing": 0,
            "coverage": None,
        }
    )
    for student in expected:
        career = str(student.get("career_name") or "Sin carrera").strip() or "Sin carrera"
        row = by_career[career.casefold()]
        row["career"] = career
        row["expected"] += 1
        if student.get("has_nuclei"):
            row["with_nuclei"] += 1
        else:
            row["missing"] += 1

    career_rows = sorted(by_career.values(), key=lambda row: str(row["career"]).casefold())
    for row in career_rows:
        row["coverage"] = _coverage(int(row["with_nuclei"]), int(row["expected"]))

    def _student_row(student: dict[str, Any]) -> dict[str, Any]:
        return {
            "student_id": int(student.get("id") or 0),
            "identification": str(student.get("identification") or ""),
            "full_name": str(student.get("full_name") or ""),
            "career_name": str(student.get("career_name") or ""),
            "modality": str(student.get("modality") or ""),
            "route": str(student.get("route") or ""),
            "process_status": str(student.get("process_status") or ""),
            "reconciliation_status": str(student.get("reconciliation_status") or ""),
            "reconciliation_detail": str(student.get("reconciliation_detail") or ""),
        }

    source = get_excel_import_summary(report_id) or {}
    nuclei_reconciliation = dict((reconciliation or {}).get("nuclei") or {})

    source_pending = int(nuclei_reconciliation.get("pending") or 0)
    source_conflicts = int(nuclei_reconciliation.get("conflicts") or 0)
    route_conflicts = int(nuclei_reconciliation.get("route_conflicts") or 0)

    complete = (
        not missing
        and source_pending == 0
        and source_conflicts == 0
        and route_conflicts == 0
    )

    return {
        "ok": complete,
        "report_id": int(report_id),
        "expected_students": len(expected),
        "with_nuclei": len(matched),
        "missing_students": len(missing),
        "coverage": _coverage(len(matched), len(expected)),
        "careers": career_rows,
        "missing": [_student_row(student) for student in missing],
        "unexpected": [_student_row(student) for student in unexpected],
        "source_links": {
            "matched_records": int(nuclei_reconciliation.get("matched") or 0),
            "pending_records": source_pending,
            "conflicts": source_conflicts,
            "route_conflicts": route_conflicts,
        },
        "source_import": {
            "source_rows": int(source.get("source_rows") or 0),
            "imported_rows": int(source.get("imported_rows") or 0),
            "duplicate_rows": int(source.get("duplicate_rows") or 0),
            "skipped_rows": int(source.get("skipped_rows") or 0),
            "students": int(source.get("students") or 0),
            "courses": int(source.get("courses") or 0),
            "filename": str(source.get("filename") or ""),
        },
    }
