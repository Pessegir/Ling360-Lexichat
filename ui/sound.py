"""Sound engine — preload WAV samples + JS play() + mute toggle.

Sounds live in `static/sounds/*.wav`, served by Streamlit at
`<host>/app/static/sounds/<name>.wav` (gated by `.streamlit/config.toml`
`enableStaticServing = true`). Each event in the game injects a tiny
JS payload that calls `window.parent.lexi.play(name)`; the engine itself
preloads the audio on first inject so the first hit isn't a cold fetch.

Browser autoplay policy: most browsers block audio playback before any
user gesture. Our first sound only fires after the player clicks
"Yeni oyun" (and types into chat), so the gesture-gate is naturally
cleared. We also install a one-time unlock handler that primes every
preloaded Audio on the first click anywhere — belt-and-suspenders.
"""
from __future__ import annotations

from ui.components import _inject_parent_js


SOUND_FILES = [
    "tile-reveal", "correct", "wrong",
    "score-up", "score-down", "timer-tick",
    "game-start", "game-end", "new-record",
]
BASE_URL = "/app/static/sounds/"


def inject_sound_engine(st):
    """Set up window.parent.lexi.{sounds,muted,play}.

    Idempotent: skips reinitialization if `lexi.sounds` is already
    populated. Called from theme.inject() so it runs on every page,
    but only does work once per page load.
    """
    files_js = ",".join(f'"{n}"' for n in SOUND_FILES)
    js = (
        'var w=window.parent;'
        'if(!w.lexi){w.lexi={};}'
        'if(!w.lexi.sounds||Object.keys(w.lexi.sounds).length===0){'
          'w.lexi.sounds={};'
          'if(typeof w.lexi.muted!=="boolean"){w.lexi.muted=false;}'
          'w.lexi.play=function(name){'
            'try{'
              'if(this.muted)return;'
              'var a=this.sounds[name];'
              'if(!a)return;'
              'a.currentTime=0;'
              'var p=a.play();'
              'if(p&&p.catch){p.catch(function(){});}'
            '}catch(e){}'
          '};'
          f'var names=[{files_js}];'
          'names.forEach(function(n){'
            f'var a=new Audio("{BASE_URL}"+n+".wav");'
            'a.preload="auto";'
            'a.volume=0.55;'
            'w.lexi.sounds[n]=a;'
          '});'
          # Unlock playback on the first user gesture (autoplay policy)
          'var unlock=function(){'
            'Object.values(w.lexi.sounds).forEach(function(a){'
              'try{'
                'var p=a.play();'
                'if(p&&p.then){p.then(function(){a.pause();a.currentTime=0;}).catch(function(){});}'
              '}catch(e){}'
            '});'
            'w.document.removeEventListener("pointerdown",unlock);'
            'w.document.removeEventListener("keydown",unlock);'
          '};'
          'w.document.addEventListener("pointerdown",unlock,{once:true});'
          'w.document.addEventListener("keydown",unlock,{once:true});'
        '}'
    )
    _inject_parent_js(js)


def play(st, name: str):
    """Trigger a sound by injecting a one-line JS call.

    Safe to call from any phase — if the engine isn't initialized yet
    or the named file doesn't exist, the call is a no-op.

    NOTE: Streamlit reruns destroy components.html iframes mid-flight,
    so calling play() right before st.rerun() can swallow the sound.
    For sounds that fire during phase transitions, use queue() instead.
    """
    _inject_parent_js(
        f'try{{var w=window.parent;if(w.lexi&&w.lexi.play)w.lexi.play("{name}");}}catch(e){{}}'
    )


def queue(st, name: str):
    """Defer a sound to the next page render.

    Used when the call site is about to st.rerun() — direct play()
    would race the iframe lifecycle and silently drop the audio.
    The next renderer calls flush() to actually fire queued sounds.
    """
    pending = st.session_state.get("_pending_sounds")
    if pending is None:
        pending = []
        st.session_state._pending_sounds = pending
    pending.append(name)


def flush(st):
    """Play and clear any queued sounds. Call once per renderer."""
    pending = st.session_state.get("_pending_sounds")
    if not pending:
        return
    for name in pending:
        play(st, name)
    st.session_state._pending_sounds = []


def set_muted(st, muted: bool):
    """Sync mute state from session_state to the JS engine."""
    val = "true" if muted else "false"
    _inject_parent_js(
        f'try{{var w=window.parent;if(w.lexi)w.lexi.muted={val};}}catch(e){{}}'
    )
