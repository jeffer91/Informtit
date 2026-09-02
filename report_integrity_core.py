from __future__ import annotations

import json
import math
import re
import shutil
import unicodedata
import uuid
from collections import Counter, defaultdict
from statistics import mean, median, pstdev
from typing import Any, Callable

import completion_service
import nuclei_excel_import
import nuclei_population_integrity
import process_service
import report_completion
import report_pdf_polish as polish
import report_quality
import report_full_detail as full
from db import connection, rows_to_dicts, utcnow
from nuclei_excel_import import REQUIRED_HEADERS, get_excel_import_summary
from roster_service import REQUIREMENTS, get_report_roster


VALID_STATES = {
    "CUMPLE",
    "NO CUMPLE",
    "SIN INFORMACIÓN",
    "NO EVALUADO",
    "NO APLICA",
    "EN REVISIÓN",
    "REQUIERE CORRECCIÓN",
    "RETIRADO",
    "AUSENTE",
    "PENDIENTE DE CLASIFICAR",
}

_RAW_NUCLEI_PROVIDER: Callable[[int], dict[str, Any]] | None = None


def set_raw_nuclei_provider(provider: Callable[[int], dict[str, Any]]) -> None:
    global _RAW_NUCLEI_PROVIDER
    _RAW_NUCLEI_PROVIDER = provider


def norm(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").strip().split())


def ascii_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", norm(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def canonical_state(value: Any) -> str:
    raw = ascii_key(value)
    if not raw:
        return "SIN INFORMACIÓN"
    aliases = {
        "CUMPLE": "CUMPLE",
        "NO CUMPLE": "NO CUMPLE",
        "SIN INFORMACION": "SIN INFORMACIÓN",
        "NO EVALUADO": "NO EVALUADO",
        "SIN NOTA": "NO EVALUADO",
        "NO APLICA": "NO APLICA",
        "EN REVISION": "EN REVISIÓN",
        "REQUIERE CORRECCION": "REQUIERE CORRECCIÓN",
        "RETIRADO": "RETIRADO",
        "RETIRADA": "RETIRADO",
        "AUSENTE": "AUSENTE",
        "PENDIENTE": "PENDIENTE DE CLASIFICAR",
        "PENDIENTE DE CLASIFICAR": "PENDIENTE DE CLASIFICAR",
    }
    return aliases.get(raw, "PENDIENTE DE CLASIFICAR")


def nucleus_state(student: dict[str, Any]) -> str:
    raw = ascii_key(student.get("final_status"))
    if raw in {"APROBADO", "APROBADA", "APR"}:
        return "approved"
    if raw in {"REPROBADO", "REPROBADA", "REP", "SUSPENSO"}:
        return "failed"
    return "unevaluated"


def stats(values: list[float]) -> dict[str, float | None]:
    clean = [float(value) for value in values if number(value) is not None]
    if not clean:
        return {"average": None, "median": None, "minimum": None, "maximum": None, "stdev": None}
    return {
        "average": round(mean(clean), 2),
        "median": round(median(clean), 2),
        "minimum": round(min(clean), 2),
        "maximum": round(max(clean), 2),
        "stdev": round(pstdev(clean), 2) if len(clean) > 1 else 0.0,
    }


def evaluated_grades(students: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for student in students:
        if nucleus_state(student) not in {"approved", "failed"}:
            continue
        grade = number(student.get("final_grade"))
        if grade is not None:
            values.append(grade)
    return values


def compact_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(round(value, 2)).replace(".", ",")


def metric(name: str, numerator: int | float, denominator: int | float, denominator_type: str) -> dict[str, Any]:
    num = float(numerator or 0)
    den = float(denominator or 0)
    result = round(num / den * 100, 2) if den > 0 else None
    return {
        "name": name,
        "numerator": num,
        "denominator": den,
        "denominator_type": denominator_type,
        "result": result,
        "formula": f"{compact_number(num)} / {compact_number(den)} × 100",
    }


def metric_gap(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    comparable = (
        left.get("denominator_type") == right.get("denominator_type")
        and left.get("result") is not None
        and right.get("result") is not None
    )
    return {
        "comparable": comparable,
        "difference": round(float(left["result"]) - float(right["result"]), 2) if comparable else None,
        "reason": "" if comparable else "Los indicadores usan denominadores diferentes o no tienen población calculable.",
    }


def raw_nuclei(report_id: int) -> list[dict[str, Any]]:
    if _RAW_NUCLEI_PROVIDER is None:
        return []
    return list((_RAW_NUCLEI_PROVIDER(report_id) or {}).get("courses", []))


def _years(value: Any) -> set[str]:
    return set(re.findall(r"\b20\d{2}\b", norm(value)))


def course_in_period(report: dict[str, Any], course: dict[str, Any]) -> bool:
    label = norm(course.get("period_label"))
    if not label:
        return True
    report_years = _years(report.get("period"))
    course_years = _years(label)
    return not (report_years and course_years and report_years.isdisjoint(course_years))


def _course_signature(course: dict[str, Any]) -> tuple[Any, ...]:
    students = tuple(sorted(
        (
            ascii_key(student.get("full_name")),
            ascii_key(student.get("email")),
            number(student.get("final_grade")),
            ascii_key(student.get("final_status")),
        )
        for student in course.get("students", [])
    ))
    return (
        ascii_key(course.get("career_name")),
        int(course.get("nucleus_number") or 0),
        ascii_key(course.get("course_title")),
        ascii_key(course.get("teacher_name")),
        ascii_key(course.get("campus")),
        ascii_key(course.get("group_code")),
        students,
    )


def reconciled_courses(report_id: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    report = report_quality._report_data(report_id)
    reasons = {
        "Otra modalidad": 0,
        "Fuera del período": 0,
        "Duplicado": 0,
        "Registro vacío": 0,
        "Curso no aplicable": 0,
        "Otro": 0,
    }
    included: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for course in raw_nuclei(report_id):
        career = norm(course.get("career_name"))
        title = norm(course.get("course_title"))
        if not career or (not title and not course.get("nucleus_number")):
            reasons["Registro vacío"] += 1
            continue
        explicit_modality = ascii_key(
            course.get("official_modality")
            or course.get("dataset_modality")
            or course.get("modality")
        )
        if explicit_modality in {"EN LINEA", "ONLINE", "EN_LINEA"}:
            online = True
        elif explicit_modality == "PRESENCIAL":
            online = False
        else:
            # Compatibilidad con evidencias históricas que todavía no llevan una
            # modalidad explícita. Los datos nuevos deben venir etiquetados desde
            # Requisitos/dataset, no inferirse por el nombre de la carrera.
            online = (
                "ONLINE" in ascii_key(career)
                or "EN LINEA" in ascii_key(career)
                or "-L-" in str(course.get("career_code") or "").upper()
            )
        if report.get("modality") == "en_linea" and not online:
            reasons["Otra modalidad"] += 1
            continue
        if report.get("modality") == "presencial" and online:
            reasons["Otra modalidad"] += 1
            continue
        if not course_in_period(report, course):
            reasons["Fuera del período"] += 1
            continue
        if not polish._allowed_nuclei_career(
            course.get("career_name"),
            report,
            course.get("official_modality")
            or course.get("dataset_modality")
            or course.get("modality"),
        ):
            reasons["Curso no aplicable"] += 1
            continue
        signature = _course_signature(course)
        if signature in seen:
            reasons["Duplicado"] += 1
            continue
        seen.add(signature)
        included.append(course)
    return included, reasons


def strict_nuclei(report_id: int) -> dict[str, Any]:
    report = report_quality._report_data(report_id)
    courses, _ = reconciled_courses(report_id)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for course in courses:
        grouped[norm(course.get("career_name")) or "Sin carrera"].append(course)

    career_rows: list[dict[str, Any]] = []
    course_rows: list[dict[str, Any]] = []
    all_grades: list[float] = []
    lookup_raw: dict[str, dict[str, Any]] = {}
    for raw_career, career_courses in grouped.items():
        students = [student for course in career_courses for student in course.get("students", [])]
        approved = sum(nucleus_state(student) == "approved" for student in students)
        failed = sum(nucleus_state(student) == "failed" for student in students)
        unevaluated = len(students) - approved - failed
        evaluated = approved + failed
        grades = evaluated_grades(students)
        all_grades.extend(grades)
        row = {
            "career": polish._display_career(raw_career),
            "raw_career": raw_career,
            "modality": report_quality.base.modality(report),
            "courses": len(career_courses),
            "records": len(students),
            "evaluated": evaluated,
            "approved": approved,
            "failed": failed,
            "unevaluated": unevaluated,
            **stats(grades),
            "approval": full._pct(approved, evaluated),
            "approval_denominator_type": "EVALUADOS",
        }
        career_rows.append(row)
        lookup_raw[raw_career] = row
        for course in career_courses:
            course_students = list(course.get("students", []))
            capproved = sum(nucleus_state(student) == "approved" for student in course_students)
            cfailed = sum(nucleus_state(student) == "failed" for student in course_students)
            cevaluated = capproved + cfailed
            cunevaluated = len(course_students) - cevaluated
            cgrades = evaluated_grades(course_students)
            course_rows.append({
                "career": polish._display_career(raw_career),
                "raw_career": raw_career,
                "nucleus": norm(course.get("course_title")) or f"Núcleo {course.get('nucleus_number') or '—'}",
                "teacher": norm(course.get("teacher_name")) or "No registrado",
                "students": len(course_students),
                "evaluated": cevaluated,
                "approved": capproved,
                "failed": cfailed,
                "unevaluated": cunevaluated,
                "average": stats(cgrades)["average"],
                "approval": full._pct(capproved, cevaluated),
                "approval_denominator_type": "EVALUADOS",
                "course": course,
            })

    career_rows.sort(key=lambda row: row["career"].casefold())
    total_evaluated = sum(row["evaluated"] for row in career_rows)
    total_approved = sum(row["approved"] for row in career_rows)
    return {
        "courses": courses,
        "careers": career_rows,
        "course_rows": course_rows,
        "career_lookup": {row["career"]: row for row in career_rows},
        "career_lookup_raw": lookup_raw,
        "institutional_stats": stats(all_grades),
        "institutional_approval": full._pct(total_approved, total_evaluated),
        "approval_denominator_type": "EVALUADOS",
    }


def schedule_key(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        ascii_key(entry.get("activity")),
        process_service._valid_date(str(entry.get("start_date") or "")),
        process_service._valid_date(str(entry.get("end_date") or "")),
    )


def dedupe_schedule_entries(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    duplicates = 0
    for entry in entries:
        if not norm(entry.get("activity")):
            continue
        key = schedule_key(entry)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(entry)
    return unique, duplicates


def schedule_summary(report_id: int) -> dict[str, Any]:
    data = completion_service.get_schedules_extended(report_id)
    rows = list(data.get("complexive", [])) + list(data.get("thesis", []))
    seen: set[tuple[Any, ...]] = set()
    unique: list[dict[str, Any]] = []
    duplicates = 0
    for row in rows:
        try:
            key = (str(row.get("schedule_type") or ""), *schedule_key(row))
        except ValueError:
            unique.append(row)
            continue
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(row)
    evaluated = [row for row in unique if row.get("execution_status") or row.get("compliance_percentage") is not None or row.get("executed_date")]
    incomplete = [row for row in evaluated if not row.get("executed_date") or not row.get("execution_status") or not row.get("evidence")]
    return {
        "rows": unique,
        "total": len(unique),
        "evaluated": len(evaluated),
        "pending_evaluation": len(unique) - len(evaluated),
        "duplicates": duplicates,
        "incomplete_evidence": len(incomplete),
    }


def ensure_integrity_schema() -> None:
    with connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS report_duplicate_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                module TEXT NOT NULL,
                duplicate_type TEXT NOT NULL,
                original_json TEXT DEFAULT '',
                omitted_json TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_duplicate_audit_report
                ON report_duplicate_audit(report_id, module);
        """)


def write_duplicate_logs(report_id: int, module: str, entries: list[dict[str, Any]]) -> None:
    ensure_integrity_schema()
    with connection() as conn:
        conn.execute("DELETE FROM report_duplicate_audit WHERE report_id=? AND module=?", (report_id, module))
        for item in entries[:1000]:
            conn.execute(
                """INSERT INTO report_duplicate_audit
                   (report_id, module, duplicate_type, original_json, omitted_json, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    report_id,
                    module,
                    item.get("duplicate_type") or "DUPLICADO PROBABLE",
                    json.dumps(item.get("original") or {}, ensure_ascii=False),
                    json.dumps(item.get("omitted") or {}, ensure_ascii=False),
                    item.get("reason") or "",
                    utcnow(),
                ),
            )


def nuclei_duplicate_entries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exact_seen: dict[tuple[str, ...], dict[str, Any]] = {}
    probable_seen: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    result: list[dict[str, Any]] = []
    for record in records:
        exact = tuple(norm(record.get(header)) for header in REQUIRED_HEADERS)
        if exact in exact_seen:
            result.append({
                "duplicate_type": "DUPLICADO EXACTO",
                "original": exact_seen[exact],
                "omitted": record,
                "reason": "La fila coincide exactamente en todos los campos importados.",
            })
            continue
        exact_seen[exact] = record
        probable = (
            ascii_key(record.get("nombre_carrera")),
            ascii_key(record.get("nombre_estudiante")),
            ascii_key(record.get("materia")),
            ascii_key(record.get("nombre_profesor")),
        )
        previous = probable_seen.get(probable)
        if previous and tuple(norm(previous.get(h)) for h in REQUIRED_HEADERS) != exact:
            result.append({
                "duplicate_type": "DUPLICADO PROBABLE",
                "original": previous,
                "omitted": record,
                "reason": "Misma carrera, estudiante, materia y docente, pero con diferencias en otros campos; el Excel de Núcleos no incluye cédula.",
            })
        else:
            probable_seen[probable] = record
    return result


def requirements_duplicate_summary(report_id: int) -> dict[str, Any]:
    students = list(get_report_roster(report_id).get("students", []))
    exact_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    probable_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for student in students:
        career = ascii_key(student.get("career_name"))
        identification = ascii_key(student.get("identification"))
        if identification:
            exact_groups[(career, identification)].append(student)
        else:
            probable_groups[(career, ascii_key(student.get("full_name")))].append(student)
    exact = [items for items in exact_groups.values() if len(items) > 1]
    probable = [items for key, items in probable_groups.items() if key[1] and len(items) > 1]
    entries: list[dict[str, Any]] = []
    for items, duplicate_type, reason in (
        (exact, "DUPLICADO EXACTO", "Misma carrera y cédula dentro del informe."),
        (probable, "DUPLICADO PROBABLE", "Sin cédula; coincide carrera y nombre normalizado."),
    ):
        for group in items:
            for duplicate in group[1:]:
                entries.append({"duplicate_type": duplicate_type, "original": group[0], "omitted": duplicate, "reason": reason})
    write_duplicate_logs(report_id, "Requisitos", entries)
    return {
        "exact": sum(len(group) - 1 for group in exact),
        "probable": sum(len(group) - 1 for group in probable),
    }


def duplicate_summary(report_id: int) -> dict[str, Any]:
    requirements = requirements_duplicate_summary(report_id)
    import_summary = get_excel_import_summary(report_id) or {}
    ensure_integrity_schema()
    with connection() as conn:
        rows = rows_to_dicts(conn.execute(
            """SELECT duplicate_type, COUNT(*) AS total
               FROM report_duplicate_audit
               WHERE report_id=? AND module='Núcleos'
               GROUP BY duplicate_type""",
            (report_id,),
        ).fetchall())
    logged = {row["duplicate_type"]: int(row["total"]) for row in rows}
    nuclei_exact = max(int(import_summary.get("duplicate_rows") or 0), logged.get("DUPLICADO EXACTO", 0))
    nuclei_probable = logged.get("DUPLICADO PROBABLE", 0)
    return {
        "requirements_exact": requirements["exact"],
        "requirements_probable": requirements["probable"],
        "nuclei_exact_omitted": nuclei_exact,
        "nuclei_probable": nuclei_probable,
        "unresolved_probable": requirements["probable"] + nuclei_probable,
    }


def reconciliation(report_id: int) -> dict[str, Any]:
    raw = raw_nuclei(report_id)
    included, reasons = reconciled_courses(report_id)
    excluded = sum(reasons.values())
    source = get_excel_import_summary(report_id) or {}
    return {
        "scope": "cursos de Núcleos",
        "imported": len(raw),
        "included": len(included),
        "excluded": excluded,
        "reasons": reasons,
        "balanced": len(raw) == len(included) + excluded,
        "source_quality": {
            "source_rows": int(source.get("source_rows") or 0),
            "imported_rows": int(source.get("imported_rows") or 0),
            "duplicate_rows": int(source.get("duplicate_rows") or 0),
            "skipped_rows": int(source.get("skipped_rows") or 0),
            "students": int(source.get("students") or 0),
            "courses": int(source.get("courses") or 0),
        },
    }


def source_context(report: dict[str, Any]) -> dict[str, Any]:
    source_import_id = report.get("source_import_id")
    row = None
    if source_import_id:
        with connection() as conn:
            row = conn.execute("SELECT * FROM import_history WHERE id=?", (int(source_import_id),)).fetchone()
    source = dict(row) if row else {}
    modality_count = int(source.get("online_students") or 0) if report.get("modality") == "en_linea" else int(source.get("presencial_students") or 0)
    return {
        "exists": bool(row),
        "source_import_id": source_import_id,
        "source_total": int(source.get("total_students") or 0),
        "source_modality_count": modality_count,
        "source_presencial": int(source.get("presencial_students") or 0),
        "source_online": int(source.get("online_students") or 0),
        "filename": norm(source.get("original_name")),
    }


def resolve_logo(report_id: int) -> bool:
    report = report_quality._report_data(report_id)
    base = report_quality.base
    if base.image_path(base.image_for(report, base.LOGO)):
        return True
    with connection() as conn:
        candidates = rows_to_dicts(conn.execute(
            """SELECT i.* FROM images i JOIN reports r ON r.id=i.report_id
               WHERE i.section=? AND i.report_id<>?
               ORDER BY CASE WHEN r.source_import_id=(SELECT source_import_id FROM reports WHERE id=?) THEN 0 ELSE 1 END, i.id DESC""",
            (base.LOGO, report_id, report_id),
        ).fetchall())
    source = next((base.image_path(item) for item in candidates if base.image_path(item)), None)
    if not source:
        return False
    base.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target_name = f"{uuid.uuid4().hex}{source.suffix.lower() or '.png'}"
    shutil.copy2(source, base.UPLOAD_DIR / target_name)
    with connection() as conn:
        conn.execute(
            """INSERT INTO images
               (report_id, career_id, section, filename, original_name, title, description, source, sort_order, created_at)
               VALUES (?, NULL, ?, ?, ?, 'Logo institucional', 'Recurso institucional reutilizado automáticamente.', 'Configuración institucional', 0, ?)""",
            (report_id, base.LOGO, target_name, source.name, utcnow()),
        )
    return True


def status_summary(report_id: int) -> dict[str, Any]:
    students = list(get_report_roster(report_id).get("students", []))
    counts: Counter[str] = Counter()
    pending = 0
    for student in students:
        for key, _ in REQUIREMENTS:
            raw = norm(student.get(key))
            state = canonical_state(raw)
            counts[state] += 1
            if raw and state == "PENDIENTE DE CLASIFICAR":
                pending += 1
    return {"counts": dict(counts), "pending_classification": pending, "valid_states": sorted(VALID_STATES)}


def report_metrics(report_id: int) -> dict[str, Any]:
    report = report_quality._report_data(report_id)
    requirements = report_completion.corrected_requirement_analysis(report_id)
    nuclei = strict_nuclei(report_id)
    complexive = report_completion._complexive_data(report)
    projects = process_service.get_projects(report_id)
    schedules = schedule_summary(report_id)

    req_total = int(requirements["total"]) if requirements else 0
    req_complete = int(requirements["complete"]) if requirements else 0
    req_pending = int(requirements["pending"]) if requirements else 0
    req_incomplete = int(requirements["incomplete"]) if requirements else 0
    nuc_records = sum(int(row["records"]) for row in nuclei["careers"])
    nuc_evaluated = sum(int(row["evaluated"]) for row in nuclei["careers"])
    nuc_approved = sum(int(row["approved"]) for row in nuclei["careers"])
    nuc_failed = sum(int(row["failed"]) for row in nuclei["careers"])
    nuc_unevaluated = sum(int(row["unevaluated"]) for row in nuclei["careers"])
    nuc_zero_noeval = sum(
        nucleus_state(student) == "unevaluated" and number(student.get("final_grade")) == 0
        for course in nuclei["courses"]
        for student in course.get("students", [])
    )
    comp = complexive["totals"]
    project = projects.get("summary") or {}
    project_total = int(project.get("total") or 0)
    project_approved = int(project.get("approved") or 0)
    project_failed = int(project.get("failed") or 0)
    project_incomplete = max(0, project_total - project_approved - project_failed)

    indicators = {
        "requirements_compliance": metric("Cumplimiento integral de requisitos", req_complete, req_total, "REGISTRADOS"),
        "nuclei_approval": metric("Aprobación Núcleos", nuc_approved, nuc_evaluated, "EVALUADOS"),
        "complexive_approval": metric("Aprobación Complexivo", int(comp.get("final_approved") or 0), int(comp.get("registered") or 0), "REGISTRADOS"),
        "supplementary_effectiveness": metric("Efectividad supletorio", int(comp.get("recovered") or 0), int(comp.get("supplementary") or 0), "PARTICIPANTES_SUPLETORIO"),
        "thesis_approval": metric("Aprobación Trabajo de Titulación", project_approved, project_approved + project_failed, "EVALUADOS"),
        "schedule_documented": metric("Actividades con ejecución registrada", schedules["evaluated"], schedules["total"], "ACTIVIDADES_PLANIFICADAS"),
    }
    return {
        "report": report,
        "requirements": {"registered": req_total, "complete": req_complete, "pending": req_pending, "incomplete": req_incomplete},
        "nuclei": {
            "courses": len(nuclei["courses"]),
            "records": nuc_records,
            "evaluated": nuc_evaluated,
            "approved": nuc_approved,
            "failed": nuc_failed,
            "unevaluated": nuc_unevaluated,
            "zero_noeval": nuc_zero_noeval,
            "institutional_stats": nuclei["institutional_stats"],
            "careers": nuclei["careers"],
            "course_rows": nuclei.get("course_rows", []),
        },
        "complexive": {"registered": int(comp.get("registered") or 0), "approved": int(comp.get("final_approved") or 0), "failed": int(comp.get("final_failed") or 0), "not_evaluated": int(comp.get("not_evaluated") or 0), "supplementary": int(comp.get("supplementary") or 0), "recovered": int(comp.get("recovered") or 0), "careers": complexive.get("rows", [])},
        "thesis": {
            "total": project_total,
            "approved": project_approved,
            "failed": project_failed,
            "incomplete": project_incomplete,
            "average_final": project.get("average_final"),
        },
        "schedules": schedules,
        "indicators": indicators,
        "comparisons": {"nuclei_vs_complexive": metric_gap(indicators["nuclei_approval"], indicators["complexive_approval"])},
    }


def formula_checks(metrics: dict[str, Any], reconciliation_data: dict[str, Any]) -> list[dict[str, Any]]:
    req, nuc, comp, thesis = metrics["requirements"], metrics["nuclei"], metrics["complexive"], metrics["thesis"]
    return [
        {"name": "Balance de requisitos", "ok": req["complete"] + req["pending"] + req["incomplete"] == req["registered"], "formula": f"{req['complete']} + {req['pending']} + {req['incomplete']} = {req['registered']}"},
        {"name": "Balance de evaluados en Núcleos", "ok": nuc["approved"] + nuc["failed"] == nuc["evaluated"], "formula": f"{nuc['approved']} + {nuc['failed']} = {nuc['evaluated']}"},
        {"name": "Balance total de Núcleos", "ok": nuc["evaluated"] + nuc["unevaluated"] == nuc["records"], "formula": f"{nuc['evaluated']} + {nuc['unevaluated']} = {nuc['records']}"},
        {"name": "Balance del Examen Complexivo", "ok": comp["approved"] + comp["failed"] + comp["not_evaluated"] == comp["registered"], "formula": f"{comp['approved']} + {comp['failed']} + {comp['not_evaluated']} = {comp['registered']}"},
        {"name": "Recuperados de supletorio", "ok": comp["recovered"] <= comp["supplementary"], "formula": f"{comp['recovered']} ≤ {comp['supplementary']}"},
        {"name": "Balance de Trabajo de Titulación", "ok": thesis["approved"] + thesis["failed"] + thesis["incomplete"] == thesis["total"], "formula": f"{thesis['approved']} + {thesis['failed']} + {thesis['incomplete']} = {thesis['total']}"},
        {"name": "Conciliación de cursos importados", "ok": bool(reconciliation_data["balanced"]), "formula": f"{reconciliation_data['included']} + {reconciliation_data['excluded']} = {reconciliation_data['imported']}"},
    ]


def no_evaluated_zero_count(report_id: int) -> int:
    return sum(
        nucleus_state(student) == "unevaluated" and number(student.get("final_grade")) == 0
        for course in strict_nuclei(report_id)["courses"]
        for student in course.get("students", [])
    )


def _source_mode(metrics: dict[str, Any], source: dict[str, Any]) -> str:
    total = metrics["requirements"]["registered"] + metrics["nuclei"]["records"] + metrics["complexive"]["registered"] + metrics["thesis"]["total"]
    if total:
        return "normal"
    if source["exists"] and source["source_modality_count"] == 0:
        return "no_population"
    return "import_error"


def control(name: str, status: str, detail: str, blocking: bool = False) -> dict[str, Any]:
    return {"name": name, "status": status, "ok": status == "ok", "detail": detail, "blocking": blocking}


def audit_report(report_id: int, resolve_resources: bool = True) -> dict[str, Any]:
    if resolve_resources:
        resolve_logo(report_id)
    metrics = report_metrics(report_id)
    population = nuclei_population_integrity.reconcile_population(report_id, refresh=False)
    source = source_context(metrics["report"])
    mode = _source_mode(metrics, source)
    reconciliation_data = reconciliation(report_id)
    duplicates = duplicate_summary(report_id)
    states = status_summary(report_id)
    formulas = formula_checks(metrics, reconciliation_data)
    schedules = metrics["schedules"]
    zero_noeval = int(metrics["nuclei"].get("zero_noeval") or 0)
    refreshed = metrics["report"]
    logo_ok = bool(report_quality.base.image_path(report_quality.base.image_for(refreshed, report_quality.base.LOGO)))

    period_text = str(refreshed.get("period") or "").strip()
    report_name = str(refreshed.get("name") or "").strip()
    period_in_name = not period_text or period_text.casefold() in report_name.casefold()

    nuclei_courses = strict_nuclei(report_id).get("courses", [])
    singleton_courses = [
        str(course.get("course_title") or course.get("course_key") or "Curso sin nombre")
        for course in nuclei_courses
        if len(course.get("students", [])) == 1
    ]
    nuclei_records = int(metrics["nuclei"].get("records") or 0)
    small_sample = 0 < nuclei_records < 10

    formula_errors = [item for item in formulas if not item["ok"]]
    controls = [
        control("Registros conciliados", "ok" if reconciliation_data["balanced"] else "error", f"Importados: {reconciliation_data['imported']}; incluidos: {reconciliation_data['included']}; excluidos: {reconciliation_data['excluded']}.", not reconciliation_data["balanced"]),
        control(
            "Población maestra de Núcleos conciliada",
            "ok" if population["ok"] else "error",
            (
                f"Esperados en ruta Complexivo: {population['expected_students']}; "
                f"con registros de Núcleos: {population['with_nuclei']}; "
                f"sin Núcleos: {population['missing_students']}; "
                f"cobertura: {population['coverage'] if population['coverage'] is not None else 'No aplica'} %. "
                f"Registros fuente sin conciliar: {population['source_links']['pending_records']}; "
                f"ambiguos/revisión: {population['source_links']['conflicts']}; "
                f"conflictos de ruta: {population['source_links']['route_conflicts']}."
            ),
            not population["ok"],
        ),
        control("Duplicados resueltos", "warning" if duplicates["unresolved_probable"] else "ok", f"Exactos omitidos en Núcleos: {duplicates['nuclei_exact_omitted']}; probables pendientes: {duplicates['unresolved_probable']}."),
        control("Estados válidos", "warning" if states["pending_classification"] else "ok", f"Pendientes de clasificar: {states['pending_classification']}." if states["pending_classification"] else "Los estados pertenecen al catálogo institucional."),
        control("Cronograma sin duplicados", "error" if schedules["duplicates"] else "ok", f"Duplicados detectados: {schedules['duplicates']}.", bool(schedules["duplicates"])),
        control("Fórmulas correctas", "error" if formula_errors else "ok", "; ".join(item["name"] for item in formula_errors) if formula_errors else "Todos los balances matemáticos principales son consistentes.", bool(formula_errors)),
        control("No evaluados tratados correctamente", "ok", f"{zero_noeval} registro(s) con estado No evaluado y nota 0 fueron excluidos de las estadísticas."),
        control("Actividades ejecutadas documentadas", "warning" if schedules["pending_evaluation"] or schedules["incomplete_evidence"] else "ok", f"Sin evaluar: {schedules['pending_evaluation']}; con evidencia incompleta: {schedules['incomplete_evidence']}."),
        control(
            "Coherencia temporal del informe",
            "ok" if period_in_name else "error",
            "El período del nombre coincide con el período académico configurado."
            if period_in_name
            else f"El nombre del informe no contiene el período configurado «{period_text}».",
            not period_in_name,
        ),
        control(
            "Granularidad de Núcleos",
            "warning" if singleton_courses else "ok",
            (
                f"{len(singleton_courses)} curso(s) contienen un solo estudiante en la fuente. "
                "El PDF mostrará la población consolidada por carrera antes del detalle por curso; "
                "los cursos individuales no se interpretan como la cohorte completa."
            )
            if singleton_courses
            else "Los cursos de Núcleos contienen poblaciones nominales consistentes con la fuente.",
        ),
        control(
            "Tamaño muestral para inferencias",
            "warning" if small_sample else "ok",
            (
                f"Núcleos contiene {nuclei_records} registros; el tamaño es reducido para formular conclusiones institucionales generales."
            )
            if small_sample
            else f"Núcleos contiene {nuclei_records} registros; no se activa la alerta de muestra reducida.",
        ),
        control("Logo institucional", "ok" if logo_ok else "error", "Logo institucional disponible." if logo_ok else "Falta el logo institucional obligatorio.", not logo_ok),
    ]
    if mode == "no_population":
        controls.append(control("Datos faltantes", "ok", "La fuente confirma que no existen registros de esta modalidad para el período."))
    elif mode == "import_error":
        controls.append(control("Datos faltantes", "error", "No hay población procesada y la fuente no confirma una ausencia real. Revise la carga.", True))
    else:
        missing = [name for name, total in (("Requisitos", metrics["requirements"]["registered"]), ("Núcleos", metrics["nuclei"]["records"]), ("Complexivo", metrics["complexive"]["registered"]), ("Trabajo de Titulación", metrics["thesis"]["total"])) if total == 0]
        controls.append(control("Datos faltantes", "warning" if missing else "ok", "Sin registros en: " + ", ".join(missing) + "." if missing else "Los módulos con población registran información."))

    critical_pending = (
        metrics["requirements"]["pending"] + metrics["requirements"]["incomplete"] +
        metrics["nuclei"]["unevaluated"] + metrics["complexive"]["not_evaluated"] +
        metrics["thesis"]["incomplete"] + schedules["pending_evaluation"] +
        schedules["incomplete_evidence"] + states["pending_classification"] +
        duplicates["unresolved_probable"] +
        population["missing_students"] +
        population["source_links"]["pending_records"] +
        population["source_links"]["conflicts"] +
        population["source_links"]["route_conflicts"]
    )
    blocking_errors = [item for item in controls if item["status"] == "error" and item["blocking"]]
    can_generate = not blocking_errors and mode != "import_error"
    # El documento solicitado es final. La ausencia de información opcional no
    # cambia el nombre a "Preliminar": esos campos/columnas se omiten y el audit
    # mantiene las advertencias para trazabilidad. Solo un error bloqueante impide
    # emitir el informe final.
    final_ready = mode == "normal" and can_generate
    if mode == "no_population":
        state, title = "SIN POBLACIÓN", "Informe Final del Proceso de Titulación - Sin Población Registrada"
    elif not can_generate:
        state, title = "ERROR DE CARGA", "Informe Final del Proceso de Titulación"
    elif critical_pending:
        state, title = "APTO PARA EMITIR CON DATOS DISPONIBLES", "Informe Final del Proceso de Titulación"
    else:
        state, title = "APTO PARA EMITIR", "Informe Final del Proceso de Titulación"
    return {
        "ok": can_generate,
        "report_id": report_id,
        "mode": mode,
        "state": state,
        "document_title": title,
        "final_ready": final_ready,
        "can_generate_pdf": can_generate,
        "critical_pending": critical_pending,
        "controls": controls,
        "blocking_errors": blocking_errors,
        "metrics": metrics,
        "reconciliation": reconciliation_data,
        "nuclei_population": population,
        "duplicates": duplicates,
        "states": states,
        "formulas": formulas,
        "source": source,
    }
