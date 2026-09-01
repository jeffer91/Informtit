from __future__ import annotations

from typing import Any, Callable

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

import completion_routes
import completion_service
import institutional_export as institutional
import nuclei_excel_import
import period_policy_runtime
import process_routes
import process_service
import report_integrity_core as integrity
import report_integrity_final_fixes as final_fixes
import report_quality
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
    """Una modalidad regular con población 0 se considera un error de fuente/carga."""
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
            # Para los períodos regulares Presencial y Online deben existir en
            # la misma fuente. Un cero no se interpreta como "sin población":
            # se bloquea la emisión hasta revisar el archivo o la clasificación.
            return "import_error"
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
        # El cero también es un dato válido para detectar un error; no se debe
        # sustituir por estudiantes residuales de la estructura antigua.
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


def _wrap_cell_lines(canvas: Any, text: Any, width: float, font: str, size: float, max_lines: int) -> list[str]:
    words = str(text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    usable = max(10.0, width - 0.35 * cm)
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or canvas.stringWidth(candidate, font, size) <= usable:
            current = candidate
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and canvas.stringWidth(last + "…", font, size) > usable:
            last = last[:-1]
        lines[-1] = (last.rstrip() + "…") if last else "…"
    return lines


def _draw_cell_text(
    canvas: Any,
    text: Any,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    size: float = 7.0,
    bold: bool = False,
    max_lines: int = 3,
) -> None:
    """Dibuja texto envuelto y centrado dentro de una celda con margen real."""
    font = "Helvetica-Bold" if bold else "Helvetica"
    lines = _wrap_cell_lines(canvas, text, width, font, size, max_lines)
    leading = size + 1.8
    block_height = max(leading, len(lines) * leading)
    center_y = y + height / 2
    first_baseline = center_y + block_height / 2 - leading * 0.78
    canvas.setFont(font, size)
    for index, line in enumerate(lines):
        canvas.drawCentredString(x + width / 2, first_baseline - index * leading, line)


def _recent_table_context(story: list[Any]) -> bool:
    for item in reversed(story[-5:]):
        if isinstance(item, Spacer):
            continue
        if not isinstance(item, Paragraph):
            return False
        style_name = str(getattr(getattr(item, "style", None), "name", "") or "")
        if "Caption" in style_name or style_name.startswith("Heading") or style_name == "Title":
            return False
        text = item.getPlainText().strip()
        return bool(text)
    return False


def _contextual_pdf_caption(base_caption: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(story: list[Any], styles: Any, text: str) -> Any:
        caption = str(text or "").strip()
        if caption.startswith("Tabla ") and not _recent_table_context(story):
            title = caption
            if ". " in caption:
                title = caption.split(". ", 1)[1]
            title = title.rstrip(".")
            report_quality._pdf_body(
                story,
                styles,
                f"La siguiente tabla presenta {title[:1].lower() + title[1:] if title else 'la información disponible'}, utilizando únicamente los datos registrados en la fuente del informe.",
            )
        return base_caption(story, styles, text)

    return wrapped


def draw_header_safe(canvas: Any, report: dict[str, Any], page: int, pages: int) -> None:
    """Encabezado institucional con texto completamente contenido en cada celda."""
    width, height = A4
    x = 0.90 * cm
    top = height - 0.55 * cm
    row = 1.50 * cm
    total = width - 1.80 * cm
    left = 4.80 * cm
    right = 4.60 * cm
    middle = total - left - right
    bottom = top - 2 * row
    right_x = x + left + middle

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
            x + 0.15 * cm,
            top - row + 0.14 * cm,
            width=left - 0.30 * cm,
            height=row - 0.28 * cm,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
    else:
        _draw_cell_text(
            canvas, "LOGO INSTITUCIONAL NO CARGADO",
            x, top - row, left, row, size=6.5, bold=True, max_lines=2,
        )

    _draw_cell_text(
        canvas,
        "Unidad Titulación y Eficiencia Terminal",
        x + left,
        top - row,
        middle,
        row,
        size=8.8,
        max_lines=2,
    )
    _draw_cell_text(
        canvas,
        f"Código: {report.get('code', '')}\nVersión: {report.get('version', '1.0')}".replace("\n", " | "),
        right_x,
        top - row,
        right,
        row,
        size=6.6,
        max_lines=2,
    )

    _draw_cell_text(
        canvas,
        f"Fecha de Elaboración: {institutional.format_date(report.get('elaboration_date'))}",
        x,
        bottom,
        left,
        row,
        size=7.0,
        max_lines=2,
    )
    _draw_cell_text(
        canvas,
        institutional.header_title(report),
        x + left,
        bottom,
        middle,
        row,
        size=7.0,
        bold=True,
        max_lines=3,
    )
    _draw_cell_text(
        canvas,
        f"Página {page} de {pages}",
        right_x,
        bottom,
        right,
        row,
        size=7.6,
        max_lines=1,
    )
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
    institutional.draw_header = draw_header_safe
    final_fixes.install()

    # Toda tabla debe tener contexto inmediato. Se añade únicamente cuando la
    # función que construyó la sección no proporcionó ya un párrafo explicativo.
    if not getattr(report_quality, "_table_context_guard_installed", False):
        report_quality._pdf_caption = _contextual_pdf_caption(report_quality._pdf_caption)
        report_quality._table_context_guard_installed = True

    _INSTALLED = True
