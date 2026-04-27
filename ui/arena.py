"""Game arena — the main play screen.

Phase 4 step 4a: hint phase ("playing") only. The bb / answer phase comes
in step 4b. State machine values used here:
- "playing" — main hint phase, global timer ticking
- "between" — between rounds (advance / show score)
"""
from __future__ import annotations

import os
import random
import time

import nltk

# Set LEXICHAT_PROFILE=1 to print where each input's time goes.
PROFILE = os.environ.get("LEXICHAT_PROFILE") == "1"

from game import host
from game.config import (
    SILENCE_MAX_SECONDS, SILENCE_MIN_SECONDS, STUCK_KEYWORDS,
    TOTAL_GAME_TIME, TOTAL_ROUNDS,
)
from game.nlp import get_synonym_phrase
from game.round import (
    almost_had_it_reminder, end_game_lines, give_hint, letter_request,
    nonsense_meme, pre_info_messages, react_to_guess, repetition_nudge,
)
from ui.components import clue_card, host_bubble, info_chips, tile_board, topbar, wordmark


# --------------------------------------------------------------------------
# Time management — Streamlit-friendly. No threads. Each rerun computes
# elapsed time since last_tick_at and decrements the appropriate counter.
# --------------------------------------------------------------------------


def _tick_global_timer(st):
    """Decrement the global 5-min timer based on wall clock since last tick.
    Called on every rerun while in "playing" phase.
    """
    now = time.time()
    last = st.session_state.get("last_tick_at")
    if last is None:
        st.session_state.last_tick_at = now
        return
    elapsed = now - last
    if elapsed > 0:
        st.session_state.game_state.total_time = max(
            0, st.session_state.game_state.total_time - elapsed
        )
    st.session_state.last_tick_at = now


def _check_silence(st):
    """If the player has been quiet past the random threshold, append a
    silence-filler bubble to the chat history. Resets the threshold after
    firing so the next one is also random.

    Tier-2 escalation: if the player has typed the answer but not pressed
    bb (almost_had_it=True) AND has been reminded ≥2 times, shorten the
    silence threshold so the host nudges them more frequently. Use a
    pointed insistence line instead of generic silence reply.

    NOTE: without autorefresh, this only fires when the user triggers
    a rerun (e.g. sends a message). A truly idle player won't see a
    silence prompt until they do something. Acceptable for V1.
    """
    state = st.session_state.game_state
    last_input = st.session_state.get("last_input_at", time.time())
    threshold = st.session_state.get("silence_threshold")

    # Tier-2: pointed, frequent reminders
    in_tier_2 = state.almost_had_it and state.almost_reminded_count >= 2

    if threshold is None:
        if in_tier_2:
            threshold = random.uniform(5, 8)  # tighter when escalating
        else:
            threshold = random.uniform(SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS)
        st.session_state.silence_threshold = threshold

    if time.time() - last_input >= threshold:
        round_ctx = st.session_state.round_ctx
        if in_tier_2:
            line = almost_had_it_reminder(state.almost_reminded_count)
            state.almost_reminded_count += 1
        else:
            line = host.llm_silence_reply(
                st.session_state.llm, state, round_ctx, in_answer_mode=False
            )
        st.session_state.chat_log.append(("assistant", line))
        # Reset silence baseline so we don't fire again immediately
        st.session_state.last_input_at = time.time()
        if in_tier_2:
            st.session_state.silence_threshold = random.uniform(5, 8)
        else:
            st.session_state.silence_threshold = random.uniform(
                SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS
            )


# --------------------------------------------------------------------------
# Round setup — called when entering a new round
# --------------------------------------------------------------------------


_NONSENSE_KEYWORDS = {
    "h", "bb", "d", "puan", "ipucu", "ver", "evet", "olur",
    "tamam", "yok", "iyi", "peki", "yine", "yani", "neden",
    "niye", "köken", "kök", "hmm",
}
_TR_VOWELS = set("aeıioöuüAEIİOÖUÜ")
_TR_NON_VOWELS = set("bcçdfgğhjklmnpqrsştvwxyzBCÇDFGĞHJKLMNPQRSŞTVWXYZ")


def _looks_like_nonsense(raw: str) -> bool:
    """Detect keyboard-mashing input. Heuristics, in priority order:

    1. Empty / single char → not nonsense (could be 'h' keyword) [handled above]
    2. Reserved game keyword or conversational ack → not nonsense
    3. No vowels at all → nonsense (real Turkish words have ≥1 vowel)
    4. Vowel ratio < 25% → nonsense (Turkish words avg ~40-45% vowels)
    5. 4+ consecutive consonants → nonsense (e.g. 'dfslk')
    6. Short input (≤3 chars) with 3 consonants → nonsense ('fds', 'dfs')
    """
    s = raw.strip()
    if not s or len(s) < 2:
        return False
    if s in _NONSENSE_KEYWORDS:
        return False

    vowel_count = sum(1 for c in s if c in _TR_VOWELS)
    letter_count = sum(1 for c in s if c.isalpha())

    if letter_count == 0:
        return False  # all symbols/spaces — let the wrong-guess path handle
    if vowel_count == 0:
        return True

    vowel_ratio = vowel_count / letter_count
    if vowel_ratio < 0.25:
        return True

    # Consecutive consonant cluster check
    consec = 0
    for c in s:
        if c in _TR_NON_VOWELS:
            consec += 1
            if consec >= 4:
                return True
        else:
            consec = 0

    if len(s) <= 3 and vowel_count == 0:
        # already caught above, but defensive
        return True

    return False


def _start_round(st, round_idx: int):
    """Initialize state for round `round_idx`. Resets revealed letters,
    chat log scoped to this round, hint chance list, silence baselines.
    """
    state = st.session_state.game_state
    word_list = st.session_state.word_list
    word = word_list[round_idx]
    definition = st.session_state.definition_list[round_idx]
    syns = st.session_state.synonym_list[round_idx]

    state.reset_revealed()
    # Initialize blank tiles
    state.revealed_letters = ["_  "] * len(word)
    state.reset_round_history()
    state.reset_almost_memory()
    state.reset_nonsense_counters()
    state.reset_input_counts()

    st.session_state.round_idx = round_idx
    st.session_state.round_ctx = {
        "word": word,
        "clue": definition,
        "synonyms": syns if syns != "None" else [],
    }
    st.session_state.chance_list = [2, 3, 4, 7, 9, 5, 25, 65]
    st.session_state.list_active_input = []
    st.session_state.last_input_at = time.time()
    st.session_state.silence_threshold = random.uniform(
        SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS
    )
    st.session_state.last_tick_at = time.time()
    # Info chips revealed during this round; cleared when round changes.
    st.session_state.revealed_info = {}

    # Pre-round flavor lines from the host
    chat_log = st.session_state.chat_log
    pre_msgs = list(pre_info_messages(
        round_idx + 1, state.total_score, round_idx,
        st.session_state.function_list,
        st.session_state.structure_list,
        st.session_state.origin_list,
    ))
    for msg, _sleep in pre_msgs:
        chat_log.append(("assistant", msg))

    # Mirror anything pre_info_messages revealed into the chip row.
    # We scan the messages because pre_info_messages decides probabilistically
    # whether to mention each fact — so we can't assume from the lists alone.
    pre_text = " ".join(m for m, _ in pre_msgs).lower()
    f_type = st.session_state.function_list[round_idx]
    s_type = st.session_state.structure_list[round_idx]
    origin = st.session_state.origin_list[round_idx]
    if f_type and f_type != "None" and f_type.lower() in pre_text:
        st.session_state.revealed_info["function"] = f_type
    if s_type and s_type != "None" and s_type.lower() in pre_text:
        st.session_state.revealed_info["structure"] = s_type
    if origin and origin != "None" and origin.lower() in pre_text:
        st.session_state.revealed_info["origin"] = origin

    chat_log.append(("system", f"📝 İPUCU: {definition}"))


# --------------------------------------------------------------------------
# Input handling — runs once per submitted message
# --------------------------------------------------------------------------


def _handle_input(st, line: str, user_already_logged: bool = False):
    """Process one player message during the hint phase.

    user_already_logged=True means the caller has already appended the user's
    bubble to chat_log (used by the two-step input pattern).
    """
    t_start = time.perf_counter()
    state = st.session_state.game_state
    round_idx = st.session_state.round_idx
    round_ctx = st.session_state.round_ctx
    word = round_ctx["word"]
    chat_log = st.session_state.chat_log

    if not user_already_logged:
        chat_log.append(("user", line))
    raw = line.lower().strip()
    branch_taken = "unknown"
    tkn = nltk.word_tokenize(raw)
    st.session_state.last_input_at = time.time()
    st.session_state.silence_threshold = random.uniform(
        SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS
    )

    # === Branch: tries to answer without pressing bb ===
    if raw == word.lower() or word in tkn:
        branch_taken = "answer-without-bb"
        chat_log.append(("assistant", random.choice([
            f"{word} sığıyor mu oraya?",
            "Bana mı soruyorsunuz, cevap mı veriyorsunuz?..",
            "Haydi, şöyle bir cesaret... ",
            "Efendim bana sormayın... Ben bir şey diyemem ki...",
            "Ben bilmem...",
            "... emin misiniz..?",
            "Risk alacak mısınız..?",
            "Buton... Buton..., Unutuyorsunuz basmayı ya da risk almak mı istemiyorsunuz..?",
            "Şu \"bb\" tuşunu unutmayın efendim.",
        ])))
        # Remember it for later teasing reminders
        state.almost_had_it = True

    # === Branch: asks about origin ===
    elif any(it in ["kök", "köken", "kökenli", "kökeni"] for it in tkn):
        branch_taken = "origin"
        origin = st.session_state.origin_list[round_idx]
        if origin != "None":
            chat_log.append(("assistant", random.choice([
                f"Sanırım {origin} olmalı",
                f"Hmm... Bu, sanıyorum {origin}",
                f"{origin}",
                f"{origin} olma ihtimali yüksek",
            ])))
            st.session_state.revealed_info["origin"] = origin
        else:
            chat_log.append(("assistant", "Maalesef kökeninden emin değilim..."))
            st.session_state.revealed_info["origin"] = "Bilinmiyor"

    # === Branch: bb (placeholder for step 4b) ===
    elif raw == "bb":
        branch_taken = "bb-placeholder"
        chat_log.append(("assistant",
            "Cevap fazı henüz hazır değil — Phase 4 step 4b'de gelecek. "
            "Şimdilik tahmininizi doğrudan yazabilirsiniz."))

    # === Branch: letter request ===
    elif raw == "h" or ("harf" in tkn and ("alabilir" in tkn or "alayım" in tkn)) or "harf" in tkn:
        branch_taken = "letter-request"
        _, status = letter_request(word, state.revealed_letters)
        if status == "all-revealed":
            chat_log.append(("assistant",
                "Üzgünüm efendim, tüm harfleri açtınız. Bu sorudan puan alamadınız!\n"
                "Sıradaki soruya geçelim..."))
            _advance_to_next_round(st)
            return

    # === Branch: explicit hint request ===
    elif any(it in STUCK_KEYWORDS for it in tkn):
        branch_taken = "hint-request"
        msgs = give_hint(
            st.session_state.chance_list, round_idx, word,
            st.session_state.example_sentences,
            st.session_state.compound_list,
            st.session_state.additional_defs,
            st.session_state.definition_list,
            st.session_state.synonym_list,
        )
        for msg in msgs:
            chat_log.append(("assistant", msg))
        # If the dispatcher chose to reveal the compound form, surface it
        compound = st.session_state.compound_list[round_idx]
        if compound and compound != "None":
            joined = " ".join(msgs)
            if compound in joined:
                st.session_state.revealed_info["compound"] = compound

    # === Branch: synonym request ===
    elif (("eş" in tkn and any(a in tkn for a in ("anlamlı", "anlamlısı", "anlam", "anlamı")))
          or ("benzer" in tkn and any(a in tkn for a in ("anlamda", "anlamlı")))):
        branch_taken = "synonym-request"
        syn_phrase = get_synonym_phrase(st.session_state.synonym_list, round_idx)
        if syn_phrase != "None":
            chat_log.append(("assistant", syn_phrase))
        else:
            chat_log.append(("assistant", "Maalesef aklıma bir şey gelmedi şu an..."))

    # === Branch: between-rounds keyword while in a round ===
    elif raw == "puan":
        branch_taken = "score-check"
        chat_log.append(("assistant", f"Şu anki toplam puanınız: {state.total_score}"))

    # === Default: try react_to_guess, fall through to LLM if chatter ===
    else:
        cleaned_tokens, sorted_keywords = st.session_state.corpus
        reaction = react_to_guess(
            raw, round_idx, word, tkn, st.session_state.list_active_input,
            st.session_state.synonym_list, cleaned_tokens, sorted_keywords,
        )
        if reaction is not None:
            branch_taken = "guess-reaction"
            chat_log.append(("assistant", reaction))
        else:
            branch_taken = "llm-fallback"
            state.round_history.append(("user", line))
            t_llm = time.perf_counter()
            reply = host.llm_host_reply(
                st.session_state.llm, state, round_ctx, line,
                state.round_history, in_answer_mode=False,
            )
            llm_ms = (time.perf_counter() - t_llm) * 1000
            chat_log.append(("assistant", reply))
            state.round_history.append(("assistant", reply))

    st.session_state.list_active_input.append(raw)

    # === Track per-round repetition counts ===
    # We count meaningful inputs only (skip empty / pure keywords that the
    # game expects you to repeat — h, ipucu, etc.).
    if raw and raw not in {"h", "bb", "d", "puan", "ipucu"}:
        state.input_counts[raw] = state.input_counts.get(raw, 0) + 1

    # === Repetition nudge / meme escalation ===
    # 3+ same input → append a "stop saying that" line.
    # 5+ same input → append a meme line on top (the player is clearly stuck).
    repeat_count = state.input_counts.get(raw, 0)
    if repeat_count >= 5 and random.random() < 0.7:
        chat_log.append(("assistant", nonsense_meme()))
    elif repeat_count >= 3 and branch_taken in ("guess-reaction", "llm-fallback"):
        chat_log.append(("assistant", repetition_nudge()))

    # === "Az önce çıktı sanki ağzınızdan..." teasing ===
    # Fires after stuck-requests or wrong-guesses when the player has
    # already typed the answer earlier without pressing bb.
    # No hard cap on count: tier escalation (gentle → insistent) handles
    # not-becoming-nagging. Probability rises with reminded_count so the
    # host gets more persistent the longer the player ignores the answer.
    REMINDER_BRANCHES = {"hint-request", "guess-reaction", "llm-fallback"}
    if state.almost_had_it and branch_taken in REMINDER_BRANCHES:
        # 50% chance for first 2 reminders, then 80% chance once we've
        # escalated to tier-2 insistence.
        prob = 0.5 if state.almost_reminded_count < 2 else 0.8
        if random.random() < prob:
            chat_log.append(("assistant", almost_had_it_reminder(state.almost_reminded_count)))
            state.almost_reminded_count += 1

    # === Nonsense / meme reply ===
    # When the player types gibberish (low vowel ratio, consonant clusters,
    # or short non-keyword), eventually emit a funny line.
    # - 2+ consecutive nonsense → ~40% chance
    # - 4+ total nonsense in round → ~60% chance
    nonsense_branches = {"guess-reaction", "llm-fallback"}
    if branch_taken in nonsense_branches and _looks_like_nonsense(raw):
        state.nonsense_streak += 1
        state.nonsense_total += 1
        prob = 0.0
        if state.nonsense_streak >= 2:
            prob = 0.4
        if state.nonsense_total >= 4:
            prob = max(prob, 0.6)
        if prob > 0 and random.random() < prob:
            chat_log.append(("assistant", nonsense_meme()))
    elif branch_taken in nonsense_branches:
        # Real attempt — reset the consecutive counter
        state.nonsense_streak = 0

    if PROFILE:
        total_ms = (time.perf_counter() - t_start) * 1000
        extra = f" llm={llm_ms:.0f}ms" if branch_taken == "llm-fallback" else ""
        print(f"[profile] input={line!r:<30} branch={branch_taken:<18} total={total_ms:.0f}ms{extra}")


def _advance_to_next_round(st):
    """Move to the next round, or end the game if we're at the last."""
    next_idx = st.session_state.round_idx + 1
    if next_idx >= TOTAL_ROUNDS:
        st.session_state.phase = "end"
    else:
        _start_round(st, next_idx)


# --------------------------------------------------------------------------
# Main render
# --------------------------------------------------------------------------


def render_arena(st):
    state = st.session_state.game_state

    # Tick the global timer first — this might end the game
    _tick_global_timer(st)
    if state.total_time <= 0:
        state.game_over = True
        st.session_state.phase = "end"
        st.rerun()
        return

    # === Process input BEFORE rendering ===
    # st.chat_input always anchors to the bottom of the page regardless of
    # where in the script we call it, so calling it first is purely a
    # data-flow choice — it lets us render tiles/clue with the POST-input
    # state when the input advances to the next round.
    line = st.chat_input(
        "Tahmin yap, harf iste ('h'), ya da ipucu iste...",
        key="arena_input",
    )
    if line:
        # Show a spinner during processing so even slow paths (LLM call)
        # feel intentional rather than frozen.
        with st.spinner("Sunucu düşünüyor..."):
            _handle_input(st, line)
        # If _handle_input transitioned us to "end" (or another phase),
        # bail and let the router pick up the new phase.
        if st.session_state.phase != "playing":
            st.rerun()
            return

    # Silence check runs AFTER input handling so that a freshly-typed
    # message resets last_input_at before we measure idleness. Otherwise
    # the player can type for 10s, hit submit, and have a silence-filler
    # appear right after their own message.
    _check_silence(st)

    # Now read the (possibly updated) state for rendering
    round_idx = st.session_state.round_idx
    round_ctx = st.session_state.round_ctx
    word = round_ctx["word"]

    # === Header ===
    wordmark(st, level="h3")
    topbar(
        st,
        score=state.total_score,
        round_num=round_idx + 1,
        total_rounds=TOTAL_ROUNDS,
        seconds_remaining=int(state.total_time),
        in_answer_mode=False,
    )

    # === Letter board ===
    tile_board(st, word, state.revealed_letters)

    # === Revealed-info chips (TÜR / YAPI / KÖKEN / BİRLEŞİK) ===
    info_chips(st, st.session_state.get("revealed_info", {}))

    # === Clue ===
    clue_card(st, round_ctx["clue"])

    st.write("")

    # === Chat history (fixed-height, scrolls internally) ===
    chat_log = st.session_state.chat_log
    with st.container(height=320, border=False):
        for role, text in chat_log:
            if role == "system":
                st.caption(text)
            elif role == "assistant":
                with st.chat_message("assistant", avatar="🎙️"):
                    st.write(text)
            else:
                with st.chat_message("user"):
                    st.write(text)
