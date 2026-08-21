from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import app as core
import db


MEANINGFUL_TABLES = (
    "reports",
    "requirements_students",
    "careers",
    "students",
    "nucleus_courses",
    "thesis_projects",
    "schedule_items",
)


def _database_score(path: Path) -> int:
    """Cuenta datos útiles sin crear ni modificar la base inspeccionada."""
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
            for table in MEANINGFUL_TABLES:
                if table not in tables:
                    continue
                score += int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
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

    Una versión anterior podía crear primero una base persistente vacía. En ese
    caso se conserva una copia de seguridad de esa base vacía y se recupera la
    base antigua con datos. Si ambas bases contienen información, ninguna se
    sobrescribe automáticamente.
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
