from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

from coordinator_registry import normalize


def _nucleus(number: int, guide: str, subjects: list[str] | None = None) -> dict[str, Any]:
    return {"number": number, "guide": guide, "subjects": subjects or []}


NUCLEI_CATALOG: dict[str, dict[str, Any]] = {
    "administracion": {
        "career": "Administración",
        "nuclei": [
            _nucleus(1, "Gestión estratégica"),
            _nucleus(2, "Gestión de procesos y calidad"),
            _nucleus(3, "Gestión financiera"),
            _nucleus(4, "Gestión comercial"),
        ],
    },
    "contabilidad": {
        "career": "Contabilidad",
        "nuclei": [
            _nucleus(1, "Contabilidad financiera"),
            _nucleus(2, "Contabilidad de costos"),
            _nucleus(3, "Tributación"),
            _nucleus(4, "Gestión financiera"),
        ],
    },
    "desarrollo de software": {
        "career": "Desarrollo de Software",
        "nuclei": [
            _nucleus(1, "Programación orientada a objetos"),
            _nucleus(2, "Implementación y gestión de base de datos"),
            _nucleus(3, "Desarrollo de aplicaciones móviles"),
            _nucleus(4, "Aplicaciones web"),
        ],
    },
    "educacion inicial": {
        "career": "Educación Inicial",
        "nuclei": [
            _nucleus(1, "Desarrollo integral"),
            _nucleus(2, "Gerencia pedagógica"),
            _nucleus(3, "Planificación curricular"),
            _nucleus(4, "Habilidades neurolingüísticas"),
        ],
    },
    "educacion basica": {
        "career": "Educación Básica",
        "nuclei": [
            _nucleus(1, "Psicología y neuroeducación en el entorno educativo"),
            _nucleus(2, "Fundamentos teórico-prácticos de la educación"),
            _nucleus(3, "Aprendizaje y enseñanza en Educación Básica"),
            _nucleus(4, "Planificación y diseño curricular"),
        ],
    },
    "enfermeria": {
        "career": "Enfermería",
        "nuclei": [
            _nucleus(1, "Enfermería en promoción y prevención de la salud"),
            _nucleus(2, "Práctica clínica en enfermería"),
            _nucleus(3, "Enfermería técnica y comunitaria"),
            _nucleus(4, "Enfermería para el cuidado integral de pacientes"),
        ],
    },
    "estetica integral": {
        "career": "Estética Integral",
        "nuclei": [
            _nucleus(
                1,
                "Química cosmética y ciencias dermatocosméticas",
                ["Química cosmética", "Cosmiatría", "Dermocosmética"],
            ),
            _nucleus(
                2,
                "Fundamentos del diagnóstico y tratamientos estéticos",
                ["Cuidado de la piel", "Valoración estética", "Aparatología en estética"],
            ),
            _nucleus(
                3,
                "Abordaje integral en terapias faciales y estéticas",
                ["Terapias faciales", "Terapéutica en estética", "Terapias estéticas integrales"],
            ),
            _nucleus(
                4,
                "Terapias corporales integrales y prácticas sostenibles",
                ["Masajes y terapias corporales", "Terapias alternativas", "Terapia y manejo de desechos"],
            ),
        ],
    },
    "gestion del talento humano": {
        "career": "Gestión del Talento Humano",
        "nuclei": [
            _nucleus(1, "Administración de la compensación y beneficios laborales"),
            _nucleus(2, "Atracción y gestión del talento humano"),
            _nucleus(3, "Salud y bienestar de talento humano"),
            _nucleus(4, "Evaluación organizacional"),
        ],
    },
    "marketing digital y comercio electronico": {
        "career": "Marketing Digital y Comercio Electrónico",
        "nuclei": [
            _nucleus(1, "Bases del marketing"),
            _nucleus(2, "El consumidor"),
            _nucleus(3, "Comunicación"),
            _nucleus(4, "Acción del marketing"),
        ],
    },
    "redes y telecomunicaciones": {
        "career": "Redes y Telecomunicaciones",
        "nuclei": [
            _nucleus(1, "Sistemas de transmisión de datos"),
            _nucleus(2, "Redes LAN y WAN"),
            _nucleus(3, "Sistemas operativos y servidores"),
            _nucleus(4, "Administración, seguridad y auditoría de redes"),
        ],
    },
}


CATALOG_ORDER = tuple(NUCLEI_CATALOG)


def catalog_for_career(career_name: str) -> dict[str, Any] | None:
    key = normalize(career_name)
    if key in NUCLEI_CATALOG:
        return NUCLEI_CATALOG[key]
    for catalog_key, item in NUCLEI_CATALOG.items():
        if catalog_key in key or key in catalog_key:
            return item
    return None


def catalogs_for_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    active = {
        normalize(str(career.get("name") or "")): career
        for career in report.get("careers", [])
    }
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in CATALOG_ORDER:
        item = NUCLEI_CATALOG[key]
        if not any(key == active_key or key in active_key or active_key in key for active_key in active):
            continue
        normalized = normalize(item["career"])
        if normalized not in seen:
            found.append(item)
            seen.add(normalized)
    return found


def _wrapped_guide(guide: str) -> str:
    length = len(guide)
    width = 23 if length <= 40 else 21 if length <= 60 else 19
    return textwrap.fill(guide, width=width, break_long_words=False, break_on_hyphens=False)


def _font_size(guide: str) -> float:
    length = len(guide)
    if length <= 28:
        return 10.4
    if length <= 45:
        return 9.4
    if length <= 65:
        return 8.4
    return 7.6


def create_cycle_diagram(catalog: dict[str, Any], output_path: Path) -> Path:
    """Crea un diagrama limpio y uniforme para Word y PDF."""

    nuclei = catalog.get("nuclei", [])
    if len(nuclei) != 4:
        raise ValueError("El gráfico circular requiere exactamente cuatro núcleos.")

    figure, axis = plt.subplots(figsize=(10.8, 6.7), facecolor="white")
    axis.set_xlim(0, 12)
    axis.set_ylim(0, 7.6)
    axis.set_aspect("equal")
    axis.axis("off")

    positions = [(6.0, 6.15), (9.55, 3.8), (6.0, 1.45), (2.45, 3.8)]
    card_width = 3.15
    card_height = 1.45
    card_colors = ("#E6F0F8", "#E4F3ED", "#FFF0DA", "#EEE8F7")
    border_colors = ("#2D638B", "#32745E", "#B8751B", "#6D5594")
    badge_colors = ("#24557A", "#276451", "#A86410", "#5B457F")

    arrow_pairs = (
        ((7.35, 5.55), (8.45, 4.75), 0.08),
        ((8.45, 2.85), (7.35, 2.05), 0.08),
        ((4.65, 2.05), (3.55, 2.85), 0.08),
        ((3.55, 4.75), (4.65, 5.55), 0.08),
    )
    for start, end, curve in arrow_pairs:
        axis.add_patch(
            FancyArrowPatch(
                start,
                end,
                arrowstyle="-|>",
                mutation_scale=17,
                linewidth=1.8,
                color="#74879A",
                connectionstyle=f"arc3,rad={curve}",
                zorder=1,
            )
        )

    center_shadow = Circle((6.08, 3.72), 1.02, facecolor="#D8DEE5", edgecolor="none", alpha=0.55, zorder=1)
    center = Circle((6.0, 3.8), 1.02, facecolor="#244A73", edgecolor="#17354F", linewidth=1.2, zorder=2)
    axis.add_patch(center_shadow)
    axis.add_patch(center)
    axis.text(6.0, 4.02, "4 NÚCLEOS", ha="center", va="center", fontsize=12.2, fontweight="bold", color="white", zorder=3)
    axis.text(6.0, 3.62, "ESTRUCTURANTES", ha="center", va="center", fontsize=8.6, fontweight="bold", color="#DDEAF5", zorder=3)
    axis.text(6.0, 3.28, "Integración curricular", ha="center", va="center", fontsize=7.5, color="#DDEAF5", zorder=3)

    for index, nucleus in enumerate(nuclei):
        x, y = positions[index]

        shadow = FancyBboxPatch(
            (x - card_width / 2 + 0.08, y - card_height / 2 - 0.09),
            card_width,
            card_height,
            boxstyle="round,pad=0.17,rounding_size=0.18",
            linewidth=0,
            facecolor="#BFC8D1",
            alpha=0.45,
            zorder=2,
        )
        card = FancyBboxPatch(
            (x - card_width / 2, y - card_height / 2),
            card_width,
            card_height,
            boxstyle="round,pad=0.17,rounding_size=0.18",
            linewidth=1.25,
            edgecolor=border_colors[index],
            facecolor=card_colors[index],
            zorder=3,
        )
        axis.add_patch(shadow)
        axis.add_patch(card)

        badge_x = x - card_width / 2 + 0.36
        badge_y = y + card_height / 2 - 0.30
        badge = Circle((badge_x, badge_y), 0.30, facecolor=badge_colors[index], edgecolor="white", linewidth=1.2, zorder=4)
        axis.add_patch(badge)
        axis.text(
            badge_x,
            badge_y,
            f"{int(nucleus['number']):02d}",
            ha="center",
            va="center",
            fontsize=8.6,
            fontweight="bold",
            color="white",
            zorder=5,
        )

        guide = str(nucleus["guide"])
        axis.text(
            x + 0.12,
            y,
            _wrapped_guide(guide),
            ha="center",
            va="center",
            fontsize=_font_size(guide),
            fontweight="semibold",
            color="#243746",
            linespacing=1.18,
            zorder=5,
        )

    axis.text(
        6.0,
        0.15,
        "Los cuatro núcleos articulan los conocimientos y competencias de la carrera.",
        ha="center",
        va="center",
        fontsize=8.4,
        color="#526575",
    )

    figure.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.04)
    figure.savefig(output_path, dpi=220, bbox_inches="tight", pad_inches=0.06, facecolor="white")
    plt.close(figure)
    return output_path
