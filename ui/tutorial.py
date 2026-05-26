"""Tutorial — scripted walkthrough of the letter / hint / bb mechanics.

One round, one fixed word (`ELMA` — universally known), no LLM, no real
timers. The player learns by typing exactly the expected input at each
step; off-script inputs get a gentle nudge that points to what to type.
Always exitable with `çık` or via the sidebar.

Doesn't use the real game engine — too much branching in the real
`playing` phase ("what if the player types X instead?"). A hard-scripted
state machine here is bulletproof, ~5x shorter, and lets new players
focus on one mechanic at a time.
"""
from __future__ import annotations

import html as html_lib
import re
import time

from game.prefs import set_pref
from ui import sound
from ui.components import (
    focus_chat_input, release_chat_input_focus, tile_board, wordmark,
)


_TUTORIAL_WORD = "ELMA"          # 4 letters, universally known
_BLANK = "_  "                    # GameState's blank sentinel
_EXIT_WORDS = frozenset({"çık", "cik", "iptal", "exit", "vazgeç", "vazgec"})


# --------------------------------------------------------------------------
# Step machine — one branch per step inside _process_step
# --------------------------------------------------------------------------
#
# Steps:
#   0  — intro shown, waiting for `h`
#   1  — first letter revealed, waiting for `ipucu`
#   2  — hint given + bb explained, waiting for `bb`
#   3  — bb pressed (cevap fazı), waiting for "elma"
#   4  — terminal: celebration + return-to-home buttons


def _init(st) -> None:
    """Seed state on first entry. Subsequent renders see step != None
    and skip."""
    if st.session_state.get("tutorial_step") is not None:
        return
    st.session_state.tutorial_step = 0
    st.session_state.tutorial_revealed = [_BLANK] * len(_TUTORIAL_WORD)
    # Reuse chat_log so the bubble styles match the real game arena.
    st.session_state.chat_log = []
    _push(st, "assistant",
          "Hoş geldiniz efendim! Hızlı bir tanıtım yapalım — "
          "1 kelime üzerinden mekaniği görelim.")
    _push(st, "assistant",
          f"Aşağıda {len(_TUTORIAL_WORD)} boş harf kutucuğu görüyorsunuz. "
          "Önce kelimeden bir harf alalım — **h** yazın efendim.")


def _push(st, role: str, text: str) -> None:
    st.session_state.chat_log.append((role, text, time.time()))


def _exit(st) -> None:
    """Mark complete and return to home. Either button (skip or finish)
    sets the pref — once dismissed, the home banner doesn't reappear."""
    set_pref("tutorial_completed", True)
    for k in ("tutorial_step", "tutorial_revealed", "chat_log"):
        if k in st.session_state:
            del st.session_state[k]
    st.session_state.phase = "home"
    st.rerun()


_PLACEHOLDERS = {
    0: "h yazıp bir harf alın...",
    1: "ipucu yazın...",
    2: "bb yazıp cevap fazına geçin...",
    3: "Cevabınızı yazın...",
}


def render_tutorial(st) -> None:
    _init(st)
    step = st.session_state.tutorial_step

    wordmark(st, level="h3")
    st.caption(
        "📖 Tanıtım turu — istediğiniz an **çık** yazıp ana sayfaya dönebilirsiniz."
    )

    tile_board(st, _TUTORIAL_WORD, st.session_state.tutorial_revealed,
               board_key=f"tut:{step}")

    # === Terminal step: celebration + exit buttons ===
    if step >= 4:
        release_chat_input_focus(st)
        _render_chat(st)
        st.write("")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🎙️ Yarışmaya başla",
                         type="primary", use_container_width=True):
                _exit(st)
        with c2:
            if st.button("🏠 Ana sayfa",
                         type="secondary", use_container_width=True):
                _exit(st)
        return

    # === Input handling ===
    line = st.chat_input(_PLACEHOLDERS.get(step, ""), key="tutorial_input")
    focus_chat_input(st)
    _render_chat(st)

    if not line:
        return

    sound.queue(st, "click")
    raw = line.lower().strip()
    _push(st, "user", line)

    if raw in _EXIT_WORDS:
        _push(st, "assistant",
              "Tabii efendim, ana sayfaya dönüyoruz. İstediğinizde sol "
              "kenardan **📖 Nasıl oynanır?** ile tekrar bakabilirsiniz.")
        _exit(st)
        return

    _process_step(st, step, raw)
    st.rerun()


def _process_step(st, step: int, raw: str) -> None:
    if step == 0:
        if raw == "h":
            st.session_state.tutorial_revealed[0] = _TUTORIAL_WORD[0]
            sound.queue(st, "tile-reveal")
            _push(st, "assistant",
                  f"İşte oldu — ilk harf **{_TUTORIAL_WORD[0]}**. "
                  "Her açılan harf, kelimenin değerinden 100 puan götürür.")
            _push(st, "assistant",
                  "Şimdi de bir ipucu alalım. **ipucu** yazın efendim.")
            st.session_state.tutorial_step = 1
        else:
            _push(st, "assistant",
                  "Önce harf isteyelim — kısaca **h** yazın yeter efendim.")

    elif step == 1:
        if raw == "ipucu":
            _push(st, "assistant",
                  "Şöyle ki efendim... Bu bir meyve. Her sabah bir tane "
                  "yemek iyi gelir derler, doktoru bile uzaklaştırırmış...")
            _push(st, "assistant",
                  "Aklınızda bir kelime varsa **bb** yazın — süreyi "
                  "durdurur, cevap için size 45 saniye verir.")
            _push(st, "assistant",
                  "**Önemli:** bb'den sonra **harf alamazsınız** — sadece "
                  "cevap verebilir ya da yeni ipucu isteyebilirsiniz.")
            st.session_state.tutorial_step = 2
        else:
            _push(st, "assistant",
                  "İpucu için **ipucu** yazmanız yeter efendim, sizi bekliyorum.")

    elif step == 2:
        if raw == "bb":
            sound.queue(st, "bb")
            _push(st, "assistant",
                  "Pekâlâ — cevap fazındayız. Süreyi durdurdum, kelimeyi "
                  "yazın efendim.")
            st.session_state.tutorial_step = 3
        elif raw == "h":
            _push(st, "assistant",
                  "Gerçek oyunda bb'den önce harf alabilirsiniz — ama biz "
                  "şu adımda **bb** yazmayı görmek için bekliyoruz. "
                  "Hadi **bb** yazın.")
        else:
            _push(st, "assistant",
                  "Cevap vermek için önce **bb** yazın efendim — süreyi "
                  "durdurmanız gerekir.")

    elif step == 3:
        if raw == _TUTORIAL_WORD.lower():
            st.session_state.tutorial_revealed = list(_TUTORIAL_WORD)
            sound.queue(st, "correct")
            _push(st, "assistant",
                  f"BRAVO efendim! **{_TUTORIAL_WORD}** doğru cevap! "
                  "İşte tam böyle oynanır.")
            _push(st, "assistant",
                  "Hazırsanız gerçek yarışmaya geçelim — 14 kelime sizi bekliyor.")
            st.session_state.tutorial_step = 4
        else:
            _push(st, "assistant",
                  f"Cevap **{_TUTORIAL_WORD}** efendim — bir deneyin, "
                  "hep birlikte görelim.")


# --------------------------------------------------------------------------
# Chat renderer — local copy of arena's bubble HTML so tutorial doesn't
# pull in the whole arena module just for this. Supports a `**bold**`
# substitution so we can emphasize input keywords (h / ipucu / bb).
# --------------------------------------------------------------------------


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _render_chat(st) -> None:
    chat_log = st.session_state.get("chat_log") or []
    if not chat_log:
        return
    pieces = []
    for entry in chat_log:
        role = entry[0]
        text = entry[1]
        safe = html_lib.escape(text).replace("\n", "<br>")
        safe = _BOLD_RE.sub(r"<strong>\1</strong>", safe)
        if role == "assistant":
            pieces.append(
                '<div class="lexi-chat-row lexi-chat-host">'
                '<div class="lexi-chat-avatar">🎙️</div>'
                f'<div class="lexi-chat-bubble lexi-chat-host-bubble">{safe}</div>'
                '</div>'
            )
        elif role == "user":
            pieces.append(
                '<div class="lexi-chat-row lexi-chat-user">'
                f'<div class="lexi-chat-bubble lexi-chat-user-bubble">{safe}</div>'
                '</div>'
            )
    st.markdown(
        f'<div class="lexi-chat-scroll">{"".join(pieces)}</div>',
        unsafe_allow_html=True,
    )
