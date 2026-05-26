"""Persistent device-local prefs in data/prefs.json.

Tiny key-value store for things that don't justify their own SQLite
table. Today: just `tutorial_completed`. Read/write each call (no
caching) — call volume is trivial.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import SCORES_DB_PATH

PREFS_PATH: Path = SCORES_DB_PATH.parent / "prefs.json"


def _load() -> dict:
    if not PREFS_PATH.exists():
        return {}
    try:
        return json.loads(PREFS_PATH.read_text(encoding="utf-8"))
    except Exception:
        # Corrupt file shouldn't break the app — start fresh.
        return {}


def _save(data: dict) -> None:
    PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREFS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_pref(key: str, default: Any = None) -> Any:
    return _load().get(key, default)


def set_pref(key: str, value: Any) -> None:
    data = _load()
    data[key] = value
    _save(data)
