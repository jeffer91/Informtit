from __future__ import annotations

import html
from typing import Any

from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

import report_completion
import report_quality
from eligibility_service import get_eligibility


def _source_text(source: dict[str, Any]) -> str:
    parts = [
        str(source.get("campus") or "Sin sede"),
        f"nota {report_quality._fmt(source.get('grade'))}",
    ]
    if source.get("module_code"):
        parts.append(f"módulo {source['module_code']}")
    if source.get("teacher_name"):
        parts.append(str(source["teacher_name"]))
    return " · ".join(parts)


def _add_docx_eligibility(document: Any, context: Any, report_id: int) -> None:
    eligibility = get_eligibility(report_id)
    if not eligibility.get("careers") and not eligibility.get("unmatched"):
        return

    summary = eligibility["summary"]
    report_quality._docx_heading(document, context, 2, "Habilitación para el Examen Complexivo")
    narrative = (
        f"De {summary['eligible_for_nuclei']} estudiantes que cumplieron los ocho requisitos previos e ingresaron a Núcleos, "
        f"{summary['eligible_for_complexive']} aprobaron los cuatro núcleos y quedaron habilitados para rendir el Examen Complexivo, "
        f"{summary['not_habilitated']} registraron uno o más núcleos reprobados y {summary['pending']} mantuvieron uno o más núcleos pendientes. "
        f"El porcentaje de habilitación desde la etapa de Núcleos fue {report_quality._pct(summary['habilitation_percentage'])}."
    )
    if summary.get("grade_conflicts"):
        narrative += (
            f" Además, se detectaron {summary['grade_conflicts']} conflicto(s) de notas del mismo núcleo entre cursos o sedes; "
            "estos casos no se consideraron habilitados hasta su revisión."
        )
    report_quality._docx_body(document, narrative)

    report_quality._docx_caption(document, context.table_caption("Habilitación para el Examen Complexivo por carrera"))
    report_quality._docx_table(
        document,
        ["Carrera", "Ingresaron a Núcleos", "Habilitados Complexivo", "Núcleos reprobados", "Pendientes", "% habilitación"],
        [
            [
                row["career_name"], row["total"], row["habilitated"], row["not_habilitated"],
                row["pending"], report_quality._pct(row["habilitation_percentage"]),
            ]
            for row in eligibility["careers"]
        ],
        [2.25, 0.9, 0.95, 0.95, 0.75, 0.9],
    )

    for career in eligibility["careers"]:
        rows = [
            row for row in eligibility["rows"]
            if row["career_name"] == career["career_name"] and row["option"] == "Examen Complexivo"
        ]
        if not rows:
            continue
        report_quality._docx_heading(document, context, 3, career["career_name"])
        report_quality._docx_table(
            document,
            ["Estudiante", "Sede", "Núcleo 1", "Núcleo 2", "Núcleo 3", "Núcleo 4", "Estado"],
            [
                [
                    row["full_name"], row.get("campus") or "—",
                    report_quality._fmt(row["nucleus_1"]), report_quality._fmt(row["nucleus_2"]),
                    report_quality._fmt(row["nucleus_3"]), report_quality._fmt(row["nucleus_4"]),
                    row["stage_status"],
                ]
                for row in rows
            ],
            [2.25, 0.7, 0.58, 0.58, 0.58, 0.58, 1.25],
        )

    conflicts = eligibility.get("grade_conflicts", [])
    if conflicts:
        students = {int(row["student_id"]): row for row in eligibility.get("rows", [])}
        report_quality._docx_heading(document, context, 3, "Conflictos de notas por curso o sede")
        report_quality._docx_body(
            document,
            "Cuando un estudiante registró valores diferentes para el mismo núcleo en más de un curso, Informtit no seleccionó una nota de forma automática. El caso quedó pendiente de revisión.",
        )
        report_quality._docx_table(
            document,
            ["Estudiante", "Carrera", "Núcleo", "Fuentes encontradas"],
            [
                [
                    students.get(int(item["student_id"]), {}).get("full_name") or "—",
                    students.get(int(item["student_id"]), {}).get("career_name") or "—",
                    item["nucleus_number"],
                    " | ".join(_source_text(source) for source in item.get("sources", [])),
                ]
                for item in conflicts
            ],
            [2.0, 1.6, 0.6, 2.9],
        )


def _add_pdf_eligibility(story: list[Any], context: Any, styles: Any, report_id: int) -> None:
    eligibility = get_eligibility(report_id)
    if not eligibility.get("careers") and not eligibility.get("unmatched"):
        return

    summary = eligibility["summary"]
    report_quality._pdf_heading(story, context, styles, 2, "Habilitación para el Examen Complexivo")
    narrative = (
        f"De {summary['eligible_for_nuclei']} estudiantes que cumplieron los ocho requisitos previos e ingresaron a Núcleos, "
        f"{summary['eligible_for_complexive']} aprobaron los cuatro núcleos y quedaron habilitados para rendir el Examen Complexivo, "
        f"{summary['not_habilitated']} registraron uno o más núcleos reprobados y {summary['pending']} mantuvieron uno o más núcleos pendientes. "
        f"El porcentaje de habilitación desde la etapa de Núcleos fue {report_quality._pct(summary['habilitation_percentage'])}."
    )
    if summary.get("grade_conflicts"):
        narrative += (
            f" Además, se detectaron {summary['grade_conflicts']} conflicto(s) de notas del mismo núcleo entre cursos o sedes; "
            "estos casos no se consideraron habilitados hasta su revisión."
        )
    report_quality._pdf_body(story, styles, narrative)

    report_quality._pdf_caption(story, styles, context.table_caption("Habilitación para el Examen Complexivo por carrera"))
    career_rows = [
        [
            Paragraph(html.escape(row["career_name"]), styles["TableCell"]), row["total"], row["habilitated"],
            row["not_habilitated"], row["pending"], report_quality._pct(row["habilitation_percentage"]),
        ]
        for row in eligibility["careers"]
    ]
    story += [
        report_quality._pdf_table(
            ["Carrera", "Núcleos", "Habilitados", "Reprobados", "Pendientes", "% habilitación"],
            career_rows,
            [5.4 * cm, 2.0 * cm, 2.1 * cm, 2.1 * cm, 2.0 * cm, 2.4 * cm],
        ),
        Spacer(1, 0.2 * cm),
    ]

    for career in eligibility["careers"]:
        rows = [
            row for row in eligibility["rows"]
            if row["career_name"] == career["career_name"] and row["option"] == "Examen Complexivo"
        ]
        if not rows:
            continue
        report_quality._pdf_heading(story, context, styles, 3, career["career_name"])
        values = [
            [
                Paragraph(html.escape(row["full_name"]), styles["TableCell"]),
                Paragraph(html.escape(str(row.get("campus") or "—")), styles["TableCell"]),
                report_quality._fmt(row["nucleus_1"]), report_quality._fmt(row["nucleus_2"]),
                report_quality._fmt(row["nucleus_3"]), report_quality._fmt(row["nucleus_4"]),
                Paragraph(html.escape(row["stage_status"]), styles["TableCell"]),
            ]
            for row in rows
        ]
        story += [
            report_quality._pdf_table(
                ["Estudiante", "Sede", "N1", "N2", "N3", "N4", "Estado"],
                values,
                [5.3 * cm, 2.1 * cm, 1.25 * cm, 1.25 * cm, 1.25 * cm, 1.25 * cm, 4.1 * cm],
            ),
            Spacer(1, 0.2 * cm),
        ]

    conflicts = eligibility.get("grade_conflicts", [])
    if conflicts:
        students = {int(row["student_id"]): row for row in eligibility.get("rows", [])}
        report_quality._pdf_heading(story, context, styles, 3, "Conflictos de notas por curso o sede")
        report_quality._pdf_body(
            story,
            styles,
            "Cuando un estudiante registró valores diferentes para el mismo núcleo en más de un curso, Informtit no seleccionó una nota de forma automática. El caso quedó pendiente de revisión.",
        )
        values = [
            [
                Paragraph(html.escape(students.get(int(item["student_id"]), {}).get("full_name") or "—"), styles["TableCell"]),
                Paragraph(html.escape(students.get(int(item["student_id"]), {}).get("career_name") or "—"), styles["TableCell"]),
                item["nucleus_number"],
                Paragraph(html.escape(" | ".join(_source_text(source) for source in item.get("sources", []))), styles["TableCell"]),
            ]
            for item in conflicts
        ]
        story += [
            report_quality._pdf_table(
                ["Estudiante", "Carrera", "Núcleo", "Fuentes encontradas"],
                values,
                [4.5 * cm, 3.4 * cm, 1.6 * cm, 7.0 * cm],
            ),
            Spacer(1, 0.2 * cm),
        ]


def install() -> None:
    report_completion._add_docx_eligibility = _add_docx_eligibility
    report_completion._add_pdf_eligibility = _add_pdf_eligibility
