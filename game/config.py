"""Constants shared between CLI and web app drivers."""
from __future__ import annotations

from pathlib import Path

# Paths are relative to the repo root (parent of this file's parent).
ROOT = Path(__file__).parent.parent
GTS_PATH = ROOT / "gts.json"
FREQ_PATH = ROOT / "data" / "turkish_frequencies.json"
SCORES_DB_PATH = ROOT / "data" / "scores.db"
WORD_FILES = [ROOT / f"{n}.letters.txt" for n in range(4, 11)]
WORD_LENGTHS = list(range(4, 11))

# Game rules
TOTAL_ROUNDS = 14
ROUND_TIME_SECONDS = 45
TOTAL_GAME_TIME = 5 * 60  # 5 minutes

# Silence-filler timings (used by drivers that have their own scheduler)
SILENCE_MIN_SECONDS = 9
SILENCE_MAX_SECONDS = 12
SILENCE_LLM_PROBABILITY = 0.3  # 70% scripted, 30% generated

# Per-session cap on LLM calls made against the operator's BUNDLED (shared)
# key, so one visitor can't drain the free quota for everyone. A typical
# game uses ~8-15 calls, so this allows a few games before degrading to
# scripted host. Visitors who bring their own key are uncapped. Of this
# budget, the last LLM_LOW_PRIORITY_RESERVE calls are held back from
# low-value banter (silence fillers) and saved for guess reactions /
# prologue / celebrations. Tune freely; it's purely a protective backstop.
LLM_SESSION_BUDGET = 60
LLM_LOW_PRIORITY_RESERVE = 15

# "I'm stuck" signal vocabulary — broaden as players discover new phrasings
STUCK_KEYWORDS = frozenset({
    "yardım", "yardımcı", "ipucu", "destek",
    "bulamadım", "bilemedim", "bilmiyorum",
    "zor", "zormuş", "zorluymuş",
    "pas", "fikrim", "aklıma",
})

# Branding
APP_NAME = "Lexi-Chat"
APP_TAGLINE = "Bir kelime, bir sunucu, sonsuz keyif."
