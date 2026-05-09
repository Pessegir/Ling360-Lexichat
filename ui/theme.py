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
    background: {BG};
    color: {TEXT};
    font-family: {FONT_BODY};
    isolation: isolate;
}}

/* Stage spotlight — top-centered amber radial with a slow breath. */
.stApp::before {{
    content: '';
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: -1;
    background: radial-gradient(ellipse 80% 50% at 50% 0%,
        rgba(245, 199, 106, 0.12) 0%, transparent 60%);
    animation: lexi-stage-breath 8s ease-in-out infinite;
}}

/* Curtain falloff — faint amber/teal in the four corners, like a
   proscenium arch. Static. */
.stApp::after {{
    content: '';
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: -1;
    background:
        radial-gradient(circle at top left,     rgba(245, 199, 106, 0.05) 0%, transparent 28%),
        radial-gradient(circle at top right,    rgba(245, 199, 106, 0.05) 0%, transparent 28%),
        radial-gradient(circle at bottom left,  rgba(90, 139, 140, 0.04) 0%, transparent 32%),
        radial-gradient(circle at bottom right, rgba(90, 139, 140, 0.04) 0%, transparent 32%);
}}

@keyframes lexi-stage-breath {{
    0%, 100% {{ opacity: 0.65; }}
    50%      {{ opacity: 1.00; }}
}}

/* Kill EVERY way Streamlit fades the page during a rerun. The default
   running indicator dims the whole app via opacity transitions on
   stAppViewContainer + several wrapper divs. We force opacity:1 across
   the board and disable transitions globally during rerun states. */
.stApp,
.stApp > *,
.stApp [data-testid="stAppViewContainer"],
.stApp [data-testid="stAppViewContainer"] > *,
.stApp [data-testid="stMain"],
.stApp [data-testid="stMainBlockContainer"],
.stApp .main,
.stApp .main > * {{
    opacity: 1 !important;
}}

/* Some Streamlit versions add a class during reruns. Catch them all. */
.stApp[data-test-script-state="running"],
.stApp[data-test-script-state="rerunning"],
.stApp[data-test-script-state="running"] *,
.stApp[data-test-script-state="rerunning"] * {{
    opacity: 1 !important;
}}

/* Stop the fade-in/fade-out transition that creates the visible flicker */
.stApp [data-testid="stAppViewContainer"],
.stApp [data-testid="stMain"] {{
    transition: none !important;
}}

/* Hide the small "Running..." spinner in the corner during reruns */
[data-testid="stStatusWidget"],
[data-testid="stToolbar"] {{
    display: none !important;
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

/* === Chat input (st.chat_input) ===
   Streamlit applies a focus shadow that visually shifts the input height —
   we lock the size and use a glow instead of a border-shift on focus. */
[data-testid="stChatInput"] {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
}}

[data-testid="stChatInput"] textarea {{
    background: {SURFACE_HIGH};
    color: {TEXT};
    border: 1px solid {BORDER};
    box-sizing: border-box;
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
}}

[data-testid="stChatInput"] textarea:focus,
[data-testid="stChatInput"] textarea:focus-visible {{
    border-color: {ACCENT};
    outline: none !important;
    /* Soft inset glow instead of a layout-shifting outline */
    box-shadow: 0 0 0 1px {ACCENT}, 0 0 12px rgba(245, 199, 106, 0.15);
}}

/* Stop Streamlit's default focus outline from adding extra height */
[data-testid="stChatInput"] *:focus,
[data-testid="stChatInput"] *:focus-visible {{
    outline: none !important;
}}

/* Lock the wrapper height so the bar never jumps */
[data-testid="stChatInput"] > div {{
    border: none !important;
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

/* Subtle warm vignette behind tiles — the "stage spotlight" with a
   slow shimmer to keep the studio feeling alive. */
.lexi-tiles::before {{
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 120%;
    height: 240%;
    transform: translate(-50%, -50%);
    background: radial-gradient(ellipse, rgba(245, 199, 106, 0.10) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
    animation: lexi-spotlight-breath 6s ease-in-out infinite;
}}

@keyframes lexi-spotlight-breath {{
    0%, 100% {{
        opacity: 0.7;
        transform: translate(-50%, -50%) scale(0.95);
    }}
    50% {{
        opacity: 1.0;
        transform: translate(-50%, -50%) scale(1.05);
    }}
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
    transition: border-color 0.3s ease, box-shadow 0.3s ease, transform 0.2s ease;
    position: relative;
    z-index: 1;
}}

/* Desktop hover: subtle lift. Pointer-coarse devices don't get hover at all
   (they'd interpret tap as hover and stick). */
@media (hover: hover) and (pointer: fine) {{
    .lexi-tile:hover {{
        transform: rotate(45deg) translateY(-3px);
    }}
}}

.lexi-tile.revealed {{
    border-color: {ACCENT};
    box-shadow: 0 0 16px rgba(245, 199, 106, 0.25);
}}

/* Tile flip-on-reveal — JS adds .lexi-flip the moment a tile transitions
   from blank to revealed (per-board dedup in window.parent), so the
   animation never re-fires for already-revealed tiles on autorefresh. */
.lexi-tile.revealed.lexi-flip {{
    animation: lexi-tile-flip 540ms cubic-bezier(0.34, 1.56, 0.64, 1);
}}

@keyframes lexi-tile-flip {{
    0%   {{ transform: rotate(45deg) scale(0.6); box-shadow: 0 0 0 rgba(245, 199, 106, 0); }}
    55%  {{ transform: rotate(45deg) scale(1.18); box-shadow: 0 0 32px rgba(245, 199, 106, 0.75); }}
    100% {{ transform: rotate(45deg) scale(1.0);  box-shadow: 0 0 16px rgba(245, 199, 106, 0.25); }}
}}

.lexi-tile span {{
    transform: rotate(-45deg);
    font-family: {FONT_HEADING};
    font-weight: 600;
    font-size: 1.4rem;
    color: {TEXT};
    /* No text-transform: Turkish casing breaks (ı→I, ş→S) without locale rules. */
}}

.lexi-tile.revealed span {{
    color: {ACCENT};
}}

/* Info chips — revealed cues (word type, structure, origin) */
.lexi-info-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    margin: 0.5rem 0 1rem 0;
    min-height: 1.8rem;
}}

.lexi-info-chip {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    background: rgba(245, 199, 106, 0.08);
    border: 1px solid {ACCENT_DIM};
    border-radius: 14px;
    font-family: {FONT_BODY};
    font-size: 0.85rem;
    color: {TEXT};
}}

.lexi-info-chip-label {{
    font-family: {FONT_HEADING};
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: {ACCENT};
    font-weight: 600;
}}

.lexi-info-chip-value {{
    color: {TEXT};
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
    animation: lexi-timer-pulse 1.5s ease-in-out infinite;
}}

@keyframes lexi-timer-pulse {{
    0%, 100% {{ opacity: 1.0; }}
    50%      {{ opacity: 0.65; }}
}}

.lexi-chip-value.timer-active {{
    color: {ACCENT};
}}

/* Score-pop animation — floating +N or -N near the score chip */
.lexi-score-pop {{
    position: relative;
    display: inline-block;
    margin-left: 0.5rem;
    font-family: {FONT_HEADING};
    font-weight: 700;
    font-size: 1rem;
    animation: lexi-score-pop-anim 1.6s ease-out forwards;
    pointer-events: none;
}}

.lexi-score-pop.gain {{ color: {SUCCESS}; }}
.lexi-score-pop.loss {{ color: {WARNING}; }}

@keyframes lexi-score-pop-anim {{
    0%   {{ transform: translateY(0) scale(0.8); opacity: 0; }}
    20%  {{ transform: translateY(-4px) scale(1.15); opacity: 1; }}
    80%  {{ transform: translateY(-18px) scale(1); opacity: 1; }}
    100% {{ transform: translateY(-26px) scale(0.95); opacity: 0; }}
}}

/* Answer-phase timer pill (bb mode) */
.lexi-answer-timer {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.35rem;
    padding: 0.85rem 1.1rem;
    background: linear-gradient(180deg, {SURFACE} 0%, {SURFACE_HIGH} 100%);
    border: 1px solid {WARNING};
    border-radius: 6px;
    margin: 0.5rem 0 1rem 0;
    box-shadow: 0 0 0 1px {WARNING}33, 0 0 18px {WARNING}22;
}}

.lexi-answer-timer-label {{
    font-family: {FONT_HEADING};
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: {WARNING};
    font-weight: 600;
}}

.lexi-answer-timer-value {{
    font-family: {FONT_HEADING};
    font-size: 2.2rem;
    font-weight: 700;
    color: {WARNING};
    font-variant-numeric: tabular-nums;
    line-height: 1;
}}

.lexi-answer-timer-bar {{
    width: 100%;
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
    overflow: hidden;
}}

.lexi-answer-timer-fill {{
    height: 100%;
    background: {WARNING};
    transition: width 0.95s linear;
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

/* === End screen === */
.lexi-end-score-block {{
    text-align: center;
    margin: 1.5rem 0 2rem;
    padding: 1.5rem 1rem 1.75rem;
    background:
        radial-gradient(ellipse 70% 70% at 50% 50%, rgba(245, 199, 106, 0.08) 0%, transparent 75%),
        {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    position: relative;
}}

/* New-record celebration: two amber ribbons sweep across the score
   card once, top and bottom, slightly offset and skewed. Pure CSS,
   fires on first paint of `.is-record`. */
.lexi-end-score-block.is-record {{
    overflow: hidden;
}}

.lexi-end-score-block.is-record::before,
.lexi-end-score-block.is-record::after {{
    content: '';
    position: absolute;
    left: 0;
    width: 200%;
    height: 28px;
    pointer-events: none;
    background: linear-gradient(90deg,
        transparent 0%,
        rgba(245, 199, 106, 0.45) 35%,
        rgba(245, 199, 106, 0.85) 50%,
        rgba(245, 199, 106, 0.45) 65%,
        transparent 100%);
    opacity: 0;
}}

.lexi-end-score-block.is-record::before {{
    top: 18px;
    animation: lexi-record-ribbon-l 1.7s cubic-bezier(0.4, 0, 0.2, 1) 0.35s 1 forwards;
}}

.lexi-end-score-block.is-record::after {{
    bottom: 18px;
    animation: lexi-record-ribbon-r 1.7s cubic-bezier(0.4, 0, 0.2, 1) 0.6s 1 forwards;
}}

@keyframes lexi-record-ribbon-l {{
    0%   {{ opacity: 0; transform: translateX(-100%) skewY(-3deg); }}
    20%  {{ opacity: 1; }}
    80%  {{ opacity: 1; }}
    100% {{ opacity: 0; transform: translateX( 50%) skewY(-3deg); }}
}}

@keyframes lexi-record-ribbon-r {{
    0%   {{ opacity: 0; transform: translateX(-100%) skewY(3deg); }}
    20%  {{ opacity: 1; }}
    80%  {{ opacity: 1; }}
    100% {{ opacity: 0; transform: translateX( 50%) skewY(3deg); }}
}}

.lexi-end-score-label {{
    font-family: {FONT_BODY};
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.18em;
    color: {TEXT_DIM};
    text-transform: uppercase;
    margin-bottom: 0.4rem;
}}

.lexi-end-score-value {{
    font-family: {FONT_HEADING};
    font-size: 3.4rem;
    font-weight: 700;
    color: {ACCENT};
    line-height: 1;
    letter-spacing: -0.01em;
}}

.lexi-end-stats {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.6rem;
    margin: 0.5rem 0 1rem;
}}

.lexi-stat-card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 0.85rem 0.75rem;
    text-align: center;
}}

.lexi-stat-label {{
    font-family: {FONT_BODY};
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.14em;
    color: {TEXT_DIM};
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}}

.lexi-stat-value {{
    font-family: {FONT_HEADING};
    font-size: 1.4rem;
    font-weight: 600;
    color: {TEXT};
    line-height: 1.1;
}}

/* Personal-best line below the big score on the end screen */
.lexi-end-pb {{
    margin-top: 0.85rem;
    font-family: {FONT_HEADING};
    font-size: 0.85rem;
    letter-spacing: 0.06em;
    color: {TEXT_DIM};
}}

.lexi-end-pb strong {{
    color: {TEXT};
    font-weight: 600;
}}

.lexi-end-pb.new-record {{
    color: {ACCENT};
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    font-size: 0.95rem;
}}

/* === History list === */
.lexi-hist-row {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.5rem;
    transition: border-color 0.15s ease;
}}

.lexi-hist-row:hover {{
    border-color: {BORDER_BRIGHT};
}}

.lexi-hist-row-top {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.75rem;
    flex-wrap: wrap;
}}

.lexi-hist-date {{
    font-family: {FONT_HEADING};
    font-size: 0.85rem;
    color: {TEXT_DIM};
    letter-spacing: 0.04em;
}}

.lexi-hist-player {{
    font-family: {FONT_BODY};
    font-size: 0.8rem;
    color: {TEXT_DIM};
    flex-grow: 1;
    text-align: left;
}}

.lexi-hist-score {{
    font-family: {FONT_HEADING};
    font-size: 1.35rem;
    font-weight: 700;
    color: {ACCENT};
    line-height: 1;
    margin-left: auto;
}}

.lexi-hist-row-meta {{
    margin-top: 0.45rem;
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    color: {TEXT_DIM};
    font-size: 0.82rem;
    font-family: {FONT_BODY};
}}

/* === Stat-card icons (end screen + history) === */
.lexi-stat-label {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.35rem;
}}

.lexi-stat-label svg {{
    width: 12px;
    height: 12px;
    color: {ACCENT};
    flex-shrink: 0;
}}

/* === Round-indicator dots (replaces "3 / 14" text) === */
.lexi-round-dots {{
    display: flex;
    gap: 4px;
    margin-top: 0.35rem;
    flex-wrap: wrap;
    max-width: 240px;
    align-items: center;
}}

.lexi-round-dot {{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: {BORDER_BRIGHT};
    transition: background 0.3s ease, box-shadow 0.3s ease;
}}

.lexi-round-dot.done {{
    background: {ACCENT_DIM};
}}

.lexi-round-dot.active {{
    background: {ACCENT};
    box-shadow: 0 0 6px rgba(245, 199, 106, 0.55);
    width: 9px;
    height: 9px;
}}

/* === Wordmark microphone glyph (home screen) === */
.lexi-wordmark-row {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.85rem;
}}

.lexi-mic-glyph {{
    color: {ACCENT};
    width: 36px;
    height: 36px;
    flex-shrink: 0;
    filter: drop-shadow(0 0 8px rgba(245, 199, 106, 0.25));
}}

/* === Loading "tuning lights" === */
.lexi-loading {{
    text-align: center;
    padding: 1.25rem 0 0.5rem;
}}

.lexi-lights {{
    display: flex;
    gap: 16px;
    justify-content: center;
    margin-bottom: 0.9rem;
}}

.lexi-lights .lexi-light {{
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: {BORDER_BRIGHT};
    box-shadow: inset 0 0 4px rgba(0, 0, 0, 0.4);
    transition: background 0.3s ease, box-shadow 0.3s ease;
}}

.lexi-lights .lexi-light.on {{
    background: {ACCENT_DIM};
    box-shadow: 0 0 10px rgba(245, 199, 106, 0.4);
}}

.lexi-lights .lexi-light.active {{
    background: {ACCENT};
    box-shadow: 0 0 14px rgba(245, 199, 106, 0.7);
    animation: lexi-light-pulse 1.1s ease-in-out infinite;
}}

@keyframes lexi-light-pulse {{
    0%, 100% {{ transform: scale(1); }}
    50%      {{ transform: scale(1.25); }}
}}

.lexi-loading-step {{
    color: {TEXT_DIM};
    font-family: {FONT_HEADING};
    font-size: 0.78rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
}}

/* === Mobile breakpoint (≤ 480 px) === */
@media (max-width: 480px) {{
    .main .block-container {{
        padding-left: 0.75rem;
        padding-right: 0.75rem;
    }}

    .lexi-tile {{
        width: 42px;
        height: 42px;
    }}

    .lexi-tile span {{
        font-size: 1.1rem;
    }}

    .lexi-tiles {{
        gap: 6px;
        padding: 1rem 0;
    }}

    .lexi-topbar {{
        flex-wrap: wrap;
        gap: 0.6rem 1rem;
        padding: 0.7rem 0.85rem;
    }}

    .lexi-topbar .lexi-chip {{
        flex-basis: 45%;
    }}

    /* Round dots wrap two rows on mobile rather than overflow */
    .lexi-round-dots {{
        max-width: 160px;
    }}

    .lexi-end-stats {{
        grid-template-columns: 1fr 1fr;
    }}

    .lexi-end-score-value {{
        font-size: 2.6rem;
    }}

    .lexi-mic-glyph {{
        width: 28px;
        height: 28px;
    }}
}}

/* === Custom chat layout — replaces st.chat_message ===
   Host gets italic Lora + teal stripe + mic avatar; player gets a
   right-aligned ivory bubble. Container scrolls internally so the
   topbar/tile board stay anchored. */
.lexi-chat-scroll {{
    height: 320px;
    overflow-y: auto;
    padding: 0.25rem 0.5rem 0.5rem 0;
    scrollbar-width: thin;
    scrollbar-color: {BORDER_BRIGHT} transparent;
    scroll-behavior: smooth;
}}

.lexi-chat-scroll::-webkit-scrollbar {{
    width: 6px;
}}

.lexi-chat-scroll::-webkit-scrollbar-track {{
    background: transparent;
}}

.lexi-chat-scroll::-webkit-scrollbar-thumb {{
    background: {BORDER_BRIGHT};
    border-radius: 3px;
}}

.lexi-chat-row {{
    display: flex;
    margin: 0.55rem 0;
    align-items: flex-start;
    gap: 0.6rem;
}}

.lexi-chat-row.lexi-chat-host {{
    justify-content: flex-start;
}}

.lexi-chat-row.lexi-chat-user {{
    justify-content: flex-end;
}}

.lexi-chat-avatar {{
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: {SURFACE};
    border: 1px solid {TEAL};
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.95rem;
    margin-top: 2px;
}}

.lexi-chat-bubble {{
    padding: 0.6rem 0.95rem;
    line-height: 1.55;
    max-width: 78%;
    border-radius: 4px;
    word-wrap: break-word;
    overflow-wrap: anywhere;
}}

.lexi-chat-host-bubble {{
    background: {SURFACE};
    border-left: 3px solid {TEAL};
    color: {TEXT};
    font-family: {FONT_HOST};
    font-style: italic;
    font-size: 1.0rem;
}}

.lexi-chat-user-bubble {{
    background: {SURFACE_HIGH};
    border: 1px solid {BORDER};
    color: {TEXT};
    text-align: left;
    font-size: 0.97rem;
}}

.lexi-chat-system {{
    color: {TEXT_DIM};
    font-size: 0.85rem;
    text-align: center;
    margin: 0.6rem 0;
    font-family: {FONT_BODY};
    letter-spacing: 0.02em;
}}

/* Bubble entry animation — JS marks new rows with .lexi-fresh on each
   rerun, so only freshly-added bubbles slide-fade in. Older bubbles
   re-render without the class and don't re-animate. */
.lexi-fresh {{
    animation: lexi-bubble-in 320ms cubic-bezier(0.16, 1, 0.3, 1);
}}

@keyframes lexi-bubble-in {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}

/* Mobile: smaller avatar, tighter padding */
@media (max-width: 480px) {{
    .lexi-chat-bubble {{
        max-width: 85%;
        padding: 0.5rem 0.75rem;
    }}
    .lexi-chat-avatar {{
        width: 26px;
        height: 26px;
        font-size: 0.8rem;
    }}
    .lexi-chat-scroll {{
        height: 280px;
    }}
}}

/* === Score odometer wrapper ===
   The score number lives in a <span> so JS can swap its textContent
   during the rAF tween without rebuilding the parent chip. */
.lexi-score-num {{
    display: inline-block;
    font-variant-numeric: tabular-nums;
}}

/* === Typing indicator (replaces st.spinner during host turns) === */
.lexi-typing {{
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.5rem 0.85rem;
    margin: 0.4rem 0;
    background: {SURFACE};
    border-left: 3px solid {TEAL};
    border-radius: 4px;
    color: {TEXT_DIM};
    font-family: {FONT_HEADING};
    font-size: 0.78rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    width: max-content;
    max-width: 60%;
}}

.lexi-typing .lexi-typing-dots {{
    display: inline-flex;
    gap: 4px;
    margin-left: 0.5rem;
}}

.lexi-typing .lexi-typing-dot {{
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: {ACCENT};
    animation: lexi-typing-bounce 1.1s ease-in-out infinite;
}}

.lexi-typing .lexi-typing-dot:nth-child(2) {{ animation-delay: 0.15s; }}
.lexi-typing .lexi-typing-dot:nth-child(3) {{ animation-delay: 0.30s; }}

@keyframes lexi-typing-bounce {{
    0%, 65%, 100% {{ opacity: 0.3; transform: scale(0.7); }}
    30%           {{ opacity: 1.0; transform: scale(1.0); }}
}}
</style>
"""


def inject(st):
    """Call once at the top of every Streamlit page to apply the theme.

    Also primes the sound engine (idempotent — only does work on first
    page load). Sounds rely on Streamlit's static file serving (see
    .streamlit/config.toml).
    """
    st.markdown(stylesheet(), unsafe_allow_html=True)
    # Lazy import to avoid circular (sound imports from components, which
    # is also referenced elsewhere in theme.inject's call sites).
    from ui.sound import inject_sound_engine
    inject_sound_engine(st)
