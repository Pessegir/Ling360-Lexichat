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
                words_json TEXT NOT NULL DEFAULT '[]',
                mode TEXT NOT NULL DEFAULT 'free',
                daily_date TEXT
            )
        """)
        # Migrations for DBs created before the daily-challenge feature:
        # add the two new columns if missing. PRAGMA table_info is the
        # standard idiom for SQLite schema introspection.
        existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(games)")}
        if "mode" not in existing_cols:
            cur.execute("ALTER TABLE games ADD COLUMN mode TEXT NOT NULL DEFAULT 'free'")
        if "daily_date" not in existing_cols:
            cur.execute("ALTER TABLE games ADD COLUMN daily_date TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_player ON games(player_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_played_at ON games(played_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON games(daily_date)")
        conn.commit()
    return conn


def save_game(*, player_name: str, score: int, rounds_completed: int,
              hints_used: int, duration_seconds: int, difficulty: str = "normal",
              ran_out_of_time: bool = False, words: list = None,
              mode: str = "free", daily_date: str | None = None,
              path: Path = SCORES_DB_PATH) -> int:
    """Persist a finished game. Returns the new row id.

    mode: 'free' (normal 14-round) or 'daily' (Bugünün Yarışması).
    daily_date: TR-local ISO date string (YYYY-MM-DD) for daily games;
                None for free games. Used by daily_run_today() to gate
                replays.
    """
    with closing(_connect(path)) as conn, closing(conn.cursor()) as cur:
        cur.execute("""
            INSERT INTO games (player_name, played_at, score, rounds_completed,
                               hints_used, duration_seconds, difficulty,
                               ran_out_of_time, words_json, mode, daily_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            mode,
            daily_date,
        ))
        conn.commit()
        return cur.lastrowid


def daily_run_today(daily_date: str, path: Path = SCORES_DB_PATH) -> dict | None:
    """Return the saved daily run for `daily_date` (TR-local YYYY-MM-DD)
    if any, else None. Used by the home screen to block replay attempts
    and to surface today's score on the locked-out CTA."""
    with closing(_connect(path)) as conn, closing(conn.cursor()) as cur:
        cur.execute(
            "SELECT * FROM games WHERE mode = 'daily' AND daily_date = ? "
            "ORDER BY id DESC LIMIT 1",
            (daily_date,),
        )
        row = cur.fetchone()
        if not row:
            return None
        out = dict(row)
        try:
            out["words"] = json.loads(out.pop("words_json", "[]"))
        except Exception:
            out["words"] = []
        out["ran_out_of_time"] = bool(out["ran_out_of_time"])
        return out


def get_history(player_name: str = None, limit: int = 50,
                path: Path = SCORES_DB_PATH) -> list[dict]:
    """Return finished games, newest first. Filter by player_name if given."""
    with closing(_connect(path)) as conn, closing(conn.cursor()) as cur:
        if player_name:
            cur.execute(
                "SELECT * FROM games WHERE player_name = ? "
                "ORDER BY played_at DESC, id DESC LIMIT ?",
                (player_name.strip(), limit),
            )
        else:
            cur.execute(
                "SELECT * FROM games ORDER BY played_at DESC, id DESC LIMIT ?",
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


def has_any_games(path: Path = SCORES_DB_PATH) -> bool:
    """True if any finished game has been saved on this device. Used by
    the home screen to decide whether to surface the tutorial banner."""
    with closing(_connect(path)) as conn, closing(conn.cursor()) as cur:
        cur.execute("SELECT 1 FROM games LIMIT 1")
        return cur.fetchone() is not None


def clear_history(player_name: str = None, path: Path = SCORES_DB_PATH):
    """Delete history. If player_name is given, only that player's."""
    with closing(_connect(path)) as conn, closing(conn.cursor()) as cur:
        if player_name:
            cur.execute("DELETE FROM games WHERE player_name = ?", (player_name.strip(),))
        else:
            cur.execute("DELETE FROM games")
        conn.commit()
