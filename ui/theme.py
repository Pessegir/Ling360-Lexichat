"""Visual theme: color tokens, fonts, and a Streamlit CSS injector.

Design language: warm TV-studio aesthetic, NOT sci-fi. Deep navy backdrop,
amber spotlight accent, ivory text, diamond letter tiles. Designed by
Nurullah to "overcome machine bias" — the host is a Turkish TV personality,
not a hacker terminal.
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# Color tokens (single source of truth — change here, propagates everywhere)
# --------------------------------------------------------------------------

BG = "#0F1419"              # deep navy-charcoal — the studio backdrop
SURFACE = "#1A2030"         # panels, cards
SURFACE_HIGH = "#252D40"    # raised elements (focused inputs, hover)
SURFACE_DIM = "#0B0F18"     # below-base layer (sidebar, gutter)

ACCENT = "#F5C76A"          # warm amber — stage spotlight (NOT neon)
ACCENT_DIM = "#A88747"      # muted amber for borders/inactive states
SUCCESS = "#D4A04C"         # muted gold — correct answer
WARNING = "#C97D6A"         # dusty rose — timer low (NOT red)

TEAL = "#5A8B8C"            # secondary accent for chat outline

TEXT = "#EDE8DD"            # ivory — primary text
TEXT_DIM = "#A29D92"        # muted ivory — secondary text
TEXT_FAINT = "#6B6760"      # very muted — placeholders, disabled

BORDER = "#2A3245"          # subtle divider
BORDER_BRIGHT = "#3D475F"   # focused divider

# Fonts (loaded from Google Fonts in the CSS below)
FONT_HEADING = "'Space Grotesk', system-ui, sans-serif"
FONT_BODY = "'Inter', system-ui, sans-serif"
FONT_HOST = "'Lora', Georgia, serif"  # italic — host's "voice"


# --------------------------------------------------------------------------
# Streamlit CSS injection
#
# The strategy: hide Streamlit's default chrome (header, footer, hamburger),
# repaint the app shell, and override the default chat/input/button styles
# to match our palette. Custom HTML components (in ui/components.py) handle
# the bespoke pieces (letter tiles, wordmark).
# --------------------------------------------------------------------------


def stylesheet() -> str:
    return f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=Lora:ital,wght@0,400;0,500;1,400;1,500&display=swap">

<style>
/* === App shell === */
.stApp {{
    background:
        radial-gradient(ellipse 80% 50% at 50% 0%, rgba(245, 199, 106, 0.06) 0%, transparent 60%),
        {BG};
    color: {TEXT};
    font-family: {FONT_BODY};
}}

/* Hide Streamlit's default chrome */
#MainMenu, footer, header[data-testid="stHeader"] {{
    visibility: hidden;
    height: 0;
}}

/* Tighter top padding now that the header is hidden */
.main .block-container {{
    padding-top: 2rem;
    max-width: 920px;
}}

/* === Typography === */
h1, h2, h3, h4, h5 {{
    font-family: {FONT_HEADING};
    color: {TEXT};
    letter-spacing: -0.01em;
}}

p, li, label, .stMarkdown {{
    color: {TEXT};
    font-family: {FONT_BODY};
}}

/* === Sidebar === */
section[data-testid="stSidebar"] > div {{
    background: {SURFACE_DIM};
    border-right: 1px solid {BORDER};
}}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {{
    color: {ACCENT};
}}

/* === Buttons === */
.stButton > button {{
    background: {ACCENT};
    color: {BG};
    font-family: {FONT_HEADING};
    font-weight: 600;
    border: none;
    border-radius: 4px;
    padding: 0.6rem 1.4rem;
    transition: transform 0.1s ease, box-shadow 0.2s ease;
}}

.stButton > button:hover {{
    background: #FFD27A;
    box-shadow: 0 0 24px rgba(245, 199, 106, 0.35);
    transform: translateY(-1px);
}}

.stButton > button:active {{
    transform: translateY(0);
}}

/* Secondary button variant via key="ghost-..." (kind="secondary" works too) */
.stButton > button[kind="secondary"] {{
    background: transparent;
    color: {TEXT};
    border: 1px solid {BORDER_BRIGHT};
}}

.stButton > button[kind="secondary"]:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
    box-shadow: none;
}}

/* === Inputs === */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    font-family: {FONT_BODY};
}}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {{
    border-color: {ACCENT};
    box-shadow: 0 0 0 1px {ACCENT};
}}

.stTextInput > label,
.stTextArea > label {{
    color: {TEXT_DIM};
    font-family: {FONT_HEADING};
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}

/* === Chat input (st.chat_input) === */
[data-testid="stChatInput"] {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
}}

[data-testid="stChatInput"] textarea {{
    background: {SURFACE_HIGH};
    color: {TEXT};
    border: 1px solid {BORDER};
}}

[data-testid="stChatInput"] textarea:focus {{
    border-color: {ACCENT};
}}

/* === Chat messages (st.chat_message) === */
[data-testid="stChatMessage"] {{
    background: transparent;
    padding: 0.5rem 0;
}}

/* Host bubble (assistant) */
[data-testid="stChatMessage"][data-testid-stchatmessageavatarcustom="assistant"],
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {{
    /* targeting variations across Streamlit versions */
}}

/* === Selectbox === */
.stSelectbox > div > div {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    color: {TEXT};
}}

.stSelectbox label {{
    color: {TEXT_DIM};
    font-family: {FONT_HEADING};
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}

/* === Dividers === */
hr {{
    border-color: {BORDER};
    opacity: 0.6;
}}

/* === Custom utility classes used by ui/components.py === */
.lexi-wordmark {{
    font-family: {FONT_HEADING};
    font-weight: 700;
    font-size: 2rem;
    letter-spacing: -0.02em;
    color: {TEXT};
}}

.lexi-wordmark .accent {{
    color: {ACCENT};
}}

.lexi-tagline {{
    font-family: {FONT_HOST};
    font-style: italic;
    color: {TEXT_DIM};
    font-size: 1rem;
    margin-top: 0.4rem;
}}

.lexi-clue {{
    background: {SURFACE};
    border-left: 3px solid {ACCENT};
    padding: 1rem 1.2rem;
    border-radius: 4px;
    color: {TEXT};
    font-size: 1.05rem;
    line-height: 1.55;
}}

.lexi-clue-label {{
    font-family: {FONT_HEADING};
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: {ACCENT};
    margin-bottom: 0.3rem;
    display: block;
}}

/* Letter tile board */
.lexi-tiles {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 12px;
    padding: 1.5rem 0;
    position: relative;
}}

/* Subtle warm vignette behind tiles — the "stage spotlight" */
.lexi-tiles::before {{
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 120%;
    height: 240%;
    transform: translate(-50%, -50%);
    background: radial-gradient(ellipse, rgba(245, 199, 106, 0.08) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
}}

.lexi-tile {{
    width: 56px;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: center;
    transform: rotate(45deg);
    border: 1.5px solid {BORDER_BRIGHT};
    background: {SURFACE};
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
    position: relative;
    z-index: 1;
}}

.lexi-tile.revealed {{
    border-color: {ACCENT};
    box-shadow: 0 0 16px rgba(245, 199, 106, 0.25);
}}

.lexi-tile span {{
    transform: rotate(-45deg);
    font-family: {FONT_HEADING};
    font-weight: 600;
    font-size: 1.4rem;
    color: {TEXT};
    text-transform: uppercase;
}}

.lexi-tile.revealed span {{
    color: {ACCENT};
}}

/* Top-bar chips — score / round / timer */
.lexi-topbar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.8rem 1rem;
    background: {SURFACE};
    border-radius: 4px;
    margin-bottom: 1rem;
    border: 1px solid {BORDER};
}}

.lexi-chip {{
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    line-height: 1.1;
}}

.lexi-chip-label {{
    font-family: {FONT_HEADING};
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: {TEXT_DIM};
}}

.lexi-chip-value {{
    font-family: {FONT_HEADING};
    font-weight: 600;
    font-size: 1.3rem;
    color: {TEXT};
    margin-top: 0.15rem;
}}

.lexi-chip-value.timer-warn {{
    color: {WARNING};
}}

.lexi-chip-value.timer-active {{
    color: {ACCENT};
}}

/* Host bubble (custom rendering — used when we don't go via st.chat_message) */
.lexi-host-bubble {{
    background: {SURFACE};
    border-left: 3px solid {TEAL};
    padding: 0.85rem 1.1rem;
    border-radius: 4px;
    margin: 0.5rem 0;
    color: {TEXT};
    font-family: {FONT_HOST};
    font-style: italic;
    line-height: 1.55;
    max-width: 85%;
}}

.lexi-player-bubble {{
    background: transparent;
    border: 1px solid {BORDER};
    padding: 0.7rem 1rem;
    border-radius: 4px;
    margin: 0.5rem 0 0.5rem auto;
    color: {TEXT};
    line-height: 1.5;
    max-width: 75%;
    text-align: right;
}}
</style>
"""


def inject(st):
    """Call once at the top of every Streamlit page to apply the theme."""
    st.markdown(stylesheet(), unsafe_allow_html=True)
