"""Standalone preview of the Lexi-Chat UI components.

Renders every component in isolation so we can verify the look before
wiring anything to the real game state. Not the real app — that's
streamlit_app.py (built in Phase 4 step 3+).

Run with:
    streamlit run scripts/ui_preview.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `from ui...` and `from game...` from this script
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from ui import theme
from ui.components import (
    clue_card, host_bubble, player_bubble, tile_board, topbar, wordmark,
)

st.set_page_config(page_title="Lexi-Chat UI Preview", page_icon="🎙️", layout="centered")
theme.inject(st)

# === Wordmark ===
st.markdown("### Wordmark")
wordmark(st, with_tagline=True, level="h1")
st.markdown("---")

# === Top bar — three states ===
st.markdown("### Top bar")
st.caption("Default state (timer healthy, hint phase)")
topbar(st, score=2400, round_num=4, total_rounds=14, seconds_remaining=192, in_answer_mode=False)

st.caption("Timer warning (under 30s, hint phase)")
topbar(st, score=5800, round_num=11, total_rounds=14, seconds_remaining=18, in_answer_mode=False)

st.caption("Answer mode (45s round timer)")
topbar(st, score=5800, round_num=11, total_rounds=14, seconds_remaining=32, in_answer_mode=True)
st.markdown("---")

# === Letter tiles ===
st.markdown("### Letter tiles")
st.caption("All blank (length 5)")
tile_board(st, 5)

st.caption('Mixed: "uzay" with first and third revealed')
tile_board(st, "uzay", ["U", "_  ", "A", "_  "])

st.caption('All revealed: "naftalin"')
tile_board(st, "naftalin", list("naftalin"))
st.markdown("---")

# === Clue ===
st.markdown("### Clue card")
clue_card(st, "Bütün gök cisimlerinin içinde bulunduğu sonsuz boşluk")
st.markdown("---")

# === Chat bubbles (custom) ===
st.markdown("### Chat bubbles (custom HTML)")
host_bubble(st, "Merhaba efendim, hoşgeldiniz! Nasılsınız bugün?")
player_bubble(st, "İyiyim, teşekkürler. Siz nasılsınız?")
host_bubble(st, "Ben de gayet iyiyim efendim, sizinle sohbet etmekten mutluluk duyuyorum.")
player_bubble(st, "hazırım")
host_bubble(st, "Öyleyse başlayabiliriz... Şöyle derin bir nefes alın...")
st.markdown("---")

# === Native Streamlit chat widgets (for comparison) ===
st.markdown("### Native st.chat_message (for in-game running chat)")
with st.chat_message("assistant"):
    st.write("Bu bir host mesajı — Streamlit'in yerleşik widget'ı.")
with st.chat_message("user"):
    st.write("Bu da bir oyuncu mesajı.")
st.markdown("---")

# === Buttons ===
st.markdown("### Buttons")
col1, col2 = st.columns(2)
with col1:
    st.button("Yeni oyun", type="primary", use_container_width=True)
with col2:
    st.button("Önceki skorlar", type="secondary", use_container_width=True)
st.markdown("---")

# === Inputs ===
st.markdown("### Inputs")
st.text_input("İsminiz", placeholder="Nurullah")
st.text_input("Gemini API anahtarı", type="password", placeholder="AIzaSy...")
st.selectbox("Zorluk", ["Normal (varsayılan)", "Kolay", "Zor", "Uzman"], disabled=True,
             help="Phase 2'de açılacak")

st.markdown("---")
st.caption("Bu sayfa yalnızca bileşen önizlemesidir, gerçek oyun değildir.")
