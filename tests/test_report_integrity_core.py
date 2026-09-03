from __future__ import annotations

import unittest
from unittest.mock import patch

import report_integrity_core as integrity
import report_integrity_final_fixes as final_fixes
import report_integrity_requirements as integrity_requirements
import report_pdf_guard


class ReportIntegrityCoreTests(unittest.TestCase):
    def test_no_evaluated_zero_is_excluded_from_statistics(self):
        students = [
            {"final_status": "No evaluado", "final_grade": 0},
            {"final_status": "Aprobado", "final_grade": 8},
            {"final_status": "Reprobado", "final_grade": 6},
        ]
        grades = integrity.evaluated_grades(students)
        self.assertEqual(grades, [8.0, 6.0])
        values = integrity.stats(grades)
        self.assertEqual(values["average"], 7.0)
        self.assertEqual(values["median"], 7.0)
        self.assertEqual(values["minimum"], 6.0)
        self.assertEqual(values["maximum"], 8.0)
        self.assertEqual(values["stdev"], 1.0)

    def test_denominator_gap_requires_same_type(self):
        nuclei = integrity.metric("Aprobación Núcleos", 1012, 1019, "EVALUADOS")
        complexive = integrity.metric("Aprobación Complexivo", 241, 354, "REGISTRADOS")
        result = integrity.metric_gap(nuclei, complexive)
        self.assertFalse(result["comparable"])
        self.assertIsNone(result["difference"])

        a = integrity.metric("A", 80, 100, "REGISTRADOS")
        b = integrity.metric("B", 70, 100, "REGISTRADOS")
        comparable = integrity.metric_gap(a, b)
        self.assertTrue(comparable["comparable"])
        self.assertEqual(comparable["difference"], 10.0)

    def test_schedule_dedupe_normalizes_activity_and_dates(self):
        entries = [
            {
                "activity": " Núcleo 1 ",
                "start_date": "05/10/2026",
                "end_date": "08/10/2026",
            },
            {
                "activity": "núcleo   1",
                "start_date": "2026-10-05",
                "end_date": "2026-10-08",
            },
        ]
        unique, duplicates = integrity.dedupe_schedule_entries(entries)
        self.assertEqual(len(unique), 1)
        self.assertEqual(duplicates, 1)

    def test_rich_status_catalog(self):
        self.assertEqual(integrity.canonical_state(""), "SIN INFORMACIÓN")
        self.assertEqual(integrity.canonical_state("No aplica"), "NO APLICA")
        self.assertEqual(integrity.canonical_state("En revisión"), "EN REVISIÓN")
        self.assertEqual(integrity.canonical_state("Requiere corrección"), "REQUIERE CORRECCIÓN")
        self.assertEqual(integrity.canonical_state("Ausente"), "AUSENTE")
        self.assertEqual(integrity.canonical_state("texto desconocido"), "PENDIENTE DE CLASIFICAR")

    def test_duplicate_classification_distinguishes_exact_and_probable(self):
        base = {
            "nombre_carrera": "ENFERMERÍA",
            "nombre_profesor": "DOCENTE UNO",
            "nombre_estudiante": "ESTUDIANTE A",
            "materia": "NÚCLEO 1",
            "nota_final": "8",
            "estado": "Aprobado",
            "trabajoTitulacion": "Examen Complexivo",
        }
        exact = dict(base)
        probable = dict(base, nota_final="9")
        entries = integrity.nuclei_duplicate_entries([base, exact, probable])
        self.assertEqual(entries[0]["duplicate_type"], "DUPLICADO EXACTO")
        self.assertTrue(any(item["duplicate_type"] == "DUPLICADO PROBABLE" for item in entries))

    def test_nuclei_integrity_uses_explicit_modality_before_career_text(self):
        original_provider = integrity._RAW_NUCLEI_PROVIDER
        original_report_data = integrity.report_quality._report_data
        integrity._RAW_NUCLEI_PROVIDER = lambda _report_id: {
            "courses": [{
                "career_name": "ENFERMERÍA",
                "nucleus_number": 1,
                "course_title": "Núcleo 1",
                "official_modality": "en_linea",
                "students": [],
            }]
        }
        integrity.report_quality._report_data = lambda _report_id: {
            "modality": "en_linea",
            "period": "Mayo - Noviembre 2026",
        }
        try:
            courses, reasons = integrity.reconciled_courses(1)
        finally:
            integrity._RAW_NUCLEI_PROVIDER = original_provider
            integrity.report_quality._report_data = original_report_data

        self.assertEqual(len(courses), 1)
        self.assertEqual(reasons["Otra modalidad"], 0)

    def test_pdf_guard_accepts_explicit_modality_and_does_not_infer_from_career_name(self):
        online_report = {"modality": "en_linea"}
        presencial_report = {"modality": "presencial"}

        self.assertTrue(
            report_pdf_guard._allowed_nuclei_career(
                "ENFERMERÍA", online_report, "en_linea"
            )
        )
        self.assertFalse(
            report_pdf_guard._allowed_nuclei_career(
                "ENFERMERÍA", online_report, "presencial"
            )
        )
        self.assertTrue(
            report_pdf_guard._allowed_nuclei_career(
                "ENFERMERÍA", presencial_report, "presencial"
            )
        )
        self.assertFalse(
            report_pdf_guard._allowed_nuclei_career(
                "ENFERMERÍA", presencial_report, "en_linea"
            )
        )

    def test_nuclei_integrity_rejects_explicit_other_modality_even_without_online_name(self):
        original_provider = integrity._RAW_NUCLEI_PROVIDER
        original_report_data = integrity.report_quality._report_data
        integrity._RAW_NUCLEI_PROVIDER = lambda _report_id: {
            "courses": [{
                "career_name": "ENFERMERÍA",
                "nucleus_number": 1,
                "course_title": "Núcleo 1",
                "official_modality": "presencial",
                "students": [],
            }]
        }
        integrity.report_quality._report_data = lambda _report_id: {
            "modality": "en_linea",
            "period": "Mayo - Noviembre 2026",
        }
        try:
            courses, reasons = integrity.reconciled_courses(1)
        finally:
            integrity._RAW_NUCLEI_PROVIDER = original_provider
            integrity.report_quality._report_data = original_report_data

        self.assertEqual(courses, [])
        self.assertEqual(reasons["Otra modalidad"], 1)


    def test_audit_source_contains_blocking_population_controls(self):
        source = open("report_integrity_core.py", encoding="utf-8").read()
        self.assertIn("Población maestra de Núcleos conciliada", source)
        self.assertIn("Integridad de cursos importados de Núcleos", source)
        self.assertIn("not population[\"ok\"]", source)
        self.assertIn("source_course_count != stored_course_count", source)

    def test_pdf_preflight_exposes_missing_student_names(self):
        source = open("static/pdf-progress.js", encoding="utf-8").read()
        self.assertIn("audit.nuclei_population", source)
        self.assertIn("<strong>Faltantes:</strong>", source)
        self.assertIn("population.missing_students", source)

    def test_dense_ranking_keeps_ties_in_same_position(self):
        self.assertEqual(
            final_fixes.dense_ranks([100.0, 100.0, 97.37, 97.37, 90.0]),
            [1, 1, 2, 2, 3],
        )

    def test_requirement_dedupe_preserves_more_critical_state(self):
        students = [
            {
                "identification": "0101",
                "full_name": "ESTUDIANTE UNO",
                "career_name": "CARRERA",
                "documentation_status": "CUMPLE",
            },
            {
                "identification": "0101",
                "full_name": "ESTUDIANTE UNO",
                "career_name": "CARRERA",
                "documentation_status": "REQUIERE CORRECCIÓN",
            },
        ]
        merged = integrity_requirements._dedupe(students)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["documentation_status"], "REQUIERE CORRECCIÓN")

    def test_empty_requirement_columns_are_not_silently_omitted(self):
        original = integrity_requirements.get_report_roster
        integrity_requirements.get_report_roster = lambda report_id: {
            "students": [
                {
                    "identification": "0101",
                    "full_name": "ESTUDIANTE UNO",
                    "career_name": "CARRERA",
                }
            ]
        }
        try:
            result = integrity_requirements.corrected_requirement_analysis(1)
        finally:
            integrity_requirements.get_report_roster = original

        self.assertIsNotNone(result)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["incomplete"], 1)
        self.assertEqual(len(result["requirements"]), len(integrity_requirements.REQUIREMENTS))
        self.assertTrue(all(row["blank"] == 1 for row in result["requirements"]))


    def test_failed_nuclei_do_not_require_complexive_result(self):
        student = {
            "id": 1,
            "identification": "111",
            "full_name": "ESTUDIANTE",
            "career_name": "DESARROLLO DE SOFTWARE",
            "route": "COMPLEXIVO",
            "process_status": "ACTIVO",
            "reconciliation_status": "OK",
            "has_complexive": False,
            "has_thesis": False,
            "nuclei_records": [
                {"nucleus_number": 1, "final_status": "APROBADO"},
                {"nucleus_number": 2, "final_status": "APROBADO"},
                {"nucleus_number": 3, "final_status": "REPROBADO"},
                {"nucleus_number": 4, "final_status": "APROBADO"},
            ],
        }
        with patch.object(
            integrity.student_domain_read_model,
            "consolidated_students",
            return_value={"students": [student]},
        ):
            closure = integrity.final_student_closure(1)
        self.assertEqual(closure["unresolved"], 0)

    def test_approved_nuclei_require_complexive_result(self):
        student = {
            "id": 1,
            "identification": "111",
            "full_name": "ESTUDIANTE",
            "career_name": "DESARROLLO DE SOFTWARE",
            "route": "COMPLEXIVO",
            "process_status": "ACTIVO",
            "reconciliation_status": "OK",
            "has_complexive": False,
            "has_thesis": False,
            "nuclei_records": [
                {"nucleus_number": 1, "final_status": "APROBADO"},
                {"nucleus_number": 2, "final_status": "APROBADO"},
                {"nucleus_number": 3, "final_status": "APROBADO"},
                {"nucleus_number": 4, "final_status": "APROBADO"},
            ],
        }
        with patch.object(
            integrity.student_domain_read_model,
            "consolidated_students",
            return_value={"students": [student]},
        ):
            closure = integrity.final_student_closure(1)
        self.assertEqual(closure["unresolved"], 1)
        self.assertIn("Examen Complexivo", closure["students"][0]["reasons"][0])

    def test_terminal_requirement_noncompliance_does_not_block_final_close(self):
        metrics = {
            "requirements": {"pending": 3, "incomplete": 0},
            "nuclei": {"unevaluated": 0},
            "complexive": {"not_evaluated": 0},
            "thesis": {"incomplete": 0},
        }
        count = integrity._final_unresolved_count(
            metrics,
            {"pending_classification": 0},
            {"unresolved_probable": 0},
            {
                "missing_students": 0,
                "source_links": {
                    "pending_records": 0,
                    "conflicts": 0,
                    "route_conflicts": 0,
                },
            },
            {"unresolved": 0},
        )
        self.assertEqual(count, 0)

    def test_unresolved_academic_evidence_blocks_final_close(self):
        metrics = {
            "requirements": {"pending": 0, "incomplete": 1},
            "nuclei": {"unevaluated": 1},
            "complexive": {"not_evaluated": 1},
            "thesis": {"incomplete": 0},
        }
        count = integrity._final_unresolved_count(
            metrics,
            {"pending_classification": 0},
            {"unresolved_probable": 0},
            {
                "missing_students": 1,
                "source_links": {
                    "pending_records": 0,
                    "conflicts": 0,
                    "route_conflicts": 0,
                },
            },
            {"unresolved": 1},
        )
        self.assertGreater(count, 0)



if __name__ == "__main__":
    unittest.main()
