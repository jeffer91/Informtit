from __future__ import annotations

import unittest

import report_integrity_last_guard as guard


class ReportIntegrityLastGuardTests(unittest.TestCase):
    def test_schedule_wrapper_restores_presence(self):
        calls: list[tuple[int, str, bool]] = []
        original = guard.set_presence
        guard.set_presence = lambda report_id, key, included: calls.append((report_id, key, included))
        try:
            wrapped = guard._with_presence(
                lambda report_id, schedule_type, entries: {
                    "ok": True,
                    "report_id": report_id,
                    "schedule_type": schedule_type,
                    "count": len(entries),
                }
            )
            result = wrapped(7, "complexive", [{"activity": "Núcleo 1"}])
        finally:
            guard.set_presence = original

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [(7, "schedule_complexive", True)])

    def test_source_zero_with_stale_academic_data_is_import_error(self):
        metrics = {
            "requirements": {"registered": 0},
            "nuclei": {"records": 4},
            "complexive": {"registered": 0},
            "thesis": {"total": 0},
        }
        source = {"exists": True, "source_modality_count": 0}
        self.assertEqual(guard.source_mode_strict(metrics, source), "import_error")

    def test_source_zero_without_population_is_no_population(self):
        metrics = {
            "requirements": {"registered": 0},
            "nuclei": {"records": 0},
            "complexive": {"registered": 0},
            "thesis": {"total": 0},
        }
        source = {"exists": True, "source_modality_count": 0}
        self.assertEqual(guard.source_mode_strict(metrics, source), "no_population")

    def test_source_with_population_but_empty_requirements_is_import_error(self):
        metrics = {
            "requirements": {"registered": 0},
            "nuclei": {"records": 10},
            "complexive": {"registered": 8},
            "thesis": {"total": 0},
        }
        source = {"exists": True, "source_modality_count": 12}
        self.assertEqual(guard.source_mode_strict(metrics, source), "import_error")

    def test_probable_nuclei_duplicate_does_not_depend_on_teacher(self):
        first = {
            "nombre_carrera": "ENFERMERÍA",
            "nombre_profesor": "DOCENTE A",
            "nombre_estudiante": "ESTUDIANTE UNO",
            "materia": "NÚCLEO 1",
            "nota_final": "8",
            "estado": "Aprobado",
            "trabajoTitulacion": "Examen Complexivo",
        }
        second = dict(first, nombre_profesor="DOCENTE B", nota_final="9")
        entries = guard.nuclei_duplicate_entries_strict([first, second])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["duplicate_type"], "DUPLICADO PROBABLE")


if __name__ == "__main__":
    unittest.main()
