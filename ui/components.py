"""Reusable UI components for the Lexi-Chat web app.

Each function takes Streamlit (`st`) as its first arg so the module itself
has no Streamlit import-side-effect — easier to unit-test the HTML output.
"""
from __future__ import annotations

import html as html_lib

from game.config import APP_NAME, APP_TAGLINE


# --------------------------------------------------------------------------
# Branding
# --------------------------------------------------------------------------


def wordmark(st, *, with_tagline: bool = False, level: str = "h1"):
    """Render the Lexi-Chat wordmark. Accent dot on the hyphen.

    level: HTML tag — h1 for landing, h3 for in-game header.
    """
    name = html_lib.escape(APP_NAME)
    parts = name.split("-", 1)
    if len(parts) == 2:
        markup = f'<{level} class="lexi-wordmark">{parts[0]}<span class="accent">-</span>{parts[1]}</{level}>'
    else:
        markup = f'<{level} class="lexi-wordmark">{name}</{level}>'

    if with_tagline:
        markup += f'<div class="lexi-tagline">{html_lib.escape(APP_TAGLINE)}</div>'

    st.markdown(markup, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Letter tile board
# --------------------------------------------------------------------------


def tile_board(st, word_or_length, revealed_letters=None):
    """Render the diamond letter board.

    Two ways to call:
      tile_board(st, 5)                              # all blank, length 5
      tile_board(st, "uzay", ["_  ", "z", "_  ", "y"])  # mix of revealed + blank

    revealed_letters uses the engine's "_  " sentinel for blanks (matches
    GameState.revealed_letters). Strings of length 1 are treated as revealed.
    """
    if isinstance(word_or_length, int):
        slots = ["_  "] * word_or_length
        revealed = ["_  "] * word_or_length
    else:
        slots = list(word_or_length)
        revealed = revealed_letters or ["_  "] * len(slots)

    tiles_html = []
    for i, slot in enumerate(slots):
        if i < len(revealed) and revealed[i] != "_  " and len(revealed[i].strip()) >= 1:
            ch = html_lib.escape(revealed[i].strip()[:1].upper())
            tiles_html.append(f'<div class="lexi-tile revealed"><span>{ch}</span></div>')
        else:
            tiles_html.append('<div class="lexi-tile"><span>&nbsp;</span></div>')

    st.markdown(
        f'<div class="lexi-tiles">{"".join(tiles_html)}</div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Clue card
# --------------------------------------------------------------------------


def clue_card(st, text: str, label: str = "İPUCU"):
    safe = html_lib.escape(text)
    st.markdown(
        f'<div class="lexi-clue"><span class="lexi-clue-label">{html_lib.escape(label)}</span>{safe}</div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Top bar — score / round / timer
# --------------------------------------------------------------------------


def topbar(st, *, score: int, round_num: int, total_rounds: int,
           seconds_remaining: int, in_answer_mode: bool = False):
    """Render the score/round/timer header strip.

    in_answer_mode = True → label changes to "CEVAP SÜRESİ", color shifts amber.
    seconds_remaining < 30 → color shifts to dusty rose (warning).
    """
    mins, secs = divmod(max(0, seconds_remaining), 60)
    timer_str = f"{mins:02d}:{secs:02d}"
    if in_answer_mode:
        timer_class = "timer-active"
        timer_label = "CEVAP SÜRESİ"
    elif seconds_remaining < 30:
        timer_class = "timer-warn"
        timer_label = "KALAN SÜRE"
    else:
        timer_class = ""
        timer_label = "KALAN SÜRE"

    st.markdown(
        f'''
<div class="lexi-topbar">
  <div class="lexi-chip">
    <div class="lexi-chip-label">PUAN</div>
    <div class="lexi-chip-value">{score:,}</div>
  </div>
  <div class="lexi-chip">
    <div class="lexi-chip-label">SORU</div>
    <div class="lexi-chip-value">{round_num} / {total_rounds}</div>
  </div>
  <div class="lexi-chip" style="align-items: flex-end;">
    <div class="lexi-chip-label">{timer_label}</div>
    <div class="lexi-chip-value {timer_class}">{timer_str}</div>
  </div>
</div>
''',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Chat bubbles
#
# Two flavors:
#   - Use `st.chat_message("assistant"|"user")` for the running game chat —
#     Streamlit's native widget gives nice scrolling and avatars.
#   - Use these custom HTML bubbles for special moments (end-of-round
#     congratulation, prologue, etc.) where we want full styling control
#     and the host's italic Lora voice.
# --------------------------------------------------------------------------


def host_bubble(st, text: str):
    """Standalone host bubble (italic, teal-bordered)."""
    safe = html_lib.escape(text).replace("\n", "<br>")
    st.markdown(
        f'<div class="lexi-host-bubble">{safe}</div>',
        unsafe_allow_html=True,
    )


def player_bubble(st, text: str):
    """Standalone player bubble (right-aligned, no border accent)."""
    safe = html_lib.escape(text).replace("\n", "<br>")
    st.markdown(
        f'<div class="lexi-player-bubble">{safe}</div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# A future hook: speaker icon for voice mode (wired into bubbles later)
# --------------------------------------------------------------------------


def host_bubble_with_audio_hook(st, text: str, audio_url: str | None = None):
    """Host bubble that *will* show a 🔊 button when voice mode ships.

    For now, audio_url is ignored. When voice arrives in a future phase,
    we render a play button next to the text. Designed in now so the
    bubble layout doesn't change later.
    """
    # TODO Phase 5+: render audio_url as an inline player when present
    return host_bubble(st, text)
