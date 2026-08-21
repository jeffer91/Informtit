from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import app as core
import db


DATA_TABLE_WEIGHTS = {
    "requirements_students": 1000,
    "students": 500,
    "nucleus_courses": 100,
    "thesis_projects": 100,
    "images": 25,
}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _database_score(path: Path) -> int:
    """Mide datos reales sin contar estructuras automáticas o cronogramas semilla."""
    if not path.exists() or not path.is_file() or path.stat().st_size == 0:
        return 0
    try:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("PRAGMA query_only = ON")
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            score = 0

            for table, weight in DATA_TABLE_WEIGHTS.items():
                if table not in tables:
                    continue
                count = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                score += count * weight

            # Los cronogramas se crean automáticamente. Solo cuentan si existe
            # evidencia de ejecución real ingresada por el usuario.
            if "schedule_items" in tables:
                columns = _columns(conn, "schedule_items")
                execution_fields = {
                    "executed_date",
                    "execution_status",
                    "compliance_percentage",
                    "evidence",
                    "observation",
                }
                if execution_fields.issubset(columns):
                    executed = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) FROM schedule_items
                            WHERE COALESCE(executed_date,'')<>''
                               OR COALESCE(execution_status,'')<>''
                               OR compliance_percentage IS NOT NULL
                               OR COALESCE(evidence,'')<>''
                               OR COALESCE(observation,'')<>''
                            """
                        ).fetchone()[0]
                    )
                    score += executed * 20

            if "analyses" in tables:
                columns = _columns(conn, "analyses")
                if {"text_before", "text_after"}.issubset(columns):
                    analyses = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) FROM analyses
                            WHERE COALESCE(text_before,'')<>''
                               OR COALESCE(text_after,'')<>''
                            """
                        ).fetchone()[0]
                    )
                    score += analyses * 20

            if "institutional_sections" in tables:
                columns = _columns(conn, "institutional_sections")
                if "customized" in columns:
                    customized = int(
                        conn.execute(
                            "SELECT COUNT(*) FROM institutional_sections WHERE customized=1"
                        ).fetchone()[0]
                    )
                    score += customized * 10

            # Un informe creado automáticamente no cuenta por sí solo. Un informe
            # que provino de una importación sí constituye trabajo recuperable.
            if "reports" in tables:
                columns = _columns(conn, "reports")
                if "source_import_id" in columns:
                    imported = int(
                        conn.execute(
                            "SELECT COUNT(*) FROM reports WHERE source_import_id IS NOT NULL"
                        ).fetchone()[0]
                    )
                    score += imported * 50

            return score
        finally:
            conn.close()
    except sqlite3.Error:
        return -1


def _merge_directory(source: Path, target: Path) -> bool:
    """Copia únicamente archivos ausentes para no pisar trabajo persistente."""
    if not source.exists() or not source.is_dir():
        return False
    changed = False
    target.mkdir(parents=True, exist_ok=True)
    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue
        relative = source_file.relative_to(source)
        target_file = target / relative
        if target_file.exists():
            continue
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        changed = True
    return changed


def migrate_legacy_storage() -> dict[str, bool]:
    """Migra de forma conservadora la base/cargas antiguas a userData de Electron.

    Una versión anterior podía crear primero una base persistente con informes y
    cronogramas semilla, pero sin información real. Ese cascarón ya no bloquea la
    recuperación de una base antigua que sí contiene estudiantes o trabajo del
    usuario. Si ambas bases contienen datos reales, ninguna se sobrescribe.
    """
    storage = str(os.environ.get("INFORMTIT_STORAGE_DIR") or "").strip()
    if not storage:
        return {
            "database": False,
            "database_backup": False,
            "uploads": False,
            "imports": False,
        }

    target = Path(storage).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    result = {
        "database": False,
        "database_backup": False,
        "uploads": False,
        "imports": False,
    }

    old_db = Path(db.DB_PATH)
    new_db = target / "informtit.db"
    if old_db.resolve() != new_db.resolve() and old_db.exists():
        old_score = _database_score(old_db)
        new_score = _database_score(new_db)
        should_restore = not new_db.exists() or (old_score > 0 and new_score <= 0)
        if should_restore:
            if new_db.exists():
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                backup = target / f"informtit.pre-migration-{stamp}.db"
                shutil.copy2(new_db, backup)
                result["database_backup"] = True
            shutil.copy2(old_db, new_db)
            result["database"] = True

    old_uploads = Path(core.UPLOAD_DIR)
    new_uploads = target / "uploads"
    result["uploads"] = _merge_directory(old_uploads, new_uploads)

    old_imports = Path(db.DATA_DIR) / "imports"
    new_imports = target / "imports"
    result["imports"] = _merge_directory(old_imports, new_imports)

    return result
