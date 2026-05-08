"""Score history — list of past games, newest first.

Reads from `data/scores.db` via `game.scores`. Filters by current
`player_name` when set; offers a toggle to show all players. Includes a
two-step "Skorları temizle" destructive action.
"""
from __future__ import annotations

import html as html_lib
from datetime import datetime

from game.config import TOTAL_ROUNDS
from game.scores import clear_history, get_history
from ui.components import release_chat_input_focus, wordmark


_ICON_DECK = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="4" y="6" width="16" height="14" rx="2"/>'
    '<path d="M8 6V4M16 6V4M4 11h16"/></svg>'
)
_ICON_TROPHY = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M7 4h10v5a5 5 0 0 1-10 0V4z"/>'
    '<path d="M5 5H3v2a3 3 0 0 0 3 3"/>'
    '<path d="M19 5h2v2a3 3 0 0 1-3 3"/>'
    '<path d="M10 14v3"/><path d="M14 14v3"/>'
    '<path d="M8 21h8"/></svg>'
)
_ICON_CHART = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="3 17 9 11 13 15 21 7"/>'
    '<polyline points="14 7 21 7 21 14"/></svg>'
)


def _fmt_duration(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d}"


def _fmt_played_at(iso: str) -> str:
    """Render ISO timestamp as a friendly local string. Falls back to raw."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return dt.strftime("%d.%m.%Y %H:%M")


def _render_row(st, row: dict, *, show_player: bool):
    """One game's summary card + expandable word list."""
    played_at = _fmt_played_at(row.get("played_at", ""))
    score = int(row.get("score", 0))
    rounds = int(row.get("rounds_completed", 0))
    hints = int(row.get("hints_used", 0))
    duration = _fmt_duration(row.get("duration_seconds", 0))
    ran_out = bool(row.get("ran_out_of_time"))
    player = (row.get("player_name") or "").strip()

    timer_icon = " ⏱" if ran_out else ""
    player_chunk = ""
    if show_player and player:
        player_chunk = (
            f'<span class="lexi-hist-player">{html_lib.escape(player)}</span>'
        )

    st.markdown(
        f'''
<div class="lexi-hist-row">
  <div class="lexi-hist-row-top">
    <span class="lexi-hist-date">{html_lib.escape(played_at)}{timer_icon}</span>
    {player_chunk}
    <span class="lexi-hist-score">{score:,}</span>
  </div>
  <div class="lexi-hist-row-meta">
    <span>{rounds} / {TOTAL_ROUNDS} tur</span>
    <span>·</span>
    <span>{hints} harf</span>
    <span>·</span>
    <span>{duration}</span>
  </div>
</div>
''',
        unsafe_allow_html=True,
    )

    words = row.get("words") or []
    if words:
        with st.expander("Kelimeleri gör"):
            lines = []
            for i, entry in enumerate(words, 1):
                # Stored as [word, outcome] (was tuple at save time).
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    word, outcome = entry[0], entry[1]
                else:
                    word, outcome = str(entry), "?"
                icon = "✓" if outcome == "solved" else "✗"
                lines.append(f"{i}. {icon} **{html_lib.escape(str(word))}**")
            st.markdown("  \n".join(lines))


def render_history(st):
    release_chat_input_focus(st)
    wordmark(st, level="h2")
    st.write("")
    st.markdown("### Önceki Oyunlar")

    player_name = (st.session_state.get("player_name") or "").strip()

    # Show-all toggle: defaults to "my games" when there is a name, else
    # to "all" since there's nothing else to filter on.
    show_all_default = not bool(player_name)
    show_all = st.toggle(
        "Tüm oyuncuları göster",
        value=st.session_state.get("history_show_all", show_all_default),
        key="history_show_all",
    )
    filter_name = None if show_all else (player_name or None)

    rows = get_history(player_name=filter_name, limit=100)

    if not rows:
        if filter_name:
            st.info(
                f"**{filter_name}** için kayıt yok. Bir oyun bitirdiğinizde "
                "buraya gelecek.",
                icon="📭",
            )
        else:
            st.info(
                "Henüz hiç oyun kaydı yok. Bir oyun bitirdiğinizde buraya "
                "gelecek.",
                icon="📭",
            )
    else:
        # Quick stats strip across all visible rows.
        total = len(rows)
        best = max(int(r.get("score", 0)) for r in rows)
        avg = sum(int(r.get("score", 0)) for r in rows) // total
        st.markdown(
            f'''
<div class="lexi-end-stats">
  <div class="lexi-stat-card">
    <div class="lexi-stat-label">{_ICON_DECK}<span>OYUN</span></div>
    <div class="lexi-stat-value">{total}</div>
  </div>
  <div class="lexi-stat-card">
    <div class="lexi-stat-label">{_ICON_TROPHY}<span>EN İYİ</span></div>
    <div class="lexi-stat-value">{best:,}</div>
  </div>
  <div class="lexi-stat-card">
    <div class="lexi-stat-label">{_ICON_CHART}<span>ORTALAMA</span></div>
    <div class="lexi-stat-value">{avg:,}</div>
  </div>
</div>
''',
            unsafe_allow_html=True,
        )

        st.write("")

        for row in rows:
            _render_row(st, row, show_player=show_all)

    st.write("")

    # === Footer actions ===
    col_back, col_clear = st.columns([2, 1])
    with col_back:
        if st.button("🏠 Ana sayfa", type="secondary", use_container_width=True):
            st.session_state.phase = "home"
            st.rerun()

    with col_clear:
        if rows:
            confirm = st.session_state.get("history_clear_confirm", False)
            label = (
                "⚠️ Emin misiniz?" if confirm else "🗑 Skorları temizle"
            )
            if st.button(label, type="secondary", use_container_width=True,
                         key="history_clear_btn"):
                if confirm:
                    try:
                        clear_history(
                            player_name=None if show_all else filter_name
                        )
                    except Exception as e:
                        st.error(f"Silinemedi: {e}")
                    st.session_state.history_clear_confirm = False
                    st.rerun()
                else:
                    st.session_state.history_clear_confirm = True
                    st.rerun()
            if confirm:
                st.caption(
                    "Tekrar tıklayın — bu işlem geri alınamaz."
                    if show_all
                    else f"Tekrar tıklayın — yalnızca **{filter_name}** silinecek."
                )
