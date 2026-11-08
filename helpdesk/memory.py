from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from . import data


def checkpoint_path(storage_dir: Path | None = None) -> Path:
    base = storage_dir or data.storage_dir()
    return base / "conversations.sqlite"


def user_memory_path(storage_dir: Path | None = None) -> Path:
    base = storage_dir or data.storage_dir()
    return base / "user_memory.sqlite"


class UserMemory:
    """Persistent, per-user key/value store (separate from conversation state)."""

    def __init__(self, path: Path | None = None):
        self.path = path or user_memory_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS user_prefs ("
                "user_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
                "PRIMARY KEY (user_id, key))"
            )
            conn.commit()

    def set(self, user_id: str, key: str, value: str) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "INSERT INTO user_prefs (user_id, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
                (user_id, key, value),
            )
            conn.commit()

    def get(self, user_id: str, key: str) -> str | None:
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT value FROM user_prefs WHERE user_id = ? AND key = ?",
                (user_id, key),
            ).fetchone()
        return row[0] if row else None

    def all_for(self, user_id: str) -> dict[str, str]:
        with closing(sqlite3.connect(self.path)) as conn:
            rows = conn.execute(
                "SELECT key, value FROM user_prefs WHERE user_id = ?", (user_id,)
            ).fetchall()
        return {key: value for key, value in rows}

    def clear(self, user_id: str | None = None) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            if user_id is None:
                conn.execute("DELETE FROM user_prefs")
            else:
                conn.execute("DELETE FROM user_prefs WHERE user_id = ?", (user_id,))
            conn.commit()


def reset_all(storage_dir: Path | None = None) -> None:
    base = storage_dir or data.storage_dir()
    for path in (checkpoint_path(base), user_memory_path(base)):
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(path) + suffix)
            if candidate.exists():
                candidate.unlink()
