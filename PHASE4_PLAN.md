# Phase 4 — Streamlit Web App

V1 of Lexi-Chat as a shareable web app. Faithful port of the CLI game's mechanics, dressed in a warm TV-studio aesthetic (NOT sci-fi).

---

## Scope

### In scope
- 4 screens: Home, Game arena, End screen, Score history
- Settings: small gear dropdown (difficulty / API provider / key)
- BYOK key flow (Gemini default; Hugging Face as second option)
- Demo mode for visitors without a key (scripted host only, IP-rate-limited)
- Original timer mechanics preserved exactly
- Local SQLite for score history
- Deploy to Streamlit Community Cloud as V1 testbed

### Out of scope (deferred)
- Voice (host TTS, player STT) — designed *for*, not *built*
- Multi-player leaderboard
- Mobile-specific layout (desktop-first; responsive comes later)
- Auth / user accounts
- Difficulty implementation (Phase 2 builds the data, Phase 4 wires the selector)

---

## Visual direction

| Element | Value |
|---|---|
| Background | `#0F1419` (deep navy-charcoal, warmer than pure black) |
| Panels / cards | `#1A2030` |
| Accent (spotlight) | `#F5C76A` (warm amber) |
| Success | `#D4A04C` (muted gold) |
| Warning (timer low) | `#C97D6A` (dusty rose, NOT red) |
| Secondary accent | `#5A8B8C` (deep teal) for chat bubbles |
| Text primary | `#EDE8DD` (ivory) |
| Text muted | `#8B8680` |
| Heading font | Space Grotesk |
| Body font | Inter |
| Host-voice font | Lora (italic) — optional, for host bubbles only |
| Letter tile shape | Diamond/lozenge, amber stroke when revealed |
| Mood | Late-evening TV studio. Subtle radial vignette behind tile board (stage spotlight). |

**Drop completely:** hex pattern background, neon glow, sci-fi copy ("operator", "neural link", "cypher", "hive").

---

## Screen designs

### 1. Home / Landing
- Lexi-Chat wordmark (Space Grotesk, amber dot accent — typographic-only logo for V1)
- Tagline: *"Bir kelime, bir sunucu, sonsuz keyif."* (or similar — TBC with Nurullah)
- Big primary button: **Yeni oyun**
- Secondary link: **Önceki skorlar**
- Sidebar (always visible): API key input (password-masked), provider selector (Gemini / Hugging Face / Demo Mode), difficulty selector (Easy/Normal/Hard/Expert — disabled in V1 if Phase 2 not done)
- Footer: small "60 saniyede ücretsiz API anahtarı al" guide link

### 2. Game arena
- **Top bar**: round indicator (`Soru 3/14`), total score (left), live timer `MM:SS` (right; amber when >1min, dusty-rose when <30s)
- **Center**:
  - Letter tile board (diamond tiles, gap 8px, revealed letters in amber, blanks dimmed)
  - Clue text below tiles in muted ivory, italic optional
- **Below**: chat history (scrollable, host bubbles teal-bordered, player bubbles right-aligned ivory)
- **Bottom**: `st.chat_input` with placeholder *"Tahmin yap, ipucu iste, ya da 'bb' yaz..."*
- **Floating controls** (bottom-left as small chips): `[h] Harf al` `[bb] Cevap ver` `[ipucu] İpucu iste`
- **Phase indicator**: when in `bb` mode, the timer turns dusty-rose, label changes to "Cevap süresi: 0:42", letter-request button is greyed

### 3. End screen
- "Yarışma sona erdi" + final score in large amber type
- Host's closing line (one of the existing scripted closers, or LLM-generated based on score)
- Stats: words seen, hints used, time taken
- Buttons: **Tekrar oyna**, **Skorları gör**

### 4. Score history
- Simple list view, newest first
- Per row: date, score, difficulty, time taken, # hints used
- Click a row → expand to show the words played that round
- "Skorları temizle" link in footer

---

## State machine (Streamlit `session_state`)

```python
st.session_state.phase ∈ {
    "home",       # landing
    "prologue",   # gpt_prologue equivalent — small talk before round 1
    "playing",    # in a round, "->" mode
    "answering",  # in a round, "-BB>" mode (45-s timer)
    "between",    # between rounds, awaiting "d" / "puan"
    "end",        # final screen
    "history",    # score history view
}
```

Other state:
- `game_state` = serialized `GameState` (score, revealed_letters, round_history, timers, etc.)
- `word_list`, `definition_list`, `synonym_list`, etc. (computed once at game start)
- `chat_log` = list of `(role, text)` for current screen
- `llm_client` = instance, recreated when key/provider changes
- `last_input_at` = timestamp for silence-trigger logic
- `next_silence_at` = randomized 9-12s ahead

---

## Timer implementation

Streamlit's challenge: it re-runs the script on every interaction, no native always-running timer. Solution:

- Store `total_time_remaining` and `last_tick_at` in session_state
- Use `streamlit-autorefresh` (1s interval) to force a rerun
- On each rerun: `elapsed = now - last_tick_at; total_time_remaining -= elapsed; last_tick_at = now`
- Pause logic: when phase is `answering`, decrement only the round timer, not the global

This avoids any threading. All timer math happens during rerun.

---

## File structure

```
Ling360-Lexichat/
├── lexichat_game.py              # CLI version, kept working
├── lexichat_game_legacy.py       # frozen 2023 reference
├── llm_client.py                 # extended: + HuggingFaceClient
├── streamlit_app.py              # NEW: Phase 4 entry point
├── ui/
│   ├── __init__.py
│   ├── theme.py                  # CSS injection, color constants
│   ├── components.py             # tile_board(), host_bubble(), player_bubble(), gear_dropdown()
│   ├── home.py                   # render_home()
│   ├── arena.py                  # render_arena() — main game screen
│   ├── end.py                    # render_end()
│   └── history.py                # render_history()
├── game/                         # extracted from lexichat_game.py — refactor for reuse
│   ├── __init__.py
│   ├── state.py                  # GameState dataclass
│   ├── data.py                   # load_words, load_gts, load_corpus
│   ├── host.py                   # llm_host_reply, silence, sanitize
│   ├── hints.py                  # _give_hint, _react_to_guess
│   └── round.py                  # game-mechanics functions, no I/O
├── data/
│   └── turkish_frequencies.json
└── data/scores.db                # NEW: SQLite for history
```

This refactor (extracting game logic from the CLI script into reusable `game/` modules) is **Phase 3 work that we'll fold into Phase 4** since we need the separation anyway. CLI version keeps working by importing from `game/`.

---

## Implementation order

1. **Refactor**: extract game logic from `lexichat_game.py` into `game/` modules. CLI still works.
2. **Theme & components**: `ui/theme.py` (CSS), `ui/components.py` (tile board, bubbles).
3. **Home screen** + sidebar (key input, provider).
4. **Arena screen** — phase=playing branch first (no timer yet).
5. **Timer** — wire up autorefresh + pause logic.
6. **Arena phase=answering** — `bb` flow, 45-s timer, locked controls.
7. **Silence filler** — port from CLI (use last_input_at).
8. **End screen** + state transitions.
9. **Score history** — SQLite layer + history view.
10. **HuggingFaceClient** — second provider in `llm_client.py`.
11. **Demo mode** — scripted-only fallback when no key.
12. **CSS polish** — vignette, tile glow, transitions.
13. **Deploy to Streamlit Community Cloud** + smoke test.

Each step is a checkpoint. We test between each.

---

## Pre-flight questions for Nurullah before implementation starts

1. **Tagline copy** — "Bir kelime, bir sunucu, sonsuz keyif" or do you want to write it?
2. **Difficulty: gate behind Phase 2, or build the selector now and wire it up later?** (V1 with no real difficulty yet is fine — just shows "Normal" locked.)
3. **Score history scope**: only your own past games on this browser? Or do you want it tied to a name, so you can compare across sessions?
4. **Demo mode hard cap**: 1 game per IP per day reasonable? Or 3? Or just always-on scripted mode?
5. **OK to install** these new dependencies? `streamlit`, `streamlit-autorefresh`, `huggingface-hub`. (No paid stuff.)

Once those are answered, I'll start with step 1 (refactor).
