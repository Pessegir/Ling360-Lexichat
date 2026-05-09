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
    "click",
]
BASE_URL = "/app/static/sounds/"


def inject_sound_engine(st):
    """Set up window.top.lexi.{ctx,buffers,muted,play} — Web Audio API.

    Why Web Audio (not HTMLAudioElement): Firefox blocks <audio>.play()
    even from inside a user-gesture handler unless the site has explicit
    autoplay permission, which most users don't grant. Web Audio uses a
    different model: AudioContext.resume() during a single user gesture
    grants playback permission for the rest of the session, so every
    later sample fires without further authorization checks.

    Idempotent: only initializes on first call per page load. Mirrored
    onto window.parent so consumers using either window.top or
    window.parent find the same engine object.
    """
    files_js = ",".join(f'"{n}"' for n in SOUND_FILES)
    js = (
        # window.top reaches the outermost frame; falls back to parent
        # if cross-origin (shouldn't happen on same-origin Streamlit).
        'var w;try{w=window.top;w.document;}catch(e){w=window.parent;}'
        'console.log("[lexi sound] init starting, target=",w===window.top?"top":"parent");'
        'if(!w.lexi){w.lexi={};}'
        'if(!w.lexi.buffers){'
          # Use w.AudioContext (parent window's class), NOT window.AudioContext
          # (iframe's class). The iframe gets destroyed on every Streamlit
          # rerun, which orphans any AudioContext tied to it — the JS object
          # lingers but the audio thread is gone. Constructing via the parent
          # window's class binds the audio thread to the persistent top frame.
          'var Ctx=w.AudioContext||w.webkitAudioContext;'
          'if(!Ctx){console.warn("[lexi sound] Web Audio API unavailable");return;}'
          'w.lexi.ctx=new Ctx();'
          'w.lexi.buffers={};'
          'if(typeof w.lexi.muted!=="boolean"){w.lexi.muted=false;}'
          'w.lexi.volume=0.55;'
          'w.lexi.play=function(name){'
            'try{'
              'if(this.muted)return;'
              'var buf=this.buffers[name];'
              'if(!buf){console.warn("[lexi sound] no buffer for",name);return;}'
              'var ctx=this.ctx;'
              # Resume on demand in case context drifted back to suspended
              'if(ctx.state==="suspended"){ctx.resume();}'
              'var src=ctx.createBufferSource();'
              'src.buffer=buf;'
              'var gain=ctx.createGain();'
              'gain.gain.value=this.volume;'
              'src.connect(gain).connect(ctx.destination);'
              'src.start();'
            '}catch(e){console.warn("[lexi sound] play threw:",e);}'
          '};'
          # Preload all WAV files via fetch + decodeAudioData
          f'var names=[{files_js}];'
          'var loaded=0;'
          'names.forEach(function(n){'
            f'fetch("{BASE_URL}"+n+".wav")'
              '.then(function(r){if(!r.ok)throw new Error("HTTP "+r.status);return r.arrayBuffer();})'
              '.then(function(buf){return w.lexi.ctx.decodeAudioData(buf);})'
              '.then(function(audioBuf){w.lexi.buffers[n]=audioBuf;loaded++;'
                'if(loaded===names.length){console.log("[lexi sound] all",loaded,"buffers decoded");}'
              '})'
              '.catch(function(err){console.warn("[lexi sound] load failed for",n,err.message);});'
          '});'
          'console.log("[lexi sound] init complete, fetching",names.length,"sounds");'
          # Resume the AudioContext on the first user gesture. Once
          # resumed, all future play() calls work without re-prompting.
          'var resume=function(){'
            'if(w.lexi.ctx.state==="suspended"){'
              'w.lexi.ctx.resume().then(function(){'
                'console.log("[lexi sound] AudioContext resumed");'
              '}).catch(function(e){console.warn("[lexi sound] resume failed:",e);});'
            '}'
            'w.document.removeEventListener("pointerdown",resume);'
            'w.document.removeEventListener("keydown",resume);'
          '};'
          'w.document.addEventListener("pointerdown",resume,{once:true});'
          'w.document.addEventListener("keydown",resume,{once:true});'
          # Global UI click sound — fires once per click on any
          # button, link, or role=button. Capture phase so we hear
          # it even if a child stops propagation. Skip clicks on
          # the chat textarea / inputs (those generate text, not actions).
          'w.document.addEventListener("click",function(ev){'
            'try{'
              'var el=ev.target;'
              'if(!el||!el.closest)return;'
              'var btn=el.closest("button,a,[role=\\"button\\"]");'
              'if(!btn)return;'
              # Skip elements inside the chat input area (composer button etc.)
              'if(el.closest("[data-testid=\\"stChatInput\\"]"))return;'
              'if(w.lexi&&w.lexi.play)w.lexi.play("click");'
            '}catch(e){}'
          '},true);'
        '}else{console.log("[lexi sound] already initialized, skipping");}'
        # Mirror onto window.parent too, in case Streamlit nests the
        # component iframe one level deeper than expected. Consumers
        # in components.py use w=window.parent and read w.lexi — both
        # refs point to the same engine object.
        'try{if(window.parent!==w){window.parent.lexi=w.lexi;}}catch(e){}'
    )
    _inject_parent_js(js)


def _target_js(body: str) -> str:
    """Wrap a JS body so it executes against window.top (with fallback to
    window.parent). Lets us reach the lexi engine no matter how many
    iframe layers Streamlit wraps the component in."""
    return (
        'var w;try{w=window.top;w.document;}catch(e){w=window.parent;}'
        + body
    )


def play(st, name: str):
    """Trigger a sound by injecting a one-line JS call.

    Safe to call from any phase — if the engine isn't initialized yet
    or the named file doesn't exist, the call is a no-op.

    NOTE: Streamlit reruns destroy components.html iframes mid-flight,
    so calling play() right before st.rerun() can swallow the sound.
    For sounds that fire during phase transitions, use queue() instead.
    """
    _inject_parent_js(_target_js(
        f'try{{if(w.lexi&&w.lexi.play)w.lexi.play("{name}");}}catch(e){{console.warn("[lexi sound] play({name!r}) failed:",e);}}'
    ))


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
    _inject_parent_js(_target_js(
        f'try{{if(w.lexi)w.lexi.muted={val};}}catch(e){{}}'
    ))
