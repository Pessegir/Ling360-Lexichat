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

    def reset_revealed(self):
        self.revealed_letters = []

    def reset_round_history(self):
        self.round_history = []
