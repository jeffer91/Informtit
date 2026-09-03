from __future__ import annotations

import json
import os
import re
from statistics import mean
from typing import Any
from urllib.parse import quote

import requests

import analytics
import app as core
import period_policy_runtime as period_policy
import requirements_store
from db import connection, create_default_sections, rows_to_dicts, utcnow
from import_service import clean_cell, settings_for_report
from nuclei_service import ensure_nuclei_schema
from process_service import ensure_process_schema
from thesis_independent import ensure_thesis_schema


PROJECT_ID = clean_cell(os.environ.get("INFORMTIT_FIREBASE_PROJECT_ID")) or "utet-4387a"
API_KEY = (
    clean_cell(os.environ.get("INFORMTIT_FIREBASE_API_KEY"))
    or "AIzaSyCaHf1C0BB0X_H3BDZ1o-UDAsPmLTjsZLA"
)
AUTH_TOKEN = clean_cell(os.environ.get("INFORMTIT_FIREBASE_TOKEN"))

READ_ONLY_COLLECTIONS = {
    "Estudiante",
    "carreras",
    "historial",
    "importaciones",
    "matriculas",
    "periodos",
    "requisitos",
    # Colecciones antiguas: Informtit puede leerlas para compatibilidad, pero
    # desde esta versión ya no vuelve a escribirlas.
    "titulacion",
    "cronogramas",
}
WRITABLE_COLLECTIONS = {"nucleos", "complexivo", "trabajoTitulacion", "articulo"}
ALL_ALLOWED_COLLECTIONS = READ_ONLY_COLLECTIONS | WRITABLE_COLLECTIONS

BASE_URL = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
    "/databases/(default)"
)


def _value_from_firestore(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    if "nullValue" in value:
        return None
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "integerValue" in value:
        try:
            return int(value["integerValue"])
        except (TypeError, ValueError):
            return 0
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "timestampValue" in value:
        return value["timestampValue"]
    if "stringValue" in value:
        return value["stringValue"]
    if "referenceValue" in value:
        return value["referenceValue"]
    if "geoPointValue" in value:
        return dict(value["geoPointValue"])
    if "arrayValue" in value:
        return [
            _value_from_firestore(item)
            for item in (value.get("arrayValue", {}).get("values") or [])
        ]
    if "mapValue" in value:
        return {
            key: _value_from_firestore(item)
            for key, item in (value.get("mapValue", {}).get("fields") or {}).items()
        }
    return None


def _value_to_firestore(value: Any) -> dict[str, Any]:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, (list, tuple)):
        return {
            "arrayValue": {
                "values": [_value_to_firestore(item) for item in value]
            }
        }
    if isinstance(value, dict):
        return {
            "mapValue": {
                "fields": {
                    str(key): _value_to_firestore(item)
                    for key, item in value.items()
                }
            }
        }
    return {"stringValue": str(value)}


def _decode_document(document: dict[str, Any]) -> dict[str, Any]:
    data = {
        key: _value_from_firestore(value)
        for key, value in (document.get("fields") or {}).items()
    }
    name = str(document.get("name") or "")
    data["_id"] = name.rsplit("/", 1)[-1] if name else ""
    data["_createTime"] = document.get("createTime")
    data["_updateTime"] = document.get("updateTime")
    return data


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    allow_404: bool = False,
) -> Any:
    query_params = dict(params or {})
    if API_KEY:
        query_params["key"] = API_KEY
    headers = {"Accept": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    response = requests.request(
        method,
        BASE_URL + path,
        params=query_params,
        json=body,
        headers=headers,
        timeout=35,
    )
    if allow_404 and response.status_code == 404:
        return None
    if response.status_code >= 400:
        detail = ""
        try:
            payload = response.json()
            detail = clean_cell((payload.get("error") or {}).get("message"))
        except Exception:
            detail = clean_cell(response.text)
        if response.status_code in {401, 403}:
            raise ValueError(
                "Firebase rechazó el acceso. Revise las reglas de Firestore."
                + (f" {detail}" if detail else "")
            )
        raise ValueError(
            f"Firebase respondió con error {response.status_code}."
            + (f" {detail}" if detail else "")
        )
    if not response.content:
        return {}
    return response.json()


def _validate_collection(collection: str) -> None:
    if collection not in ALL_ALLOWED_COLLECTIONS:
        raise ValueError(f"La colección '{collection}' no está autorizada.")


def list_collection(collection: str, page_size: int = 300) -> list[dict[str, Any]]:
    _validate_collection(collection)
    results: list[dict[str, Any]] = []
    token = ""
    while True:
        params: dict[str, Any] = {"pageSize": min(max(page_size, 1), 1000)}
        if token:
            params["pageToken"] = token
        payload = _request("GET", f"/documents/{collection}", params=params, allow_404=True) or {}
        results.extend(
            _decode_document(document)
            for document in (payload.get("documents") or [])
        )
        token = clean_cell(payload.get("nextPageToken"))
        if not token:
            break
    return results


def get_document(collection: str, document_id: str) -> dict[str, Any] | None:
    _validate_collection(collection)
    payload = _request(
        "GET",
        f"/documents/{collection}/{quote(document_id, safe='')}",
        allow_404=True,
    )
    return _decode_document(payload) if payload else None


def query_equal(collection: str, field: str, value: Any) -> list[dict[str, Any]]:
    _validate_collection(collection)
    body = {
        "structuredQuery": {
            "from": [{"collectionId": collection}],
            "where": {
                "fieldFilter": {
                    "field": {"fieldPath": field},
                    "op": "EQUAL",
                    "value": _value_to_firestore(value),
                }
            },
        }
    }
    try:
        payload = _request("POST", "/documents:runQuery", body=body)
        return [
            _decode_document(item["document"])
            for item in payload
            if item.get("document")
        ]
    except ValueError:
        return [
            item
            for item in list_collection(collection)
            if item.get(field) == value
        ]


def batch_get_students(cedulas: list[str]) -> dict[str, dict[str, Any]]:
    unique = list(dict.fromkeys(clean_cell(item) for item in cedulas if clean_cell(item)))
    results: dict[str, dict[str, Any]] = {}
    for start in range(0, len(unique), 100):
        batch = unique[start : start + 100]
        names = [
            f"{BASE_URL}/documents/Estudiante/{quote(cedula, safe='')}"
            for cedula in batch
        ]
        payload = _request(
            "POST",
            "/documents:batchGet",
            body={"documents": names},
        )
        for item in payload:
            if item.get("found"):
                decoded = _decode_document(item["found"])
                key = clean_cell(decoded.get("cedula") or decoded.get("_id"))
                if key:
                    results[key] = decoded
    return results


def write_document(collection: str, document_id: str, data: dict[str, Any]) -> None:
    if collection not in WRITABLE_COLLECTIONS:
        raise ValueError(
            f"Informtit tiene prohibido escribir en la colección '{collection}'."
        )
    fields = {
        str(key): _value_to_firestore(value)
        for key, value in data.items()
        if not str(key).startswith("_")
    }
    _request(
        "PATCH",
        f"/documents/{collection}/{quote(document_id, safe='')}",
        body={"fields": fields},
    )


def _active(item: dict[str, Any]) -> bool:
    return not bool(item.get("eliminado"))


def _period_doc(period_id: str) -> dict[str, Any]:
    document = get_document("periodos", period_id)
    if document:
        return document
    return {
        "_id": period_id,
        "periodoId": period_id,
        "label": period_policy.period_label(period_id),
    }


def list_periods() -> list[dict[str, Any]]:
    periods = [item for item in list_collection("periodos") if _active(item)]
    output: list[dict[str, Any]] = []
    for item in periods:
        period_id = clean_cell(item.get("periodoId") or item.get("_id"))
        if not period_id:
            continue
        kind = period_policy.classify_period(period_id)
        output.append(
            {
                "periodoId": period_id,
                "label": clean_cell(item.get("label"))
                or period_policy.period_label(period_id),
                "inicio": item.get("inicio") or "",
                "fin": item.get("fin") or "",
                "activo": item.get("activo", True),
                "orden": item.get("orden") or 0,
                "report_type": kind,
                "report_label": "PVC" if kind == "pvc" else "Presencial + Online",
            }
        )
    output.sort(
        key=lambda item: (
            int(item.get("orden") or 0),
            str(item.get("periodoId") or ""),
        ),
        reverse=True,
    )
    return output


def _modality(value: Any, career_name: str = "", career_code: str = "") -> str:
    text = period_policy._fold(value)
    name = period_policy._fold(career_name)
    code = clean_cell(career_code).upper()
    online = (
        any(token in text for token in ("ONLINE", "EN LINEA", "VIRTUAL"))
        or any(token in name for token in ("ONLINE", "EN LINEA"))
        or "-L-" in code
    )
    return "en_linea" if online else "presencial"


def _clean_status(value: Any) -> str:
    return clean_cell(value).upper()


REQUIREMENT_MAP = {
    "Academico": "academic_status",
    "Documentacion": "documentation_status",
    "Financiero": "financial_status",
    "Titulacion": "titulation_status",
    "PracticasVinculacion": "practices_linkage_status",
    "Vinculacion": "linkage_status",
    "SeguimientoGraduados": "graduate_followup_status",
    "Ingles": "english_status",
    "ActualizacionDatos": "data_update_status",
    "AprobacionTitulacion": "titulation_approval",
    "AprobacionComplexivoProyecto": "complexive_approval",
}


def _make_requirement_record(
    cedula: str,
    student: dict[str, Any],
    enrollment: dict[str, Any],
    requirement: dict[str, Any],
    career_catalog: dict[str, dict[str, Any]],
    kind: str,
) -> dict[str, Any]:
    values = requirement.get("valores") or {}
    if not isinstance(values, dict):
        values = {}
    # Estudiante es la fuente maestra de identidad y datos actuales. Matrícula
    # solo aporta contexto del período cuando el dato maestro no existe.
    career_code = clean_cell(
        student.get("codigoCarreraActual")
        or enrollment.get("codigoCarrera")
    )
    catalog = career_catalog.get(career_code, {})
    career_name = clean_cell(
        student.get("nombreCarreraActual")
        or catalog.get("nombreCarrera")
        or enrollment.get("nombreCarrera")
        or "Sin carrera"
    )
    modality = (
        "presencial"
        if kind == "pvc"
        else _modality(
            enrollment.get("modalidadTitulacion"),
            career_name,
            career_code,
        )
    )
    row = {
        "identification": cedula,
        "full_name": clean_cell(student.get("nombres") or cedula),
        "career_code": career_code,
        "career_name": career_name,
        "modality": modality,
        "schedule": clean_cell(
            enrollment.get("division")
            or enrollment.get("jornada")
            or enrollment.get("horario")
        ),
        "personal_email": clean_cell(student.get("correoPersonal")),
        "email": clean_cell(student.get("correoInstitucional")).lower(),
        "phone": clean_cell(student.get("celular")),
        "campus": clean_cell(student.get("sede") or enrollment.get("sede")),
        "retired": bool(enrollment.get("retirado")),
    }
    for firebase_key, local_key in REQUIREMENT_MAP.items():
        row[local_key] = _clean_status(values.get(firebase_key))
    return row


def _ensure_reports(
    period_id: str,
    period: dict[str, Any],
) -> tuple[str, str, dict[str, int]]:
    period_policy.ensure_schema()
    kind = period_policy.classify_period(period_id)
    label = clean_cell(period.get("label")) or period_policy.period_label(period_id)
    settings = settings_for_report()
    now = utcnow()
    wanted = ["presencial"] if kind == "pvc" else ["presencial", "en_linea"]
    report_ids: dict[str, int] = {}

    with connection() as conn:
        existing = conn.execute(
            """
            SELECT * FROM reports
            WHERE firebase_period_id=? OR period=?
            ORDER BY updated_at DESC, id DESC
            """,
            (period_id, label),
        ).fetchall()

        for modality in wanted:
            row = next(
                (
                    item
                    for item in existing
                    if (
                        kind == "pvc"
                        and (clean_cell(item["report_type"]) == "pvc"
                             or period_policy.classify_period(item["period"]) == "pvc")
                    )
                    or (
                        kind == "normal"
                        and clean_cell(item["modality"]) == modality
                        and (clean_cell(item["report_type"]) in {"", "normal"})
                    )
                ),
                None,
            )
            if row:
                report_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE reports SET period=?, modality=?, report_type=?,
                        firebase_period_id=?, firebase_synced_at=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        label,
                        "presencial" if kind == "pvc" else modality,
                        kind,
                        period_id,
                        now,
                        now,
                        report_id,
                    ),
                )
            else:
                name = (
                    "Informe PVC"
                    if kind == "pvc"
                    else "Informe Final del Proceso de Titulación"
                )
                cursor = conn.execute(
                    """
                    INSERT INTO reports
                    (name, period, modality, code, version, elaboration_date,
                     prepared_by, prepared_role, reviewed_by, reviewed_role,
                     approved_by, approved_role, status, created_at, updated_at,
                     report_type, firebase_period_id, firebase_synced_at)
                    VALUES (?, ?, ?, '', '1.0', '', ?, ?, ?, ?, ?, ?,
                            'borrador', ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        label,
                        "presencial" if kind == "pvc" else modality,
                        settings["prepared_by"],
                        settings["prepared_role"],
                        settings["reviewed_by"],
                        settings["reviewed_role"],
                        settings["approved_by"],
                        settings["approved_role"],
                        now,
                        now,
                        kind,
                        period_id,
                        now,
                    ),
                )
                report_id = int(cursor.lastrowid)
                create_default_sections(conn, report_id)
            report_ids["pvc" if kind == "pvc" else modality] = report_id

    return kind, label, report_ids


def _load_requirements_to_local(
    period_id: str,
    kind: str,
    report_ids: dict[str, int],
) -> dict[str, Any]:
    requirements_store.ensure_requirements_schema()
    requirements = [
        item
        for item in query_equal("requisitos", "periodoId", period_id)
        if _active(item)
    ]
    enrollments = [
        item
        for item in query_equal("matriculas", "periodoId", period_id)
        if _active(item)
    ]
    req_by_id = {
        clean_cell(item.get("cedula")): item
        for item in requirements
        if clean_cell(item.get("cedula"))
    }
    enr_by_id = {
        clean_cell(item.get("cedula")): item
        for item in enrollments
        if clean_cell(item.get("cedula"))
    }
    cedulas = list(enr_by_id) or list(req_by_id)
    students = batch_get_students(cedulas)
    career_catalog = {
        clean_cell(item.get("codigoCarrera") or item.get("_id")): item
        for item in list_collection("carreras")
        if _active(item)
    }

    records = [
        _make_requirement_record(
            cedula,
            students.get(cedula, {}),
            enr_by_id.get(cedula, {}),
            req_by_id.get(cedula, {}),
            career_catalog,
            kind,
        )
        for cedula in cedulas
    ]

    grouped = {"presencial": [], "en_linea": []}
    for record in records:
        grouped[record["modality"]].append(record)

    now = utcnow()
    with connection() as conn:
        if kind == "pvc":
            report_id = report_ids["pvc"]
            conn.execute(
                "DELETE FROM requirements_students WHERE report_id=?",
                (report_id,),
            )
            for record in records:
                normalized = dict(record)
                normalized["modality"] = "presencial"
                requirements_store._insert_requirement_record(
                    conn, report_id, normalized, now
                )
        else:
            for modality, report_id in report_ids.items():
                conn.execute(
                    "DELETE FROM requirements_students WHERE report_id=?",
                    (report_id,),
                )
                for record in grouped.get(modality, []):
                    requirements_store._insert_requirement_record(
                        conn, report_id, record, now
                    )
        for report_id in report_ids.values():
            conn.execute(
                "UPDATE reports SET firebase_synced_at=?, updated_at=? WHERE id=?",
                (now, now, report_id),
            )

    return {
        "students": len(records),
        "requirements": len(requirements),
        "enrollments": len(enrollments),
        "presencial": len(records) if kind == "pvc" else len(grouped["presencial"]),
        "en_linea": 0 if kind == "pvc" else len(grouped["en_linea"]),
        "student_map": students,
    }


def _slug(value: Any) -> str:
    text = period_policy._fold(value)
    text = re.sub(r"[^A-Z0-9]+", "-", text).strip("-")
    return text[:60] or "SIN-CARRERA"


def _group_label(kind: str, modality: str) -> str:
    if kind == "pvc":
        return "PVC"
    return "ONLINE" if modality == "en_linea" else "PRESENCIAL"


def _local_nuclei(
    report_id: int,
    period_id: str,
    group: str,
) -> list[tuple[str, dict[str, Any]]]:
    ensure_nuclei_schema()
    with connection() as conn:
        courses = rows_to_dicts(
            conn.execute(
                "SELECT * FROM nucleus_courses WHERE report_id=? ORDER BY career_name, nucleus_number",
                (report_id,),
            ).fetchall()
        )
        requirements = rows_to_dicts(
            conn.execute(
                "SELECT identification, email FROM requirements_students WHERE report_id=?",
                (report_id,),
            ).fetchall()
        )
        cedula_by_email = {
            clean_cell(item.get("email")).lower(): clean_cell(item.get("identification"))
            for item in requirements
            if clean_cell(item.get("email"))
        }
        output: list[tuple[str, dict[str, Any]]] = []
        for course in courses:
            students = rows_to_dicts(
                conn.execute(
                    "SELECT * FROM nucleus_students WHERE course_id=? ORDER BY full_name",
                    (course["id"],),
                ).fetchall()
            )
            assessments = rows_to_dicts(
                conn.execute(
                    "SELECT * FROM nucleus_assessments WHERE course_id=? ORDER BY sort_order, id",
                    (course["id"],),
                ).fetchall()
            )
            results = []
            for student in students:
                email = clean_cell(student.get("email")).lower()
                results.append(
                    {
                        "cedula": cedula_by_email.get(email, ""),
                        "correo": email,
                        "notaFinal": student.get("final_grade"),
                        "estado": clean_cell(student.get("final_status")),
                    }
                )
            activities = [
                {
                    "nombre": clean_cell(item.get("name")),
                    "promedio": item.get("average"),
                }
                for item in assessments
            ]
            career_key = _slug(
                course.get("career_code") or course.get("career_name")
            )
            doc_id = (
                f"{period_id}__{career_key}__N{int(course.get('nucleus_number') or 1)}"
            )
            output.append(
                (
                    doc_id,
                    {
                        "periodoId": period_id,
                        "carreraId": clean_cell(course.get("career_code")),
                        "carrera": clean_cell(course.get("career_name")),
                        "nucleo": int(course.get("nucleus_number") or 1),
                        "curso": clean_cell(course.get("course_title")),
                        "docente": clean_cell(course.get("teacher_name")),
                        "grupoInforme": group,
                        "resultados": results,
                        "actividades": activities,
                        "version": 1,
                        "updatedAt": utcnow(),
                    },
                )
            )
    return output


def _local_complexive(
    report_id: int,
    period_id: str,
    group: str,
) -> list[tuple[str, dict[str, Any]]]:
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT s.*, c.name AS career_name,
                       COALESCE(NULLIF(s.career_code,''), c.career_code, '') AS report_career_code
                FROM students s
                JOIN careers c ON c.id=s.career_id
                WHERE c.report_id=?
                ORDER BY c.name, s.full_name
                """,
                (report_id,),
            ).fetchall()
        )
    output: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        cedula = clean_cell(row.get("identification"))
        if not cedula:
            continue
        enriched = analytics.enrich_student(row)
        output.append(
            (
                f"{period_id}__{cedula}",
                {
                    "periodoId": period_id,
                    "cedula": cedula,
                    "carreraId": clean_cell(row.get("report_career_code")),
                    "carrera": clean_cell(row.get("career_name")),
                    "grupoInforme": group,
                    "notaTeorica": row.get("ordinary_theory"),
                    "notaPractica": row.get("ordinary_practical"),
                    "notaOrdinaria": enriched.get("ordinary_final"),
                    "notaTeoricaSupletorio": row.get("supplementary_theory"),
                    "notaPracticaSupletorio": row.get("supplementary_practical"),
                    "notaFinal": enriched.get("final_grade"),
                    "estadoFinal": clean_cell(enriched.get("final_status")),
                    "version": 1,
                    "updatedAt": utcnow(),
                },
            )
        )
    return output


def _local_thesis(
    report_id: int,
    period_id: str,
    group: str,
) -> list[tuple[str, dict[str, Any]]]:
    ensure_thesis_schema()
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM thesis_projects WHERE report_id=? ORDER BY career_name, full_name",
                (report_id,),
            ).fetchall()
        )
    output: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        cedula = clean_cell(row.get("identification"))
        if not cedula:
            continue
        output.append(
            (
                f"{period_id}__{cedula}",
                {
                    "periodoId": period_id,
                    "cedula": cedula,
                    "carreraId": clean_cell(row.get("career_code")),
                    "carrera": clean_cell(row.get("career_name")),
                    "grupoInforme": group,
                    "tema": clean_cell(row.get("project_title")),
                    "numeroActa": clean_cell(row.get("act_number")),
                    "fechaActa": clean_cell(row.get("act_date")),
                    "notaTutor": row.get("tutor_grade"),
                    "notaLector": row.get("reader_grade"),
                    "promedioEscrito": row.get("written_average"),
                    "jurado1": clean_cell(row.get("vocal_1")),
                    "jurado2": clean_cell(row.get("vocal_2")),
                    "jurado3": clean_cell(row.get("vocal_3")),
                    "notaPractica": row.get("practical_average"),
                    "notaDefensa": row.get("defense_average"),
                    "promedioOral": row.get("oral_average"),
                    "notaFinal": row.get("final_grade"),
                    "estado": clean_cell(row.get("final_status")),
                    "version": 1,
                    "updatedAt": utcnow(),
                },
            )
        )
    return output


def _local_schedule(
    report_id: int,
    period_id: str,
    group: str,
) -> tuple[str, dict[str, Any]] | None:
    ensure_process_schema()
    with connection() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM schedule_items
                WHERE report_id=?
                ORDER BY schedule_type, sort_order, id
                """,
                (report_id,),
            ).fetchall()
        )
    if not rows:
        return None
    has_real_execution = any(
        clean_cell(row.get("executed_date"))
        or clean_cell(row.get("execution_status"))
        or row.get("compliance_percentage") is not None
        or clean_cell(row.get("evidence"))
        or clean_cell(row.get("observation"))
        for row in rows
    )
    if not has_real_execution:
        return None
    activities = [
        {
            "tipo": clean_cell(row.get("schedule_type")),
            "fase": clean_cell(row.get("phase")),
            "nombre": clean_cell(row.get("activity")),
            "fechaInicio": clean_cell(row.get("start_date")),
            "fechaFin": clean_cell(row.get("end_date")),
            "fechaEjecutada": clean_cell(row.get("executed_date")),
            "estado": clean_cell(row.get("execution_status")),
            "cumplimiento": row.get("compliance_percentage"),
            "evidencia": clean_cell(row.get("evidence")),
            "observacion": clean_cell(row.get("observation")),
        }
        for row in rows
    ]
    suffix = "PVC" if group == "PVC" else group
    return (
        f"{period_id}__{suffix}",
        {
            "periodoId": period_id,
            "grupoInforme": group,
            "actividades": activities,
            "version": 1,
            "updatedAt": utcnow(),
        },
    )


def _push_new_collections(
    period_id: str,
    kind: str,
    report_ids: dict[str, int],
) -> tuple[dict[str, int], list[str]]:
    written = {name: 0 for name in WRITABLE_COLLECTIONS}
    warnings: list[str] = []
    for key, report_id in report_ids.items():
        modality = "presencial" if key in {"pvc", "presencial"} else "en_linea"
        group = _group_label(kind, modality)
        items = {
            "nucleos": _local_nuclei(report_id, period_id, group),
            "complexivo": _local_complexive(report_id, period_id, group),
            "titulacion": _local_thesis(report_id, period_id, group),
        }
        schedule = _local_schedule(report_id, period_id, group)
        if schedule:
            items["cronogramas"] = [schedule]
        else:
            items["cronogramas"] = []

        for collection, documents in items.items():
            for doc_id, data in documents:
                try:
                    write_document(collection, doc_id, data)
                    written[collection] += 1
                except Exception as exc:
                    message = f"{collection}: {clean_cell(exc)}"
                    if message not in warnings:
                        warnings.append(message)
                    break
    return written, warnings


def _report_has_local_data(report_id: int, module: str) -> bool:
    with connection() as conn:
        if module == "nucleos":
            return bool(
                conn.execute(
                    "SELECT 1 FROM nucleus_courses WHERE report_id=? LIMIT 1",
                    (report_id,),
                ).fetchone()
            )
        if module == "complexivo":
            return bool(
                conn.execute(
                    """
                    SELECT 1 FROM students s
                    JOIN careers c ON c.id=s.career_id
                    WHERE c.report_id=? AND COALESCE(s.identification,'')<>''
                    LIMIT 1
                    """,
                    (report_id,),
                ).fetchone()
            )
        if module == "titulacion":
            return bool(
                conn.execute(
                    "SELECT 1 FROM thesis_projects WHERE report_id=? LIMIT 1",
                    (report_id,),
                ).fetchone()
            )
        if module == "cronogramas":
            return bool(
                conn.execute(
                    """
                    SELECT 1 FROM schedule_items
                    WHERE report_id=? AND (
                        COALESCE(execution_status,'')<>'' OR
                        executed_date<>'' OR compliance_percentage IS NOT NULL OR
                        COALESCE(evidence,'')<>'' OR COALESCE(observation,'')<>''
                    ) LIMIT 1
                    """,
                    (report_id,),
                ).fetchone()
            )
    return False


def _remote_for_group(
    collection: str,
    period_id: str,
    group: str,
) -> list[dict[str, Any]]:
    rows = query_equal(collection, "periodoId", period_id)
    return [
        row
        for row in rows
        if clean_cell(row.get("grupoInforme")).upper() == group
    ]


def _ensure_local_career(
    conn: Any,
    report_id: int,
    name: str,
    code: str,
) -> int:
    clean_name = clean_cell(name) or "Sin carrera"
    row = conn.execute(
        "SELECT id FROM careers WHERE report_id=? AND name=?",
        (report_id, clean_name),
    ).fetchone()
    if row:
        career_id = int(row["id"])
        if code:
            conn.execute(
                "UPDATE careers SET career_code=? WHERE id=?",
                (code, career_id),
            )
        return career_id
    order = int(
        conn.execute(
            "SELECT COALESCE(MAX(sort_order),0)+1 FROM careers WHERE report_id=?",
            (report_id,),
        ).fetchone()[0]
    )
    cursor = conn.execute(
        """
        INSERT INTO careers(report_id,name,sort_order,created_at,career_code)
        VALUES(?,?,?,?,?)
        """,
        (report_id, clean_name, order, utcnow(), code),
    )
    return int(cursor.lastrowid)


def _restore_nuclei(
    report_id: int,
    rows: list[dict[str, Any]],
    students: dict[str, dict[str, Any]],
) -> int:
    ensure_nuclei_schema()
    restored = 0
    now = utcnow()
    with connection() as conn:
        for item in rows:
            career = clean_cell(item.get("carrera")) or "Sin carrera"
            nucleus = int(item.get("nucleo") or 1)
            results = item.get("resultados") if isinstance(item.get("resultados"), list) else []
            grades = [
                float(row["notaFinal"])
                for row in results
                if row.get("notaFinal") is not None
            ]
            approved = sum(
                clean_cell(row.get("estado")).upper() == "APROBADO"
                for row in results
            )
            failed = sum(
                clean_cell(row.get("estado")).upper() in {"REPROBADO", "SUSPENSO"}
                for row in results
            )
            unevaluated = max(len(results) - approved - failed, 0)
            cursor = conn.execute(
                """
                INSERT INTO nucleus_courses
                (report_id, career_name, nucleus_number, course_title, teacher_name,
                 participant_students, graded_students, matched_students, missing_grades,
                 extra_grades, course_average, approved_count, failed_count,
                 unevaluated_count, activity_averages, raw_grades, raw_participants,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, '', '', ?, ?)
                ON CONFLICT(report_id, career_name, nucleus_number) DO UPDATE SET
                    course_title=excluded.course_title,
                    teacher_name=excluded.teacher_name,
                    participant_students=excluded.participant_students,
                    graded_students=excluded.graded_students,
                    matched_students=excluded.matched_students,
                    course_average=excluded.course_average,
                    approved_count=excluded.approved_count,
                    failed_count=excluded.failed_count,
                    unevaluated_count=excluded.unevaluated_count,
                    activity_averages=excluded.activity_averages,
                    updated_at=excluded.updated_at
                RETURNING id
                """,
                (
                    report_id,
                    career,
                    nucleus,
                    clean_cell(item.get("curso")),
                    clean_cell(item.get("docente")),
                    len(results),
                    len(grades),
                    len(results),
                    round(mean(grades), 2) if grades else None,
                    approved,
                    failed,
                    unevaluated,
                    json.dumps(item.get("actividades") or [], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            course_id = int(cursor.fetchone()[0])
            conn.execute(
                "DELETE FROM nucleus_assessments WHERE course_id=?",
                (course_id,),
            )
            conn.execute(
                "DELETE FROM nucleus_students WHERE course_id=?",
                (course_id,),
            )
            for order, activity in enumerate(item.get("actividades") or [], start=1):
                conn.execute(
                    """
                    INSERT INTO nucleus_assessments(course_id,name,sort_order,average)
                    VALUES(?,?,?,?)
                    """,
                    (
                        course_id,
                        clean_cell(activity.get("nombre")) or f"Actividad {order}",
                        order,
                        activity.get("promedio"),
                    ),
                )
            for result in results:
                cedula = clean_cell(result.get("cedula"))
                profile = students.get(cedula, {})
                email = (
                    clean_cell(result.get("correo"))
                    or clean_cell(profile.get("correoInstitucional"))
                    or (f"firebase-{cedula}" if cedula else f"firebase-{restored}-{course_id}")
                ).lower()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO nucleus_students
                    (course_id, full_name, email, final_grade, final_status,
                     participant_found)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (
                        course_id,
                        clean_cell(profile.get("nombres") or cedula or "Estudiante"),
                        email,
                        result.get("notaFinal"),
                        clean_cell(result.get("estado")) or "No evaluado",
                    ),
                )
            restored += 1
    return restored


def _restore_complexive(
    report_id: int,
    rows: list[dict[str, Any]],
    students: dict[str, dict[str, Any]],
) -> int:
    restored = 0
    now = utcnow()
    with connection() as conn:
        for item in rows:
            cedula = clean_cell(item.get("cedula"))
            if not cedula:
                continue
            profile = students.get(cedula, {})
            career_id = _ensure_local_career(
                conn,
                report_id,
                clean_cell(item.get("carrera")),
                clean_cell(item.get("carreraId")),
            )
            email = clean_cell(profile.get("correoInstitucional")).lower() or None
            conn.execute(
                """
                INSERT INTO students
                (career_id, full_name, email, ordinary_theory, ordinary_practical,
                 supplementary_theory, supplementary_practical, source_total_course,
                 created_at, updated_at, identification, career_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(career_id, email) DO UPDATE SET
                    full_name=excluded.full_name,
                    ordinary_theory=excluded.ordinary_theory,
                    ordinary_practical=excluded.ordinary_practical,
                    supplementary_theory=excluded.supplementary_theory,
                    supplementary_practical=excluded.supplementary_practical,
                    source_total_course=excluded.source_total_course,
                    identification=excluded.identification,
                    career_code=excluded.career_code,
                    updated_at=excluded.updated_at
                """,
                (
                    career_id,
                    clean_cell(profile.get("nombres") or cedula),
                    email,
                    item.get("notaTeorica"),
                    item.get("notaPractica"),
                    item.get("notaTeoricaSupletorio"),
                    item.get("notaPracticaSupletorio"),
                    item.get("notaFinal"),
                    now,
                    now,
                    cedula,
                    clean_cell(item.get("carreraId")),
                ),
            )
            restored += 1
    return restored


def _restore_thesis(
    report_id: int,
    rows: list[dict[str, Any]],
    students: dict[str, dict[str, Any]],
) -> int:
    ensure_thesis_schema()
    restored = 0
    now = utcnow()
    with connection() as conn:
        for item in rows:
            cedula = clean_cell(item.get("cedula"))
            if not cedula:
                continue
            profile = students.get(cedula, {})
            conn.execute(
                """
                INSERT INTO thesis_projects
                (report_id, identification, full_name, career_code, career_name,
                 act_number, act_date, tutor_grade, reader_grade, written_average,
                 vocal_1, vocal_2, vocal_3, practical_average, defense_average,
                 oral_average, final_grade, project_title, final_status,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id, identification) DO UPDATE SET
                    full_name=excluded.full_name,
                    career_code=excluded.career_code,
                    career_name=excluded.career_name,
                    act_number=excluded.act_number,
                    act_date=excluded.act_date,
                    tutor_grade=excluded.tutor_grade,
                    reader_grade=excluded.reader_grade,
                    written_average=excluded.written_average,
                    vocal_1=excluded.vocal_1,
                    vocal_2=excluded.vocal_2,
                    vocal_3=excluded.vocal_3,
                    practical_average=excluded.practical_average,
                    defense_average=excluded.defense_average,
                    oral_average=excluded.oral_average,
                    final_grade=excluded.final_grade,
                    project_title=excluded.project_title,
                    final_status=excluded.final_status,
                    updated_at=excluded.updated_at
                """,
                (
                    report_id,
                    cedula,
                    clean_cell(profile.get("nombres") or cedula),
                    clean_cell(item.get("carreraId")),
                    clean_cell(item.get("carrera")),
                    clean_cell(item.get("numeroActa")),
                    clean_cell(item.get("fechaActa")),
                    item.get("notaTutor"),
                    item.get("notaLector"),
                    item.get("promedioEscrito"),
                    clean_cell(item.get("jurado1")),
                    clean_cell(item.get("jurado2")),
                    clean_cell(item.get("jurado3")),
                    item.get("notaPractica"),
                    item.get("notaDefensa"),
                    item.get("promedioOral"),
                    item.get("notaFinal"),
                    clean_cell(item.get("tema")),
                    clean_cell(item.get("estado")) or "INCOMPLETO",
                    now,
                    now,
                ),
            )
            restored += 1
    return restored


def _restore_schedule(report_id: int, rows: list[dict[str, Any]]) -> int:
    ensure_process_schema()
    if not rows:
        return 0
    item = rows[0]
    activities = (
        item.get("actividades")
        if isinstance(item.get("actividades"), list)
        else []
    )
    if not activities:
        return 0
    now = utcnow()
    with connection() as conn:
        conn.execute("DELETE FROM schedule_items WHERE report_id=?", (report_id,))
        for order, activity in enumerate(activities, start=1):
            schedule_type = clean_cell(activity.get("tipo"))
            if schedule_type not in {"complexive", "thesis"}:
                schedule_type = "complexive"
            conn.execute(
                """
                INSERT INTO schedule_items
                (report_id, schedule_type, phase, activity, start_date, end_date,
                 sort_order, created_at, updated_at, executed_date, execution_status,
                 compliance_percentage, evidence, observation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    schedule_type,
                    clean_cell(activity.get("fase")),
                    clean_cell(activity.get("nombre")) or f"Actividad {order}",
                    clean_cell(activity.get("fechaInicio")),
                    clean_cell(activity.get("fechaFin")),
                    order,
                    now,
                    now,
                    clean_cell(activity.get("fechaEjecutada")),
                    clean_cell(activity.get("estado")),
                    activity.get("cumplimiento"),
                    clean_cell(activity.get("evidencia")),
                    clean_cell(activity.get("observacion")),
                ),
            )
    return len(activities)


def _restore_missing_modules(
    period_id: str,
    kind: str,
    report_ids: dict[str, int],
    students: dict[str, dict[str, Any]],
) -> dict[str, int]:
    restored = {name: 0 for name in WRITABLE_COLLECTIONS}
    for key, report_id in report_ids.items():
        modality = "presencial" if key in {"pvc", "presencial"} else "en_linea"
        group = _group_label(kind, modality)
        if not _report_has_local_data(report_id, "nucleos"):
            restored["nucleos"] += _restore_nuclei(
                report_id,
                _remote_for_group("nucleos", period_id, group),
                students,
            )
        if not _report_has_local_data(report_id, "complexivo"):
            restored["complexivo"] += _restore_complexive(
                report_id,
                _remote_for_group("complexivo", period_id, group),
                students,
            )
        if not _report_has_local_data(report_id, "titulacion"):
            restored["titulacion"] += _restore_thesis(
                report_id,
                _remote_for_group("titulacion", period_id, group),
                students,
            )
        if not _report_has_local_data(report_id, "cronogramas"):
            restored["cronogramas"] += _restore_schedule(
                report_id,
                _remote_for_group("cronogramas", period_id, group),
            )
    return restored


def sync_period(period_id: str) -> dict[str, Any]:
    """Sincroniza exclusivamente las fuentes oficiales compartidas.

    Leer Firebase nunca publica notas. Las colecciones académicas se escriben
    únicamente mediante los botones explícitos de publicación de cada módulo.
    """
    period_id = clean_cell(period_id)
    if not period_id:
        raise ValueError("Seleccione un periodo.")
    period = _period_doc(period_id)
    kind, label, report_ids = _ensure_reports(period_id, period)
    requirements_result = _load_requirements_to_local(
        period_id,
        kind,
        report_ids,
    )

    requirements_result.pop("student_map", None)
    return {
        "ok": True,
        "periodoId": period_id,
        "period": label,
        "report_type": kind,
        "report_ids": report_ids,
        "report_id": next(iter(report_ids.values())),
        "requirements": requirements_result,
        "restored": {},
        "written": {name: 0 for name in WRITABLE_COLLECTIONS},
        "warnings": [],
        "mode": "read_only_sources",
        "protected_collections": sorted(READ_ONLY_COLLECTIONS),
        "writable_collections": sorted(WRITABLE_COLLECTIONS),
    }


def status() -> dict[str, Any]:
    return {
        "ok": True,
        "project_id": PROJECT_ID,
        "configured": bool(PROJECT_ID and API_KEY),
        "source": "Firebase",
        "protected_collections": sorted(READ_ONLY_COLLECTIONS),
        "writable_collections": sorted(WRITABLE_COLLECTIONS),
    }


def install() -> None:
    if getattr(core.InformtitHandler, "_firebase_sync_installed", False):
        return

    previous_get = core.InformtitHandler._handle_api_get
    previous_write = core.InformtitHandler._handle_api_write
    previous_static = core.InformtitHandler._serve_static

    def handle_get(self: Any, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/firebase/status":
            self._send_json(status())
            return
        if path == "/api/firebase/periods":
            self._send_json({"ok": True, "periods": list_periods()})
            return
        previous_get(self, path, query)

    def handle_write(
        self: Any,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> None:
        if method == "POST" and path == "/api/firebase/sync":
            self._send_json(sync_period(clean_cell(payload.get("period_id"))))
            return
        previous_write(self, method, path, payload)

    def serve_static(self: Any, path: str) -> None:
        if path in {"", "/"}:
            target = core.STATIC_DIR / "index.html"
            if target.exists():
                text = target.read_text(encoding="utf-8")
                marker = '<script src="/firebase-ui.js?v=1.0"></script>'
                if marker not in text:
                    text = text.replace("</body>", f"  {marker}\n</body>")
                body = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        previous_static(self, path)

    core.InformtitHandler._handle_api_get = handle_get
    core.InformtitHandler._handle_api_write = handle_write
    core.InformtitHandler._serve_static = serve_static
    core.InformtitHandler._firebase_sync_installed = True
