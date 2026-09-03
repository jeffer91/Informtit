from __future__ import annotations

import hashlib
import json
from difflib import SequenceMatcher
from typing import Any

from db import connection, rows_to_dicts, utcnow
from parser import canonical_name_key, clean_moodle_name
from workflow_rules import downstream_state, prerequisite_state

ROUTE_COMPLEXIVE = "COMPLEXIVO"
ROUTE_THESIS = "TRABAJO_TITULACION"
ROUTE_ARTICLE = "ARTICULO"
ROUTES = {ROUTE_COMPLEXIVE, ROUTE_THESIS, ROUTE_ARTICLE}

PROCESS_ACTIVE = "ACTIVO"
PROCESS_WITH_ONE_MISSING = "NO_APROBADO_REQUISITO"
PROCESS_RETIRED = "RETIRADO"
PROCESS_STATUSES = {PROCESS_ACTIVE, PROCESS_WITH_ONE_MISSING, PROCESS_RETIRED}

MATCH_OK = "OK"
MATCH_REVIEW = "REVIEW_REQUIRED"
MATCH_UNMATCHED = "UNMATCHED"
MATCH_AMBIGUOUS = "AMBIGUOUS"
MATCH_ROUTE_CONFLICT = "ROUTE_CONFLICT"
MATCH_GRADE_CONFLICT = "GRADE_CONFLICT"
MATCH_OFFICIAL_CONFLICT = "OFFICIAL_DATA_CONFLICT"


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _fold(value: Any) -> str:
    return canonical_name_key(clean_moodle_name(str(value or "")))


def _email(value: Any) -> str:
    return str(value or "").strip().casefold()


def _id_number(value: Any) -> str:
    """Normaliza identificaciones numéricas sin confundir claves internas locales.

    Las claves NOID:/REQ- contienen letras y por tanto nunca se consideran una
    identificación oficial. Se preserva compatibilidad con datos históricos y
    pruebas que puedan usar identificaciones numéricas cortas.
    """
    raw = str(value or "").strip()
    if not raw or any(character.isalpha() for character in raw):
        return ""
    return "".join(character for character in raw if character.isdigit())


def _synthetic_identification(row: dict[str, Any]) -> str:
    """Clave local determinista para registros de Requisitos sin cédula."""
    institutional = _email(row.get("email"))
    if institutional:
        return f"NOID:EMAIL:{institutional}"
    personal = _email(row.get("personal_email"))
    if personal:
        return f"NOID:PERSONAL:{personal}"
    payload = "|".join(
        (
            _fold(row.get("full_name")),
            str(row.get("career_code") or "").strip().casefold(),
            _fold(row.get("career_name")),
            str(row.get("modality") or "").strip().casefold(),
            str(row.get("campus") or "").strip().casefold(),
            str(row.get("schedule") or "").strip().casefold(),
        )
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:24]
    return f"NOID:PROFILE:{digest}"


def _stable_identification(row: dict[str, Any]) -> str:
    return _id_number(row.get("identification")) or _synthetic_identification(row)


def _existing_master(conn: Any, report_id: int, identification: str, row: dict[str, Any]) -> Any:
    """Resuelve un maestro existente incluso al migrar antiguas claves REQ-<id>."""
    existing = conn.execute(
        "SELECT * FROM period_students WHERE report_id=? AND identification=?",
        (report_id, identification),
    ).fetchone()
    if existing:
        return existing

    if identification.startswith("NOID:"):
        legacy = conn.execute(
            "SELECT * FROM period_students WHERE report_id=? AND identification=?",
            (report_id, f"REQ-{int(row['id'])}"),
        ).fetchone()
        if legacy:
            return legacy

        email = _email(row.get("email"))
        if email:
            matches = conn.execute(
                "SELECT * FROM period_students WHERE report_id=? AND lower(trim(email))=? ORDER BY id",
                (report_id, email),
            ).fetchall()
            if len(matches) == 1:
                return matches[0]

        name = _fold(row.get("full_name"))
        career = _fold(row.get("career_name"))
        if name:
            candidates = conn.execute(
                "SELECT * FROM period_students WHERE report_id=? ORDER BY id",
                (report_id,),
            ).fetchall()
            matches = [
                candidate
                for candidate in candidates
                if _fold(candidate["full_name"]) == name
                and (not career or _fold(candidate["career_name"]) == career)
            ]
            if len(matches) == 1:
                return matches[0]
    return None


def ensure_student_domain_schema() -> None:
    """Crea el dominio maestro local sin alterar colecciones Firebase compartidas."""
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS period_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_project_id INTEGER,
                report_id INTEGER NOT NULL,
                requirements_student_id INTEGER,
                identification TEXT DEFAULT '',
                full_name TEXT NOT NULL,
                email TEXT DEFAULT '',
                personal_email TEXT DEFAULT '',
                career_code TEXT DEFAULT '',
                career_name TEXT DEFAULT '',
                modality TEXT DEFAULT '',
                campus TEXT DEFAULT '',
                schedule TEXT DEFAULT '',
                route TEXT NOT NULL DEFAULT 'COMPLEXIVO',
                route_source TEXT NOT NULL DEFAULT 'DEFAULT',
                process_status TEXT NOT NULL DEFAULT 'ACTIVO',
                process_status_source TEXT NOT NULL DEFAULT 'DERIVED',
                reconciliation_status TEXT NOT NULL DEFAULT 'OK',
                reconciliation_detail TEXT DEFAULT '',
                official_graduated INTEGER NOT NULL DEFAULT 0,
                official_titulation_completed INTEGER NOT NULL DEFAULT 0,
                missing_requirements_json TEXT NOT NULL DEFAULT '[]',
                source_snapshot_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
                UNIQUE(report_id, identification)
            );
            CREATE INDEX IF NOT EXISTS idx_period_students_project
                ON period_students(period_project_id, modality, career_name);
            CREATE INDEX IF NOT EXISTS idx_period_students_route
                ON period_students(report_id, route, process_status);
            CREATE INDEX IF NOT EXISTS idx_period_students_name
                ON period_students(report_id, full_name);

            CREATE TABLE IF NOT EXISTS student_source_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                period_student_id INTEGER,
                source_module TEXT NOT NULL,
                source_key TEXT NOT NULL,
                source_name TEXT DEFAULT '',
                source_email TEXT DEFAULT '',
                source_identification TEXT DEFAULT '',
                source_career TEXT DEFAULT '',
                match_status TEXT NOT NULL DEFAULT 'UNMATCHED',
                match_method TEXT DEFAULT '',
                match_confidence REAL,
                candidates_json TEXT NOT NULL DEFAULT '[]',
                detail TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
                FOREIGN KEY(period_student_id) REFERENCES period_students(id) ON DELETE SET NULL,
                UNIQUE(report_id, source_module, source_key)
            );
            CREATE INDEX IF NOT EXISTS idx_student_source_links_student
                ON student_source_links(period_student_id, source_module);

            CREATE TABLE IF NOT EXISTS student_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                period_student_id INTEGER,
                action TEXT NOT NULL,
                field_name TEXT DEFAULT '',
                old_value TEXT DEFAULT '',
                new_value TEXT DEFAULT '',
                detail TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
                FOREIGN KEY(period_student_id) REFERENCES period_students(id) ON DELETE SET NULL
            );
            """
        )


def _report_project_id(conn: Any, report_id: int) -> int | None:
    columns = _columns(conn, "reports")
    if "period_project_id" not in columns:
        return None
    row = conn.execute("SELECT period_project_id FROM reports WHERE id=?", (report_id,)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _default_route_for_report(conn: Any, report_id: int) -> str:
    """PVC/Artículo es automático; los períodos regulares parten por Complexivo.

    Las bases antiguas y los tests mínimos pueden no tener todavía report_type;
    un período no reconocible conserva la política histórica de Complexivo.
    """
    columns = _columns(conn, "reports")
    if "report_type" in columns:
        row = conn.execute(
            "SELECT report_type, period FROM reports WHERE id=?",
            (report_id,),
        ).fetchone()
        explicit = str(row["report_type"] or "").strip().lower() if row else ""
    else:
        row = conn.execute(
            "SELECT period FROM reports WHERE id=?",
            (report_id,),
        ).fetchone()
        explicit = ""
    if not row:
        return ROUTE_COMPLEXIVE
    if explicit in {"normal", "pvc"}:
        return ROUTE_ARTICLE if explicit == "pvc" else ROUTE_COMPLEXIVE

    import period_policy_runtime
    if period_policy_runtime.period_months(row["period"]) is None:
        return ROUTE_COMPLEXIVE
    return (
        ROUTE_ARTICLE
        if period_policy_runtime.classify_period(row["period"]) == "pvc"
        else ROUTE_COMPLEXIVE
    )


def _official_flags(row: dict[str, Any]) -> tuple[bool, bool]:
    downstream = downstream_state(row)
    # AprobacionTitulacion es el cierre institucional que el usuario definió
    # como requisito para considerar terminada oficialmente la titulación.
    titulation_completed = bool(downstream["titles_uploaded"])
    graduated = bool(
        downstream["complexive_project_approved"]
        and downstream["titles_uploaded"]
    )
    return graduated, titulation_completed


def _derived_process(row: dict[str, Any]) -> tuple[str, list[str]]:
    state = prerequisite_state(row)
    missing = list(state["missing"])
    if bool(row.get("retired")):
        return PROCESS_RETIRED, missing
    if not missing:
        return PROCESS_ACTIVE, missing
    # No cumplir varios requisitos NO significa que el estudiante esté retirado.
    # RETIRADO proviene exclusivamente de la matrícula/estado administrativo.
    return PROCESS_WITH_ONE_MISSING, missing


def _official_conflicts(row: dict[str, Any]) -> list[str]:
    state = prerequisite_state(row)
    downstream = downstream_state(row)
    issues: list[str] = []
    if state["missing"] and downstream["titulation_marked"]:
        issues.append("Titulación consta CUMPLE pese a existir requisitos habilitantes pendientes.")
    if not downstream["titulation_marked"] and downstream["complexive_project_approved"]:
        issues.append("Aprobación Complexivo/Proyecto consta CUMPLE sin Titulación habilitada.")
    if not downstream["complexive_project_approved"] and downstream["titles_uploaded"]:
        issues.append("Aprobación de Titulación consta CUMPLE sin aprobación Complexivo/Proyecto.")
    return issues


def sync_report_students(report_id: int) -> dict[str, Any]:
    """Sincroniza Requisitos -> estudiante maestro preservando decisiones manuales."""
    ensure_student_domain_schema()
    with connection() as conn:
        if not _table_exists(conn, "requirements_students"):
            return {"ok": True, "students": 0, "created": 0, "updated": 0}
        source = rows_to_dicts(
            conn.execute(
                "SELECT * FROM requirements_students WHERE report_id=? ORDER BY id",
                (report_id,),
            ).fetchall()
        )
        project_id = _report_project_id(conn, report_id)
        now = utcnow()
        created = 0
        updated = 0
        seen_ids: set[int] = set()
        default_route = _default_route_for_report(conn, report_id)

        for row in source:
            identification = _stable_identification(row)
            existing = _existing_master(conn, report_id, identification, row)
            process_status, missing = _derived_process(row)
            graduated, titulation_completed = _official_flags(row)
            conflicts = _official_conflicts(row)
            reconciliation_status = MATCH_OFFICIAL_CONFLICT if conflicts else MATCH_OK
            detail = " ".join(conflicts)
            snapshot = json.dumps(row, ensure_ascii=False, default=str)

            if existing:
                period_student_id = int(existing["id"])
                seen_ids.add(period_student_id)
                final_process = str(existing["process_status"])
                process_source = str(existing["process_status_source"])
                if process_source != "MANUAL":
                    final_process = process_status
                    process_source = "DERIVED"
                final_route = str(existing["route"] or default_route)
                route_source = str(existing["route_source"] or "DEFAULT")
                if route_source != "MANUAL":
                    final_route = default_route
                    route_source = "DEFAULT"
                conn.execute(
                    """
                    UPDATE period_students SET
                        period_project_id=?, requirements_student_id=?, identification=?, full_name=?,
                        email=?, personal_email=?, career_code=?, career_name=?, modality=?, campus=?,
                        schedule=?, route=?, route_source=?, process_status=?, process_status_source=?, reconciliation_status=?,
                        reconciliation_detail=?, official_graduated=?, official_titulation_completed=?,
                        missing_requirements_json=?, source_snapshot_json=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        project_id,
                        row.get("id"),
                        identification,
                        row.get("full_name") or "",
                        _email(row.get("email")),
                        row.get("personal_email") or "",
                        row.get("career_code") or "",
                        row.get("career_name") or "",
                        row.get("modality") or "",
                        row.get("campus") or "",
                        row.get("schedule") or "",
                        final_route,
                        route_source,
                        final_process,
                        process_source,
                        reconciliation_status,
                        detail,
                        int(graduated),
                        int(titulation_completed),
                        json.dumps(missing, ensure_ascii=False),
                        snapshot,
                        now,
                        period_student_id,
                    ),
                )
                updated += 1
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO period_students
                    (period_project_id, report_id, requirements_student_id, identification, full_name, email,
                     personal_email, career_code, career_name, modality, campus, schedule, route, route_source,
                     process_status, process_status_source, reconciliation_status, reconciliation_detail,
                     official_graduated, official_titulation_completed, missing_requirements_json,
                     source_snapshot_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DEFAULT', ?, 'DERIVED', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        report_id,
                        row.get("id"),
                        identification,
                        row.get("full_name") or "",
                        _email(row.get("email")),
                        row.get("personal_email") or "",
                        row.get("career_code") or "",
                        row.get("career_name") or "",
                        row.get("modality") or "",
                        row.get("campus") or "",
                        row.get("schedule") or "",
                        default_route,
                        process_status,
                        reconciliation_status,
                        detail,
                        int(graduated),
                        int(titulation_completed),
                        json.dumps(missing, ensure_ascii=False),
                        snapshot,
                        now,
                        now,
                    ),
                )
                period_student_id = int(cursor.lastrowid)
                seen_ids.add(period_student_id)
                created += 1

        if source:
            rows = conn.execute(
                "SELECT id FROM period_students WHERE report_id=?",
                (report_id,),
            ).fetchall()
            for item in rows:
                student_id = int(item["id"])
                if student_id not in seen_ids:
                    conn.execute(
                        "UPDATE period_students SET reconciliation_status=?, reconciliation_detail=?, updated_at=? WHERE id=?",
                        (MATCH_REVIEW, "El estudiante ya no aparece en la carga actual de Requisitos.", now, student_id),
                    )

    return {"ok": True, "students": len(source), "created": created, "updated": updated}


def get_period_students(report_id: int, *, sync: bool = True) -> dict[str, Any]:
    """Lee la población maestra.

    sync=True mantiene compatibilidad con las pantallas que necesitan refrescar
    Requisitos. Los procesos de conciliación y generación pueden usar sync=False
    cuando ya sincronizaron explícitamente una sola vez.
    """
    if sync:
        sync_report_students(report_id)
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM period_students WHERE report_id=? ORDER BY career_name, full_name, id",
                (report_id,),
            ).fetchall()
        )
        links = rows_to_dicts(
            conn.execute(
                "SELECT * FROM student_source_links WHERE report_id=? ORDER BY source_module, id",
                (report_id,),
            ).fetchall()
        )
    by_student: dict[int, list[dict[str, Any]]] = {}
    for link in links:
        sid = int(link["period_student_id"]) if link.get("period_student_id") else 0
        if sid:
            by_student.setdefault(sid, []).append(link)
    for row in rows:
        try:
            row["missing_requirements"] = json.loads(row.get("missing_requirements_json") or "[]")
        except json.JSONDecodeError:
            row["missing_requirements"] = []
        row["source_links"] = by_student.get(int(row["id"]), [])

    return {
        "ok": True,
        "summary": {
            "students": len(rows),
            "complexive": sum(row["route"] == ROUTE_COMPLEXIVE for row in rows),
            "thesis": sum(row["route"] == ROUTE_THESIS for row in rows),
            "article": sum(row["route"] == ROUTE_ARTICLE for row in rows),
            "graduated": sum(bool(row["official_graduated"]) for row in rows),
            "retired": sum(row["process_status"] == PROCESS_RETIRED for row in rows),
            "one_missing": sum(row["process_status"] == PROCESS_WITH_ONE_MISSING for row in rows),
            "review": sum(row["reconciliation_status"] != MATCH_OK for row in rows),
        },
        "students": rows,
    }


def _validate_route_for_period(default_route: str, route: str) -> None:
    """Impide que una llamada directa al API contradiga la política del período."""
    if default_route == ROUTE_ARTICLE:
        if route != ROUTE_ARTICLE:
            raise ValueError(
                "Los períodos PVC pertenecen automáticamente a Artículo Académico."
            )
        return
    if route == ROUTE_ARTICLE:
        raise ValueError(
            "Artículo Académico solo corresponde a períodos PVC. "
            "En períodos regulares use Complexivo o Trabajo de Titulación."
        )


def set_student_route(report_id: int, student_id: int, route: str) -> dict[str, Any]:
    ensure_student_domain_schema()
    route = str(route or "").strip().upper()
    if route not in ROUTES:
        raise ValueError("La ruta debe ser COMPLEXIVO, TRABAJO_TITULACION o ARTICULO.")
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM period_students WHERE id=? AND report_id=?",
            (student_id, report_id),
        ).fetchone()
        if not row:
            raise ValueError("El estudiante no existe en este período.")

        default_route = _default_route_for_report(conn, report_id)
        _validate_route_for_period(default_route, route)
        old = str(row["route"])
        if default_route == ROUTE_ARTICLE and old == ROUTE_ARTICLE:
            # En PVC la ruta es automática; no se convierte en una decisión manual.
            return {"ok": True, "student_id": student_id, "route": ROUTE_ARTICLE}
        if old == route and str(row["route_source"]) == "MANUAL":
            return {"ok": True, "student_id": student_id, "route": route}
        now = utcnow()
        conn.execute(
            "UPDATE period_students SET route=?, route_source='MANUAL', updated_at=? WHERE id=?",
            (route, now, student_id),
        )
        conn.execute(
            """
            INSERT INTO student_audit_log
            (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
            VALUES (?, ?, 'CHANGE_ROUTE', 'route', ?, ?, 'Cambio manual desde la pantalla de Estudiantes.', ?)
            """,
            (report_id, student_id, old, route, now),
        )

        # Seleccionar Trabajo de Titulación crea inmediatamente su registro local
        # de proceso, aunque todavía no tenga notas. Firebase se publica después,
        # únicamente cuando la auditoría académica esté completa.
        if route == ROUTE_THESIS and _table_exists(conn, "thesis_projects"):
            existing_project = conn.execute(
                "SELECT id FROM thesis_projects WHERE report_id=? AND identification=?",
                (report_id, str(row["identification"] or "")),
            ).fetchone()
            if not existing_project:
                cursor = conn.execute(
                    """
                    INSERT INTO thesis_projects
                    (report_id, identification, full_name, career_code, career_name,
                     raw_text, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, '', ?, ?)
                    """,
                    (
                        report_id,
                        str(row["identification"] or ""),
                        str(row["full_name"] or ""),
                        str(row["career_code"] or ""),
                        str(row["career_name"] or ""),
                        now,
                        now,
                    ),
                )
                project_id = int(cursor.lastrowid)
                columns = _columns(conn, "thesis_projects")
                if "period_student_id" in columns:
                    conn.execute(
                        "UPDATE thesis_projects SET period_student_id=? WHERE id=?",
                        (student_id, project_id),
                    )
    return {"ok": True, "student_id": student_id, "route": route}


def set_process_status(report_id: int, student_id: int, status: str) -> dict[str, Any]:
    ensure_student_domain_schema()
    status = str(status or "").strip().upper()
    if status not in PROCESS_STATUSES:
        raise ValueError("Estado de proceso no válido.")
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM period_students WHERE id=? AND report_id=?",
            (student_id, report_id),
        ).fetchone()
        if not row:
            raise ValueError("El estudiante no existe en este período.")
        old = str(row["process_status"])
        now = utcnow()
        conn.execute(
            "UPDATE period_students SET process_status=?, process_status_source='MANUAL', updated_at=? WHERE id=?",
            (status, now, student_id),
        )
        conn.execute(
            """
            INSERT INTO student_audit_log
            (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
            VALUES (?, ?, 'CHANGE_PROCESS_STATUS', 'process_status', ?, ?, 'Override manual.', ?)
            """,
            (report_id, student_id, old, status, now),
        )
    return {"ok": True, "student_id": student_id, "process_status": status}


def _candidate_score(source: dict[str, Any], student: dict[str, Any]) -> float:
    sid = _id_number(source.get("identification"))
    tid = _id_number(student.get("identification"))
    if sid and tid and sid == tid:
        return 1.0
    semail = _email(source.get("email"))
    temail = _email(student.get("email"))
    if semail and temail and semail == temail:
        return 0.995
    sname = _fold(source.get("full_name"))
    tname = _fold(student.get("full_name"))
    if not sname or not tname:
        return 0.0
    name_score = SequenceMatcher(None, sname, tname).ratio()
    source_career = _fold(source.get("career_name"))
    target_career = _fold(student.get("career_name"))
    if source_career and target_career and source_career != target_career:
        name_score *= 0.80
    return name_score


def build_match_index(students: list[dict[str, Any]]) -> dict[str, Any]:
    """Índices O(1) para resolver primero cédula, correo y nombre+carrera."""
    by_id: dict[str, list[dict[str, Any]]] = {}
    by_email: dict[str, list[dict[str, Any]]] = {}
    by_name_career: dict[tuple[str, str], list[dict[str, Any]]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}

    for student in students:
        sid = _id_number(student.get("identification"))
        email = _email(student.get("email"))
        name = _fold(student.get("full_name"))
        career = _fold(student.get("career_name"))
        if sid:
            by_id.setdefault(sid, []).append(student)
        if email:
            by_email.setdefault(email, []).append(student)
        if name:
            by_name.setdefault(name, []).append(student)
            by_name_career.setdefault((name, career), []).append(student)

    return {
        "students": students,
        "by_id": by_id,
        "by_email": by_email,
        "by_name_career": by_name_career,
        "by_name": by_name,
    }


def _candidate_payload(student: dict[str, Any], similarity: float) -> dict[str, Any]:
    return {
        "student_id": int(student["id"]),
        "identification": student.get("identification") or "",
        "full_name": student.get("full_name") or "",
        "email": student.get("email") or "",
        "career_name": student.get("career_name") or "",
        "similarity": round(similarity * 100, 1),
    }


def match_source_record(
    report_id: int,
    source_module: str,
    source_key: str,
    source: dict[str, Any],
    *,
    persist: bool = True,
    students: list[dict[str, Any]] | None = None,
    match_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Matcher común optimizado.

    Las coincidencias exactas usan índices en memoria. SequenceMatcher solo se
    ejecuta como último recurso cuando no existe cédula, correo ni
    nombre+carrera exactos.
    """
    if students is None:
        students = get_period_students(report_id, sync=False)["students"]
    if match_index is None:
        match_index = build_match_index(students)

    sid = _id_number(source.get("identification"))
    semail = _email(source.get("email"))
    sname = _fold(source.get("full_name"))
    scareer = _fold(source.get("career_name"))

    status = MATCH_UNMATCHED
    method = ""
    selected_id: int | None = None
    score = 0.0
    candidates: list[dict[str, Any]] = []

    exact: list[dict[str, Any]] = []
    exact_method = ""
    exact_score = 0.0

    if sid:
        exact = list(match_index["by_id"].get(sid, []))
        exact_method = "CEDULA"
        exact_score = 1.0
    if not exact and semail:
        exact = list(match_index["by_email"].get(semail, []))
        exact_method = "CORREO"
        exact_score = 0.995
    if not exact and sname:
        exact = list(match_index["by_name_career"].get((sname, scareer), []))
        if not exact and not scareer:
            exact = list(match_index["by_name"].get(sname, []))
        exact_method = "NOMBRE_EXACTO"
        exact_score = 0.99

    if len(exact) == 1:
        student = exact[0]
        status = MATCH_OK
        method = exact_method
        selected_id = int(student["id"])
        score = exact_score
        candidates = [_candidate_payload(student, exact_score)]
    elif len(exact) > 1:
        status = MATCH_AMBIGUOUS
        method = exact_method + "_AMBIGUO"
        score = exact_score
        candidates = [_candidate_payload(student, exact_score) for student in exact[:8]]
    else:
        # Solo los casos sin coincidencia exacta pagan el costo del fuzzy matching.
        ranked = sorted(
            ((_candidate_score(source, student), student) for student in students),
            key=lambda item: (-item[0], str(item[1].get("full_name") or "")),
        )
        top = ranked[0] if ranked else (0.0, None)
        second = ranked[1][0] if len(ranked) > 1 else 0.0
        score, student = top
        if student:
            if score >= 0.97 and (score - second) >= 0.04:
                status, method, selected_id = MATCH_OK, "NOMBRE_ALTA_CONFIANZA", int(student["id"])
            elif score > 0 and abs(score - second) < 0.03:
                status, method = MATCH_AMBIGUOUS, "NOMBRE_AMBIGUO"
            elif score >= 0.85:
                status, method = MATCH_REVIEW, "NOMBRE_POSIBLE"
        candidates = [
            _candidate_payload(item[1], item[0])
            for item in ranked[:8]
            if item[0] > 0
        ]

    result = {
        "status": status,
        "method": method,
        "confidence": round(score * 100, 1) if score else 0.0,
        "period_student_id": selected_id,
        "candidates": candidates,
    }
    if persist:
        save_source_link(report_id, source_module, source_key, source, result)
    return result


def save_source_link(
    report_id: int,
    source_module: str,
    source_key: str,
    source: dict[str, Any],
    match: dict[str, Any],
) -> None:
    ensure_student_domain_schema()
    now = utcnow()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO student_source_links
            (report_id, period_student_id, source_module, source_key, source_name, source_email,
             source_identification, source_career, match_status, match_method, match_confidence,
             candidates_json, detail, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_id, source_module, source_key) DO UPDATE SET
                period_student_id=excluded.period_student_id,
                source_name=excluded.source_name,
                source_email=excluded.source_email,
                source_identification=excluded.source_identification,
                source_career=excluded.source_career,
                match_status=excluded.match_status,
                match_method=excluded.match_method,
                match_confidence=excluded.match_confidence,
                candidates_json=excluded.candidates_json,
                detail=excluded.detail,
                updated_at=excluded.updated_at
            """,
            (
                report_id,
                match.get("period_student_id"),
                source_module,
                source_key,
                source.get("full_name") or "",
                _email(source.get("email")),
                _id_number(source.get("identification")),
                source.get("career_name") or "",
                match.get("status") or MATCH_UNMATCHED,
                match.get("method") or "",
                match.get("confidence"),
                json.dumps(match.get("candidates") or [], ensure_ascii=False),
                match.get("detail") or "",
                now,
                now,
            ),
        )


def confirm_source_link(
    report_id: int,
    source_module: str,
    source_key: str,
    student_id: int,
) -> dict[str, Any]:
    ensure_student_domain_schema()
    with connection() as conn:
        student = conn.execute(
            "SELECT * FROM period_students WHERE id=? AND report_id=?",
            (student_id, report_id),
        ).fetchone()
        if not student:
            raise ValueError("El estudiante seleccionado no existe en este período.")
        link = conn.execute(
            "SELECT * FROM student_source_links WHERE report_id=? AND source_module=? AND source_key=?",
            (report_id, source_module, source_key),
        ).fetchone()
        if not link:
            raise ValueError("El registro de origen ya no existe en la conciliación.")
        old = str(link["period_student_id"] or "")
        now = utcnow()
        conn.execute(
            """
            UPDATE student_source_links SET period_student_id=?, match_status='OK', match_method='MANUAL',
                match_confidence=100, detail='Asociación confirmada manualmente.', updated_at=?
            WHERE id=?
            """,
            (student_id, now, int(link["id"])),
        )
        conn.execute(
            """
            INSERT INTO student_audit_log
            (report_id, period_student_id, action, field_name, old_value, new_value, detail, created_at)
            VALUES (?, ?, 'CONFIRM_MATCH', 'source_link', ?, ?, ?, ?)
            """,
            (report_id, student_id, old, str(student_id), f"{source_module}:{source_key}", now),
        )
    return {"ok": True, "student_id": student_id}


def get_student_audit(report_id: int, student_id: int | None = None) -> dict[str, Any]:
    ensure_student_domain_schema()
    with connection() as conn:
        if student_id:
            rows = rows_to_dicts(
                conn.execute(
                    "SELECT * FROM student_audit_log WHERE report_id=? AND period_student_id=? ORDER BY id DESC",
                    (report_id, student_id),
                ).fetchall()
            )
        else:
            rows = rows_to_dicts(
                conn.execute(
                    "SELECT * FROM student_audit_log WHERE report_id=? ORDER BY id DESC LIMIT 1000",
                    (report_id,),
                ).fetchall()
            )
    return {"ok": True, "audit": rows}


def students_by_route(report_id: int, route: str) -> list[dict[str, Any]]:
    data = get_period_students(report_id)
    return [row for row in data["students"] if row["route"] == route]


def resolve_master_student(
    report_id: int,
    *,
    identification: Any = "",
    email: Any = "",
    full_name: Any = "",
    career_name: Any = "",
) -> dict[str, Any] | None:
    source = {
        "identification": identification,
        "email": email,
        "full_name": full_name,
        "career_name": career_name,
    }
    match = match_source_record(report_id, "LOOKUP", "volatile", source, persist=False)
    if match.get("status") != MATCH_OK or not match.get("period_student_id"):
        return None
    student_id = int(match["period_student_id"])
    return next(
        (row for row in get_period_students(report_id)["students"] if int(row["id"]) == student_id),
        None,
    )
