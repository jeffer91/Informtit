from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from coordinator_registry import normalize


NUCLEI_CATALOG: dict[str, dict[str, Any]] = {
    "estetica integral": {
        "career": "ESTÉTICA INTEGRAL",
        "nuclei": [
            {
                "number": 1,
                "guide": "QUÍMICA COSMETICA Y CIENCIAS DERMATOCOSMÉTICAS",
                "subjects": [
                    "QUIMÍCA COSMETICA",
                    "COSMIATRÍA",
                    "DERMOCOSMETICA",
                ],
            },
            {
                "number": 2,
                "guide": "FUNDAMENTOS DEL DIAGNOSTICO Y TRATAMIENTOS ESTÉTICO",
                "subjects": [
                    "CUIDADO DE LA PIEL",
                    "VALORACIÓN ESTÉTICA",
                    "APARATOLOGÍA EN ESTÉTICA",
                ],
            },
            {
                "number": 3,
                "guide": "ABORDAJE INTEGRAL EN TERAPIAS FACIALES Y ESTÉTICAS",
                "subjects": [
                    "TERAPIAS FACIALES",
                    "TERAPEUTICA EN ESTÉTICA",
                    "TERAPIAS ESTÉTICAS INTEGRALES",
                ],
            },
            {
                "number": 4,
                "guide": "TERAPIAS CORPORALES INTEGRALES Y PRACTICAS SOSTENIBLES",
                "subjects": [
                    "MASAJES Y TERAPIAS CORPORALES",
                    "TERAPIAS ALTERNATIVAS",
                    "TERAPIA Y MANEJO DE DESECHOS",
                ],
            },
        ],
    }
}


def catalog_for_career(career_name: str) -> dict[str, Any] | None:
    key = normalize(career_name)
    if key in NUCLEI_CATALOG:
        return NUCLEI_CATALOG[key]
    for catalog_key, item in NUCLEI_CATALOG.items():
        if catalog_key in key or key in catalog_key:
            return item
    return None


def catalogs_for_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for career in report.get("careers", []):
        item = catalog_for_career(str(career.get("name") or ""))
        if not item:
            continue
        key = normalize(item["career"])
        if key not in seen:
            found.append(item)
            seen.add(key)
    return found


def create_cycle_diagram(catalog: dict[str, Any], output_path: Path) -> Path:
    nuclei = catalog.get("nuclei", [])
    if len(nuclei) != 4:
        raise ValueError("El gráfico circular requiere exactamente cuatro núcleos.")

    figure, axis = plt.subplots(figsize=(9.4, 6.2))
    axis.set_xlim(0, 10)
    axis.set_ylim(0, 7)
    axis.axis("off")

    positions = [(5, 5.75), (8.05, 3.5), (5, 1.25), (1.95, 3.5)]
    box_width = 2.65
    box_height = 1.3

    for index, nucleus in enumerate(nuclei):
        x, y = positions[index]
        next_x, next_y = positions[(index + 1) % 4]
        arrow = FancyArrowPatch(
            (x, y),
            (next_x, next_y),
            arrowstyle="-|>",
            mutation_scale=20,
            linewidth=2.2,
            color="#d49a45",
            connectionstyle="arc3,rad=0.18",
            shrinkA=48,
            shrinkB=48,
            zorder=1,
        )
        axis.add_patch(arrow)

    for index, nucleus in enumerate(nuclei):
        x, y = positions[index]
        box = FancyBboxPatch(
            (x - box_width / 2, y - box_height / 2),
            box_width,
            box_height,
            boxstyle="round,pad=0.18,rounding_size=0.16",
            linewidth=1.2,
            edgecolor="#9a6d2f",
            facecolor="#f4c77f",
            zorder=2,
        )
        axis.add_patch(box)
        label = f"Núcleo {nucleus['number']}\n{nucleus['guide']}"
        axis.text(
            x,
            y,
            label,
            ha="center",
            va="center",
            fontsize=8.2,
            fontweight="bold",
            wrap=True,
            zorder=3,
        )

    axis.set_title(
        catalog.get("career") or "Contenido de núcleos",
        fontsize=15,
        fontweight="bold",
        pad=12,
    )
    figure.tight_layout()
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output_path
