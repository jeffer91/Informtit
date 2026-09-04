from __future__ import annotations

import re
from statistics import mean
from typing import Any

import app as core
import firebase_sync_runtime as firebase
import nuclei_multicampus
import student_domain_bridge
from coordinator_registry import normalize
from db import connection, rows_to_dicts, utcnow
from import_service import clean_cell

_INSTALLED = False
_STATE: dict[str, dict[str, Any]] = {}


def _table(conn: Any, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def _columns(conn: Any, name: str) -> set[str]:
    if not _table(conn, name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _context(report_id: int) -> tuple[str, list[int]]:
    with connection() as conn:
        report = conn.execute("SELECT * FROM reports WHERE id=?", (int(report_id),)).fetchone()
        if not report:
            raise ValueError("El informe no existe.")
        period_id = clean_cell(report["firebase_period_id"]) if "firebase_period_id" in report.keys() else ""
        if not period_id:
            raise ValueError("El informe no tiene un período Firebase asociado.")
        ids = [int(report_id)]
        if "period_project_id" in _columns(conn, "reports") and report["period_project_id"] is not None:
            ids = [int(row[0]) for row in conn.execute(
                "SELECT id FROM reports WHERE period_project_id=? ORDER BY id",
                (int(report["period_project_id"]),),
            ).fetchall()] or ids
        else:
            ids = [int(row[0]) for row in conn.execute(
                "SELECT id FROM reports WHERE firebase_period_id=? ORDER BY id", (period_id,)
            ).fetchall()] or ids
    return period_id, ids


def _masters(report_ids: list[int]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    placeholders = ",".join("?" for _ in report_ids)
    rows: list[dict[str, Any]] = []
    with connection() as conn:
        if _table(conn, "period_students"):
            rows = rows_to_dicts(conn.execute(
                f"SELECT * FROM period_students WHERE report_id IN ({placeholders}) ORDER BY id",
                tuple(report_ids),
            ).fetchall())
        if not rows and _table(conn, "requirements_students"):
            rows = rows_to_dicts(conn.execute(
                f"SELECT * FROM requirements_students WHERE report_id IN ({placeholders}) ORDER BY id",
                tuple(report_ids),
            ).fetchall())
    by_id: dict[str, dict[str, Any]] = {}
    by_email: dict[str, dict[str, Any]] = {}
    for row in rows:
        cedula = clean_cell(row.get("identification"))
        email = clean_cell(row.get("email")).lower()
        if cedula and not cedula.upper().startswith(("NOID:", "REQ-")):
            by_id[cedula] = row
        if email:
            by_email[email] = row
    return by_id, by_email


def _grade(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 100 else None


def _status(value: Any, grade: float | None = None) -> str:
    text = clean_cell(value).upper()
    if text in {"APR", "APROBADA", "APROBADO"}:
        return "APROBADO"
    if text in {"REP", "REPROBADA", "REPROBADO", "SUSPENSO"}:
        return "REPROBADO"
    return "APROBADO" if grade is not None and grade >= 7 else "REPROBADO" if grade is not None else "NO EVALUADO"


def _doc_id(period_id: str, cedula: str, nucleus: int) -> str:
    return f"{period_id}__{cedula}__N{int(nucleus)}"


def _remote(period_id: str) -> list[dict[str, Any]]:
    return [
        row for row in firebase.query_equal("nucleos", "periodoId", period_id)
        if clean_cell(row.get("cedula"))
        and int(row.get("nucleo") or 0) in {1, 2, 3, 4}
        and row.get("notaFinal") is not None
        and not bool(row.get("eliminado"))
    ]


def _local_documents(report_id: int) -> list[tuple[str, dict[str, Any]]]:
    student_domain_bridge.ensure_bridge_schema()
    nuclei_multicampus.ensure_multicampus_schema()
    period_id, report_ids = _context(report_id)
    by_id, by_email = _masters(report_ids)
    placeholders = ",".join("?" for _ in report_ids)
    with connection() as conn:
        rows = rows_to_dicts(conn.execute(
            f"""
            SELECT ns.period_student_id, ns.full_name, ns.email, ns.final_grade, ns.final_status,
                   c.career_name, c.nucleus_number, c.campus, c.course_key, c.course_title,
                   ps.identification AS master_id, ps.full_name AS master_name,
                   ps.email AS master_email, ps.career_name AS master_career,
                   ps.modality AS master_modality, ps.campus AS master_campus
            FROM nucleus_instance_students ns
            JOIN nucleus_course_instances c ON c.id=ns.course_id
            LEFT JOIN period_students ps ON ps.id=ns.period_student_id
            WHERE c.report_id IN ({placeholders})
            ORDER BY c.id, ns.id
            """,
            tuple(report_ids),
        ).fetchall())
    output: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for row in rows:
        grade = _grade(row.get("final_grade"))
        nucleus = int(row.get("nucleus_number") or 0)
        if grade is None or nucleus not in {1, 2, 3, 4}:
            continue
        master = None
        cedula = clean_cell(row.get("master_id"))
        if cedula:
            master = by_id.get(cedula)
        if not master:
            master = by_email.get(clean_cell(row.get("email")).lower())
            cedula = clean_cell(master.get("identification")) if master else ""
        if not cedula or cedula.upper().startswith(("NOID:", "REQ-")):
            continue
        key = _doc_id(period_id, cedula, nucleus)
        if key in seen:
            continue
        seen.add(key)
        master = master or by_id.get(cedula) or {}
        output.append((key, {
            "periodoId": period_id,
            "cedula": cedula,
            "nucleo": nucleus,
            "notaFinal": grade,
            "estado": _status(row.get("final_status"), grade),
            "nombre": clean_cell(master.get("full_name") or row.get("full_name") or cedula),
            "correo": clean_cell(master.get("email") or row.get("email")).lower(),
            "carrera": clean_cell(master.get("career_name") or row.get("career_name")),
            "sede": clean_cell(master.get("campus") or row.get("campus")),
            "modalidad": clean_cell(master.get("modality")),
            "courseKey": clean_cell(row.get("course_key")),
            "curso": clean_cell(row.get("course_title")) or f"Núcleo {nucleus}",
            "source": "Informtit npm start",
            "version": 2,
            "updatedAt": utcnow(),
            "eliminado": False,
        }))
    return output


def _course_key(career: str, nucleus: int, campus: str, remote: dict[str, Any]) -> str:
    return clean_cell(remote.get("courseKey")) or "firebase|" + "|".join(
        (normalize(career), str(nucleus), normalize(campus))
    )


def _ensure_course(conn: Any, report_id: int, master: dict[str, Any], remote: dict[str, Any]) -> int:
    career = clean_cell(remote.get("carrera") or master.get("career_name") or "Sin carrera")
    nucleus = int(remote.get("nucleo") or 1)
    campus = clean_cell(remote.get("sede") or master.get("campus"))
    key = _course_key(career, nucleus, campus, remote)
    found = conn.execute(
        "SELECT id FROM nucleus_course_instances WHERE report_id=? AND course_key=?",
        (report_id, key),
    ).fetchone()
    if found:
        return int(found[0])
    compatible = conn.execute(
        """
        SELECT id FROM nucleus_course_instances
        WHERE report_id=? AND nucleus_number=? AND upper(trim(career_name))=upper(trim(?))
          AND (trim(?)='' OR upper(trim(campus))=upper(trim(?)))
        ORDER BY id
        """,
        (report_id, nucleus, career, campus, campus),
    ).fetchall()
    if len(compatible) == 1:
        return int(compatible[0][0])
    now = utcnow()
    cursor = conn.execute(
        """
        INSERT INTO nucleus_course_instances
        (report_id, career_name, nucleus_number, campus, module_code, period_label,
         group_code, schedule, course_key, course_title, teacher_name, teacher_candidates,
         coordinator_name, coordinator_program, coordinator_telegram, participant_students,
         graded_students, matched_students, missing_grades, extra_grades, course_average,
         approved_count, failed_count, unevaluated_count, activity_averages, raw_grades,
         raw_participants, created_at, updated_at)
        VALUES (?, ?, ?, ?, '', '', '', '', ?, ?, '', '[]', '', '', '', 0, 0, 0,
                0, 0, NULL, 0, 0, 0, '[]', '', '', ?, ?)
        """,
        (report_id, career, nucleus, campus, key, clean_cell(remote.get("curso")) or f"Núcleo {nucleus}", now, now),
    )
    return int(cursor.lastrowid)


def _recount(conn: Any, course_id: int) -> None:
    rows = conn.execute(
        "SELECT final_grade, final_status FROM nucleus_instance_students WHERE course_id=?", (course_id,)
    ).fetchall()
    grades = [float(row["final_grade"]) for row in rows if row["final_grade"] is not None]
    approved = sum(_status(row["final_status"], float(row["final_grade"]) if row["final_grade"] is not None else None) == "APROBADO" for row in rows)
    failed = sum(_status(row["final_status"], float(row["final_grade"]) if row["final_grade"] is not None else None) == "REPROBADO" for row in rows)
    unevaluated = max(len(rows) - approved - failed, 0)
    conn.execute(
        """
        UPDATE nucleus_course_instances SET participant_students=?, graded_students=?, matched_students=?,
            missing_grades=?, course_average=?, approved_count=?, failed_count=?, unevaluated_count=?, updated_at=?
        WHERE id=?
        """,
        (len(rows), len(grades), len(rows), unevaluated, round(mean(grades), 2) if grades else None,
         approved, failed, unevaluated, utcnow(), course_id),
    )


def _pull(report_id: int, remote_rows: list[dict[str, Any]]) -> dict[str, int]:
    student_domain_bridge.ensure_bridge_schema()
    nuclei_multicampus.ensure_multicampus_schema()
    _, report_ids = _context(report_id)
    by_id, _ = _masters(report_ids)
    restored = ignored = 0
    touched: set[int] = set()
    with connection() as conn:
        for remote in remote_rows:
            cedula = clean_cell(remote.get("cedula"))
            master = by_id.get(cedula)
            grade = _grade(remote.get("notaFinal"))
            nucleus = int(remote.get("nucleo") or 0)
            if not master or grade is None or nucleus not in {1, 2, 3, 4}:
                ignored += 1
                continue
            destination_report = int(master.get("report_id") or report_id)
            course_id = _ensure_course(conn, destination_report, master, remote)
            touched.add(course_id)
            period_student_id = master.get("id") if _table(conn, "period_students") else None
            email = clean_cell(master.get("email") or remote.get("correo")).lower()
            name = clean_cell(master.get("full_name") or remote.get("nombre") or cedula)
            state = _status(remote.get("estado"), grade)
            existing = None
            if period_student_id:
                existing = conn.execute(
                    "SELECT id FROM nucleus_instance_students WHERE course_id=? AND period_student_id=?",
                    (course_id, int(period_student_id)),
                ).fetchone()
            if not existing and email:
                existing = conn.execute(
                    "SELECT id FROM nucleus_instance_students WHERE course_id=? AND lower(trim(email))=?",
                    (course_id, email),
                ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE nucleus_instance_students SET full_name=?, email=?, final_grade=?, final_status=?,
                        participant_found=1, period_student_id=?, match_status='OK',
                        match_method='FIREBASE_CEDULA', match_confidence=100 WHERE id=?
                    """,
                    (name, email, grade, state, period_student_id, int(existing[0])),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO nucleus_instance_students
                    (course_id, full_name, email, final_grade, final_status, participant_found,
                     period_student_id, match_status, match_method, match_confidence)
                    VALUES (?, ?, ?, ?, ?, 1, ?, 'OK', 'FIREBASE_CEDULA', 100)
                    """,
                    (course_id, name, email, grade, state, period_student_id),
                )
            restored += 1
        for course_id in touched:
            _recount(conn, course_id)
    return {"restored": restored, "ignored": ignored}


def sync_nuclei(report_id: int, *, force_push: bool = False) -> dict[str, Any]:
    period_id, _ = _context(report_id)
    state: dict[str, Any] = {
        "ok": False, "periodoId": period_id, "pushed": 0, "unchanged": 0,
        "pulled": 0, "ignored": 0, "error": "", "updatedAt": utcnow(),
    }
    try:
        remote_before = _remote(period_id)
        existing = {clean_cell(row.get("_id")) or _doc_id(period_id, clean_cell(row.get("cedula")), int(row.get("nucleo") or 0)) for row in remote_before}
        for doc_id, data in _local_documents(report_id):
            if force_push or doc_id not in existing:
                firebase.write_document("nucleos", doc_id, data)
                state["pushed"] += 1
            else:
                state["unchanged"] += 1
        pulled = _pull(report_id, _remote(period_id))
        state["pulled"] = pulled["restored"]
        state["ignored"] = pulled["ignored"]
        state["ok"] = True
    except Exception as error:
        state["error"] = clean_cell(error)
    _STATE[period_id] = state
    return state


def status_for(report_id: int) -> dict[str, Any]:
    period_id, _ = _context(report_id)
    return _STATE.get(period_id) or {
        "ok": True, "periodoId": period_id, "pending": True,
        "pushed": 0, "unchanged": 0, "pulled": 0, "ignored": 0,
        "error": "", "updatedAt": "",
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    student_domain_bridge.ensure_bridge_schema()
    nuclei_multicampus.ensure_multicampus_schema()
    previous_get = core.InformtitHandler._handle_api_get
    previous_write = core.InformtitHandler._handle_api_write

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/firebase/nuclei-sync-status":
            values = query.get("report_id") or []
            report_id = int(values[0]) if values and str(values[0]).isdigit() else 0
            if not report_id:
                raise ValueError("Seleccione un informe.")
            self._send_json(status_for(report_id))
            return
        match = re.fullmatch(r"/api/reports/(\d+)/nuclei", path)
        if match:
            # Al abrir Núcleos: sube al Firebase común solo lo que todavía no existe
            # y después restaura la versión compartida en SQLite.
            sync_nuclei(int(match.group(1)), force_push=False)
        previous_get(self, path, query)

    def handle_write(self: Any, method: str, path: str, payload: dict[str, Any]) -> None:
        match = re.match(r"^/api/reports/(\d+)/nuclei(?:/|$)", path)
        previous_write(self, method, path, payload)
        if match and method in {"POST", "PUT", "PATCH", "DELETE"} and not path.endswith("/analyze"):
            # Una edición hecha en npm start sí prevalece y se publica de inmediato.
            # Los borrados locales no eliminan notas remotas automáticamente.
            sync_nuclei(int(match.group(1)), force_push=True)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
    _INSTALLED = True
