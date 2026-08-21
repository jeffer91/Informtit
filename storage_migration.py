from __future__ import annotations

import os
import shutil
from pathlib import Path

import app as core
import db


def migrate_legacy_storage() -> dict[str, bool]:
    """Migra una sola vez la base/cargas antiguas a la carpeta persistente de Electron."""
    storage = str(os.environ.get("INFORMTIT_STORAGE_DIR") or "").strip()
    if not storage:
        return {"database": False, "uploads": False, "imports": False}

    target = Path(storage).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    result = {"database": False, "uploads": False, "imports": False}

    old_db = Path(db.DB_PATH)
    new_db = target / "informtit.db"
    if old_db.resolve() != new_db.resolve() and old_db.exists() and not new_db.exists():
        shutil.copy2(old_db, new_db)
        result["database"] = True

    old_uploads = Path(core.UPLOAD_DIR)
    new_uploads = target / "uploads"
    if old_uploads.exists() and old_uploads.is_dir() and not new_uploads.exists():
        shutil.copytree(old_uploads, new_uploads)
        result["uploads"] = True

    old_imports = Path(db.DATA_DIR) / "imports"
    new_imports = target / "imports"
    if old_imports.exists() and old_imports.is_dir() and not new_imports.exists():
        shutil.copytree(old_imports, new_imports)
        result["imports"] = True

    return result
