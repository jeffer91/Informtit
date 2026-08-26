from __future__ import annotations

from typing import Any

import report_completion
import report_integrity_core as integrity
import report_integrity_pdf as integrity_pdf
import report_quality


def _format_names(names: list[str]) -> str:
    clean = list(dict.fromkeys(str(name or "").strip() for name in names if str(name or "").strip()))
    if not clean:
        return "—"
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} y {clean[1]}"
    return ", ".join(clean[:-1]) + f" y {clean[-1]}"


def _pct(value: Any) -> str:
    if value is None:
        return "No aplica"
    return report_quality._pct(float(value))


def _extreme_names(rows: list[dict[str, Any]], value_key: str, name_key: str) -> tuple[list[str], list[str], float | None, float | None]:
    usable = [row for row in rows if row.get(value_key) is not None]
    if not usable:
        return [], [], None, None
    maximum = max(float(row[value_key]) for row in usable)
    minimum = min(float(row[value_key]) for row in usable)
    best = [str(row.get(name_key) or "Sin nombre") for row in usable if float(row[value_key]) == maximum]
    worst = [str(row.get(name_key) or "Sin nombre") for row in usable if float(row[value_key]) == minimum]
    return best, worst, maximum, minimum


def header_title(report: dict[str, Any]) -> str:
    audit = integrity_pdf.current_audit()
    title = str((audit or {}).get("document_title") or report.get("name") or "Informe de Titulación").rstrip(".")
    return f"{title}. {report.get('period', '')} - Modalidad {report_quality.base.modality(report)}"


def cover_pdf(report: dict[str, Any], styles: Any) -> list[Any]:
    effective = dict(report)
    audit = integrity_pdf.current_audit()
    if audit and audit.get("document_title"):
        effective["name"] = audit["document_title"]
    return integrity_pdf.cover_pdf_integrity(effective, styles)


def conclusions(report_id: int, report: dict[str, Any]) -> list[str]:
    audit = integrity.audit_report(report_id, resolve_resources=False)
    if audit["mode"] == "no_population":
        return ["No se identificaron hallazgos cuantificables con la información disponible."]
    if audit["mode"] == "import_error":
        return ["La información disponible no permite emitir conclusiones institucionales porque la carga no pudo conciliarse correctamente."]

    metrics = audit["metrics"]
    out: list[str] = []

    req = metrics["requirements"]
    if req["registered"]:
        req_metric = metrics["indicators"]["requirements_compliance"]
        out.append(
            f"Requisitos registró {req['registered']} estudiantes; {req['complete']} cumplieron integralmente "
            f"({_pct(req_metric['result'])}), {req['pending']} presentaron incumplimientos y {req['incomplete']} información incompleta."
        )
        req_detail = report_completion.corrected_requirement_analysis(report_id)
        requirement_rows = list((req_detail or {}).get("requirements", []))
        if requirement_rows:
            minimum = min(float(row["percentage"]) for row in requirement_rows)
            tied = [row for row in requirement_rows if float(row["percentage"]) == minimum]
            labels = _format_names([str(row["label"]) for row in tied])
            total_no = sum(int(row.get("does_not_comply") or 0) for row in tied)
            noun = "El requisito" if len(tied) == 1 else "Los requisitos"
            verb = "fue" if len(tied) == 1 else "fueron"
            out.append(
                f"{noun} con menor cumplimiento {verb} {labels}, con {_pct(minimum)}; "
                f"en conjunto registraron {total_no} marcaciones de NO CUMPLE."
            )

    schedules = metrics["schedules"]
    if schedules["total"]:
        out.append(
            f"El cronograma contiene {schedules['total']} actividades únicas; {schedules['evaluated']} cuentan con datos de ejecución y "
            f"{schedules['pending_evaluation']} permanecen sin evaluar. Se identificaron {schedules['incomplete_evidence']} actividades evaluadas con evidencia incompleta."
        )

    nuclei = metrics["nuclei"]
    if nuclei["records"]:
        nuc_metric = metrics["indicators"]["nuclei_approval"]
        out.append(
            f"Núcleos conserva {nuclei['courses']} cursos y {nuclei['records']} registros; {nuclei['evaluated']} fueron evaluados, "
            f"{nuclei['unevaluated']} quedaron no evaluados y la aprobación entre evaluados fue {_pct(nuc_metric['result'])}. "
            f"El promedio institucional de las notas evaluadas fue {report_quality._fmt(nuclei['institutional_stats']['average'])}."
        )
        best, worst, maximum, minimum = _extreme_names(list(nuclei["careers"]), "approval", "career")
        if maximum is not None and minimum is not None:
            if maximum == minimum:
                out.append(f"Todas las carreras analizadas en Núcleos registraron la misma aprobación ({_pct(maximum)}).")
            else:
                out.append(
                    f"La mayor aprobación en Núcleos correspondió{' conjuntamente' if len(best) > 1 else ''} a {_format_names(best)} ({_pct(maximum)}) y "
                    f"la menor correspondió{' conjuntamente' if len(worst) > 1 else ''} a {_format_names(worst)} ({_pct(minimum)})."
                )

    comp = metrics["complexive"]
    if comp["registered"]:
        comp_metric = metrics["indicators"]["complexive_approval"]
        out.append(
            f"El Examen Complexivo registró {comp['registered']} estudiantes: {comp['approved']} aprobados finales, {comp['failed']} reprobados y "
            f"{comp['not_evaluated']} no evaluados. La aprobación final sobre registrados fue {_pct(comp_metric['result'])}."
        )
        best, worst, maximum, minimum = _extreme_names(list(comp["careers"]), "approval_percentage", "career")
        if maximum is not None and minimum is not None:
            if maximum == minimum:
                out.append(f"Todas las carreras del Examen Complexivo registraron la misma aprobación final ({_pct(maximum)}).")
            else:
                out.append(
                    f"La mayor aprobación final del Complexivo correspondió{' conjuntamente' if len(best) > 1 else ''} a {_format_names(best)} ({_pct(maximum)}) y "
                    f"la menor correspondió{' conjuntamente' if len(worst) > 1 else ''} a {_format_names(worst)} ({_pct(minimum)})."
                )
        if comp["supplementary"]:
            sup_metric = metrics["indicators"]["supplementary_effectiveness"]
            out.append(
                f"El supletorio contó con {comp['supplementary']} participantes y {comp['recovered']} recuperados, con una efectividad de {_pct(sup_metric['result'])}."
            )

    thesis = metrics["thesis"]
    if thesis["total"]:
        average_final = thesis.get("average_final")
        out.append(
            f"Trabajo de Titulación registró {thesis['total']} {'estudiante' if thesis['total'] == 1 else 'estudiantes'}, "
            f"{thesis['approved']} {'aprobado' if thesis['approved'] == 1 else 'aprobados'}, {thesis['failed']} reprobados y {thesis['incomplete']} casos incompletos; "
            f"el promedio final de los casos con nota fue {report_quality._fmt(average_final)}."
        )
        if thesis["total"] == 1:
            out.append("El resultado de Trabajo de Titulación corresponde a un caso individual y no constituye una tendencia institucional.")
        elif 2 <= thesis["total"] <= 9:
            out.append(f"Trabajo de Titulación presenta una población reducida (n = {thesis['total']}), por lo que sus resultados deben interpretarse con cautela.")

    zero_noeval = integrity.no_evaluated_zero_count(report_id)
    if zero_noeval:
        out.append(
            f"Se detectaron {zero_noeval} registros de Núcleos con estado No evaluado y nota numérica 0; esos ceros se conservaron para trazabilidad, pero fueron excluidos de promedios, mínimos, máximos, medianas, desviaciones y denominadores de aprobación."
        )

    return out


def recommendations(report_id: int, report: dict[str, Any]) -> list[dict[str, str]]:
    audit = integrity.audit_report(report_id, resolve_resources=False)
    if audit["mode"] != "normal":
        return []
    metrics = audit["metrics"]
    rows: list[dict[str, str]] = []

    def add(hallazgo: str, accion: str, responsable: str, indicador: str, actual: str, meta: str, plazo: str, prioridad: str, evidencia: str) -> None:
        rows.append({
            "hallazgo": hallazgo,
            "accion": accion,
            "responsable": responsable,
            "indicador": indicador,
            "actual": actual,
            "meta": meta,
            "plazo": plazo,
            "prioridad": prioridad,
            "evidencia": evidencia,
        })

    req = metrics["requirements"]
    if req["pending"] or req["incomplete"]:
        total = req["pending"] + req["incomplete"]
        add(
            f"{total} casos de requisitos requieren cierre o clasificación",
            "Regularizar los incumplimientos y completar la información faltante por responsable y fecha de cierre.",
            "Coordinación de Titulación y áreas responsables",
            "Casos de requisitos pendientes o incompletos",
            str(total),
            "0",
            "Antes del cierre del período",
            "Alta",
            "Matriz de requisitos",
        )

    nuclei = metrics["nuclei"]
    nuc_metric = metrics["indicators"]["nuclei_approval"]
    if nuclei["unevaluated"]:
        add(
            f"{nuclei['unevaluated']} registros no evaluados en Núcleos",
            "Clasificar cada caso como ausencia, retiro, pendiente académico u otra novedad documentada.",
            "Coordinaciones de carrera",
            "No evaluados en Núcleos",
            str(nuclei["unevaluated"]),
            "0 sin clasificar",
            "Antes de emitir la versión final",
            "Alta",
            "Consolidado de Núcleos",
        )
    if nuc_metric["result"] is not None and float(nuc_metric["result"]) < 70:
        best, worst, _, minimum = _extreme_names(list(nuclei["careers"]), "approval", "career")
        del best
        add(
            f"Aprobación institucional de Núcleos por debajo del 70 %; menor resultado en {_format_names(worst)} ({_pct(minimum)})",
            "Implementar refuerzo académico focalizado en los cursos y carreras con menor desempeño y verificar el resultado en la siguiente evaluación.",
            "Coordinaciones de carrera y docentes responsables",
            "Aprobación de Núcleos sobre evaluados",
            _pct(nuc_metric["result"]),
            "≥ 70,00 %",
            "Siguiente evaluación",
            "Alta",
            "Plan de refuerzo y consolidado de Núcleos",
        )

    comp = metrics["complexive"]
    comp_metric = metrics["indicators"]["complexive_approval"]
    if comp["not_evaluated"]:
        add(
            f"{comp['not_evaluated']} estudiantes no evaluados en Complexivo",
            "Clasificar y documentar individualmente la causa de cada caso antes del cierre.",
            "Coordinaciones de carrera",
            "No evaluados en Complexivo",
            str(comp["not_evaluated"]),
            "0 sin clasificar",
            "Antes de emitir la versión final",
            "Alta",
            "Consolidado del Examen Complexivo",
        )
    if comp_metric["result"] is not None and float(comp_metric["result"]) < 70:
        _, worst, _, minimum = _extreme_names(list(comp["careers"]), "approval_percentage", "career")
        add(
            f"Aprobación institucional del Complexivo por debajo del 70 %; menor resultado en {_format_names(worst)} ({_pct(minimum)})",
            "Implementar refuerzo académico focalizado y revisar los componentes con mayor dificultad antes de la siguiente convocatoria.",
            "Coordinaciones de carrera y docentes responsables",
            "Aprobación final del Examen Complexivo",
            _pct(comp_metric["result"]),
            "≥ 70,00 %",
            "Siguiente convocatoria",
            "Alta",
            "Plan de refuerzo y reporte comparativo",
        )

    thesis = metrics["thesis"]
    if thesis["incomplete"]:
        add(
            f"{thesis['incomplete']} casos incompletos en Trabajo de Titulación",
            "Completar la información académica y documental de cada caso antes del cierre.",
            "Tutoría y Coordinación de Titulación",
            "Casos incompletos en Trabajo de Titulación",
            str(thesis["incomplete"]),
            "0",
            "Antes de emitir la versión final",
            "Alta",
            "Expedientes y rúbricas",
        )

    schedules = metrics["schedules"]
    if schedules["pending_evaluation"] or schedules["incomplete_evidence"]:
        add(
            f"Cronograma con {schedules['pending_evaluation']} actividades sin evaluar y {schedules['incomplete_evidence']} con evidencia incompleta",
            "Completar fecha ejecutada, estado, porcentaje, evidencia y observación de cada actividad.",
            "Responsables de cada fase",
            "Actividades con ejecución completamente documentada",
            f"{schedules['evaluated']}/{schedules['total']}",
            f"{schedules['total']}/{schedules['total']}",
            "Antes de emitir la versión final",
            "Alta",
            "Cronograma y evidencias",
        )

    duplicates = audit["duplicates"]
    if duplicates["unresolved_probable"]:
        add(
            f"{duplicates['unresolved_probable']} duplicados probables requieren resolución",
            "Verificar identidad, carrera y fuente original; confirmar o descartar cada coincidencia antes del cierre.",
            "Coordinación de Titulación",
            "Duplicados probables sin resolver",
            str(duplicates["unresolved_probable"]),
            "0",
            "Antes del cierre",
            "Media",
            "Bitácora de duplicados",
        )

    pending_states = audit["states"]["pending_classification"]
    if pending_states:
        add(
            f"{pending_states} estados requieren clasificación específica",
            "Reclasificar cada caso usando el catálogo institucional de estados y conservar la evidencia de la decisión.",
            "Coordinación de Titulación y áreas responsables",
            "Estados pendientes de clasificar",
            str(pending_states),
            "0",
            "Antes del cierre",
            "Media",
            "Matriz de estados",
        )

    return rows


def strengths_criticals_actions(report_id: int, report: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    audit = integrity.audit_report(report_id, resolve_resources=False)
    if audit["mode"] != "normal":
        return [], ["No se identificaron hallazgos cuantificables con la información disponible."], []

    metrics = audit["metrics"]
    strengths: list[str] = []
    critical: list[str] = []

    req_metric = metrics["indicators"]["requirements_compliance"]
    if req_metric["result"] is not None:
        text = f"Cumplimiento integral de requisitos: {_pct(req_metric['result'])}."
        (strengths if float(req_metric["result"]) >= 80 else critical).append(text)

    nuc_metric = metrics["indicators"]["nuclei_approval"]
    if nuc_metric["result"] is not None:
        text = f"Aprobación institucional de Núcleos sobre evaluados: {_pct(nuc_metric['result'])}."
        (strengths if float(nuc_metric["result"]) >= 70 else critical).append(text)
    if metrics["nuclei"]["unevaluated"]:
        critical.append(f"{metrics['nuclei']['unevaluated']} registros de Núcleos permanecen no evaluados.")

    comp_metric = metrics["indicators"]["complexive_approval"]
    if comp_metric["result"] is not None:
        text = f"Aprobación final del Examen Complexivo sobre registrados: {_pct(comp_metric['result'])}."
        (strengths if float(comp_metric["result"]) >= 70 else critical).append(text)
    if metrics["complexive"]["not_evaluated"]:
        critical.append(f"{metrics['complexive']['not_evaluated']} estudiantes del Complexivo permanecen no evaluados.")

    thesis = metrics["thesis"]
    if thesis["total"] and not thesis["incomplete"]:
        strengths.append(f"Trabajo de Titulación registra {thesis['total']} casos con estado final completo.")
    elif thesis["incomplete"]:
        critical.append(f"Trabajo de Titulación mantiene {thesis['incomplete']} casos incompletos.")

    schedules = metrics["schedules"]
    if schedules["pending_evaluation"] or schedules["incomplete_evidence"]:
        critical.append(
            f"Cronograma: {schedules['pending_evaluation']} actividades sin evaluar y {schedules['incomplete_evidence']} con evidencia incompleta."
        )
    elif schedules["total"]:
        strengths.append(f"Las {schedules['total']} actividades del cronograma cuentan con ejecución documentada.")

    if not critical:
        critical.append("No se identificaron hallazgos críticos cuantificables con la información disponible.")

    recs = recommendations(report_id, report)
    actions = [f"{row['accion']} Indicador: {row['indicador']}; meta: {row['meta']}." for row in recs[:5]]
    return strengths, critical, actions
