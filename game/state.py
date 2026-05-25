"""GameState — the single source of truth for one playthrough."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import TOTAL_GAME_TIME


@dataclass
class GameState:
    """Mutable state for one playthrough. Drivers (CLI / Streamlit) own one
    instance per game. Pure data — no I/O, no timers, no threads.
    """
    total_score: int = 0
    revealed_letters: list = field(default_factory=list)
    is_paused: bool = True
    total_time: int = TOTAL_GAME_TIME
    resume_time: int = TOTAL_GAME_TIME
    active_input_bb: str = ""
    chosen_phrase: str = ""
    round_done: bool = False
    game_over: bool = False
    round_history: list = field(default_factory=list)  # [(role, text)] reset each round
    username: str = ""

    # "Almost had it" memory — set when the player types the exact answer
    # without pressing 'bb' first. Used to tease them in subsequent
    # stuck/wrong-guess turns ("Az önce çıktı sanki ağzınızdan...").
    # Reset per round. Escalates with reminded_count:
    #   0      → no memory, no teasing
    #   1-2    → gentle teases ("ipin ucunu...")
    #   3+     → pointed insistence ("az önce ne dediniz?")
    almost_had_it: bool = False
    almost_reminded_count: int = 0

    # Gibberish detection. Counts inputs that don't look like a real
    # Turkish word AND aren't game keywords. Used to emit meme-style
    # replies when the player is mashing the keyboard.
    nonsense_streak: int = 0      # consecutive nonsense inputs (resets on real input)
    nonsense_total: int = 0       # total nonsense inputs in this round

    # Per-round Counter of {input: count} so we can react to "you've now
    # said the same wrong thing 5 times". Reset per round.
    input_counts: dict = field(default_factory=dict)

    # Mood signals — feed compute_mood() to vary the host's tone within
    # the same persona. Both reset per round; updated by _handle_input
    # after each user input.
    #   wrong_streak    — consecutive failed real-word guesses this round
    #                     (≥ 3 flips host into `teasing`).
    #   last_was_close  — most recent guess was edit-distance close OR
    #                     a typo of the answer (flips host into `playful`).
    wrong_streak: int = 0
    last_was_close: bool = False

    # Run-wide stats — survive across rounds, used by the end screen.
    hints_used: int = 0
    rounds_solved: int = 0
    rounds_failed: int = 0
    # (word, outcome) where outcome is "solved" or "failed".
    words_played: list = field(default_factory=list)

    def reset_revealed(self):
        self.revealed_letters = []

    def reset_round_history(self):
        self.round_history = []

    def reset_almost_memory(self):
        self.almost_had_it = False
        self.almost_reminded_count = 0

    def reset_nonsense_counters(self):
        self.nonsense_streak = 0
        self.nonsense_total = 0

    def reset_input_counts(self):
        self.input_counts = {}

    def reset_mood_signals(self):
        self.wrong_streak = 0
        self.last_was_close = False
