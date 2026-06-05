"""Reusable UI components for the Lexi-Chat web app.

Each function takes Streamlit (`st`) as its first arg so the module itself
has no Streamlit import-side-effect — easier to unit-test the HTML output.
"""
from __future__ import annotations

import html as html_lib
import json
import time
from contextlib import contextmanager

import streamlit.components.v1 as components

from game.config import APP_NAME, APP_TAGLINE
from game.text_utils import tr_upper


def _inject_parent_js(script_body: str, *, height: int = 0):
    """Run JS in the Streamlit parent document.

    `st.markdown(unsafe_allow_html=True)` STRIPS <script> tags, so any
    JS we want to run lives in a small components.html iframe whose
    body reaches up to the parent document via window.parent.document.

    height=0 keeps the iframe invisible.
    """
    components.html(
        f'<script>(function(){{try{{var d=window.parent.document;{script_body}}}catch(e){{console.warn("lexi js error",e);}}}})();</script>',
        height=height,
        scrolling=False,
    )


# --------------------------------------------------------------------------
# Branding
# --------------------------------------------------------------------------


# Microphone glyph for the wordmark — line-art SVG, amber stroke.
# Inline so the home screen has zero extra HTTP requests.
_MIC_SVG = (
    '<svg class="lexi-mic-glyph" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true">'
    '<rect x="9" y="3" width="6" height="11" rx="3"/>'
    '<path d="M5 11a7 7 0 0 0 14 0"/>'
    '<line x1="12" y1="18" x2="12" y2="22"/>'
    '<line x1="8" y1="22" x2="16" y2="22"/>'
    '</svg>'
)


def wordmark(st, *, with_tagline: bool = False, level: str = "h1"):
    """Render the Lexi-Chat wordmark. Accent dot on the hyphen.

    level: HTML tag — h1 for landing, h3 for in-game header.
    Microphone glyph appears alongside on the landing wordmark
    (with_tagline=True) — a small TV-studio cue.
    """
    name = html_lib.escape(APP_NAME)
    parts = name.split("-", 1)
    if len(parts) == 2:
        wm_inner = f'{parts[0]}<span class="accent">-</span>{parts[1]}'
    else:
        wm_inner = name

    if with_tagline:
        markup = (
            f'<div class="lexi-wordmark-row">'
            f'  {_MIC_SVG}'
            f'  <{level} class="lexi-wordmark" style="margin:0;">{wm_inner}</{level}>'
            f'</div>'
            f'<div class="lexi-tagline" style="text-align:center;">{html_lib.escape(APP_TAGLINE)}</div>'
        )
    else:
        markup = f'<{level} class="lexi-wordmark">{wm_inner}</{level}>'

    st.markdown(markup, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Letter tile board
# --------------------------------------------------------------------------


def tile_board(st, word_or_length, revealed_letters=None, *, board_key: str = ""):
    """Render the diamond letter board.

    Two ways to call:
      tile_board(st, 5)                              # all blank, length 5
      tile_board(st, "uzay", ["_  ", "z", "_  ", "y"])  # mix of revealed + blank

    revealed_letters uses the engine's "_  " sentinel for blanks (matches
    GameState.revealed_letters). Strings of length 1 are treated as revealed.

    board_key: stable per-round identifier (e.g. "{round_idx}:{word}").
    JS uses it to dedup which tiles are newly-revealed and only animate
    the flip on those — without dedup, every rerun re-fires the
    animation on every revealed tile.
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
            # Turkish-correct uppercase: ı → I, i → İ, ş → Ş, etc.
            ch = html_lib.escape(tr_upper(revealed[i].strip()[:1]))
            tiles_html.append(
                f'<div class="lexi-tile revealed" data-pos="{i}"><span>{ch}</span></div>'
            )
        else:
            tiles_html.append(
                f'<div class="lexi-tile" data-pos="{i}"><span>&nbsp;</span></div>'
            )

    safe_key = html_lib.escape(board_key)
    st.markdown(
        f'<div class="lexi-tiles" data-board-key="{safe_key}">{"".join(tiles_html)}</div>',
        unsafe_allow_html=True,
    )

    if board_key:
        # Per-board dedup: track which positions were already revealed in
        # __lexiTileSeen[boardKey]. Only NEWLY revealed tiles get the
        # .lexi-flip class on this rerun, so the flip animation fires
        # exactly once per reveal — even though autorefresh in the
        # answering phase rebuilds the DOM every 3 s.
        js = (
            'var w=window.parent;'
            'var board=d.querySelector(".lexi-tiles");'
            'if(!board)return;'
            'var key=board.getAttribute("data-board-key")||"";'
            'w.__lexiTileSeen=w.__lexiTileSeen||{};'
            'var seen=w.__lexiTileSeen[key]||{};'
            'var tiles=board.querySelectorAll(".lexi-tile");'
            # Track whether THIS render newly revealed any tile so we
            # only fire the reveal sound once per real reveal (not per
            # tile, in case multiple flip at once).
            'var anyNew=false;'
            'tiles.forEach(function(t,i){'
              'var isRev=t.classList.contains("revealed");'
              'if(isRev && !seen[i]){t.classList.add("lexi-flip");anyNew=true;}'
              'seen[i]=isRev;'
            '});'
            'w.__lexiTileSeen[key]=seen;'
            # Sound is queued from Python (sound.queue("tile-reveal") in
            # arena.py letter-request branch) — more reliable than this
            # JS path, which races the components.html iframe lifecycle.
            # Keep the dedup loop only for the visual flip animation.
        )
        _inject_parent_js(js)


# --------------------------------------------------------------------------
# Clue card
# --------------------------------------------------------------------------


def clue_card(st, text: str, label: str = "İPUCU"):
    safe = html_lib.escape(text)
    st.markdown(
        f'<div class="lexi-clue"><span class="lexi-clue-label">{html_lib.escape(label)}</span>{safe}</div>',
        unsafe_allow_html=True,
    )


def info_chips(st, revealed: dict):
    """Render the row of revealed-info chips above the clue.

    revealed: dict with optional keys 'function', 'structure', 'origin',
    'compound', etc. Empty dict → nothing renders.
    """
    if not revealed:
        return

    chips = []
    label_map = {
        "function": "TÜR",
        "structure": "YAPI",
        "origin": "KÖKEN",
        "compound": "BİRLEŞİK",
    }
    for key, label in label_map.items():
        val = revealed.get(key)
        if val and val != "None":
            safe_val = html_lib.escape(str(val))
            chips.append(
                f'<span class="lexi-info-chip">'
                f'<span class="lexi-info-chip-label">{label}</span>'
                f'<span class="lexi-info-chip-value">{safe_val}</span>'
                f'</span>'
            )

    if chips:
        st.markdown(
            f'<div class="lexi-info-row">{"".join(chips)}</div>',
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------
# Top bar — score / round / timer
# --------------------------------------------------------------------------


def topbar(st, *, score: int, round_num: int, total_rounds: int,
           seconds_remaining: int, in_answer_mode: bool = False,
           live: bool = False, pop: dict | None = None,
           game_key: str = ""):
    """Render the score/round/timer header strip.

    in_answer_mode = True → label changes to "CEVAP SÜRESİ", color shifts amber.
    seconds_remaining < 30 → color shifts to dusty rose (warning).
    live = True → attach a JS countdown so the visible timer ticks every
                  second even without a Streamlit rerun (server stays
                  authoritative — value is reconciled on the next rerun).
    pop  = {"delta": int} → render a floating +N / -N badge that
                  auto-fades. Driver decides whether the pop is "due"
                  (e.g. its `at` timestamp ≤ now); we just paint when
                  it's passed in.
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

    # Score-pop badge: rendered next to the score value, CSS animation
    # handles the float+fade. The `key=` trick (data-pop-id) forces a
    # fresh DOM node per pop so the @keyframes restart cleanly.
    pop_html = ""
    if pop:
        delta = int(pop.get("delta", 0))
        if delta != 0:
            sign = "+" if delta > 0 else ""
            cls = "gain" if delta > 0 else "loss"
            pop_id = pop.get("id", str(int(time.time() * 1000)))
            pop_html = (
                f'<span class="lexi-score-pop {cls}" '
                f'data-pop-id="{pop_id}">{sign}{delta:,}</span>'
            )

    # Round indicator: dots instead of "3 / 14" text. Done = dim amber,
    # active = bright amber + glow, future = neutral. The chip-value
    # text version is kept as aria-label for screen readers.
    dot_html = []
    for i in range(total_rounds):
        if i < round_num - 1:
            cls = "lexi-round-dot done"
        elif i == round_num - 1:
            cls = "lexi-round-dot active"
        else:
            cls = "lexi-round-dot"
        dot_html.append(f'<span class="{cls}"></span>')
    dots = "".join(dot_html)

    safe_game_key = html_lib.escape(game_key)
    st.markdown(
        f'''
<div class="lexi-topbar">
  <div class="lexi-chip">
    <div class="lexi-chip-label">PUAN</div>
    <div class="lexi-chip-value">
      <span class="lexi-score-num" data-score="{score}" data-game-key="{safe_game_key}">{score:,}</span>{pop_html}
    </div>
  </div>
  <div class="lexi-chip">
    <div class="lexi-chip-label">SORU</div>
    <div class="lexi-round-dots" aria-label="{round_num} / {total_rounds}">{dots}</div>
  </div>
  <div class="lexi-chip" style="align-items: flex-end;">
    <div class="lexi-chip-label">{timer_label}</div>
    <div class="lexi-chip-value {timer_class}" id="lexi-global-timer">{timer_str}</div>
  </div>
</div>
''',
        unsafe_allow_html=True,
    )

    # Score odometer — tween from previous value to current using rAF.
    # Game-key check resets the in-flight value across new games so we
    # don't tween 4200 → 0 between games.
    odometer_js = (
        'var w=window.parent;'
        'var n=d.querySelector(".lexi-score-num");'
        'if(!n)return;'
        'var target=parseInt(n.getAttribute("data-score"),10);'
        'var gk=n.getAttribute("data-game-key")||"";'
        'var lastKey=w.__lexiScoreGameKey;'
        'var current=(lastKey===gk && typeof w.__lexiLastScore==="number")?w.__lexiLastScore:target;'
        'w.__lexiScoreGameKey=gk;'
        'function fmt(v){return v.toLocaleString("tr-TR");}'
        'if(current===target){n.textContent=fmt(target);w.__lexiLastScore=target;return;}'
        # Sound on score change — only when we actually have a delta to
        # tween (not on first render of a fresh game, where current===target).
        'if(w.lexi && w.lexi.play){w.lexi.play(target>current?"score-up":"score-down");}'
        'if(w.__lexiScoreRaf){cancelAnimationFrame(w.__lexiScoreRaf);}'
        'var start=performance.now(),dur=600,from=current;'
        'function tick(now){'
          'var t=Math.min(1,(now-start)/dur);'
          'var e=1-Math.pow(1-t,3);'
          'var v=Math.round(from+(target-from)*e);'
          'n.textContent=fmt(v);'
          'w.__lexiLastScore=v;'
          'if(t<1){w.__lexiScoreRaf=requestAnimationFrame(tick);}'
          'else{w.__lexiLastScore=target;w.__lexiScoreRaf=null;}'
        '}'
        'w.__lexiScoreRaf=requestAnimationFrame(tick);'
    )
    _inject_parent_js(odometer_js)

    # JS state is stored on window.parent so it survives the per-rerun
    # iframe recreation. The element it paints into (#lexi-global-timer)
    # lives in the parent document — we look it up via window.parent.document.
    if not live:
        # Stop any running countdown; we're showing a static value
        # (paused timer during answering). Otherwise the prior interval
        # would keep ticking and overwrite the static digits.
        _inject_parent_js(
            'var w=window.parent;'
            'if(w.__lexiGlobalTimer){clearInterval(w.__lexiGlobalTimer);w.__lexiGlobalTimer=null;}'
            'w.__lexiGlobalJsSecs=null;'
        )
    else:
        server_secs = max(0, int(seconds_remaining))
        js = (
            'var w=window.parent;'
            f'var serverSecs={server_secs};'
            'var jsSecs=(typeof w.__lexiGlobalJsSecs==="number")?w.__lexiGlobalJsSecs:serverSecs;'
            # Normally server <= js (wall clock advanced between reruns).
            # But if the gap is large (>5s), trust the server — pause/restore.
            'var remaining=(Math.abs(serverSecs-jsSecs)>5)?serverSecs:Math.min(serverSecs,jsSecs);'
            'w.__lexiGlobalJsSecs=remaining;'
            'function paint(){'
              'var node=d.getElementById("lexi-global-timer");'
              'if(!node)return false;'
              'var m=Math.floor(remaining/60),s=remaining%60;'
              'node.textContent=(m<10?"0":"")+m+":"+(s<10?"0":"")+s;'
              'return true;'
            '}'
            'paint();'
            'if(w.__lexiGlobalTimer){clearInterval(w.__lexiGlobalTimer);w.__lexiGlobalTimer=null;}'
            'w.__lexiGlobalTimer=setInterval(function(){'
              'remaining=Math.max(0,remaining-1);'
              'w.__lexiGlobalJsSecs=remaining;'
              'if(!paint()||remaining<=0){clearInterval(w.__lexiGlobalTimer);w.__lexiGlobalTimer=null;}'
            '},1000);'
        )
        _inject_parent_js(js)


# --------------------------------------------------------------------------
# Answer-phase timer — server-authoritative + JS visual countdown
# --------------------------------------------------------------------------


def answer_timer(st, *, seconds_remaining: float, total_seconds: int = 45,
                 round_key: str = ""):
    """Render the bb-phase countdown.

    The server is authoritative — `seconds_remaining` is the truth at render
    time, recomputed from wall clock on every rerun. The JS `setInterval`
    only animates the *visible* digits between reruns so the user sees a
    smooth tick instead of a frozen number.

    The JS counter starts from ceil(seconds_remaining) and counts down to 0,
    so when the server-side rerun reconciles, the visual already matches
    (the +1 grace second is added on the server side: deadline = now + 46
    while we still display 45). The displayed number is clamped to >= 0;
    real round-end is decided server-side, not by the JS.
    """
    secs = max(0, int(seconds_remaining))
    # HTML lives in the parent document via st.markdown. The JS that
    # paints/ticks runs through _inject_parent_js (st.markdown strips
    # <script> tags, so we have to use a components.html iframe).
    st.markdown(
        f'''
<div class="lexi-answer-timer" data-total="{total_seconds}">
  <div class="lexi-answer-timer-label">CEVAP SÜRESİ</div>
  <div class="lexi-answer-timer-value" id="lexi-answer-timer-value">{secs:02d}</div>
  <div class="lexi-answer-timer-bar">
    <div class="lexi-answer-timer-fill" id="lexi-answer-timer-fill"
         style="width: {min(100, max(0, (secs / max(1, total_seconds)) * 100)):.1f}%"></div>
  </div>
</div>
''',
        unsafe_allow_html=True,
    )
    js = (
        'var w=window.parent;'
        f'var serverSecs={secs};'
        f'var total={total_seconds};'
        f'var roundKey="{round_key}";'
        # New bb session → drop any stale JS countdown state.
        'if(w.__lexiAnswerRoundKey!==roundKey){w.__lexiAnswerRoundKey=roundKey;w.__lexiAnswerJsSecs=serverSecs;}'
        'var jsSecs=(typeof w.__lexiAnswerJsSecs==="number")?w.__lexiAnswerJsSecs:serverSecs;'
        'var remaining=Math.min(serverSecs,jsSecs);'
        'w.__lexiAnswerJsSecs=remaining;'
        'function paint(){'
          'var elNow=d.getElementById("lexi-answer-timer-value");'
          'var fillNow=d.getElementById("lexi-answer-timer-fill");'
          'if(!elNow||!fillNow)return false;'
          'elNow.textContent=(remaining<10?"0":"")+remaining;'
          'fillNow.style.width=Math.min(100,Math.max(0,(remaining/total)*100))+"%";'
          'return true;'
        '}'
        'paint();'
        'if(w.__lexiAnswerTimer){clearInterval(w.__lexiAnswerTimer);w.__lexiAnswerTimer=null;}'
        'w.__lexiAnswerTimer=setInterval(function(){'
          'remaining=Math.max(0,remaining-1);'
          'w.__lexiAnswerJsSecs=remaining;'
          # Soft tick during the last 10 seconds — quietly urgent.
          'if(remaining>0 && remaining<=10 && w.lexi && w.lexi.play){w.lexi.play("timer-tick");}'
          'if(!paint()||remaining<=0){clearInterval(w.__lexiAnswerTimer);w.__lexiAnswerTimer=null;}'
        '},1000);'
    )
    _inject_parent_js(js)


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


def focus_chat_input(st):
    """Persist focus on the st.chat_input textarea across reruns.

    Streamlit reruns rebuild the widget tree, dropping focus. The
    autorefresh-driven phases (`between`, `answering`) compound this by
    triggering reruns every 1.5–3 s without user interaction; our JS
    lives in a components.html iframe whose async load (~50–200 ms)
    misses the moment the textarea is recreated, so keystrokes typed
    mid-rebuild land nowhere.

    Fix: install a long-lived MutationObserver on window.parent that
    refocuses the textarea synchronously whenever the DOM mutates.
    We gate it so it never poaches focus from another input/button —
    refocus only fires when activeElement is body/html (i.e. nothing
    has explicit focus, which is the post-rerun state).
    """
    js = (
        'var w=window.parent;'
        'function _refocus(){'
          'try{'
            'if(!w.__lexiFocusActive)return;'
            'var ta=d.querySelector("textarea[data-testid=\\"stChatInputTextArea\\"]")'
            ' ||d.querySelector("[data-testid=\\"stChatInput\\"] textarea")'
            ' ||d.querySelector("section.main textarea");'
            'if(!ta)return;'
            'var ae=d.activeElement;'
            'if(ae===ta)return;'
            # Only refocus when nothing else is intentionally focused.
            # Body / html / null = post-rerun "lost focus" state — safe to grab.
            'if(ae && ae!==d.body && ae!==d.documentElement)return;'
            'ta.focus();'
          '}catch(e){}'
        '}'
        'if(!w.__lexiFocusObs){'
          'var deb;'
          'w.__lexiFocusObs=new MutationObserver(function(){'
            'clearTimeout(deb);'
            'deb=setTimeout(_refocus,30);'
          '});'
          'w.__lexiFocusObs.observe(d.body,{childList:true,subtree:true});'
        '}'
        'w.__lexiFocusActive=true;'
        '_refocus();'
    )
    _inject_parent_js(js)


def release_chat_input_focus(st):
    """Stop focus persistence — call from screens with no chat input
    (home, end, history) so the observer doesn't refocus a stale element."""
    _inject_parent_js('window.parent.__lexiFocusActive=false;')


@contextmanager
def typing_indicator(st, label: str = "SUNUCU KONUŞUYOR"):
    """Render a 3-dot animated indicator while a slow operation runs.

    Replaces st.spinner for in-game host turns so the visual matches the
    studio palette (amber dots in a teal-bordered card) instead of
    Streamlit's generic gray spinner. Use as a context manager:

        with typing_indicator(st):
            reply = host.llm_host_reply(...)
    """
    placeholder = st.empty()
    placeholder.markdown(
        f'<div class="lexi-typing">'
        f'<span>{html_lib.escape(label)}</span>'
        f'<span class="lexi-typing-dots">'
        f'<span class="lexi-typing-dot"></span>'
        f'<span class="lexi-typing-dot"></span>'
        f'<span class="lexi-typing-dot"></span>'
        f'</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    try:
        yield
    finally:
        placeholder.empty()


def mark_fresh_chat_messages(st, *, force_snap: bool = False):
    """Mark just-rendered chat messages with .lexi-fresh so only the
    new ones animate in. Also auto-scrolls the chat container to the
    bottom on new messages.

    `force_snap=True` snaps to the bottom on every beat regardless of the
    heuristics. The between phase passes this: it reruns ~1×/s under
    autorefresh, and on those same-phase reruns phaseChanged/newCount/grew
    all read false while a freshly-laid-out container reads "not at bottom",
    so the panel would otherwise drift back to the top. Manual scroll-up
    isn't a real use case during a 2-4 s auto-advancing transition.

    The state counter and the scroll itself BOTH live on the persistent
    top window — using `d` (window.parent.document) and `w`
    (window.parent) instead silently fails when Streamlit nests the
    components iframe one level deeper than expected. The scroll runs
    in a requestAnimationFrame so it sees the post-reflow scrollHeight,
    not the stale one from before the new bubble was painted.

    On a phase change the chat container is a fresh DOM node scrolled to
    the top, and a transition often adds no new bubble — so newCount,
    `grew` and `atBottom` can all read false and the snap is skipped,
    leaving the player looking at the top of the panel. We detect the
    phase change server-side and force the snap on every beat for that
    first render, while still respecting a manual scroll-up within a phase.
    """
    cur_phase = json.dumps(st.session_state.get("phase", ""))
    force_js = "true" if force_snap else "false"
    js = (
        f'var force={force_js};'
        # Probe both top and parent for the chat scroll element — they
        # can be different windows when Streamlit nests iframes, and the
        # element may live in either.
        'function _findChatSc(){'
          'try{var s=window.top.document.getElementById("lexi-chat-scroll");if(s)return s;}catch(e){}'
          'try{var s=window.parent.document.getElementById("lexi-chat-scroll");if(s)return s;}catch(e){}'
          'return null;'
        '}'
        'var pw;try{pw=window.top;pw.document;}catch(e){pw=window.parent;}'
        # Force a snap on the first render after a phase change, regardless
        # of the heuristics below — a fresh container is always at the top.
        f'var curPhase={cur_phase};'
        'var phaseChanged=(pw.__lexiChatPhase!==curPhase);'
        'pw.__lexiChatPhase=curPhase;'
        'var pd=pw.document;'
        'var msgs=pd.querySelectorAll(".lexi-chat-row,.lexi-chat-system");'
        'var count=msgs.length;'
        'var last=(typeof pw.__lexiChatLast==="number")?pw.__lexiChatLast:0;'
        'if(count<last)last=0;'
        'var newCount=count-last;'
        'if(newCount>0){'
          'for(var i=last;i<count;i++){msgs[i].classList.add("lexi-fresh");}'
        '}'
        'pw.__lexiChatLast=count;'
        # Brute-force snap to bottom: fire at multiple beats so it
        # catches the post-layout scrollHeight regardless of when
        # Streamlit finishes its DOM commit. Decision logic snaps when the
        # phase just changed (fresh container), the content grew, a new
        # bubble arrived, or the user was already near the bottom — so a
        # deliberate scroll-up within a phase is left alone.
        'function _maybeSnap(){'
          'var sc=_findChatSc();'
          'if(!sc)return;'
          'var prevH=pw.__lexiChatLastHeight||0;'
          'var curH=sc.scrollHeight;'
          'var atBottom=(curH-sc.scrollTop-sc.clientHeight)<80;'
          'var grew=(curH>prevH);'
          'if(force||phaseChanged||atBottom||newCount>0||grew){sc.scrollTop=curH;}'
          'pw.__lexiChatLastHeight=curH;'
        '}'
        '_maybeSnap();'                                # synchronous
        'pw.requestAnimationFrame(_maybeSnap);'         # post-paint
        'pw.setTimeout(_maybeSnap,80);'                 # catch slow layouts
        'pw.setTimeout(_maybeSnap,250);'                # final safety net
    )
    _inject_parent_js(js)


def host_bubble_with_audio_hook(st, text: str, audio_url: str | None = None):
    """Host bubble that *will* show a 🔊 button when voice mode ships.

    For now, audio_url is ignored. When voice arrives in a future phase,
    we render a play button next to the text. Designed in now so the
    bubble layout doesn't change later.
    """
    # TODO Phase 5+: render audio_url as an inline player when present
    return host_bubble(st, text)
