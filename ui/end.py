"""End screen — final score, stats, and replay actions.

Reached when the global 5-min timer expires, the player solves all
TOTAL_ROUNDS questions, or _advance_to_next_round runs out of rounds.
"""
from __future__ import annotations

import html as html_lib

from game.config import TOTAL_GAME_TIME, TOTAL_ROUNDS
from game.round import end_game_lines
from ui.components import host_bubble, wordmark


PRESERVE_KEYS = {"api_key", "provider", "player_name", "player_address"}


def _format_time_taken(state) -> str:
    elapsed = max(0, TOTAL_GAME_TIME - int(state.total_time))
    elapsed = min(elapsed, TOTAL_GAME_TIME)
    mins, secs = divmod(elapsed, 60)
    return f"{mins} dk {secs:02d} sn"


def _reset_for_new_game(st):
    for k in list(st.session_state.keys()):
        if k not in PRESERVE_KEYS:
            del st.session_state[k]


def render_end(st):
    state = st.session_state.game_state

    wordmark(st, level="h2")
    st.write("")

    if state is None:
        st.info("Henüz bir oyun oynamadınız.")
        if st.button("🏠 Ana sayfa", type="primary", use_container_width=True):
            st.session_state.phase = "home"
            st.rerun()
        return

    host_bubble(
        st,
        end_game_lines(state.total_score, state.username, state.game_over),
    )
    st.write("")

    st.markdown(
        f'''
<div class="lexi-end-score-block">
  <div class="lexi-end-score-label">TOPLAM PUAN</div>
  <div class="lexi-end-score-value">{state.total_score:,}</div>
</div>
''',
        unsafe_allow_html=True,
    )

    time_str = _format_time_taken(state)
    st.markdown(
        f'''
<div class="lexi-end-stats">
  <div class="lexi-stat-card">
    <div class="lexi-stat-label">DOĞRU CEVAP</div>
    <div class="lexi-stat-value">{state.rounds_solved} / {TOTAL_ROUNDS}</div>
  </div>
  <div class="lexi-stat-card">
    <div class="lexi-stat-label">HARF AÇILDI</div>
    <div class="lexi-stat-value">{state.hints_used}</div>
  </div>
  <div class="lexi-stat-card">
    <div class="lexi-stat-label">SÜRE</div>
    <div class="lexi-stat-value">{time_str}</div>
  </div>
</div>
''',
        unsafe_allow_html=True,
    )

    if state.words_played:
        with st.expander("📝 Bu oyundaki kelimeler"):
            rows = []
            for i, (word, outcome) in enumerate(state.words_played, 1):
                icon = "✓" if outcome == "solved" else "✗"
                safe_word = html_lib.escape(word)
                rows.append(f"{i}. {icon} **{safe_word}**")
            st.markdown("  \n".join(rows))

    st.write("")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🎙️ Tekrar oyna", type="primary", use_container_width=True):
            _reset_for_new_game(st)
            st.session_state.phase = "loading"
            st.rerun()
    with col2:
        if st.button("📊 Skorları gör", type="secondary", use_container_width=True):
            st.session_state.phase = "history"
            st.rerun()
