from __future__ import annotations

import json
import re
from statistics import mean
from typing import Any

import analytics
import app as core
import firebase_sync_runtime as firebase_sync
import nuclei_population_integrity
import period_policy_runtime
import pvc_report_runtime
import student_domain_bridge as student_bridge
from db import connection, rows_to_dicts, utcnow
from import_service import clean_cell
from student_domain_service import (
    MATCH_OK,
    PROCESS_RETIRED,
    ROUTE_ARTICLE,
    ROUTE_COMPLEXIVE,
    ROUTE_THESIS,
    get_period_students,
)


MODULE_LABELS = {
    "nucleos": "Núcleos",
    "complexivo": "Examen Complexivo",
    "trabajoTitulacion": "Trabajo de Titulación",
    "articulo": "Artículo Académico",
}
NORMAL_MODULES = ("nucleos", "complexivo", "trabajoTitulacion")
PVC_MODULES = ("articulo",)
TOLERANCE = 0.05
_INSTALLED = False


def _report(report_id: int) -> dict[str, Any]:
    period_policy_runtime.ensure_schema()
    with connection() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id=?", (int(report_id),)).fetchone()
    if not row:
        raise ValueError("El informe no existe.")
    return dict(row)


def _period_id(report: dict[str, Any]) -> str:
    value = clean_cell(report.get("firebase_period_id"))
    if value:
        return value
    value = period_policy_runtime.canonical_period_id(report.get("period"))
    if value:
        return value
    raise ValueError("El informe no tiene un periodo Firebase identificable.")


def _kind(report: dict[str, Any]) -> str:
    explicit = clean_cell(report.get("report_type")).lower()
    if explicit in {"normal", "pvc"}:
        return explicit
    return period_policy_runtime.classify_period(report.get("period"))


def _allowed_modules(report: dict[str, Any]) -> tuple[str, ...]:
    return PVC_MODULES if _kind(report) == "pvc" else NORMAL_MODULES


def _status(value: Any) -> str:
    text = clean_cell(value).upper()
    if text in {"APROBADA", "APR"}:
        return "APROBADO"
    if text in {"REPROBADA", "REP", "SUSPENSO"}:
        return "REPROBADO"
    if text in {"NO EVALUADO", "NO EVALUADA", "INCOMPLETO", ""}:
        return "NO EVALUADO"
    return text


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid_grade(value: Any, maximum: float) -> bool:
    number = _number(value)
    return number is not None and 0 <= number <= maximum


def _master_rows(report_id: int) -> dict[int, dict[str, Any]]:
    rows = get_period_students(report_id, sync=False).get("students", [])
    return {int(row["id"]): row for row in rows}


def _official_identity_issues(documents: list[tuple[str, dict[str, Any]]]) -> list[str]:
    cedulas = list(dict.fromkeys(
        clean_cell(data.get("cedula"))
        for _, data in documents
        if clean_cell(data.get("cedula"))
    ))
    if not cedulas:
        return []
    students = firebase_sync.batch_get_students(cedulas)
    issues: list[str] = []
    for cedula in cedulas:
        official = students.get(cedula)
        if not official or bool(official.get("eliminado")):
            issues.append(
                f"{cedula}: no existe como estudiante activo en la colección Estudiante."
            )
    return issues


def _nuclei_documents(report_id: int, period_id: str) -> tuple[list[tuple[str, dict[str, Any]]], list[str], list[str]]:
    student_bridge.ensure_bridge_schema()
    population = nuclei_population_integrity.reconcile_population(report_id, refresh=False)
    issues: list[str] = []
    warnings: list[str] = []

    if population.get("missing_students"):
        names = ", ".join(
            clean_cell(row.get("full_name")) or clean_cell(row.get("identification"))
            for row in (population.get("missing") or [])[:8]
        )
        issues.append(
            f"Faltan {population['missing_students']} estudiante(s) de ruta Complexivo en Núcleos"
            + (f": {names}" if names else "")
            + "."
        )
    links = population.get("source_links") or {}
    if int(links.get("pending_records") or 0):
        issues.append(f"Hay {int(links.get('pending_records') or 0)} registro(s) de Núcleos sin conciliar.")
    if int(links.get("conflicts") or 0):
        issues.append(f"Hay {int(links.get('conflicts') or 0)} registro(s) de Núcleos ambiguos o en revisión.")

    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT ns.id, ns.period_student_id, ns.final_grade, ns.final_status,
                       c.nucleus_number, c.course_key, c.course_title,
                       ps.identification, ps.full_name, ps.route, ps.process_status
                FROM nucleus_instance_students ns
                JOIN nucleus_course_instances c ON c.id=ns.course_id
                LEFT JOIN period_students ps ON ps.id=ns.period_student_id
                WHERE c.report_id=?
                ORDER BY ps.identification, c.nucleus_number, c.id, ns.id
                """,
                (report_id,),
            ).fetchall()
        )

    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        sid = row.get("period_student_id")
        cedula = clean_cell(row.get("identification"))
        if not sid or not cedula:
            issues.append(
                f"Núcleos: {clean_cell(row.get('full_name')) or 'registro sin nombre'} no está conciliado con Estudiante."
            )
            continue
        if clean_cell(row.get("route")).upper() != ROUTE_COMPLEXIVE:
            # Evidencia histórica de una ruta anterior: se conserva localmente,
            # pero no se publica como resultado académico vigente.
            continue
        if clean_cell(row.get("process_status")).upper() != "ACTIVO":
            continue
        nucleus = int(row.get("nucleus_number") or 0)
        if nucleus <= 0:
            issues.append(f"{cedula}: el número de Núcleo no es válido.")
            continue
        grouped.setdefault((cedula, nucleus), []).append(row)

    documents: list[tuple[str, dict[str, Any]]] = []
    for (cedula, nucleus), candidates in grouped.items():
        normalized = {
            (
                round(float(item["final_grade"]), 6) if item.get("final_grade") is not None else None,
                _status(item.get("final_status")),
            )
            for item in candidates
        }
        if len(normalized) > 1:
            issues.append(
                f"{cedula} tiene más de un resultado distinto para el Núcleo {nucleus}; no se sobrescribirá automáticamente."
            )
            continue
        row = candidates[-1]
        grade = _number(row.get("final_grade"))
        state = _status(row.get("final_status"))
        if not _valid_grade(grade, 100.0):
            issues.append(f"{cedula} · Núcleo {nucleus}: la nota final está vacía o fuera de 0-100.")
            continue
        if state == "NO EVALUADO":
            issues.append(f"{cedula} · Núcleo {nucleus}: el resultado sigue como No evaluado.")
            continue
        doc_id = f"{period_id}__{cedula}__N{nucleus}"
        documents.append(
            (
                doc_id,
                {
                    "periodoId": period_id,
                    "cedula": cedula,
                    "nucleo": nucleus,
                    "notaFinal": grade,
                    "estado": state,
                    "version": 1,
                    "updatedAt": utcnow(),
                },
            )
        )

    if population.get("unexpected"):
        warnings.append(
            f"{len(population['unexpected'])} estudiante(s) conservan evidencia histórica de Núcleos fuera de su ruta activa; no se publicarán."
        )
    return documents, list(dict.fromkeys(issues)), warnings


def _complexive_documents(report_id: int, period_id: str) -> tuple[list[tuple[str, dict[str, Any]]], list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT s.*, ps.identification AS official_identification,
                       ps.route AS official_route, ps.process_status AS official_process
                FROM students s
                JOIN careers c ON c.id=s.career_id
                LEFT JOIN period_students ps ON ps.id=s.period_student_id
                WHERE c.report_id=?
                ORDER BY s.id
                """,
                (report_id,),
            ).fetchall()
        )

    documents: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for row in rows:
        cedula = clean_cell(row.get("official_identification"))
        if not row.get("period_student_id") or not cedula:
            issues.append(
                f"Complexivo: {clean_cell(row.get('full_name')) or 'registro sin nombre'} no está conciliado con Estudiante."
            )
            continue
        if clean_cell(row.get("official_route")).upper() != ROUTE_COMPLEXIVE:
            continue
        if clean_cell(row.get("official_process")).upper() != "ACTIVO":
            continue
        if cedula in seen:
            issues.append(f"{cedula}: existe más de un registro activo de Examen Complexivo.")
            continue
        seen.add(cedula)
        enriched = analytics.enrich_student(row)
        final_grade = _number(enriched.get("final_grade"))
        if not _valid_grade(final_grade, 100.0):
            issues.append(f"{cedula}: la nota final de Complexivo está vacía o fuera de 0-100.")
            continue
        final_state = _status(enriched.get("final_status"))
        if final_state == "NO EVALUADO":
            issues.append(f"{cedula}: el Examen Complexivo sigue como No evaluado.")
            continue
        difference = _number(enriched.get("source_difference"))
        if difference is not None and abs(difference) > TOLERANCE:
            issues.append(
                f"{cedula}: la nota final calculada de Complexivo no coincide con la fuente ({difference:+.2f})."
            )
            continue
        documents.append(
            (
                f"{period_id}__{cedula}",
                {
                    "periodoId": period_id,
                    "cedula": cedula,
                    "notaTeoricaOrdinaria": _number(row.get("ordinary_theory")),
                    "notaPracticaOrdinaria": _number(row.get("ordinary_practical")),
                    "notaOrdinaria": _number(enriched.get("ordinary_final")),
                    "notaTeoricaSupletorio": _number(row.get("supplementary_theory")),
                    "notaPracticaSupletorio": _number(row.get("supplementary_practical")),
                    "notaSupletorio": _number(enriched.get("supplementary_final")),
                    "notaFinal": final_grade,
                    "estado": final_state,
                    "version": 1,
                    "updatedAt": utcnow(),
                },
            )
        )
    return documents, list(dict.fromkeys(issues)), warnings


def _thesis_documents(report_id: int, period_id: str) -> tuple[list[tuple[str, dict[str, Any]]], list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    student_bridge.ensure_bridge_schema()
    masters = _master_rows(report_id)
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM thesis_projects WHERE report_id=? ORDER BY id",
                (report_id,),
            ).fetchall()
        )

    expected = {
        clean_cell(row.get("identification"))
        for row in masters.values()
        if clean_cell(row.get("route")).upper() == ROUTE_THESIS
        and clean_cell(row.get("process_status")).upper() == "ACTIVO"
        and clean_cell(row.get("identification"))
    }
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        sid = int(row.get("period_student_id") or 0)
        master = masters.get(sid)
        cedula = clean_cell(master.get("identification")) if master else ""
        if not master or not cedula:
            # Un proyecto con ruta no confirmada nunca se publica.
            issues.append(
                f"Trabajo de Titulación: {clean_cell(row.get('full_name')) or 'registro sin nombre'} no está conciliado con Estudiante."
            )
            continue
        if clean_cell(master.get("route")).upper() != ROUTE_THESIS:
            warnings.append(
                f"{cedula}: existe evidencia histórica de Trabajo de Titulación fuera de su ruta activa; no se publicará."
            )
            continue
        if cedula in by_id:
            issues.append(f"{cedula}: existe más de un registro activo de Trabajo de Titulación.")
            continue
        by_id[cedula] = row

    for cedula in sorted(expected - set(by_id)):
        issues.append(f"{cedula}: está en ruta Trabajo de Titulación pero no tiene registro del trabajo.")

    documents: list[tuple[str, dict[str, Any]]] = []
    for cedula, row in by_id.items():
        calculated = _number(row.get("final_grade"))
        source = _number(row.get("source_final_grade"))
        difference = _number(row.get("source_difference"))
        if not _valid_grade(calculated, 10.0):
            issues.append(f"{cedula}: la calificación final de Trabajo de Titulación está incompleta.")
            continue
        if difference is not None and abs(difference) > TOLERANCE:
            issues.append(
                f"{cedula}: la calificación final pegada no coincide con el cálculo 60/40 ({difference:+.2f})."
            )
            continue
        final_grade = source if source is not None else calculated
        state = "APROBADO" if final_grade >= 7.0 else "REPROBADO"
        documents.append(
            (
                f"{period_id}__{cedula}",
                {
                    "periodoId": period_id,
                    "cedula": cedula,
                    "numeroActa": clean_cell(row.get("act_number")),
                    "fechaActa": clean_cell(row.get("act_date")),
                    "calificacionTutor": _number(row.get("tutor_grade")),
                    "calificacionLector": _number(row.get("reader_grade")),
                    "promedioTrabajoEscrito": _number(row.get("written_average")),
                    "vocal1": clean_cell(row.get("vocal_1")),
                    "vocal2": clean_cell(row.get("vocal_2")),
                    "vocal3": clean_cell(row.get("vocal_3")),
                    "promedioEvaluacionPractica": _number(row.get("practical_average")),
                    "promedioEvaluacionDefensa": _number(row.get("defense_average")),
                    "promedioDefensaOral": _number(row.get("oral_average")),
                    "calificacionFinal": final_grade,
                    "estado": state,
                    "version": 1,
                    "updatedAt": utcnow(),
                },
            )
        )
    return documents, list(dict.fromkeys(issues)), list(dict.fromkeys(warnings))


def _component_average(raw: Any) -> float | None:
    try:
        rows = json.loads(raw or "[]") if isinstance(raw, str) else list(raw or [])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    vocal_totals: list[float] = []
    for vocal in ("vocal_1", "vocal_2", "vocal_3"):
        values = [_number(row.get(vocal)) for row in rows if isinstance(row, dict)]
        if rows and values and len(values) == len(rows) and all(value is not None for value in values):
            vocal_totals.append(sum(float(value) for value in values if value is not None))
    return round(mean(vocal_totals), 2) if len(vocal_totals) == 3 else None


def _article_documents(report_id: int, period_id: str) -> tuple[list[tuple[str, dict[str, Any]]], list[str], list[str]]:
    pvc_report_runtime.ensure_schema()
    issues: list[str] = []
    warnings: list[str] = []
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM pvc_records WHERE report_id=? ORDER BY id",
                (report_id,),
            ).fetchall()
        )

    if not rows:
        issues.append("No existen resultados de Artículo Académico importados.")
        return [], issues, warnings

    documents: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for row in rows:
        cedula = clean_cell(row.get("identification"))
        if clean_cell(row.get("match_status")).upper() != "MATCHED":
            issues.append(
                f"Artículo: {clean_cell(row.get('source_name')) or cedula or 'registro sin identidad'} no está conciliado con Estudiante."
            )
            continue
        if not cedula:
            issues.append("Artículo: existe un registro conciliado sin cédula.")
            continue
        if not bool(row.get("requirements_complete")):
            # No cumplir requisitos es un resultado terminal del informe, no una
            # nota académica publicable.
            continue
        if cedula in seen:
            issues.append(f"{cedula}: existe más de un resultado de Artículo Académico.")
            continue
        seen.add(cedula)
        if clean_cell(row.get("formula_status")).upper() == "WARNING":
            issues.append(f"{cedula}: la nota de Artículo no coincide con el cálculo 70/30.")
            continue
        calculated = _number(row.get("final_calculated"))
        source = _number(row.get("final_source"))
        final_grade = source if source is not None else calculated
        if not _valid_grade(final_grade, 10.0):
            issues.append(f"{cedula}: la calificación final de Artículo está incompleta o fuera de 0-10.")
            continue
        state = _status(row.get("final_status"))
        if state == "NO EVALUADO":
            issues.append(f"{cedula}: el Artículo sigue como No evaluado.")
            continue
        documents.append(
            (
                f"{period_id}__{cedula}",
                {
                    "periodoId": period_id,
                    "cedula": cedula,
                    "numeroActa": clean_cell(row.get("act_number")),
                    "fechaActa": clean_cell(row.get("act_date")),
                    "tutor": clean_cell(row.get("tutor_name")),
                    "lector": clean_cell(row.get("reader_name")),
                    "calificacionTutor": _number(row.get("tutor_grade")),
                    "calificacionLector": _number(row.get("reader_grade")),
                    "promedioTrabajoEscrito": (
                        _number(row.get("written_calculated"))
                        if _number(row.get("written_calculated")) is not None
                        else _number(row.get("written_source"))
                    ),
                    "vocal1": clean_cell(row.get("vocal_1")),
                    "vocal2": clean_cell(row.get("vocal_2")),
                    "vocal3": clean_cell(row.get("vocal_3")),
                    "promedioEvaluacionPractica": _component_average(row.get("practical_json")),
                    "promedioEvaluacionDefensa": _component_average(row.get("defense_json")),
                    "promedioDefensaOral": _number(row.get("defense_source")),
                    "calificacionFinal": final_grade,
                    "estado": state,
                    "version": 1,
                    "updatedAt": utcnow(),
                },
            )
        )
    return documents, list(dict.fromkeys(issues)), warnings


def _documents_for(
    report_id: int,
    module: str,
    *,
    reconcile: bool,
) -> tuple[list[tuple[str, dict[str, Any]]], list[str], list[str], dict[str, Any]]:
    report = _report(report_id)
    if module not in MODULE_LABELS:
        raise ValueError("Módulo de publicación no válido.")
    if module not in _allowed_modules(report):
        raise ValueError(
            f"{MODULE_LABELS[module]} no corresponde al tipo de período seleccionado."
        )

    if reconcile and _kind(report) == "normal":
        student_bridge.reconcile_all(report_id)

    period_id = _period_id(report)
    if module == "nucleos":
        documents, issues, warnings = _nuclei_documents(report_id, period_id)
    elif module == "complexivo":
        documents, issues, warnings = _complexive_documents(report_id, period_id)
    elif module == "trabajoTitulacion":
        documents, issues, warnings = _thesis_documents(report_id, period_id)
    else:
        documents, issues, warnings = _article_documents(report_id, period_id)

    if not documents and not issues:
        issues.append(f"No existen registros de {MODULE_LABELS[module]} para publicar.")
    issues.extend(_official_identity_issues(documents))
    return documents, list(dict.fromkeys(issues)), list(dict.fromkeys(warnings)), report


def audit_module(report_id: int, module: str, *, reconcile: bool = True) -> dict[str, Any]:
    documents, issues, warnings, report = _documents_for(
        report_id,
        module,
        reconcile=reconcile,
    )
    return {
        "ok": not issues,
        "ready": not issues,
        "report_id": int(report_id),
        "periodoId": _period_id(report),
        "report_type": _kind(report),
        "module": module,
        "label": MODULE_LABELS[module],
        "documents": len(documents),
        "issues": issues,
        "warnings": warnings,
    }


def publication_status(report_id: int) -> dict[str, Any]:
    report = _report(report_id)
    modules = _allowed_modules(report)
    if _kind(report) == "normal":
        student_bridge.reconcile_all(report_id)
    statuses = [
        audit_module(report_id, module, reconcile=False)
        for module in modules
    ]
    return {
        "ok": True,
        "report_id": int(report_id),
        "periodoId": _period_id(report),
        "report_type": _kind(report),
        "modules": statuses,
    }


def publish_module(report_id: int, module: str) -> dict[str, Any]:
    documents, issues, warnings, report = _documents_for(
        report_id,
        module,
        reconcile=True,
    )
    if issues:
        return {
            "ok": False,
            "ready": False,
            "report_id": int(report_id),
            "periodoId": _period_id(report),
            "module": module,
            "label": MODULE_LABELS[module],
            "documents": len(documents),
            "written": 0,
            "unchanged": 0,
            "issues": issues,
            "warnings": warnings,
            "error": "La publicación está bloqueada por la auditoría académica.",
        }

    written = 0
    unchanged = 0
    for doc_id, data in documents:
        changed = firebase_sync.write_document(module, doc_id, data)
        if changed is False:
            unchanged += 1
        else:
            written += 1

    return {
        "ok": True,
        "ready": True,
        "report_id": int(report_id),
        "periodoId": _period_id(report),
        "module": module,
        "label": MODULE_LABELS[module],
        "documents": len(documents),
        "written": written,
        "unchanged": unchanged,
        "issues": [],
        "warnings": warnings,
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    previous_get = core.InformtitHandler._handle_api_get
    previous_write = core.InformtitHandler._handle_api_write

    def api_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/firebase/publication-status":
            values = query.get("report_id") or []
            report_id = int(values[0]) if values and str(values[0]).isdigit() else 0
            if not report_id:
                raise ValueError("Seleccione un informe para revisar la publicación.")
            self._send_json(publication_status(report_id))
            return
        previous_get(self, path, query)

    def api_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        if method == "POST" and path == "/api/firebase/publish":
            report_id = int(payload.get("report_id") or 0)
            module = clean_cell(payload.get("module"))
            if not report_id:
                raise ValueError("Seleccione un informe para publicar.")
            self._send_json(publish_module(report_id, module))
            return
        previous_write(self, method, path, payload)

    core.InformtitHandler._handle_api_get = api_get
    core.InformtitHandler._handle_api_write = api_write
    _INSTALLED = True
