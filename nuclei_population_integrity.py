from __future__ import annotations

from collections import defaultdict
from typing import Any

from nuclei_excel_import import get_excel_import_summary
import nuclei_catalog
import student_domain_bridge as bridge
from student_domain_read_model import consolidated_students
from student_domain_service import (
    PROCESS_ACTIVE,
    ROUTE_COMPLEXIVE,
)


def _coverage(matched: int, expected: int) -> float | None:
    if expected <= 0:
        return None
    return round(matched / expected * 100, 2)


def _required_nuclei(student: dict[str, Any]) -> set[int]:
    """Núcleos que debe tener un estudiante activo de Complexivo.

    El catálogo institucional define la cantidad por carrera. Para una carrera
    todavía no catalogada se conserva el estándar institucional de cuatro núcleos
    en lugar de considerar completa una carga parcial por accidente.
    """
    catalog = nuclei_catalog.catalog_for_career(
        str(student.get("career_name") or "")
    )
    numbers = {
        int(item.get("number") or 0)
        for item in ((catalog or {}).get("nuclei") or [])
        if int(item.get("number") or 0) > 0
    }
    return numbers or {1, 2, 3, 4}


def _present_nuclei(student: dict[str, Any]) -> set[int]:
    return {
        int(item.get("nucleus_number") or 0)
        for item in (student.get("nuclei_records") or [])
        if int(item.get("nucleus_number") or 0) > 0
    }


def _missing_nuclei(student: dict[str, Any]) -> list[int]:
    return sorted(_required_nuclei(student) - _present_nuclei(student))


def nuclei_route_state(student: dict[str, Any]) -> dict[str, Any]:
    """Resume si el estudiante puede avanzar de Núcleos a Complexivo."""
    required = _required_nuclei(student)
    missing = sorted(required - _present_nuclei(student))
    grouped: dict[int, set[str]] = defaultdict(set)
    for record in student.get("nuclei_records") or []:
        number = int(record.get("nucleus_number") or 0)
        if number not in required:
            continue
        status = str(record.get("final_status") or "").strip().upper()
        if status in {"APROBADO", "APROBADA", "APR"}:
            grouped[number].add("APPROVED")
        elif status in {"REPROBADO", "REPROBADA", "REP", "SUSPENSO"}:
            grouped[number].add("FAILED")
        else:
            grouped[number].add("UNEVALUATED")

    conflicting = sorted(
        number
        for number, states in grouped.items()
        if "APPROVED" in states and "FAILED" in states
    )
    failed = sorted(
        number
        for number in required
        if "FAILED" in grouped.get(number, set()) and number not in conflicting
    )
    unevaluated = sorted(
        number
        for number in required
        if number not in missing
        and number not in conflicting
        and not (
            "APPROVED" in grouped.get(number, set())
            or "FAILED" in grouped.get(number, set())
        )
    )
    if missing:
        outcome = "INCOMPLETE"
    elif conflicting:
        outcome = "CONFLICT"
    elif unevaluated:
        outcome = "UNEVALUATED"
    elif failed:
        outcome = "FAILED"
    else:
        outcome = "APPROVED"
    return {
        "outcome": outcome,
        "required": sorted(required),
        "missing": missing,
        "failed": failed,
        "unevaluated": unevaluated,
        "conflicting": conflicting,
    }


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
        reconciliation = bridge.reconcile_all(report_id)

    domain = consolidated_students(report_id, sync=False)
    students = list(domain.get("students") or [])

    expected = [
        student
        for student in students
        if str(student.get("route") or "").upper() == ROUTE_COMPLEXIVE
        and str(student.get("process_status") or "").upper() == PROCESS_ACTIVE
    ]
    # "Tiene Núcleos" no significa "tiene algún Núcleo": para el cierre final
    # debe existir la serie completa que corresponde a su carrera.
    matched = [student for student in expected if not _missing_nuclei(student)]
    missing = [student for student in expected if bool(_missing_nuclei(student))]

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
        if not _missing_nuclei(student):
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
            "missing_nuclei": _missing_nuclei(student)
            if str(student.get("route") or "").upper() == ROUTE_COMPLEXIVE
            and str(student.get("process_status") or "").upper() == PROCESS_ACTIVE
            else [],
            "nuclei_route_state": (
                nuclei_route_state(student)
                if str(student.get("route") or "").upper() == ROUTE_COMPLEXIVE
                and str(student.get("process_status") or "").upper() == PROCESS_ACTIVE
                else {}
            ),
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
