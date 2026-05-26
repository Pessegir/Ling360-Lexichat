"""Wordle-style share block — emoji grid + score line + legend.

Pure function `build_share_block(state, mode)` returns plain text the
end screen can show in an `st.code()` block (Streamlit renders a copy
button on those automatically) and feed into share-intent URLs.

Never includes the actual words — only outcomes.
"""
from __future__ import annotations

from datetime import date as _date

SQUARE_CLEAN = "🟩"    # solved, no letters revealed
SQUARE_HINTED = "🟨"   # solved, 1+ letters revealed
SQUARE_FAILED = "⬛"    # timed out / never answered

_TR_MONTHS = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)


def _format_date_tr(d: _date) -> str:
    return f"{d.day} {_TR_MONTHS[d.month - 1]} {d.year}"


def _round_emoji(entry) -> str:
    # Accept both modern dict shape and legacy [word, outcome] tuple so
    # this works on rows loaded from older saved games too.
    if isinstance(entry, dict):
        outcome = entry.get("outcome", "failed")
        letters = int(entry.get("letters_revealed", 0))
    elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
        outcome = entry[1]
        letters = 0  # unknown for legacy rows; treat as clean if solved
    else:
        return SQUARE_FAILED
    if outcome != "solved":
        return SQUARE_FAILED
    return SQUARE_CLEAN if letters == 0 else SQUARE_HINTED


def build_share_block(state, mode: str = "free", *,
                      today: _date | None = None) -> str:
    """Multi-line shareable summary of a finished game.

    state: GameState (uses .total_score, .rounds_solved, .words_played).
    mode:  'free' (14-round Serbest Yarışma) or 'daily' (Bugünün
           Yarışması). Determines the header label.
    today: date override for testing; defaults to today.
    """
    today = today or _date.today()
    title_mode = "Bugünün Yarışması" if mode == "daily" else "Serbest Yarışma"
    rounds_total = len(state.words_played)

    header = f"🎙️ Lexi-Chat — {title_mode} ({_format_date_tr(today)})"
    score_line = (
        f"{state.total_score:,} puan — "
        f"{state.rounds_solved}/{rounds_total} doğru"
    )
    grid = " ".join(_round_emoji(e) for e in state.words_played) if rounds_total else "—"
    legend = (
        f"{SQUARE_CLEAN} harfsiz doğru   "
        f"{SQUARE_HINTED} harf alarak doğru   "
        f"{SQUARE_FAILED} bulamadım"
    )
    return f"{header}\n{score_line}\n\n{grid}\n\n{legend}"
