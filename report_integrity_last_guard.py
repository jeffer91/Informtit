from __future__ import annotations

from typing import Any, Callable

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

import completion_routes
import completion_service
import institutional_export as institutional
import nuclei_excel_import
import period_policy_runtime
import process_routes
import process_service
import report_integrity_core as integrity
import report_integrity_final_fixes as final_fixes
from db import connection
from optional_content import is_present, set_presence
from process_service import COMPLEXIVE_DEFAULTS, THESIS_DEFAULTS


_INSTALLED = False


def _with_presence(function: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def wrapped(report_id: int, schedule_type: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
        result = dict(function(report_id, schedule_type, entries))
        set_presence(report_id, f"schedule_{schedule_type}", True)
        return result

    return wrapped


def repair_schedule_presence() -> int:
    """Recupera cronogramas reales que pudieron quedar ocultos por una capa anterior.

    Los cronogramas por defecto siguen marcados como ausentes; únicamente se
    reactiva la presencia cuando existen filas distintas de la plantilla base.
    """
    defaults = {
        "complexive": list(COMPLEXIVE_DEFAULTS),
        "thesis": list(THESIS_DEFAULTS),
    }
    candidates: list[tuple[int, str]] = []

    # Primero se identifican los cronogramas reales y se cierra la conexión.
    # Las funciones is_present/set_presence abren su propia conexión, por lo que
    # no se ejecutan dentro de este bloque para evitar bloqueos de SQLite.
    with connection() as conn:
        report_ids = [
            int(row[0])
            for row in conn.execute("SELECT DISTINCT report_id FROM schedule_items").fetchall()
        ]
        for report_id in report_ids:
            for schedule_type in ("complexive", "thesis"):
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
                if current and current != defaults[schedule_type]:
                    candidates.append((report_id, schedule_type))

    repaired = 0
    for report_id, schedule_type in candidates:
        key = f"schedule_{schedule_type}"
        if not is_present(report_id, key):
            set_presence(report_id, key, True)
            repaired += 1
    return repaired


def source_mode_strict(metrics: dict[str, Any], source: dict[str, Any]) -> str:
    """Distingue ausencia real de población de una carga contradictoria."""
    req_total = int(metrics["requirements"]["registered"] or 0)
    module_total = (
        req_total
        + int(metrics["nuclei"]["records"] or 0)
        + int(metrics["complexive"]["registered"] or 0)
        + int(metrics["thesis"]["total"] or 0)
    )

    if source.get("exists"):
        expected = int(source.get("source_modality_count") or 0)
        if expected == 0:
            # Si la fuente confirma cero población pero aparecen datos académicos,
            # existe una contradicción y no debe emitirse un informe normal.
            return "no_population" if module_total == 0 else "import_error"
        # La fuente confirma población. Requisitos debe contenerla; si quedó vacío,
        # no se permite encubrir el fallo con datos residuales de otros módulos.
        if req_total == 0:
            return "import_error"
        return "normal"

    return "normal" if module_total else "import_error"


def report_counts_strict(conn: Any, report_id: int) -> tuple[int, int]:
    """Usa Requisitos como población oficial cuando existe una importación fuente."""
    careers = int(
        conn.execute("SELECT COUNT(*) FROM careers WHERE report_id=?", (report_id,)).fetchone()[0]
    )
    report = conn.execute(
        "SELECT source_import_id FROM reports WHERE id=?",
        (report_id,),
    ).fetchone()
    has_requirements = bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='requirements_students'"
        ).fetchone()
    )
    if report and report["source_import_id"] and has_requirements:
        students = int(
            conn.execute(
                "SELECT COUNT(*) FROM requirements_students WHERE report_id=?",
                (report_id,),
            ).fetchone()[0]
        )
        # El cero también es un dato válido: no se debe sustituir por estudiantes
        # residuales de la estructura antigua.
        return careers, students

    return period_policy_runtime._report_counts_original(conn, report_id)


def nuclei_duplicate_entries_strict(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clasifica duplicados de Núcleos sin depender del docente.

    El informe ya fija período y modalidad mediante report_id. El Excel de Núcleos
    no contiene cédula, por lo que la mejor clave probable disponible es carrera +
    estudiante + curso/componente. Diferencias de docente, nota o estado quedan
    para revisión en vez de ocultar una coincidencia potencial.
    """
    exact_seen: dict[tuple[str, ...], dict[str, Any]] = {}
    probable_seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    result: list[dict[str, Any]] = []

    for record in records:
        exact = tuple(integrity.norm(record.get(header)) for header in nuclei_excel_import.REQUIRED_HEADERS)
        if exact in exact_seen:
            result.append(
                {
                    "duplicate_type": "DUPLICADO EXACTO",
                    "original": exact_seen[exact],
                    "omitted": record,
                    "reason": "La fila coincide exactamente en todos los campos importados.",
                }
            )
            continue
        exact_seen[exact] = record

        probable = (
            integrity.ascii_key(record.get("nombre_carrera")),
            integrity.ascii_key(record.get("nombre_estudiante")),
            integrity.ascii_key(record.get("materia")),
        )
        previous = probable_seen.get(probable)
        if previous is not None:
            result.append(
                {
                    "duplicate_type": "DUPLICADO PROBABLE",
                    "original": previous,
                    "omitted": record,
                    "reason": (
                        "Misma carrera, estudiante y curso/componente, con diferencias en otros campos. "
                        "El Excel de Núcleos no incluye cédula; la coincidencia requiere revisión."
                    ),
                }
            )
        else:
            probable_seen[probable] = record
    return result


def _font_to_fit(canvas: Any, text: str, width: float, preferred: float = 6.3, minimum: float = 4.8) -> float:
    size = preferred
    while size > minimum and canvas.stringWidth(text, "Helvetica", size) > width - 8:
        size -= 0.2
    return max(minimum, size)


def draw_header_safe(canvas: Any, report: dict[str, Any], page: int, pages: int) -> None:
    """Encabezado PDF con Código/Versión separados de la línea divisoria."""
    width, height = A4
    x = 1.25 * cm
    top = height - 0.75 * cm
    row = 0.95 * cm
    total = width - 2.5 * cm
    left = 4.25 * cm
    right = 4.15 * cm
    middle = total - left - right
    bottom = top - 2 * row
    right_x = x + left + middle
    right_center = right_x + right / 2

    canvas.saveState()
    canvas.setLineWidth(0.7)
    canvas.rect(x, bottom, total, 2 * row)
    canvas.line(x, top - row, x + total, top - row)
    canvas.line(x + left, bottom, x + left, top)
    canvas.line(right_x, bottom, right_x, top)

    logo = institutional.image_path(institutional.image_for(report, institutional.LOGO))
    if logo:
        canvas.drawImage(
            str(logo),
            x + 0.1 * cm,
            top - row + 0.08 * cm,
            width=left - 0.2 * cm,
            height=row - 0.16 * cm,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
    else:
        institutional.centered(canvas, "LOGO INSTITUCIONAL NO CARGADO", x, top - row + 0.27 * cm, left, 6.5, True)

    institutional.centered(
        canvas,
        "Unidad Titulación y Eficiencia Terminal",
        x + left,
        top - row + 0.27 * cm,
        middle,
        8.2,
    )

    code_line = f"Código: {report.get('code', '')}"
    version_line = f"Versión: {report.get('version', '1.0')}"
    code_size = _font_to_fit(canvas, code_line, right)
    canvas.setFont("Helvetica", code_size)
    canvas.drawCentredString(right_center, top - 0.30 * cm, code_line)
    canvas.setFont("Helvetica", 6.3)
    canvas.drawCentredString(right_center, top - 0.68 * cm, version_line)

    institutional.centered(
        canvas,
        f"Fecha de Elaboración: {institutional.format_date(report.get('elaboration_date'))}",
        x,
        bottom + 0.25 * cm,
        left,
        6.8,
        False,
        2,
    )
    institutional.centered(
        canvas,
        institutional.header_title(report),
        x + left,
        bottom + 0.18 * cm,
        middle,
        6.8,
        True,
    )
    canvas.setFont("Helvetica", 7.2)
    canvas.drawCentredString(right_center, bottom + 0.31 * cm, f"Página {page} de {pages}")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(width - 1.35 * cm, 0.65 * cm, f"Página {page} de {pages}")
    canvas.restoreState()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # La capa de integridad reemplaza las funciones de guardado para deduplicar.
    # Se vuelve a añadir explícitamente la marca de presencia para que el
    # cronograma guardado no desaparezca del análisis ni de la auditoría.
    process_routes.replace_schedule = _with_presence(process_routes.replace_schedule)
    completion_routes.replace_schedule_extended = _with_presence(
        completion_routes.replace_schedule_extended
    )

    # También se protegen llamadas directas a los servicios.
    process_service.replace_schedule = _with_presence(process_service.replace_schedule)
    completion_service.replace_schedule_extended = _with_presence(
        completion_service.replace_schedule_extended
    )

    repair_schedule_presence()

    # Ajustes finales que deben quedar activos después de todas las capas previas.
    integrity._source_mode = source_mode_strict
    integrity.nuclei_duplicate_entries = nuclei_duplicate_entries_strict
    if not hasattr(period_policy_runtime, "_report_counts_original"):
        period_policy_runtime._report_counts_original = period_policy_runtime._report_counts
    period_policy_runtime._report_counts = report_counts_strict
    institutional.draw_header = draw_header_safe
    final_fixes.install()
    _INSTALLED = True
