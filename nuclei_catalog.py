from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

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
            _nucleus(3, "Planificación y diseño curricular"),
            _nucleus(4, "Aprendizaje y enseñanza en Educación Básica"),
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


def _wrapped_label(nucleus: dict[str, Any]) -> str:
    guide = textwrap.fill(str(nucleus["guide"]), width=25, break_long_words=False)
    return f"Núcleo {nucleus['number']}\n{guide}"


def create_cycle_diagram(catalog: dict[str, Any], output_path: Path) -> Path:
    nuclei = catalog.get("nuclei", [])
    if len(nuclei) != 4:
        raise ValueError("El gráfico circular requiere exactamente cuatro núcleos.")

    figure, axis = plt.subplots(figsize=(10.5, 7.0))
    axis.set_xlim(0, 12)
    axis.set_ylim(0, 8)
    axis.axis("off")

    positions = [(6, 6.55), (9.65, 4.0), (6, 1.45), (2.35, 4.0)]
    box_width = 3.35
    box_height = 1.55

    for index, (x, y) in enumerate(positions):
        next_x, next_y = positions[(index + 1) % 4]
        axis.add_patch(
            FancyArrowPatch(
                (x, y),
                (next_x, next_y),
                arrowstyle="-|>",
                mutation_scale=19,
                linewidth=2.1,
                color="#b87822",
                connectionstyle="arc3,rad=0.15",
                shrinkA=62,
                shrinkB=62,
                zorder=1,
            )
        )

    for index, nucleus in enumerate(nuclei):
        x, y = positions[index]
        axis.add_patch(
            FancyBboxPatch(
                (x - box_width / 2, y - box_height / 2),
                box_width,
                box_height,
                boxstyle="round,pad=0.16,rounding_size=0.15",
                linewidth=1.25,
                edgecolor="#9a651f",
                facecolor="#f4c87f",
                zorder=2,
            )
        )
        guide_length = len(str(nucleus["guide"]))
        font_size = 8.5 if guide_length <= 34 else 7.5 if guide_length <= 52 else 6.8
        axis.text(
            x,
            y,
            _wrapped_label(nucleus),
            ha="center",
            va="center",
            fontsize=font_size,
            fontweight="bold",
            linespacing=1.15,
            zorder=3,
        )

    figure.tight_layout(pad=0.2)
    figure.savefig(output_path, dpi=200, bbox_inches="tight", pad_inches=0.08)
    plt.close(figure)
    return output_path
