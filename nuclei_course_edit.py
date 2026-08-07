from __future__ import annotations

import re
from typing import Any

import app as core
import nuclei_multicampus
from coordinator_registry import find_coordinator, normalize
from db import connection, utcnow


def _line(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").strip().split())


def update_course_metadata(report_id: int, course_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Corrige los metadatos de un curso de Núcleos sin tocar sus estudiantes ni notas."""

    nuclei_multicampus.ensure_multicampus_schema()
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM nucleus_course_instances WHERE id=? AND report_id=?",
            (course_id, report_id),
        ).fetchone()
        if not row:
            raise ValueError("El curso de núcleo no existe.")

        current = dict(row)
        career_name = _line(payload.get("career_name"))
        if not career_name or normalize(career_name) == "sin carrera":
            raise ValueError("Ingrese una carrera válida para el curso.")

        try:
            nucleus_number = int(payload.get("nucleus_number") or current.get("nucleus_number") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("El número de núcleo no es válido.") from exc
        if nucleus_number < 1 or nucleus_number > 20:
            raise ValueError("El número de núcleo debe estar entre 1 y 20.")

        campus = _line(payload.get("campus")) if "campus" in payload else _line(current.get("campus"))
        teacher_name = (
            _line(payload.get("teacher_name"))
            if "teacher_name" in payload
            else _line(current.get("teacher_name"))
        )

        key_data = {
            **current,
            "career_name": career_name,
            "nucleus_number": nucleus_number,
            "campus": campus,
        }
        course_key = nuclei_multicampus._course_key(key_data)
        duplicate = conn.execute(
            """
            SELECT id FROM nucleus_course_instances
            WHERE report_id=? AND course_key=? AND id<>?
            """,
            (report_id, course_key, course_id),
        ).fetchone()
        if duplicate:
            raise ValueError(
                "Ya existe otro curso con la misma carrera, núcleo, sede, módulo, periodo, grupo y horario."
            )

        coordinator = find_coordinator(career_name)
        now = utcnow()
        conn.execute(
            """
            UPDATE nucleus_course_instances
            SET career_name=?, nucleus_number=?, campus=?, teacher_name=?, course_key=?,
                coordinator_name=?, coordinator_program=?, coordinator_telegram=?, updated_at=?
            WHERE id=? AND report_id=?
            """,
            (
                career_name,
                nucleus_number,
                campus,
                teacher_name,
                course_key,
                coordinator.get("coordinator", ""),
                coordinator.get("program", ""),
                coordinator.get("telegram", ""),
                now,
                course_id,
                report_id,
            ),
        )

    return {
        "ok": True,
        "course": {
            "id": course_id,
            "career_name": career_name,
            "nucleus_number": nucleus_number,
            "campus": campus,
            "teacher_name": teacher_name,
        },
    }


def install() -> None:
    """Añade edición manual de metadatos a Núcleos, independiente de las demás áreas."""

    original_write = core.InformtitHandler._handle_api_write

    def handle_write(
        self: Any,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> None:
        match = re.fullmatch(r"/api/reports/(\d+)/nuclei/(\d+)", path)
        if match and method == "PUT":
            self._send_json(
                update_course_metadata(
                    int(match.group(1)),
                    int(match.group(2)),
                    payload,
                )
            )
            return
        original_write(self, method, path, payload)

    core.InformtitHandler._handle_api_write = handle_write
