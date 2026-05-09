"""Lexi-Chat — Streamlit web app entry point.

Single-page reactive layout: `st.session_state.phase` drives which screen
renders. Game logic comes from `game/`; UI components from `ui/`.

Run with:
    streamlit run streamlit_app.py
    # or, on Windows if `streamlit` isn't on PATH:
    python -m streamlit run streamlit_app.py
"""
from __future__ import annotations

import time

import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

from game import host
from game.config import APP_NAME, APP_TAGLINE, TOTAL_GAME_TIME, TOTAL_ROUNDS
from game.session import build_new_game, load_static_resources
from game.state import GameState
from llm_client import (
    DeepseekClient, GeminiClient, HuggingFaceClient, LLMError, OpenRouterClient,
)
from ui import theme
from ui.arena import render_arena, render_answering, render_between, render_prologue
from ui.components import host_bubble, release_chat_input_focus, wordmark
from ui.end import render_end
from ui.history import render_history
from ui import sound


# --------------------------------------------------------------------------
# Page setup — must be the very first Streamlit call
# --------------------------------------------------------------------------

st.set_page_config(
    page_title=f"{APP_NAME} — {APP_TAGLINE}",
    page_icon="🎙️",
    layout="centered",
    initial_sidebar_state="expanded",
)

theme.inject(st)


# --------------------------------------------------------------------------
# Session state initialization
# --------------------------------------------------------------------------

DEFAULTS = {
    "phase": "home",          # home / loading / prologue / playing / answering / between / end / history
    "player_name": "",
    "player_address": "bey",  # hanım / bey
    "api_key": "",            # legacy single-key field (migrated into provider_keys["gemini"])
    "provider": "demo",       # demo / gemini / deepseek / huggingface / openrouter
    "provider_keys": {        # per-provider key storage so swapping providers doesn't lose keys
        "gemini": "",
        "deepseek": "",
        "huggingface": "",
        "openrouter": "",
    },
    "difficulty": "normal",
    "sound_enabled": True,    # mute toggle in the sidebar
    "game_state": None,       # GameState instance once a game starts
    "llm": None,
    "word_list": None,
    "definition_list": None,
    "additional_defs": None,
    "synonym_list": None,
    "function_list": None,
    "compound_list": None,
    "origin_list": None,
    "structure_list": None,
    "example_sentences": None,
    "corpus": None,           # (cleaned_tokens, sorted_keywords)
    "chat_log": [],
    "round_idx": 0,
    "round_ctx": None,
    "chance_list": None,
    "list_active_input": [],
    "last_input_at": None,
    "silence_threshold": None,
    "last_tick_at": None,
    "revealed_info": {},
    "answer_deadline": None,  # wall-clock when bb 45-s timer expires
    "answer_started_at": None,  # wall-clock when current bb session started
    "_next_reveal_at": None,  # cursor for staggered chat reveal (see _say)
    "score_pop": None,  # transient score-animation payload
    # Prologue (pre-round small talk). messages = LLM chat history;
    # the chat_log is what the player SEES (UI), messages is what we
    # send back to the LLM each turn.
    "prologue_messages": None,
    # Between-rounds transition state. Set when a round ends; cleared
    # when the next round starts. See ui/arena._advance_to_next_round.
    "between_state": None,
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)

# One-shot migration: if a legacy single api_key was set in an earlier
# session and provider_keys is still empty, copy it into the gemini slot.
_legacy_api_key = st.session_state.get("api_key", "")
if _legacy_api_key and not st.session_state.provider_keys.get("gemini"):
    st.session_state.provider_keys["gemini"] = _legacy_api_key
    st.session_state.api_key = ""


# --------------------------------------------------------------------------
# Sidebar — always visible
# --------------------------------------------------------------------------


PROVIDER_TABLE = [
    # (key, label, key_label, placeholder, signup_url, free_caption)
    ("demo",        "Demo modu (yapay zekâsız)",      None, None, None,
     "Demo modunda sunucu yalnızca hazır cümleler kullanır."),
    ("gemini",      "Google Gemini",                  "Gemini API anahtarı", "AIzaSy...",
     "https://aistudio.google.com/apikey",
     "Ücretsiz katmanda günde geniş kotalı kullanım."),
    ("deepseek",    "Deepseek (yeni / hızlı)",        "Deepseek API anahtarı", "sk-...",
     "https://platform.deepseek.com/api_keys",
     "Yeni hesaplara 5 milyon token hediye (~285 oyun)."),
    ("huggingface", "Hugging Face (açık kaynak)",     "Hugging Face token", "hf_...",
     "https://huggingface.co/settings/tokens",
     "Aylık ücretsiz krediyle açık kaynak modeller."),
    ("openrouter",  "OpenRouter (ücretsiz modeller)", "OpenRouter API anahtarı", "sk-or-...",
     "https://openrouter.ai/keys",
     "Süresiz ücretsiz modeller — günde ~50 istek limitli."),
]


def render_sidebar():
    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.caption(APP_TAGLINE)
        st.markdown("---")

        st.markdown("**Yapay zekâ sağlayıcısı**")

        provider_keys_order = [row[0] for row in PROVIDER_TABLE]
        provider_labels = [row[1] for row in PROVIDER_TABLE]
        current = st.session_state.provider if st.session_state.provider in provider_keys_order else "demo"
        chosen_label = st.selectbox(
            "Sağlayıcı",
            options=provider_labels,
            index=provider_keys_order.index(current),
            label_visibility="collapsed",
        )
        st.session_state.provider = provider_keys_order[provider_labels.index(chosen_label)]

        # Per-provider key input + free-tier caption
        for key, _label, key_label, placeholder, signup_url, caption in PROVIDER_TABLE:
            if key != st.session_state.provider:
                continue
            if key_label is None:
                # demo — no key, just the caption
                st.caption(caption)
                break
            current_key = st.session_state.provider_keys.get(key, "")
            new_val = st.text_input(
                key_label,
                value=current_key,
                type="password",
                placeholder=placeholder,
                help=f"Ücretsiz anahtar: {signup_url}" if signup_url else None,
                key=f"provider_key_input_{key}",
            )
            st.session_state.provider_keys[key] = new_val
            if not new_val:
                st.caption(f"🔑 {caption}")
            else:
                st.caption(caption)
            break

        st.markdown("---")

        st.markdown("**Zorluk**")
        st.selectbox(
            "Zorluk",
            options=["Normal"],
            disabled=True,
            label_visibility="collapsed",
            help="Diğer zorluk seviyeleri yakında (Phase 2'de açılacak).",
        )

        st.markdown("---")

        sound_on = st.toggle(
            "🔊 Sesler",
            value=st.session_state.sound_enabled,
            help="Tile, doğru/yanlış cevap, oyun sonu sesleri.",
        )
        st.session_state.sound_enabled = sound_on
        sound.set_muted(st, not sound_on)

        st.markdown("---")

        if st.session_state.phase != "history":
            if st.button("📊 Önceki skorlar", use_container_width=True, type="secondary"):
                st.session_state.phase = "history"
                st.rerun()
        if st.session_state.phase != "home":
            if st.button("🏠 Ana sayfa", use_container_width=True, type="secondary"):
                st.session_state.phase = "home"
                st.rerun()


# --------------------------------------------------------------------------
# Home screen
# --------------------------------------------------------------------------


def render_home():
    release_chat_input_focus(st)
    wordmark(st, with_tagline=True, level="h1")
    st.write("")
    st.write("")

    host_bubble(
        st,
        "Hoşgeldiniz efendim. Bugün biraz Türkçe ile haşır neşir olalım, "
        "size 14 kelime sorum var. Hazırsanız başlayalım."
    )

    st.write("")

    col1, col2 = st.columns([3, 1])
    with col1:
        name = st.text_input(
            "İsminiz",
            value=st.session_state.player_name,
            placeholder="İsim",
            help="Skorlarınızı bu isim altında saklayacağız.",
        )
    with col2:
        address = st.selectbox(
            "Hitap",
            options=["bey", "hanım"],
            index=0 if st.session_state.player_address == "bey" else 1,
        )

    st.session_state.player_name = name.strip()
    st.session_state.player_address = address

    with st.expander("📜 Oyun kuralları"):
        st.markdown(
            f"""
- 5 dakika içinde **{TOTAL_ROUNDS} kelime** soracağım, 4 harfliden 10 harfliye.
- Her harf **100 puan** değerinde, en fazla 9800 puan kazanabilirsiniz.
- **`h`** yazarak harf isteyebilirsiniz. Açılan her harf için kelimenin değeri 100 puan azalır.
- Kelimenin tahmini olduğunda **`bb`** yazıp süreyi durdurun. **45 saniyeniz** olacak yanıt için.
- **`ipucu`** ya da "yardım" diyerek ek ipuçları isteyebilirsiniz.
- Sıradaki soruya geçmek için **`d`**, anlık skorunuzu görmek için **`puan`** yazın.
- Yanıt fazında harf isteyemezsiniz — sadece ipucu.
"""
        )

    st.write("")

    can_start = bool(st.session_state.player_name)
    provider = st.session_state.provider
    needs_key = (
        provider != "demo"
        and not (st.session_state.provider_keys.get(provider) or "").strip()
    )
    if needs_key:
        can_start = False

    button_label = "🎙️ Yeni oyun" if can_start else "🎙️ Yeni oyun"
    if st.button(button_label, type="primary", use_container_width=True, disabled=not can_start):
        st.session_state.phase = "loading"
        st.rerun()

    if not st.session_state.player_name:
        st.caption("✏️ Başlamak için isminizi yazın.")
    elif needs_key:
        st.caption("🔑 Başlamak için API anahtarınızı sol kenara yapıştırın "
                   "ya da Demo moduna geçin.")


# --------------------------------------------------------------------------
# Loading screen — placeholder until step 4 wires the game engine
# --------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _cached_static_resources():
    """Load Zemberek + WordNet + gts.json + corpus once per server lifetime."""
    return load_static_resources()


_PROVIDER_CLIENT_CLASSES = {
    "gemini": GeminiClient,
    "deepseek": DeepseekClient,
    "huggingface": HuggingFaceClient,
    "openrouter": OpenRouterClient,
}


def _make_llm():
    provider = st.session_state.provider
    if provider == "demo":
        return None
    api_key = (st.session_state.provider_keys.get(provider) or "").strip()
    if not api_key:
        return None  # Falls back to scripted-only
    cls = _PROVIDER_CLIENT_CLASSES.get(provider)
    if cls is None:
        return None
    try:
        return cls(api_key=api_key)
    except LLMError as e:
        st.error(f"{provider} bağlantı hatası: {e}")
        return None


def _lights_html(active_step: int, label: str, total_steps: int = 3) -> str:
    """Render the three "tuning lights" — past steps glow, current pulses,
    future stay dim. active_step in [0..total_steps]; total_steps means
    all three lit, no pulser.
    """
    pieces = []
    for i in range(total_steps):
        if i < active_step:
            cls = "lexi-light on"
        elif i == active_step:
            cls = "lexi-light active"
        else:
            cls = "lexi-light"
        pieces.append(f'<div class="{cls}"></div>')
    return (
        f'<div class="lexi-loading">'
        f'<div class="lexi-lights">{"".join(pieces)}</div>'
        f'<div class="lexi-loading-step">{label}</div>'
        f'</div>'
    )


# Loading-screen flavor lines — host warm-up patter, one per step.
# Lora-italic in the host bubble. Cycled (not random) so the player
# gets a sense of progression rather than chaos.
_WARMUP_LINES = [
    "Hazırlanıyorum efendim, biraz bekleyin lütfen...",
    "Sözlüğü açıyorum, kelimeleri seçiyorum...",
    "Mikrofon kontrol — bir, iki, bir, iki...",
    "Sahnemiz hazır olmak üzere efendim, son rötuşlar...",
]


def render_loading():
    wordmark(st, level="h2")
    st.write("")
    host_slot = st.empty()
    host_slot.markdown(
        f'<div class="lexi-host-bubble">{_WARMUP_LINES[0]}</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    status = st.empty()
    status.markdown(
        _lights_html(0, "Sözlük ve dil araçları yükleniyor..."),
        unsafe_allow_html=True,
    )
    try:
        resources = _cached_static_resources()
    except Exception as e:
        st.error(f"Kaynaklar yüklenirken hata: {e}")
        if st.button("← Ana sayfaya dön", type="secondary"):
            st.session_state.phase = "home"
            st.rerun()
        return
    host_slot.markdown(
        f'<div class="lexi-host-bubble">{_WARMUP_LINES[1]}</div>',
        unsafe_allow_html=True,
    )
    status.markdown(
        _lights_html(1, "Yapay zekâ bağlanıyor..."),
        unsafe_allow_html=True,
    )

    llm = _make_llm()
    host_slot.markdown(
        f'<div class="lexi-host-bubble">{_WARMUP_LINES[2]}</div>',
        unsafe_allow_html=True,
    )
    status.markdown(
        _lights_html(2, "14 kelime seçiliyor..."),
        unsafe_allow_html=True,
    )

    try:
        payload = build_new_game(resources, llm)
    except Exception as e:
        st.error(f"Oyun hazırlanırken hata: {e}")
        if st.button("← Ana sayfaya dön", type="secondary"):
            st.session_state.phase = "home"
            st.rerun()
        return
    host_slot.markdown(
        f'<div class="lexi-host-bubble">{_WARMUP_LINES[3]}</div>',
        unsafe_allow_html=True,
    )
    status.markdown(_lights_html(3, "Hazır!"), unsafe_allow_html=True)

    # Seed all session state for the game
    full_username = f"{st.session_state.player_name} {st.session_state.player_address}"
    st.session_state.game_state = GameState(username=full_username)
    st.session_state.llm = llm
    st.session_state.word_list = payload["word_list"]
    st.session_state.definition_list = payload["definition_list"]
    st.session_state.additional_defs = payload["additional_defs"]
    st.session_state.synonym_list = payload["synonym_list"]
    st.session_state.function_list = payload["function_list"]
    st.session_state.compound_list = payload["compound_list"]
    st.session_state.origin_list = payload["origin_list"]
    st.session_state.structure_list = payload["structure_list"]
    st.session_state.example_sentences = payload["example_sentences"]
    st.session_state.corpus = resources["corpus"]
    st.session_state.gts_index = resources["gts_index"]
    st.session_state.wordnet = resources["wordnet"]
    st.session_state.chat_log = []
    st.session_state._next_reveal_at = None
    # Stable per-game key — drives JS state resets (score odometer, etc.)
    # across game boundaries so we don't tween 4200 → 0 between games.
    st.session_state.game_key = f"g{int(time.time() * 1000)}"
    # Clear any leftover end-of-game flags from a previous run so this
    # game's end-screen will save its row + fire celebration sounds.
    st.session_state.score_saved_id = None
    st.session_state.end_sounds_fired = False
    st.session_state.history_clear_confirm = False
    st.session_state._pending_sounds = []

    # Open the prologue: greeting + LLM (or scripted) opener.
    from ui.arena import _say
    _say(
        st,
        "assistant",
        f"Merhaba {full_username}, {APP_NAME}'e hoşgeldiniz!",
    )
    # Seed the LLM chat history with the player's implicit "Merhaba"
    # so the first prologue_reply has something to react to.
    prologue_messages = [{"role": "user", "content": "Merhaba"}]
    try:
        opener = host.prologue_reply(llm, prologue_messages)
    except Exception:
        opener = "Çok sevindim efendim, bugün biraz Türkçe ile haşır neşir olalım."
    _say(st, "assistant", opener)
    prologue_messages.append({"role": "assistant", "content": opener})
    _say(
        st, "system",
        "Hazır olduğunuzda 'hazırım' yazın — oyun otomatik başlayacak.",
    )
    st.session_state.prologue_messages = prologue_messages

    st.session_state.phase = "prologue"
    st.rerun()


# --------------------------------------------------------------------------
# Phase router
# --------------------------------------------------------------------------


PHASE_RENDERERS = {
    "home": render_home,
    "loading": render_loading,
    "prologue": lambda: render_prologue(st),
    "playing": lambda: render_arena(st),
    "answering": lambda: render_answering(st),
    "between": lambda: render_between(st),
    "end": lambda: render_end(st),
    "history": lambda: render_history(st),
}


def main():
    render_sidebar()

    # Autorefresh is enabled ONLY during the answering phase (3 s) so the
    # 45-s server deadline fires even if the player goes idle. Playing
    # phase has NO autorefresh — the previous "chat reveal" autorefresh
    # at 700 ms raced st.chat_input submissions and made the game feel
    # broken ("can type but can't send"). Staggered chat reveals are
    # instead handled by reveal-on-next-rerun, which is good enough
    # since the player is naturally interacting; pure-idle reveal can
    # come back later if we drive it from JS instead of autorefresh.
    if st_autorefresh is not None:
        phase = st.session_state.phase
        if phase == "answering":
            # 3 s avoids racing st.chat_input submissions while still
            # firing the 45-s server timeout.
            st_autorefresh(interval=3000, key="answer_phase_tick")
        elif phase == "between":
            # Auto-advance + idle-nudge timing both need ticks. We use
            # 1.5 s here as a compromise: tight enough that the 2-4 s
            # auto-advance feels prompt, loose enough that an in-flight
            # st.chat_input submission (e.g. user typing 'devam') isn't
            # raced and dropped. Submissions are processed BEFORE the
            # auto-advance check in render_between, so even if the
            # deadline has passed by the time we paint, a typed 'devam'
            # wins and we continue cleanly into the next round.
            st_autorefresh(interval=1500, key="between_phase_tick")

    renderer = PHASE_RENDERERS.get(st.session_state.phase, render_home)
    renderer()


if __name__ == "__main__":
    main()
