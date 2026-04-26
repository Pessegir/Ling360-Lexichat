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

from game.config import APP_NAME, APP_TAGLINE, TOTAL_GAME_TIME, TOTAL_ROUNDS
from ui import theme
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
    "phase": "home",          # home / loading / playing / answering / between / end / history
    "player_name": "",
    "player_address": "bey",  # hanım / bey
    "api_key": "",
    "provider": "gemini",     # gemini / huggingface (later) / demo
    "difficulty": "normal",
    "game_state": None,       # GameState instance once a game starts
    "word_list": None,
    "definition_list": None,
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


def render_loading():
    wordmark(st, level="h2")
    st.write("")
    host_bubble(st, f"Hazırlanıyorum efendim, biraz bekleyin lütfen...")
    st.spinner("Kelimeler ve ipuçları yükleniyor...")
    st.info(
        "Bu ekran şu an bir yer tutucudur. Phase 4 step 4'te oyun motoru "
        "buraya bağlanacak ve gerçek arena ekranı gözükecek.",
        icon="🔧",
    )
    if st.button("← Ana sayfaya dön", type="secondary"):
        st.session_state.phase = "home"
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


PHASE_RENDERERS = {
    "home": render_home,
    "loading": render_loading,
    "history": render_history,
    # playing, answering, between, end → coming in steps 4 & 5
}


def main():
    render_sidebar()
    renderer = PHASE_RENDERERS.get(st.session_state.phase, render_home)
    renderer()


if __name__ == "__main__":
    main()
