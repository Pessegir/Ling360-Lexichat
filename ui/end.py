"""End screen — final score, stats, and replay actions.

Reached when the global 5-min timer expires, the player solves all
TOTAL_ROUNDS questions, or _advance_to_next_round runs out of rounds.
"""
from __future__ import annotations

import html as html_lib

from game.config import TOTAL_GAME_TIME, TOTAL_ROUNDS
from game.round import end_game_lines
from game.scores import best_score, save_game
from ui.components import host_bubble, release_chat_input_focus, wordmark


PRESERVE_KEYS = {"api_key", "provider", "player_name", "player_address"}


def _elapsed_seconds(state) -> int:
    elapsed = max(0, TOTAL_GAME_TIME - int(state.total_time))
    return min(elapsed, TOTAL_GAME_TIME)


def _format_time_taken(state) -> str:
    elapsed = _elapsed_seconds(state)
    mins, secs = divmod(elapsed, 60)
    return f"{mins} dk {secs:02d} sn"


def _reset_for_new_game(st):
    for k in list(st.session_state.keys()):
        if k not in PRESERVE_KEYS:
            del st.session_state[k]


def _persist_game(st, state) -> None:
    """Save the finished game once. Idempotent across reruns.

    Skips if no rounds were engaged (e.g., the user landed on `end`
    without playing) so the history doesn't fill with empty rows.
    """
    if st.session_state.get("score_saved_id") is not None:
        return
    if (state.rounds_solved + state.rounds_failed) == 0:
        return
    player_name = (st.session_state.get("player_name") or "").strip()
    if not player_name:
        return
    try:
        row_id = save_game(
            player_name=player_name,
            score=state.total_score,
            rounds_completed=state.rounds_solved + state.rounds_failed,
            hints_used=state.hints_used,
            duration_seconds=_elapsed_seconds(state),
            difficulty=st.session_state.get("difficulty", "normal"),
            ran_out_of_time=bool(state.game_over),
            words=[[w, outcome] for w, outcome in state.words_played],
        )
    except Exception:
        # Persisting must never block the end screen.
        st.session_state.score_saved_id = -1
        return
    st.session_state.score_saved_id = row_id


def render_end(st):
    state = st.session_state.game_state

    release_chat_input_focus(st)
    wordmark(st, level="h2")
    st.write("")

    if state is None:
        st.info("Henüz bir oyun oynamadınız.")
        if st.button("🏠 Ana sayfa", type="primary", use_container_width=True):
            st.session_state.phase = "home"
            st.rerun()
        return

    # Persist before computing best — so a fresh new-record run is
    # reflected in the comparison.
    _persist_game(st, state)

    host_bubble(
        st,
        end_game_lines(state.total_score, state.username, state.game_over),
    )
    st.write("")

    # Personal-best banner. None  → no prior games; equal → new record;
    # otherwise → show the standing best as a small caption.
    pb_line = ""
    player_name = (st.session_state.get("player_name") or "").strip()
    if player_name and st.session_state.get("score_saved_id"):
        try:
            pb = best_score(player_name)
        except Exception:
            pb = None
        if pb is not None:
            if state.total_score >= pb:
                pb_line = (
                    '<div class="lexi-end-pb new-record">'
                    '🏆 YENİ REKOR'
                    '</div>'
                )
            else:
                pb_line = (
                    f'<div class="lexi-end-pb">'
                    f'En iyi: <strong>{pb:,}</strong>'
                    f'</div>'
                )

    st.markdown(
        f'''
<div class="lexi-end-score-block">
  <div class="lexi-end-score-label">TOPLAM PUAN</div>
  <div class="lexi-end-score-value">{state.total_score:,}</div>
  {pb_line}
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
