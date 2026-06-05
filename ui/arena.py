"""Game arena — the main play screen.

State machine values used here:
- "playing"   — hint phase, global 5-min timer ticking
- "answering" — bb phase, global timer paused, 45-s round timer ticking
- "end"       — game over, handled by streamlit_app.render_end_placeholder
"""
from __future__ import annotations

import html as html_lib
import os
import random
import time

import nltk

# Set LEXICHAT_PROFILE=1 to print where each input's time goes.
PROFILE = os.environ.get("LEXICHAT_PROFILE") == "1"

from game import host
from game.config import (
    ROUND_TIME_SECONDS, SILENCE_MAX_SECONDS, SILENCE_MIN_SECONDS,
    STUCK_KEYWORDS, TOTAL_GAME_TIME, TOTAL_ROUNDS,
)
from game.mood import compute_mood
from game.nlp import get_synonym_phrase
from game.text_utils import tr_fold
from game.round import (
    almost_had_it_reminder, correct_answer_celebration, end_game_lines,
    give_hint, letter_request, nonsense_meme, pre_info_messages,
    react_to_guess, repetition_nudge, round_timeout_lines,
    score_for_correct_answer,
)
from ui import sound
from ui.components import (
    answer_timer, clue_card, focus_chat_input,
    host_bubble, info_chips, mark_fresh_chat_messages, tile_board,
    topbar, typing_indicator, wordmark,
)


# --------------------------------------------------------------------------
# Time management — Streamlit-friendly. No threads. Each rerun computes
# elapsed time since last_tick_at and decrements the appropriate counter.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Chat delivery — staggered reveal so the player can read each line
# --------------------------------------------------------------------------
#
# Every entry in chat_log is (role, text, reveal_at) where reveal_at is a
# wall-clock timestamp (time.time() seconds). The renderer hides entries
# whose reveal_at is in the future. _say() handles the queue: by default
# every host bubble is staggered ~1.6s after the previous queued one, so
# multi-line responses (round transitions, hints with several lines)
# appear progressively rather than all at once.
#
# Why timestamps instead of partial reruns: Streamlit can't yield partial
# UI mid-script. So we push everything into chat_log up-front, mark each
# with when it should appear, and use a 500ms autorefresh to reveal
# entries as their time comes due. Future TTS will use the same reveal_at
# (each line speaks when it appears). User messages always reveal_at=now.

CHAT_STAGGER_HOST = 1.6   # seconds between consecutive host lines
CHAT_STAGGER_HINT = 1.2   # tighter for hint lines (already partially sequential)
CHAT_STAGGER_SHORT = 0.8  # snappy for one-word reactions (e.g. nonsense memes)


def _say(st, role: str, text: str, *, after: float | None = None):
    """Append a chat bubble with a reveal-time stamp.

    Currently `after` is accepted for source-level intent but ignored —
    every message reveals immediately. Staggering is disabled because
    the autorefresh that drove visual reveals raced st.chat_input
    submissions and broke sending. The `after` parameter is preserved
    so the call sites that *want* to stagger (round transitions, hint
    dispatcher output, timeout) keep their semantic intent in source —
    when we re-enable staggering via JS-driven reveals (no Streamlit
    rerun), those call sites won't need to change.

    The reveal_at field on each entry is still recorded for future
    use (TTS triggers, JS reveal animation), just always set to now.
    """
    chat_log = st.session_state.chat_log
    chat_log.append((role, text, time.time()))


def _has_pending_chat(st) -> bool:
    """True if any chat_log entry has reveal_at in the future."""
    now = time.time()
    for entry in st.session_state.get("chat_log", []):
        if len(entry) >= 3 and entry[2] > now:
            return True
    return False


def _consume_score_pop(st):
    """If a score-pop is due (its `at` timestamp has passed), return it
    once and mark consumed so the animation doesn't replay on each rerun.

    Returns a dict with delta/id, or None.
    """
    pop = st.session_state.get("score_pop")
    if not pop:
        return None
    now = time.time()
    if pop.get("at", 0) > now:
        return None  # not yet — wait for the celebration line to reveal
    if pop.get("consumed"):
        return None
    pop["consumed"] = True
    pop.setdefault("id", f"pop-{int(pop['at'] * 1000)}")
    return pop


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


def _check_silence(st, in_answer_mode: bool = False):
    """If the player has been quiet past the random threshold, append a
    silence-filler bubble to the chat history. Resets the threshold after
    firing so the next one is also random.

    Tier-2 escalation: if the player has typed the answer but not pressed
    bb (almost_had_it=True) AND has been reminded ≥2 times, shorten the
    silence threshold so the host nudges them more frequently. Use a
    pointed insistence line instead of generic silence reply.

    in_answer_mode: True when called from the answering phase. Forwarded
    to llm_silence_reply so the prompt instructs the host to behave for bb
    mode (no letter offers, urgent tone). Tier-2 teasing only applies in
    playing mode — once you've pressed bb, the answer-mode timer's the
    nudge.

    NOTE: idle players in playing mode only see silence fillers when they
    do something (no autorefresh). In answering mode the 1-s autorefresh
    keeps it ticking. Acceptable for V1.
    """
    state = st.session_state.game_state
    last_input = st.session_state.get("last_input_at", time.time())
    threshold = st.session_state.get("silence_threshold")

    # Tier-2: pointed, frequent reminders. Only in playing mode — once
    # the player presses bb, the round timer is the nag, not us.
    in_tier_2 = (
        not in_answer_mode
        and state.almost_had_it
        and state.almost_reminded_count >= 2
    )

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
                st.session_state.llm, state, round_ctx,
                in_answer_mode=in_answer_mode,
                mood=compute_mood(state),
            )
        _say(st, "assistant", line)
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


def _looks_like_obvious_garbage(raw: str) -> bool:
    """Stronger signal than _looks_like_nonsense — input is so clearly
    keyboard-mash that the host should fire a meme immediately, no
    streak warmup needed. Examples that qualify:
        'fksdsdjkf' (9 letters, no vowels)
        'qwertyuiop' (10 letters, ≥5 consec consonants)
        'asdfgh' (6 letters, ≥5 consec consonants)
    Examples that don't qualify (deliberately): 'fdg', 'xyz' (too short
    to be sure they're junk; could be a typo or abbreviation).
    """
    s = raw.strip()
    if len(s) < 6:
        return False
    if s in _NONSENSE_KEYWORDS:
        return False
    vowels = sum(1 for c in s if c in _TR_VOWELS)
    if vowels == 0:
        return True
    consec = 0
    for c in s:
        if c in _TR_NON_VOWELS:
            consec += 1
            if consec >= 5:
                return True
        else:
            consec = 0
    return False


def _start_round(st, round_idx: int):
    """Initialize state for round `round_idx`. Resets revealed letters,
    chat log scoped to this round, hint chance list, silence baselines.
    """
    if round_idx == 0:
        sound.queue(st, "game-start")
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
    state.reset_mood_signals()
    # NOTE: don't clear score_pop here — the celebration line that
    # triggers it has a future reveal_at that crosses round boundaries.
    # _consume_score_pop self-clears via the `consumed` flag.

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

    # Pre-round flavor lines from the host — staggered so the player can
    # actually read each one. The "system" clue line at the end appears
    # AFTER the host's intro lines (it's the cue that the round is ready
    # for input). The player can submit input at any time; staggering is
    # purely visual.
    pre_msgs = list(pre_info_messages(
        round_idx + 1, state.total_score, round_idx,
        st.session_state.function_list,
        st.session_state.structure_list,
        st.session_state.origin_list,
    ))
    for msg, _sleep in pre_msgs:
        _say(st, "assistant", msg, after=CHAT_STAGGER_HOST)

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

    # Clue line appears after the host intro, slightly delayed.
    _say(st, "system", f"📝 İPUCU: {definition}", after=CHAT_STAGGER_HOST)


# --------------------------------------------------------------------------
# Input handling — runs once per submitted message
# --------------------------------------------------------------------------


def _handle_input(st, line: str, user_already_logged: bool = False,
                  in_answer_mode: bool = False):
    """Process one player message.

    in_answer_mode:
      False (playing) — typing the answer triggers a tease, 'bb' enters
        answering phase, letter requests work, ipucu/synonym/origin work.
      True  (answering) — typing the answer wins the round, 'bb' resets the
        45-s deadline, letter requests are blocked, everything else works.

    user_already_logged=True means the caller has already appended the user's
    bubble to chat_log (used by the two-step input pattern).
    """
    t_start = time.perf_counter()
    state = st.session_state.game_state
    round_idx = st.session_state.round_idx
    round_ctx = st.session_state.round_ctx
    word = round_ctx["word"]

    if not user_already_logged:
        _say(st, "user", line)
    raw = line.lower().strip()
    branch_taken = "unknown"
    llm_ms = 0.0
    tkn = nltk.word_tokenize(raw)
    st.session_state.last_input_at = time.time()
    st.session_state.silence_threshold = random.uniform(
        SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS
    )

    # === Branch: types the answer ===
    # Fold circumflex accents so "kakül" matches "kâkül" — Turkish
    # keyboards don't expose â/î/û. Compare folded raw and folded tokens
    # against the folded answer; never alter raw itself (we still echo
    # the original input).
    _word_folded = tr_fold(word.lower())
    _raw_folded = tr_fold(raw)
    _tkn_folded = [tr_fold(t) for t in tkn]
    if _raw_folded == _word_folded or _word_folded in _tkn_folded:
        if in_answer_mode:
            # Correct! End the round — celebration + score + advance.
            branch_taken = "answer-correct"
            sound.queue(st, "correct")
            # Stash the points we'll award so the renderer can play a
            # +N pop animation when the celebration line is revealed.
            round_score = score_for_correct_answer(word, state.revealed_letters)
            st.session_state.score_pop = {
                "delta": round_score,
                "from": state.total_score,
                "to": state.total_score + round_score,
                "at": st.session_state.get("_next_reveal_at") or time.time(),
            }
            # Honor the legacy chosen_phrase callback: if the host's last
            # tease was one of the two specific lines, the response shifts.
            # Stagger this sequence (chosen-phrase reaction + celebration)
            # so the player can read each line.
            if state.chosen_phrase == "Bana mı soruyorsunuz, cevap mı veriyorsunuz?..":
                _say(st, "assistant", random.choice([
                    "Cevap veriyorlar..!",
                    "Sanırım cevap veriyorsunuz ve doğru olanı yapıyorsunuz",
                ]), after=CHAT_STAGGER_HOST)
            elif state.chosen_phrase == f"{word} sığıyor mu oraya?":
                _say(st, "assistant", "Eyvah, eyvah! Efendim sığıyor mu ki?...",
                     after=CHAT_STAGGER_HOST)
                _say(st, "assistant",
                    "Tabii ki sığıyor! Yalnızca biraz heyecanlandırmak istedim "
                    "ancak buna kanmadılar kendileri...",
                    after=CHAT_STAGGER_HOST)

            clean_win = (round_score == len(word) * 100)
            _say(st, "assistant",
                 correct_answer_celebration(word, round_score, clean=clean_win),
                 after=CHAT_STAGGER_HOST)
            state.total_score += round_score
            state.rounds_solved += 1
            state.words_played.append({
                "word": word, "outcome": "solved",
                "letters_revealed": len(word) - state.revealed_letters.count("_  "),
            })
            # Update the score-pop's "at" so the animation triggers when
            # the celebration line reveals (cursor advanced after the
            # _say above).
            st.session_state.score_pop["at"] = (
                st.session_state.get("_next_reveal_at") or time.time()
            )
            _end_answering_round(st, success=True)
            return
        else:
            branch_taken = "answer-without-bb"
            chosen = random.choice([
                f"{word} sığıyor mu oraya?",
                "Bana mı soruyorsunuz, cevap mı veriyorsunuz?..",
                "Haydi, şöyle bir cesaret... ",
                "Efendim bana sormayın... Ben bir şey diyemem ki...",
                "Ben bilmem...",
                "... emin misiniz..?",
                "Risk alacak mısınız..?",
                "Buton... Buton..., Unutuyorsunuz basmayı ya da risk almak mı istemiyorsunuz..?",
                "Şu \"bb\" tuşunu unutmayın efendim.",
            ])
            state.chosen_phrase = chosen
            _say(st, "assistant", chosen)
            # Remember it for later teasing reminders
            state.almost_had_it = True
            # Mood reset — they just typed the exact answer. They were
            # the closest possible; on the next host turn this will
            # surface as `playful` ("dilinizin ucundaydı, hadi bb!").
            state.wrong_streak = 0
            state.last_was_close = True

    # === Branch: asks about origin ===
    elif any(it in ["kök", "köken", "kökenli", "kökeni"] for it in tkn):
        branch_taken = "origin"
        origin = st.session_state.origin_list[round_idx]
        if origin != "None":
            _say(st, "assistant", random.choice([
                f"Sanırım {origin} olmalı",
                f"Hmm... Bu, sanıyorum {origin}",
                f"{origin}",
                f"{origin} olma ihtimali yüksek",
            ]))
            st.session_state.revealed_info["origin"] = origin
        else:
            _say(st, "assistant", "Maalesef kökeninden emin değilim...")
            st.session_state.revealed_info["origin"] = "Bilinmiyor"

    # === Branch: bb ===
    elif raw == "bb":
        if in_answer_mode:
            # Already in answer mode — bb is a no-op (matches legacy CLI:
            # the deadline is set ONCE on entry, re-pressing bb doesn't
            # extend it). Just acknowledge briefly.
            branch_taken = "bb-noop"
            _say(st, "assistant", random.choice([
                "Düğmedeyiz zaten efendim, cevabınızı söyleyin...",
                "Bastınız bile, hadi bakalım — kelime nedir?",
                "Cevap modundayız efendim, dinliyorum...",
            ]))
        else:
            branch_taken = "bb-enter"
            sound.queue(st, "bb")
            _begin_answering(st)
            _say(st, "assistant", random.choice([
                "Süreyi durdurdum efendim, 45 saniyeniz var...",
                "Pekâlâ, dinliyorum. Cevabınızı söyleyin...",
                "Süre sizde — hadi bakalım, kelime nedir?",
                "Düğmeye bastınız, şimdi cevap zamanı...",
            ]))

    # === Branch: letter request ===
    elif raw == "h" or ("harf" in tkn and ("alabilir" in tkn or "alayım" in tkn)) or "harf" in tkn:
        if in_answer_mode:
            # Letter requests blocked once you've pressed bb (legacy line).
            branch_taken = "letter-blocked"
            _say(st, "assistant",
                "Efendim, harf alamazsınız artık, süreyi durdurdunuz.")
        else:
            branch_taken = "letter-request"
            _, status = letter_request(word, state.revealed_letters)
            if status != "all-revealed":
                state.hints_used += 1
                # Direct play, NOT queue — letter-request stays in the
                # same render (no st.rerun), so the sound iframe lives
                # alongside the tile-board iframe and fires immediately.
                # Queue would delay this by one input, which felt
                # "alternating" (every other 'h' triggered the previous).
                sound.play(st, "tile-reveal")
            # End the round when the LAST blank gets revealed (matches
            # legacy: it reveals the letter, then checks if any blanks
            # remain). status=="all-revealed" only fires when called with
            # zero blanks left, i.e. one click late — so also check the
            # post-reveal state here.
            no_blanks_left = "_  " not in state.revealed_letters
            if status == "all-revealed" or no_blanks_left:
                _say(st, "assistant",
                    "Üzgünüm efendim, tüm harfleri açtınız. Bu sorudan puan alamadınız!\n"
                    "Sıradaki soruya geçelim...")
                state.rounds_failed += 1
                state.words_played.append({
                    "word": word, "outcome": "failed",
                    "letters_revealed": len(word) - state.revealed_letters.count("_  "),
                })
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
            _say(st, "assistant", msg, after=CHAT_STAGGER_HINT)
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
            _say(st, "assistant", syn_phrase)
        else:
            _say(st, "assistant", "Maalesef aklıma bir şey gelmedi şu an...")

    # === Branch: between-rounds keyword while in a round ===
    elif raw == "puan":
        branch_taken = "score-check"
        _say(st, "assistant", f"Şu anki toplam puanınız: {state.total_score}")

    # === Default: try react_to_guess, fall through to LLM if chatter ===
    else:
        cleaned_tokens, sorted_keywords = st.session_state.corpus
        reaction = react_to_guess(
            raw, round_idx, word, tkn, st.session_state.list_active_input,
            st.session_state.synonym_list, cleaned_tokens, sorted_keywords,
            gts_index=st.session_state.gts_index,
            wordnet=st.session_state.wordnet,
            in_answer_mode=in_answer_mode,
        )
        if reaction is not None:
            branch_taken = "guess-reaction"
            _say(st, "assistant", reaction)
            # Mood signal update. The "yakla" substring identifies all
            # close-guess branches inside react_to_guess (string-familiar,
            # synonym overlap, edit-distance). Wrong-guess increment fires
            # only for the real-attempt filter (single token, 4-15 chars)
            # — same shape react_to_guess uses for its generic brushoff.
            if "yakla" in reaction.lower():
                state.last_was_close = True
            elif len(tkn) == 1 and " " not in raw and 4 <= len(raw) <= 15:
                state.wrong_streak += 1
                state.last_was_close = False
        else:
            branch_taken = "llm-fallback"
            state.round_history.append(("user", line))
            t_llm = time.perf_counter()
            reply = host.llm_host_reply(
                st.session_state.llm, state, round_ctx, line,
                state.round_history, in_answer_mode=in_answer_mode,
                mood=compute_mood(state),
            )
            llm_ms = (time.perf_counter() - t_llm) * 1000
            _say(st, "assistant", reply)
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
        _say(st, "assistant", nonsense_meme(), after=CHAT_STAGGER_SHORT)
    elif repeat_count >= 3 and branch_taken in ("guess-reaction", "llm-fallback"):
        _say(st, "assistant", repetition_nudge(), after=CHAT_STAGGER_SHORT)

    # === "Az önce çıktı sanki ağzınızdan..." teasing ===
    # Fires after stuck-requests or wrong-guesses when the player has
    # already typed the answer earlier — both before AND after pressing
    # bb. The host should remember the player typed the answer in the
    # hint phase and remind them when they ask for help in answer mode.
    # No hard cap on count: tier escalation (gentle → insistent) handles
    # not-becoming-nagging. Probability rises with reminded_count.
    REMINDER_BRANCHES = {"hint-request", "guess-reaction", "llm-fallback"}
    if state.almost_had_it and branch_taken in REMINDER_BRANCHES:
        # First reminder always fires — the player typed the answer and
        # the host should acknowledge that immediately the next time
        # they ask for help, especially right after pressing bb.
        # After the first one, 50% chance for the next, then 80% once
        # we've escalated to tier-2 insistence.
        if state.almost_reminded_count == 0:
            prob = 1.0
        elif state.almost_reminded_count < 2:
            prob = 0.5
        else:
            prob = 0.8
        if random.random() < prob:
            _say(st, "assistant", almost_had_it_reminder(state.almost_reminded_count),
                 after=CHAT_STAGGER_SHORT)
            state.almost_reminded_count += 1

    # === Nonsense / meme reply ===
    # When the player types gibberish, react with a funny line.
    # Three escalating triggers:
    # - "Obvious garbage" (e.g. 'fksdsdjkf', 'qwertyuiop') → 90% chance
    #   on the FIRST occurrence. The signal is strong enough that
    #   waiting for a streak is anticlimactic.
    # - 2+ consecutive nonsense → 70% chance
    # - 3+ consecutive OR 4+ total in round → 95% chance
    nonsense_branches = {"guess-reaction", "llm-fallback"}
    if branch_taken in nonsense_branches and _looks_like_nonsense(raw):
        state.nonsense_streak += 1
        state.nonsense_total += 1
        if _looks_like_obvious_garbage(raw):
            prob = 0.9
        elif state.nonsense_streak >= 3 or state.nonsense_total >= 4:
            prob = 0.95
        elif state.nonsense_streak >= 2:
            prob = 0.7
        else:
            prob = 0.0
        if prob > 0 and random.random() < prob:
            _say(st, "assistant", nonsense_meme(), after=CHAT_STAGGER_SHORT)
    elif branch_taken in nonsense_branches:
        # Real attempt — reset the consecutive counter
        state.nonsense_streak = 0

    if PROFILE:
        total_ms = (time.perf_counter() - t_start) * 1000
        extra = f" llm={llm_ms:.0f}ms" if branch_taken == "llm-fallback" else ""
        print(f"[profile] input={line!r:<30} branch={branch_taken:<18} total={total_ms:.0f}ms{extra}")


def _advance_to_next_round(st):
    """Move to the next round via the `between` transition phase.

    Two random branches (60 % auto-advance / 40 % ask for confirmation),
    handled in render_between. If we're at the last round, jump straight
    to end — no transition needed.
    """
    st.session_state.answer_deadline = None
    st.session_state.answer_started_at = None
    next_idx = st.session_state.round_idx + 1
    if next_idx >= st.session_state.game_state.total_rounds:
        st.session_state.phase = "end"
        return

    # Pick a transition mode and stash the state for render_between.
    now = time.time()
    if random.random() < 0.6:
        # AUTO branch — short flavor line, server timer ticks down to 0,
        # next round auto-starts. Random 2-4s pause feels natural.
        line = random.choice([
            "Hadi hiç ara vermeden devam edelim...",
            "Hız kesmeden devam edelim efendim...",
            "Sıradaki soruya geçiyoruz...",
            "Devam ediyoruz...",
            "Hadi bakalım sıradakine...",
            "Bir an bile durmadan devam efendim...",
        ])
        _say(st, "assistant", line)
        st.session_state.between_state = {
            "mode": "auto",
            "next_idx": next_idx,
            "auto_advance_at": now + random.uniform(2.0, 4.0),
        }
    else:
        # WAIT branch — host asks; we stay in `between` until player
        # types a continue-signal. If the player goes silent for 10 s
        # the host nudges and auto-advances.
        line = random.choice([
            "Devam mı efendim?",
            "Hazır hissediyor musunuz sıradakine?",
            "Derin bir nefes alalım — devam mı?",
            "İyi hissediyor musunuz, devam edelim mi?",
            "Bir nefes — hazır olunca devam diyin...",
            "Hazır mısınız sıradakine?",
        ])
        _say(st, "assistant", line)
        st.session_state.between_state = {
            "mode": "wait",
            "next_idx": next_idx,
            "asked_at": now,
            "idle_nudge_at": now + 10.0,  # host says "devam edelim hadi" if quiet
        }
    st.session_state.phase = "between"


# --------------------------------------------------------------------------
# bb / answering phase — global timer pauses, 45-s round timer starts
# --------------------------------------------------------------------------


def _begin_answering(st):
    """Enter the answering phase: pause the global timer, snapshot it,
    set the 45-s round deadline.

    Matches legacy: deadline is set ONCE on bb entry. Re-pressing bb later
    is a no-op (handled in _handle_input).

    Server deadline is now + 46 s; the JS visual countdown ticks from 45.
    The +1 grace second ensures the visible counter hits 0 a hair before
    the authoritative server check fires timeout — no race where the user
    sees "1" but the round has already ended.
    """
    state = st.session_state.game_state
    now = time.time()
    state.is_paused = True
    state.resume_time = state.total_time
    st.session_state.phase = "answering"
    st.session_state.answer_started_at = now
    st.session_state.answer_deadline = now + ROUND_TIME_SECONDS + 1
    # Reset silence baseline so the host doesn't fire a filler immediately
    # after the bb-enter line.
    st.session_state.last_input_at = now
    st.session_state.silence_threshold = random.uniform(
        SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS
    )


def _end_answering_round(st, *, success: bool):
    """Restore global timer and advance to the next round.

    success=True  — player got the answer. Score already added by caller.
    success=False — 45s elapsed. Caller already appended timeout lines and
                    subtracted score.
    """
    state = st.session_state.game_state
    # Restore the global timer to where it was when bb fired.
    state.total_time = state.resume_time
    state.is_paused = False
    # Make sure the next rerun's _tick_global_timer doesn't subtract the
    # whole pause duration — reset its baseline.
    st.session_state.last_tick_at = time.time()
    st.session_state.answer_deadline = None
    st.session_state.answer_started_at = None
    # If the global timer ran out *before* bb (shouldn't happen normally
    # since we check at the top of render_arena), end the game.
    if state.total_time <= 0:
        state.game_over = True
        st.session_state.phase = "end"
        return
    _advance_to_next_round(st)


def _handle_answering_timeout(st):
    """Fire when the 45-s deadline has passed without a correct answer.

    Per the legacy CLI: the round score is computed from how much was
    revealed at timeout and SUBTRACTED from total_score. Harsh on purpose —
    pressing bb is a commitment.
    """
    sound.queue(st, "wrong")
    state = st.session_state.game_state
    word = st.session_state.round_ctx["word"]

    round_score = score_for_correct_answer(word, state.revealed_letters)
    state.total_score -= round_score
    state.rounds_failed += 1
    state.words_played.append({
        "word": word, "outcome": "failed",
        "letters_revealed": len(word) - state.revealed_letters.count("_  "),
    })
    # Stash a negative score-pop so the renderer animates the loss.
    st.session_state.score_pop = {
        "delta": -round_score,
        "from": state.total_score + round_score,
        "to": state.total_score,
        "at": st.session_state.get("_next_reveal_at") or time.time(),
    }
    for line in round_timeout_lines(word, round_score, state.total_score):
        _say(st, "assistant", line, after=CHAT_STAGGER_HOST)
    # Trigger the score animation alongside the LAST timeout line.
    st.session_state.score_pop["at"] = (
        st.session_state.get("_next_reveal_at") or time.time()
    )
    _end_answering_round(st, success=False)


# --------------------------------------------------------------------------
# Main render
# --------------------------------------------------------------------------


def render_arena(st):
    sound.flush(st)
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
    focus_chat_input(st)
    if line:
        sound.queue(st, "click")
        # Show a spinner during processing so even slow paths (LLM call)
        # feel intentional rather than frozen.
        with typing_indicator(st):
            _handle_input(st, line)
        # If _handle_input transitioned us out of playing (bb → answering,
        # or end), force one rerun so the new phase renders. Otherwise let
        # the natural script-end finish — calling st.rerun() unconditionally
        # races with the autorefresh component and can drop the user's
        # bubble before it paints.
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
    game_key = st.session_state.get("game_key", "")
    wordmark(st, level="h3")
    topbar(
        st,
        score=state.total_score,
        round_num=round_idx + 1,
        total_rounds=state.total_rounds,
        seconds_remaining=int(state.total_time),
        in_answer_mode=False,
        live=True,  # JS animates the countdown between reruns
        pop=_consume_score_pop(st),
        game_key=game_key,
    )

    # === Letter board ===
    tile_board(st, word, state.revealed_letters,
               board_key=f"{game_key}:{round_idx}:{word}")

    # === Revealed-info chips (TÜR / YAPI / KÖKEN / BİRLEŞİK) ===
    info_chips(st, st.session_state.get("revealed_info", {}))

    # === Clue ===
    clue_card(st, round_ctx["clue"])

    st.write("")

    # === Chat history (fixed-height, scrolls internally) ===
    _render_chat(st)


def _render_chat(st, *, force_snap: bool = False):
    """Shared chat-history block used by both playing and answering.

    Custom HTML bubbles (not st.chat_message) so we get full styling
    control: host gets italic Lora + teal stripe + mic avatar, player
    gets right-aligned ivory. Skips entries whose reveal_at is in the
    future — those reveal on a later rerun.

    Auto-scrolls to bottom on new messages, but respects the user's
    manual scroll-up (handled in mark_fresh_chat_messages).
    """
    chat_log = st.session_state.chat_log
    now = time.time()
    pieces = []
    for entry in chat_log:
        # Tolerate legacy 2-tuples for safety; reveal them immediately.
        if len(entry) == 2:
            role, text = entry
        else:
            role, text, reveal_at = entry[0], entry[1], entry[2]
            if reveal_at > now:
                continue
        safe = html_lib.escape(text).replace("\n", "<br>")
        if role == "system":
            pieces.append(f'<div class="lexi-chat-system">{safe}</div>')
        elif role == "assistant":
            pieces.append(
                f'<div class="lexi-chat-row lexi-chat-host">'
                f'<div class="lexi-chat-avatar">🎙️</div>'
                f'<div class="lexi-chat-bubble lexi-chat-host-bubble">{safe}</div>'
                f'</div>'
            )
        else:
            pieces.append(
                f'<div class="lexi-chat-row lexi-chat-user">'
                f'<div class="lexi-chat-bubble lexi-chat-user-bubble">{safe}</div>'
                f'</div>'
            )

    st.markdown(
        f'<div class="lexi-chat-scroll" id="lexi-chat-scroll">'
        f'{"".join(pieces)}'
        f'</div>',
        unsafe_allow_html=True,
    )
    mark_fresh_chat_messages(st, force_snap=force_snap)


def render_answering(st):
    """Answering phase: global timer paused, 45-s round timer ticking.

    Server is authoritative — `answer_deadline` is the wall-clock when
    timeout fires, recomputed on every rerun. A 1-s autorefresh keeps the
    page reruning so timeout fires even if the player goes idle. The JS
    ticker in `answer_timer` only animates the displayed digits between
    reruns; truth always comes from the server.
    """
    sound.flush(st)
    state = st.session_state.game_state

    # Defensive: if we somehow got here without a deadline set, fall back
    # to playing phase. Shouldn't happen, but better than dividing by None.
    deadline = st.session_state.get("answer_deadline")
    if deadline is None:
        st.session_state.phase = "playing"
        st.rerun()
        return

    now = time.time()
    seconds_remaining = deadline - now

    # === Authoritative timeout check ===
    if seconds_remaining <= 0:
        _handle_answering_timeout(st)
        st.rerun()
        return

    # === Process input BEFORE rendering (same pattern as render_arena) ===
    # Distinct key from arena_input — sharing the key across phases
    # caused Streamlit's widget reconciliation to drop submissions
    # ("can type but can't send"). Focus loss across the bb transition
    # is the lesser evil.
    line = st.chat_input(
        "Cevabınızı söyleyin, ipucu isteyin... (harf alamazsınız)",
        key="answering_input",
    )
    focus_chat_input(st)
    if line:
        sound.queue(st, "click")
        with typing_indicator(st):
            _handle_input(st, line, in_answer_mode=True)
        # If the round ended (correct answer), force a rerun so the new
        # phase renders. Otherwise let the natural script-end finish —
        # calling st.rerun() in the steady state races with autorefresh
        # and can drop the just-appended chat bubble.
        if st.session_state.phase != "answering":
            st.rerun()
            return
        # Recompute remaining time post-input (bb-reset moves the deadline).
        deadline = st.session_state.get("answer_deadline")
        seconds_remaining = deadline - time.time() if deadline else 0

    # Silence check (in answer mode) — same anti-immediate-fire ordering.
    _check_silence(st, in_answer_mode=True)

    round_idx = st.session_state.round_idx
    round_ctx = st.session_state.round_ctx
    word = round_ctx["word"]

    # === Header ===
    game_key = st.session_state.get("game_key", "")
    wordmark(st, level="h3")
    topbar(
        st,
        score=state.total_score,
        round_num=round_idx + 1,
        total_rounds=state.total_rounds,
        # Show the (paused) global timer alongside, dim — gives the player
        # a sense of the game-wide budget they'll resume into.
        seconds_remaining=int(state.total_time),
        in_answer_mode=True,
        pop=_consume_score_pop(st),
        game_key=game_key,
    )

    # === Big answer-phase timer pill (JS-animated) ===
    # Floor the seconds for the JS start so we never display a number
    # higher than what the server actually has. ROUND_TIME_SECONDS-1 caps
    # the visible value at 45 even though the server gave us 46s.
    visible_secs = min(ROUND_TIME_SECONDS, max(0, int(seconds_remaining)))
    # round_key changes whenever a new bb session starts — used by the JS
    # to drop stale countdown state from the previous round.
    started_at = st.session_state.get("answer_started_at") or 0
    round_key = f"{round_idx}-{int(started_at)}"
    answer_timer(
        st,
        seconds_remaining=visible_secs,
        total_seconds=ROUND_TIME_SECONDS,
        round_key=round_key,
    )

    # === Letter board (frozen — no more letter requests during bb) ===
    tile_board(st, word, state.revealed_letters,
               board_key=f"{game_key}:{round_idx}:{word}")

    # === Revealed-info chips ===
    info_chips(st, st.session_state.get("revealed_info", {}))

    # === Clue ===
    clue_card(st, round_ctx["clue"])

    st.write("")

    # === Chat ===
    _render_chat(st)


# --------------------------------------------------------------------------
# Prologue phase — pre-game small talk
# --------------------------------------------------------------------------


def render_prologue(st):
    """Pre-game chat. Player chats with the host until they type a
    ready-signal ('hazırım', 'başla', etc.); then we kick off round 1.

    Works in both Gemini and Demo modes — host.prologue_reply falls
    back to a scripted line when llm is None.
    """
    state = st.session_state.game_state

    # Header (no timer, no score yet — just branding)
    wordmark(st, level="h3")
    st.caption(
        "🎙️ Yarışma öncesi sohbet — hazır olunca **'hazırım'** yazın."
    )

    line = st.chat_input(
        "Sohbet edin ya da 'hazırım' yazın...",
        key="prologue_input",
    )
    focus_chat_input(st)
    if line:
        sound.queue(st, "click")
        # Echo the player's bubble immediately
        _say(st, "user", line)

        if host.is_ready_signal(line):
            # Bridge into round 1
            _say(
                st, "assistant",
                "Öyleyse başlayabiliriz... Şöyle derin bir nefes alın...",
            )
            _say(st, "assistant", "İlk soruyla başlıyorum öyleyse...")
            # Initialize round 0 and switch phases
            _start_round(st, 0)
            st.session_state.phase = "playing"
            st.rerun()
            return

        # Otherwise — keep chatting. Append to the LLM history and reply.
        messages = st.session_state.prologue_messages or []
        messages.append({"role": "user", "content": line})
        with typing_indicator(st):
            try:
                reply = host.prologue_reply(st.session_state.llm, messages)
            except Exception:
                reply = "Hmm, devam edelim efendim."
        _say(st, "assistant", reply)
        messages.append({"role": "assistant", "content": reply})
        st.session_state.prologue_messages = messages
        st.rerun()
        return

    # Render chat below input
    _render_chat(st)


# --------------------------------------------------------------------------
# Between-rounds transition phase — auto-advance OR wait for "devam"
# --------------------------------------------------------------------------


_CONTINUE_SIGNALS = frozenset({
    "devam", "hadi", "tabii", "evet", "d", "başla", "basla",
    "hazırım", "hazir", "hazır", "olur", "tamam",
})


def _looks_like_continue(text: str) -> bool:
    low = text.lower().strip()
    if not low:
        return False
    if low in _CONTINUE_SIGNALS:
        return True
    # Match "devam" / "hadi" / "tabii devam" / "hadi bakalım" anywhere
    toks = set(low.replace("?", "").replace("!", "").replace(".", "").split())
    return bool(toks & _CONTINUE_SIGNALS)


def render_between(st):
    """Render the inter-round transition.

    Two modes (chosen at round-end in _advance_to_next_round):
      auto — short flavor line; auto-advances after 2-4 s.
      wait — host asks; waits for player to type 'devam' / 'hadi' / etc.
             Idle 10 s → host says "Devam edelim hadi" and auto-advances.

    Timer mechanism: a mode-specific st_autorefresh (wired in
    streamlit_app.main) reruns the script; the auto-advance / idle-nudge
    checks below fire on the first rerun past their deadline. This is the
    same server-side pattern the answering phase uses. It replaced an
    earlier cross-iframe JS poller (a setInterval on window.top clicking a
    hidden button) that depended on window.top variable sharing surviving
    Streamlit's iframe churn — fragile, and silently dead on some hosts.
    """
    sound.flush(st)
    state = st.session_state.game_state
    bs = st.session_state.between_state or {}
    next_idx = bs.get("next_idx", st.session_state.round_idx + 1)
    mode = bs.get("mode", "auto")

    # === Player input FIRST ===
    # Read chat_input before the timer checks so a typed 'devam' is
    # never beaten to the punch by an autorefresh-triggered auto-advance.
    placeholder = (
        "Devam diyin ya da bir şey söyleyin..."
        if mode == "wait"
        else "Hazırlanıyoruz... ('puan' yazıp skor görebilirsiniz)"
    )
    line = st.chat_input(placeholder, key="between_input")
    focus_chat_input(st)
    if line:
        sound.queue(st, "click")
        _say(st, "user", line)
        raw = line.lower().strip()
        if raw == "puan":
            _say(st, "assistant",
                 f"Şu anki toplam puanınız: {state.total_score}")
            st.rerun()
            return
        if _looks_like_continue(line):
            _start_round(st, next_idx)
            st.session_state.phase = "playing"
            st.session_state.between_state = None
            st.rerun()
            return
        # Anything else — gentle nudge, stay in `between`.
        _say(st, "assistant",
             random.choice([
                 "'Devam' deyince geçeriz efendim...",
                 "Hazır olunca 'devam' diyin yeter...",
                 "Cevabı sıradaki sorudan sonra konuşalım — 'devam' diyin...",
             ]))
        # Reset the idle-nudge clock on any input + give a longer
        # auto-advance timeout so the host doesn't immediately yank
        # the player into the next round mid-conversation.
        if mode == "wait":
            bs["idle_nudge_at"] = time.time() + 10.0
            bs["nudged"] = False
            st.session_state.between_state = bs
        st.rerun()
        return

    # === Auto-advance check (only after no input was just submitted) ===
    now = time.time()
    auto_at = bs.get("auto_advance_at")
    if auto_at is not None and now >= auto_at:
        _start_round(st, next_idx)
        st.session_state.phase = "playing"
        st.session_state.between_state = None
        st.rerun()
        return

    # === Idle-nudge check (wait mode only) ===
    if mode == "wait":
        nudge_at = bs.get("idle_nudge_at")
        if nudge_at is not None and now >= nudge_at and not bs.get("nudged"):
            _say(st, "assistant", "Devam edelim hadi efendim...")
            bs["nudged"] = True
            # After the nudge, give the player one more beat then auto-go.
            bs["auto_advance_at"] = now + 2.5
            st.session_state.between_state = bs
            st.rerun()
            return

    # === Header (compact — no timer, score chip + round indicator) ===
    wordmark(st, level="h3")
    topbar(
        st,
        score=state.total_score,
        round_num=st.session_state.round_idx + 1,
        total_rounds=state.total_rounds,
        seconds_remaining=int(state.total_time),
        in_answer_mode=False,
        live=False,  # global timer is paused-ish during transition
        pop=_consume_score_pop(st),
        game_key=st.session_state.get("game_key", ""),
    )

    # === Chat ===
    # force_snap: the between phase reruns ~1×/s under autorefresh; without
    # forcing, the panel drifts back to the top between ticks (see
    # mark_fresh_chat_messages). It's a passive auto-advancing beat, so
    # always pinning to the bottom is the right behavior.
    _render_chat(st, force_snap=True)
