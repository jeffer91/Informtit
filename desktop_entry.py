from __future__ import annotations

import app as core
from db import connection
from import_service import ensure_schema
from institutional_defaults import apply_defaults
from process_service import ensure_process_schema
import layout_v3


def prepare() -> None:
    core.init_db()
    ensure_schema()
    ensure_process_schema()
    with connection() as conn:
        apply_defaults(conn)
    layout_v3.install()


def main() -> None:
    prepare()
    import desktop_launcher
    import process_export
    import process_routes

    process_routes.install()
    process_export.install()
    desktop_launcher.main()


if __name__ == "__main__":
    main()
