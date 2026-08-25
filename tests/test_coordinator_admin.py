from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import coordinator_registry
import db


class CoordinatorAdminTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_data_dir = db.DATA_DIR
        self.old_db_path = db.DB_PATH
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "informtit.db"
        coordinator_registry.ensure_schema()

    def tearDown(self) -> None:
        db.DATA_DIR = self.old_data_dir
        db.DB_PATH = self.old_db_path
        self.temp.cleanup()

    def test_name_and_careers_are_persistent_and_editable(self) -> None:
        coordinators = coordinator_registry.list_coordinators()
        education = next(
            item for item in coordinators if "maria eugenia barre" == coordinator_registry.normalize(item["name"])
        )

        updated = coordinator_registry.update_coordinator(
            education["id"],
            name="María Eugenia Barré",
            telegram="@NUEVO_USUARIO",
            careers=[
                {"career": "Educación Básica", "program": "Tecnología Superior"},
                {"career": "Pedagogía", "program": "Tecnología Universitaria"},
            ],
        )

        self.assertEqual(updated["name"], "María Eugenia Barré")
        self.assertEqual(updated["telegram"], "@NUEVO_USUARIO")
        self.assertEqual(
            {item["career"] for item in updated["careers"]},
            {"Educación Básica", "Pedagogía"},
        )
        self.assertEqual(
            coordinator_registry.find_coordinator("Pedagogía")["coordinator"],
            "María Eugenia Barré",
        )
        self.assertEqual(
            coordinator_registry.find_coordinator("Educación Inicial")["coordinator"],
            "",
        )

    def test_assigning_career_moves_it_to_new_coordinator(self) -> None:
        coordinators = coordinator_registry.list_coordinators()
        javier = next(item for item in coordinators if item["name"] == "Javier Tapia")
        careers = list(javier["careers"]) + [
            {"career": "Administración", "program": "Tecnología Superior"}
        ]

        coordinator_registry.update_coordinator(
            javier["id"],
            name=javier["name"],
            telegram=javier["telegram"],
            careers=careers,
        )

        self.assertEqual(
            coordinator_registry.find_coordinator("Administración")["coordinator"],
            "Javier Tapia",
        )
        rodrigo = next(
            item for item in coordinator_registry.list_coordinators()
            if item["name"] == "Rodrigo Espinoza"
        )
        self.assertNotIn(
            "Administración",
            {item["career"] for item in rodrigo["careers"]},
        )


if __name__ == "__main__":
    unittest.main()
