"""Runtime configuration for fueldesk."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8792

# Local SQLite path (override with FUELDESK_DB)
_DEFAULT_DB = Path.home() / ".fueldesk" / "fueldesk.db"


def db_path() -> Path:
    raw = os.environ.get("FUELDESK_DB")
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_DB


def ensure_data_dir() -> Path:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
