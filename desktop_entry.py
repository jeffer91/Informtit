from __future__ import annotations

import app as core
import desktop_launcher
import layout_v3
import optional_content
import process_export
import process_routes
import report_structure
from db import connection
from import_service import ensure_schema
from institutional_defaults import apply_defaults
from process_service import ensure_process_schema


def prepare() -> None:
    """Prepara la base y aplica extensiones en un orden determinista."""

    core.init_db()
    ensure_schema()
    ensure_process_schema()
    with connection() as conn:
        apply_defaults(conn)

    # desktop_launcher ya instaló sus rutas al importarse. Las extensiones
    # siguientes deben quedar como la última capa utilizada por Electron.
    layout_v3.install()
    process_routes.install()
    process_export.install()
    optional_content.install()
    report_structure.install()


def main() -> None:
    prepare()
    desktop_launcher.main()


if __name__ == "__main__":
    main()
