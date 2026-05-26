"""Daily challenge — date-seeded word selection.

Every player who opens the app on the same Turkey-local date gets the
same 5 words, in the same order. Selection is deterministic from
`date.toordinal()` — no server-side coordination needed.

Audience is Turkish, so "today" rolls over at 00:00 TR local
(UTC+3, no DST). Completion tracking lives in game.scores (so daily
runs join the regular score history).
"""
from __future__ import annotations

import random
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

DAILY_ROUNDS = 5
# One word per letter-length slot — gives a fixed ramp from 4 to 8
# letters. Total ceiling: 4+5+6+7+8 = 30 letters * 100 = 3000 points.
DAILY_LENGTHS = (4, 5, 6, 7, 8)

# Turkey is UTC+3, no DST observed since 2016.
_TR_TZ = timezone(timedelta(hours=3))


def today_in_tr() -> _date:
    """Current date in Turkey's timezone. Daily resets at 00:00 TR
    (== 21:00 UTC the previous day)."""
    return datetime.now(_TR_TZ).date()


def daily_seed(d: _date) -> int:
    """RNG seed for a date. `toordinal` gives a stable monotonic int
    that doesn't depend on tzinfo or strftime locale settings."""
    return d.toordinal()


def select_daily_words(file_list, *, today: _date | None = None):
    """Pick the 5 daily words deterministically from `today`'s seed.

    Mirrors the return shape of `data.select_words_and_meanings` so
    callers can use it as a drop-in: (selected, m1, m2, m3).

    file_list: same list of .letters.txt paths passed to the regular
               selector — we filter for our lengths.
    today:     date override for testing; defaults to TR-local today.
    """
    today = today or today_in_tr()

    by_length: dict[int, list[tuple[str, str]]] = {L: [] for L in DAILY_LENGTHS}
    for path in file_list:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ": " not in line:
                    continue
                word, meaning = line.split(": ", 1)
                L = len(word)
                if L in by_length:
                    by_length[L].append((word, meaning))

    # Deterministic per-date pick. Sort the pool first so filesystem
    # iteration order can't drift the result.
    rng = random.Random(daily_seed(today))
    selected, m1, m2, m3 = [], [], [], []
    for L in DAILY_LENGTHS:
        pool = by_length[L]
        if not pool:
            raise RuntimeError(f"No words of length {L} available for daily")
        # Unique words only — same word may appear multiple times with
        # different meanings. Sort by word for stable ordering.
        unique_words = sorted({w for w, _ in pool})
        chosen_word = rng.choice(unique_words)
        # Collect all meanings for the chosen word (preserving file order).
        meanings = [m for w, m in pool if w == chosen_word]
        selected.append(chosen_word)
        m1.append(meanings[0])
        m2.append(meanings[1] if len(meanings) >= 2 else None)
        m3.append(meanings[2] if len(meanings) >= 3 else None)
    return selected, m1, m2, m3
