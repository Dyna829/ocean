from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIST = BASE_DIR / "web" / "dist"
DEFAULT_DB_PATH = BASE_DIR / "data" / "app.db"


def resolve_db_path(value: str | None = None) -> Path:
    """Resolve the database path from an argument, DB_PATH, or the default."""
    raw = value or os.environ.get("DB_PATH")
    if not raw:
        return DEFAULT_DB_PATH
    return Path(raw).expanduser().resolve()
