"""Local score history — SQLite backed.

Schema: one row per finished game, keyed by player name + timestamp.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .config import SCORES_DB_PATH


def _connect(path: Path = SCORES_DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    with closing(conn.cursor()) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                played_at TEXT NOT NULL,
                score INTEGER NOT NULL,
                rounds_completed INTEGER NOT NULL,
                hints_used INTEGER NOT NULL DEFAULT 0,
                duration_seconds INTEGER NOT NULL,
                difficulty TEXT NOT NULL DEFAULT 'normal',
                ran_out_of_time INTEGER NOT NULL DEFAULT 0,
                words_json TEXT NOT NULL DEFAULT '[]'
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_player ON games(player_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_played_at ON games(played_at)")
        conn.commit()
    return conn


def save_game(*, player_name: str, score: int, rounds_completed: int,
              hints_used: int, duration_seconds: int, difficulty: str = "normal",
              ran_out_of_time: bool = False, words: list = None,
              path: Path = SCORES_DB_PATH) -> int:
    """Persist a finished game. Returns the new row id."""
    with closing(_connect(path)) as conn, closing(conn.cursor()) as cur:
        cur.execute("""
            INSERT INTO games (player_name, played_at, score, rounds_completed,
                               hints_used, duration_seconds, difficulty,
                               ran_out_of_time, words_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            player_name.strip(),
            datetime.utcnow().isoformat(timespec="seconds"),
            int(score),
            int(rounds_completed),
            int(hints_used),
            int(duration_seconds),
            difficulty,
            1 if ran_out_of_time else 0,
            json.dumps(words or [], ensure_ascii=False),
        ))
        conn.commit()
        return cur.lastrowid


def get_history(player_name: str = None, limit: int = 50,
                path: Path = SCORES_DB_PATH) -> list[dict]:
    """Return finished games, newest first. Filter by player_name if given."""
    with closing(_connect(path)) as conn, closing(conn.cursor()) as cur:
        if player_name:
            cur.execute(
                "SELECT * FROM games WHERE player_name = ? "
                "ORDER BY played_at DESC LIMIT ?",
                (player_name.strip(), limit),
            )
        else:
            cur.execute(
                "SELECT * FROM games ORDER BY played_at DESC LIMIT ?",
                (limit,),
            )
        rows = []
        for r in cur.fetchall():
            row = dict(r)
            try:
                row["words"] = json.loads(row.pop("words_json", "[]"))
            except Exception:
                row["words"] = []
            row["ran_out_of_time"] = bool(row["ran_out_of_time"])
            rows.append(row)
        return rows


def best_score(player_name: str, path: Path = SCORES_DB_PATH) -> int | None:
    """Highest score for a player, or None if they have none yet."""
    with closing(_connect(path)) as conn, closing(conn.cursor()) as cur:
        cur.execute(
            "SELECT MAX(score) FROM games WHERE player_name = ?",
            (player_name.strip(),),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else None


def clear_history(player_name: str = None, path: Path = SCORES_DB_PATH):
    """Delete history. If player_name is given, only that player's."""
    with closing(_connect(path)) as conn, closing(conn.cursor()) as cur:
        if player_name:
            cur.execute("DELETE FROM games WHERE player_name = ?", (player_name.strip(),))
        else:
            cur.execute("DELETE FROM games")
        conn.commit()
