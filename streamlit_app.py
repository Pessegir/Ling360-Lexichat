"""Lexi-Chat — Streamlit web app entry point.

Single-page reactive layout: `st.session_state.phase` drives which screen
renders. Game logic comes from `game/`; UI components from `ui/`.

Run with:
    streamlit run streamlit_app.py
    # or, on Windows if `streamlit` isn't on PATH:
    python -m streamlit run streamlit_app.py
"""
from __future__ import annotations

import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

from game.config import APP_NAME, APP_TAGLINE, TOTAL_GAME_TIME, TOTAL_ROUNDS
from game.round import end_game_lines
from game.session import build_new_game, load_static_resources
from game.state import GameState
from llm_client import LLMError, GeminiClient
from ui import theme
from ui.arena import render_arena, render_answering
from ui.components import host_bubble, wordmark


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
    "phase": "home",          # home / loading / playing / answering / end / history
    "player_name": "",
    "player_address": "bey",  # hanım / bey
    "api_key": "",
    "provider": "gemini",     # gemini / huggingface (later) / demo
    "difficulty": "normal",
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
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


# --------------------------------------------------------------------------
# Sidebar — always visible
# --------------------------------------------------------------------------


def render_sidebar():
    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.caption(APP_TAGLINE)
        st.markdown("---")

        st.markdown("**Yapay zekâ sağlayıcısı**")
        provider_label = st.selectbox(
            "Sağlayıcı",
            options=["Google Gemini", "Hugging Face (yakında)", "Demo modu (yapay zekâsız)"],
            index=0,
            label_visibility="collapsed",
        )
        if provider_label.startswith("Google Gemini"):
            st.session_state.provider = "gemini"
        elif provider_label.startswith("Hugging Face"):
            st.session_state.provider = "huggingface"
            st.info("Hugging Face desteği yakında eklenecek. Şimdilik Gemini ya da Demo modunu seçin.", icon="ℹ️")
        else:
            st.session_state.provider = "demo"

        if st.session_state.provider == "gemini":
            key_input = st.text_input(
                "Gemini API anahtarı",
                value=st.session_state.api_key,
                type="password",
                placeholder="AIzaSy...",
                help="Ücretsiz anahtar: https://aistudio.google.com/apikey",
            )
            st.session_state.api_key = key_input
            if not key_input:
                st.caption("🔑 Anahtarınız yalnızca bu tarayıcı oturumunda saklanır.")
        elif st.session_state.provider == "demo":
            st.caption("Demo modunda sunucu yalnızca hazır cümleler kullanır. Her saat 1 oyun.")

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
            placeholder="Nurullah",
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
    needs_key = st.session_state.provider == "gemini" and not st.session_state.api_key
    if needs_key:
        can_start = False

    button_label = "🎙️ Yeni oyun" if can_start else "🎙️ Yeni oyun"
    if st.button(button_label, type="primary", use_container_width=True, disabled=not can_start):
        st.session_state.phase = "loading"
        st.rerun()

    if not st.session_state.player_name:
        st.caption("✏️ Başlamak için isminizi yazın.")
    elif needs_key:
        st.caption("🔑 Başlamak için Gemini API anahtarınızı sol kenara yapıştırın "
                   "ya da Demo moduna geçin.")


# --------------------------------------------------------------------------
# Loading screen — placeholder until step 4 wires the game engine
# --------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _cached_static_resources():
    """Load Zemberek + WordNet + gts.json + corpus once per server lifetime."""
    return load_static_resources()


def _make_llm():
    if st.session_state.provider == "gemini" and st.session_state.api_key:
        try:
            return GeminiClient(api_key=st.session_state.api_key)
        except LLMError as e:
            st.error(f"Gemini bağlantı hatası: {e}")
            return None
    # Demo mode or no key → run scripted-only
    return None


def render_loading():
    wordmark(st, level="h2")
    st.write("")
    host_bubble(st, "Hazırlanıyorum efendim, biraz bekleyin lütfen...")
    st.write("")

    progress = st.progress(0, text="Sözlük ve dil araçları yükleniyor...")
    try:
        resources = _cached_static_resources()
    except Exception as e:
        st.error(f"Kaynaklar yüklenirken hata: {e}")
        if st.button("← Ana sayfaya dön", type="secondary"):
            st.session_state.phase = "home"
            st.rerun()
        return
    progress.progress(40, text="Yapay zekâ bağlanıyor...")

    llm = _make_llm()
    progress.progress(60, text="14 kelime seçiliyor...")

    try:
        payload = build_new_game(resources, llm)
    except Exception as e:
        st.error(f"Oyun hazırlanırken hata: {e}")
        if st.button("← Ana sayfaya dön", type="secondary"):
            st.session_state.phase = "home"
            st.rerun()
        return
    progress.progress(100, text="Hazır!")

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
    st.session_state.chat_log = []
    st.session_state._next_reveal_at = None

    # Initial host greeting (staggered via _say)
    from ui.arena import _say, _start_round
    _say(
        st,
        "assistant",
        f"Merhaba {full_username}, hoşgeldiniz! İlk soruyla başlıyoruz...",
    )

    # Initialize round 0 — done via arena helper
    _start_round(st, 0)

    st.session_state.phase = "playing"
    st.rerun()


# --------------------------------------------------------------------------
# History screen — placeholder until step 6
# --------------------------------------------------------------------------


def render_history():
    wordmark(st, level="h2")
    st.write("")
    st.markdown("### Önceki Oyunlar")
    st.info(
        "Skor geçmişi Phase 4 step 6'da bağlanacak. Şimdilik bu sayfa boş.",
        icon="🔧",
    )


# --------------------------------------------------------------------------
# Phase router
# --------------------------------------------------------------------------


def render_end_placeholder():
    wordmark(st, level="h2")
    st.write("")
    state = st.session_state.game_state
    if state:
        score = state.total_score
        ran_out = state.game_over
        host_bubble(st, end_game_lines(score, state.username, ran_out))
        st.markdown(f"### Toplam puan: **{score:,}**")
    st.info(
        "Tam bitiş ekranı (puan istatistikleri, 'tekrar oyna' butonu) "
        "Phase 4 step 5'te gelecek.",
        icon="🔧",
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🏠 Ana sayfa", type="primary", use_container_width=True):
            for k in list(st.session_state.keys()):
                if k not in ("api_key", "provider", "player_name", "player_address"):
                    del st.session_state[k]
            st.session_state.phase = "home"
            st.rerun()
    with col2:
        if st.button("📊 Skorlar", type="secondary", use_container_width=True):
            st.session_state.phase = "history"
            st.rerun()


PHASE_RENDERERS = {
    "home": render_home,
    "loading": render_loading,
    "playing": lambda: render_arena(st),
    "answering": lambda: render_answering(st),
    "end": render_end_placeholder,
    "history": render_history,
}


def main():
    render_sidebar()

    # Autorefresh policy:
    # - "answering" phase always autorefreshes (3 s) so the 45-s server
    #   deadline fires even if the player goes idle. The JS countdown in
    #   the timer pill ticks every second between reruns.
    # - "playing" phase autorefreshes (700 ms) ONLY when the chat queue
    #   has pending future-reveal messages — i.e. right after a hint or
    #   round transition, so each line appears one-by-one. Otherwise
    #   playing runs refresh-free to keep the page snappy.
    #
    # Interval choices: 3 s in answering avoids racing the user's
    # submission. 700 ms during chat reveal feels close to natural
    # speech pacing without being aggressive.
    phase = st.session_state.phase
    if st_autorefresh is not None:
        if phase == "answering":
            st_autorefresh(interval=3000, key="answer_phase_tick")
        elif phase == "playing":
            from ui.arena import _has_pending_chat
            if _has_pending_chat(st):
                st_autorefresh(interval=700, key="chat_reveal_tick")

    renderer = PHASE_RENDERERS.get(st.session_state.phase, render_home)
    renderer()


if __name__ == "__main__":
    main()
