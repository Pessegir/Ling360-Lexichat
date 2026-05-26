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

import itertools

from ui.components import _inject_parent_js


# Monotonic counter — appended as a comment to every play() JS payload
# so back-to-back calls with the same sound name produce *different*
# strings. Streamlit dedupes components.html iframes by exact content;
# without this, repeated sound.play("tile-reveal") would only fire the
# first time per render position (e.g. consecutive 'h' letter requests).
_play_nonce = itertools.count()


SOUND_FILES = [
    # One-shot SFX
    "tile-reveal", "correct", "wrong",
    "score-up", "score-down", "timer-tick",
    "game-start", "game-end", "new-record",
    "click", "bb",
    # Looping background tracks — same fetch/decode path, played via
    # lexi.setBg() instead of lexi.play().
    "background_main", "bg_main", "bg_afterbb", "tension",
]

# Background tracks crossfade in the JS engine when phase changes. Volume
# sits well under SFX so spoken host lines and event sounds stay primary.
BG_DEFAULT_VOLUME = 0.10
BG_DEFAULT_FADE_MS = 400

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
          'if(typeof w.lexi.bgmuted!=="boolean"){w.lexi.bgmuted=false;}'
          'w.lexi.volume=0.55;'
          f'w.lexi.bgvolume={BG_DEFAULT_VOLUME};'
          'w.lexi.currentBg=null;'   # {source, gain, name} of the playing bg
          'w.lexi.pendingBg=null;'   # set when setBg called pre-resume
          # Looping background tracks. Crossfade between them on phase change.
          'w.lexi._startBg=function(name,fadeMs){'
            'var buf=this.buffers[name];'
            'if(!buf){console.warn("[lexi sound] no bg buffer for",name);return;}'
            'var ctx=this.ctx;'
            'var src=ctx.createBufferSource();'
            'src.buffer=buf;src.loop=true;'
            'var gain=ctx.createGain();'
            'gain.gain.value=0;'
            'src.connect(gain).connect(ctx.destination);'
            'src.start();'
            'var target=this.bgmuted?0:this.bgvolume;'
            'gain.gain.linearRampToValueAtTime(target,ctx.currentTime+fadeMs/1000);'
            'this.currentBg={source:src,gain:gain,name:name};'
          '};'
          'w.lexi._fadeOutBg=function(prev,fadeMs){'
            'var ctx=this.ctx;'
            'try{prev.gain.gain.cancelScheduledValues(ctx.currentTime);}catch(e){}'
            'prev.gain.gain.setValueAtTime(prev.gain.gain.value,ctx.currentTime);'
            'prev.gain.gain.linearRampToValueAtTime(0,ctx.currentTime+fadeMs/1000);'
            'setTimeout(function(){'
              'try{prev.source.stop();prev.source.disconnect();prev.gain.disconnect();}catch(e){}'
            '},fadeMs+80);'
          '};'
          'w.lexi.setBg=function(name,fadeMs){'
            'try{'
              'if(typeof fadeMs!=="number")fadeMs=400;'
              'var curName=this.currentBg?this.currentBg.name:null;'
              'console.log("[lexi sound] setBg",name,"(was",curName+",","ctx="+this.ctx.state+", bufReady="+!!this.buffers[name]+")");'
              'if(this.currentBg&&this.currentBg.name===name)return;'
              # AudioContext can\'t start audio until a user gesture has
              # resumed it. Queue the request; the resume handler will
              # pick it up.
              'if(this.ctx.state==="suspended"){this.pendingBg=name;return;}'
              'if(!this.buffers[name]){this.pendingBg=name;return;}'
              'var prev=this.currentBg;'
              'this._startBg(name,fadeMs);'
              'if(prev)this._fadeOutBg(prev,fadeMs);'
            '}catch(e){console.warn("[lexi sound] setBg threw:",e);}'
          '};'
          'w.lexi.stopBg=function(fadeMs){'
            'try{'
              'if(typeof fadeMs!=="number")fadeMs=400;'
              'this.pendingBg=null;'
              'if(!this.currentBg)return;'
              'var prev=this.currentBg;'
              'this.currentBg=null;'
              'this._fadeOutBg(prev,fadeMs);'
            '}catch(e){console.warn("[lexi sound] stopBg threw:",e);}'
          '};'
          'w.lexi.setBgMuted=function(b){'
            'try{'
              'this.bgmuted=!!b;'
              'if(this.currentBg){'
                'var ctx=this.ctx;'
                'var target=this.bgmuted?0:this.bgvolume;'
                'this.currentBg.gain.gain.cancelScheduledValues(ctx.currentTime);'
                'this.currentBg.gain.gain.setValueAtTime(this.currentBg.gain.gain.value,ctx.currentTime);'
                'this.currentBg.gain.gain.linearRampToValueAtTime(target,ctx.currentTime+0.25);'
              '}'
            '}catch(e){}'
          '};'
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
                # If this buffer was the one Python asked to play before
                # decode finished, kick it off now. Closes a race where
                # set_bg() fired during init, set pendingBg, the resume
                # handler ran setBg(pn) which re-set pendingBg because
                # the buffer wasn\'t ready yet, and nothing ever started.
                'if(w.lexi.pendingBg===n&&w.lexi.ctx.state==="running"){'
                  'var pn=w.lexi.pendingBg;w.lexi.pendingBg=null;'
                  'w.lexi.setBg(pn,400);'
                '}'
              '})'
              '.catch(function(err){console.warn("[lexi sound] load failed for",n,err.message);});'
          '});'
          'console.log("[lexi sound] init complete, fetching",names.length,"sounds");'
          # Resume the AudioContext on the first user gesture. Once
          # resumed, all future play() calls work without re-prompting.
          'var resume=function(){'
            'var afterResume=function(){'
              # Kick off any background music that was requested before the
              # context was unlocked (e.g. menu music on home screen).
              'if(w.lexi.pendingBg){'
                'var pn=w.lexi.pendingBg;w.lexi.pendingBg=null;'
                # Delay slightly so any in-flight decodeAudioData has a chance
                # to finish on first page load.
                'setTimeout(function(){w.lexi.setBg(pn,400);},150);'
              '}'
            '};'
            'if(w.lexi.ctx.state==="suspended"){'
              'w.lexi.ctx.resume().then(function(){'
                'console.log("[lexi sound] AudioContext resumed");'
                'afterResume();'
              '}).catch(function(e){console.warn("[lexi sound] resume failed:",e);});'
            '}else{afterResume();}'
            'w.document.removeEventListener("pointerdown",resume);'
            'w.document.removeEventListener("keydown",resume);'
            'w.document.removeEventListener("touchstart",resume);'
          '};'
          'w.document.addEventListener("pointerdown",resume,{once:true});'
          'w.document.addEventListener("keydown",resume,{once:true});'
          'w.document.addEventListener("touchstart",resume,{once:true});'
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
        # Long-lived between-phase poller. INSTALLED OUTSIDE the
        # buffers-init gate so a Streamlit hot-reload that didn\'t
        # reset window.top can still pick this up. Each render_between
        # sets w.__lexiBetweenDeadline = epoch_ms; this 250ms poller
        # clicks the hidden tick button when the deadline passes.
        # Bulletproof against the components-iframe destruction race
        # that killed the old setTimeout-based approach.
        'if(!w.__lexiBetweenPoller){'
          'w.__lexiBetweenTicks=0;'
          'w.__lexiBetweenLastDl=null;'
          'w.__lexiBetweenPoller=w.setInterval(function(){'
            'w.__lexiBetweenTicks++;'
            'var dl=w.__lexiBetweenDeadline;'
            # First time we observe a non-null deadline, log it so we
            # can verify the writer is targeting our window.
            'if(dl!=null&&dl!==w.__lexiBetweenLastDl){'
              'console.log("[lexi between] poller saw deadline",dl,'
                '"now="+Date.now()+", "+(dl-Date.now())+"ms left");'
              'w.__lexiBetweenLastDl=dl;'
            '}'
            # Heartbeat every ~5s when idle so we can confirm the poller is alive
            'if(dl==null&&w.__lexiBetweenTicks%20===0){'
              'console.log("[lexi between] poller heartbeat (no deadline set)");'
            '}'
            'if(dl==null)return;'
            'if(Date.now()<dl)return;'
            'w.__lexiBetweenDeadline=null;'
            'w.__lexiBetweenLastDl=null;'
            'var btn=null;'
            'var bts=w.document.querySelectorAll("button");'
            'bts.forEach(function(b){'
              'if(b.textContent&&b.textContent.indexOf("__lexi_between_tick__")>=0)btn=b;'
            '});'
            'if(btn){console.log("[lexi between] poll fire: clicking tick button");btn.click();}'
            'else{console.warn("[lexi between] poll fire: tick button not in DOM (phase changed?)");}'
          '},250);'
          'console.log("[lexi between] poller installed on",w===window.top?"top":"parent");'
        '}'
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
    n = next(_play_nonce)
    _inject_parent_js(_target_js(
        f'try{{if(w.lexi&&w.lexi.play)w.lexi.play("{name}");}}catch(e){{console.warn("[lexi sound] play({name!r}) failed:",e);}}/*n{n}*/'
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
    """Sync SFX mute state from session_state to the JS engine."""
    val = "true" if muted else "false"
    _inject_parent_js(_target_js(
        f'try{{if(w.lexi)w.lexi.muted={val};}}catch(e){{}}'
    ))


def set_music_muted(st, muted: bool):
    """Sync music mute state. Smoothly ramps the current bg gain to/from 0
    so toggling doesn't click."""
    val = "true" if muted else "false"
    _inject_parent_js(_target_js(
        f'try{{if(w.lexi&&w.lexi.setBgMuted)w.lexi.setBgMuted({val});}}catch(e){{}}'
    ))


def set_bg(st, name: str, fade_ms: int = BG_DEFAULT_FADE_MS):
    """Declarative: ensure `name` is the playing background track.

    No-op if the engine is already playing it (so calling on every rerun
    is fine). Crossfades over `fade_ms` when switching. If the
    AudioContext hasn't been unlocked yet by a user gesture, the request
    is queued in the JS engine and starts on first gesture.
    """
    if st.session_state.get("_current_bg") == name:
        return
    st.session_state._current_bg = name
    # Nonce comment so revisiting a previously-used track (e.g.
    # bg_afterbb → bg_main → bg_afterbb → bg_main) produces a *new* JS
    # string each time. Streamlit dedupes components.html iframes by
    # exact content at the same render position, so without this the
    # second crossfade silently never fires. Same pattern as play().
    n = next(_play_nonce)
    _inject_parent_js(_target_js(
        f'try{{if(w.lexi&&w.lexi.setBg)w.lexi.setBg("{name}",{fade_ms});}}catch(e){{}}/*bg{n}*/'
    ))


def stop_bg(st, fade_ms: int = BG_DEFAULT_FADE_MS):
    """Fade out and stop the current background track."""
    if st.session_state.get("_current_bg") is None:
        return
    st.session_state._current_bg = None
    n = next(_play_nonce)
    _inject_parent_js(_target_js(
        f'try{{if(w.lexi&&w.lexi.stopBg)w.lexi.stopBg({fade_ms});}}catch(e){{}}/*bg{n}*/'
    ))
