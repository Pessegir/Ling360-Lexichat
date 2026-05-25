"""Round mechanics: letter requests, hint dispatch, guess reactions.

These functions return what the host SAYS, not print it. Drivers (CLI / web)
decide how to display the result.
"""
from __future__ import annotations

import random

import editdistance
import nltk

from .data import lookup_definition
from .nlp import get_synonym_phrase, similar_word_hint, synonym_hint


# --------------------------------------------------------------------------
# Letter request
# --------------------------------------------------------------------------


def letter_request(word, revealed_letters):
    """Reveal one random unrevealed letter. Mutates revealed_letters in place."""
    word = word.strip()
    if len(revealed_letters) != len(word):
        revealed_letters[:] = ["_  "] * len(word)

    if "_  " not in revealed_letters:
        return revealed_letters, "all-revealed"

    unrevealed = [i for i, v in enumerate(revealed_letters) if v == "_  "]
    idx = random.choice(unrevealed)
    revealed_letters[idx] = word[idx]
    return revealed_letters, "ok"


# --------------------------------------------------------------------------
# Hint dispatcher — returns what to say (driver renders it)
# --------------------------------------------------------------------------


def _hint_example(round_idx, example_sentences):
    """Return an example-sentence hint, or None if no usable example exists."""
    ex = example_sentences[round_idx]
    if not ex or ex == "None" or "None" in ex.strip().split():
        return None
    return ["Örnek cümle verebilirim belki...", ex]


def _hint_compound_or_def(round_idx, compound_list, additional_defs, definition_list):
    if compound_list[round_idx] != "None":
        return [f"Efendim buna dikkat... {compound_list[round_idx]}"]
    if additional_defs[round_idx] and additional_defs[round_idx] != "None":
        return [f"Şöyle de tanımlanabilir...\n{additional_defs[round_idx]}"]
    return [f"Biraz daha düşünün efendim, tekrar okuyun soruyu...\n{definition_list[round_idx]}"]


def _hint_synonym(round_idx, synonym_list):
    syn_phrase = get_synonym_phrase(synonym_list, round_idx)
    if syn_phrase == "None":
        return None
    return ["Hmm...", syn_phrase, "Düşünün biraz daha..."]


def give_hint(chance_list, round_idx, word, example_sentences, compound_list,
              additional_defs, definition_list, synonym_list):
    """Dispatch a hint based on a randomized chance_list. Mutates chance_list.

    Returns a list of message strings. If the dispatched hint type has no
    usable content (e.g. example sentence is "None"), tries other types in
    a fallback order before giving up with a generic line.
    """
    if not chance_list:
        return [random.choice([
            "Maalesef, daha fazla yardımcı olamam...",
            "Efendim, daha ne diyeyim ki... Bulursunuz siz bunu...",
            "Başka bir şey gelmiyor ki aklıma...",
            "Maalesef..! Odaklanın, bulursunuz...\nSoruyu bir daha okuyun isterseniz...",
        ])]

    chance_num = random.choice(chance_list)
    msgs: list[str] = []

    if chance_num % 3 == 0:
        result = _hint_example(round_idx, example_sentences)
        if result:
            msgs = result
            for v in (3, 9):
                if v in chance_list:
                    chance_list.remove(v)
        else:
            # No example available — fall through to compound/def hint instead
            msgs = _hint_compound_or_def(round_idx, compound_list, additional_defs, definition_list)
            for v in (3, 9, 5, 25, 65):
                if v in chance_list:
                    chance_list.remove(v)

    elif chance_num % 5 == 0:
        msgs = _hint_compound_or_def(round_idx, compound_list, additional_defs, definition_list)
        for v in (5, 25, 65):
            if v in chance_list:
                chance_list.remove(v)

    elif chance_num % 2 == 0:
        result = _hint_synonym(round_idx, synonym_list)
        if result:
            msgs = result
            for v in (2, 4):
                if v in chance_list:
                    chance_list.remove(v)
        else:
            # No synonyms — fall back to compound/def
            msgs = _hint_compound_or_def(round_idx, compound_list, additional_defs, definition_list)
            for v in (2, 4, 5, 25, 65):
                if v in chance_list:
                    chance_list.remove(v)

    elif chance_num % 7 == 0:
        result = _hint_example(round_idx, example_sentences)
        if result:
            msgs = ["Hmm... Belki bu yardımcı olabilir...", result[1]]
        else:
            msgs = _hint_compound_or_def(round_idx, compound_list, additional_defs, definition_list)
        syn = _hint_synonym(round_idx, synonym_list)
        if syn:
            msgs.append("Ayrıca...")
            msgs.append(syn[1])
        if 7 in chance_list:
            chance_list.remove(7)
        msgs.append("Odaklanırsanız bulursunuz bence... Tekrar okuyun...")

    # Final guard: if msgs ended up empty for any reason, give a generic line
    if not msgs:
        msgs = ["Biraz daha düşünün efendim, tekrar okuyun soruyu...",
                definition_list[round_idx]]

    return msgs


# --------------------------------------------------------------------------
# Guess reaction (returns string OR None — None means "not handled, fall through to LLM")
# --------------------------------------------------------------------------


_TEACH_DEFINITION_LINES = [
    "Hayır efendim, '{w}' '{d}' demek; aradığımız bu değil...",
    "Olmadı, '{w}' '{d}' anlamına gelir... Bizim aradığımız başka...",
    "Yakın değil efendim, '{w}' demek '{d}' demek; tekrar düşünelim...",
    "'{w}' '{d}' anlamında ama bizim sorduğumuz bu değil...",
]

_TEACH_SYNONYM_LINES = [
    "Hayır efendim, '{w}' kelimesi {s} gibi sözcüklerle yakın anlamlı; bizim aradığımız bu değil...",
    "Olmadı, '{w}' demek aşağı yukarı {s} gibi bir şey... Aradığımız başka...",
    "'{w}' kelimesini {s} ile yan yana koyabiliriz ama bizim sorduğumuz bu değil...",
]

# Definition handling: use as-is up to _DEF_LENGTH_CAP; gracefully
# truncate at a word boundary up to _DEF_HARD_LIMIT; beyond that fall
# back to a synonym list. Calibrated on real gts entries — most words
# (huysuz=28, melun=42) fit comfortably; longer ones (kitap=92,
# cumhuriyet=133) truncate cleanly.
_DEF_LENGTH_CAP = 120
_DEF_HARD_LIMIT = 220


def _shorten_definition(text):
    """Return a host-readable definition string, or None if unusable.

    - Up to _DEF_LENGTH_CAP: returned as-is.
    - Up to _DEF_HARD_LIMIT: truncated at the last space before the cap,
      with "..." appended.
    - Beyond _DEF_HARD_LIMIT: too long to read aloud, return None.
    """
    if not text:
        return None
    text = text.strip()
    if len(text) <= _DEF_LENGTH_CAP:
        return text
    if len(text) > _DEF_HARD_LIMIT:
        return None
    cut = text.rfind(" ", 0, _DEF_LENGTH_CAP)
    if cut < _DEF_LENGTH_CAP * 0.6:  # no good break point — give up
        return None
    return text[:cut].rstrip(",;:") + "..."


# Tokens that, when present, suggest the player is asking what a word
# means rather than guessing. "neydi", "nedir", "neymiş" are single-token
# triggers; the "ne demek / ne anlama / ..." patterns need a paired token.
_DEF_QUESTION_TRIGGERS = {"neydi", "nedir", "neymiş"}
_NE_PARTNERS = {"demek", "demekti", "anlam", "anlama", "anlamı", "anlami"}
# Tokens to skip when extracting the target word from a definition question.
_QUESTION_SKIP_TOKENS = {
    "ne", "neydi", "nedir", "neymiş", "demek", "demekti", "demekmiş",
    "anlam", "anlama", "anlamı", "anlami", "ya", "ki", "peki", "hani",
    "yahu", "be", "?", ".", ",", "...", "!", "''", '"',
}


def _is_definition_question(tkn):
    """True if the input looks like 'X neydi?' / 'X ne demek?' / 'ne demek X?'."""
    if any(t in tkn for t in _DEF_QUESTION_TRIGGERS):
        return True
    if "ne" in tkn and any(t in tkn for t in _NE_PARTNERS):
        return True
    return False


def _extract_target_word(tkn, gts_index):
    """Find the word in tkn the player is most likely asking about.

    Strips question keywords, then returns the FIRST remaining token
    if it's in the dictionary. If the first non-skip token isn't a
    dictionary word, returns None — we'd rather not answer than guess
    that the player meant some other word later in the sentence.
    """
    if gts_index is None:
        return None
    for t in tkn:
        low = t.lower()
        if low in _QUESTION_SKIP_TOKENS:
            continue
        if len(t) < 3 or not t.isalpha():
            continue
        return t if low in gts_index else None
    return None


_ANSWER_DEFINITION_LINES = [
    "Efendim, '{w}' '{d}' demektir.",
    "'{w}' kelimesi '{d}' anlamına gelir efendim.",
    "'{w}' şu anlama gelir: '{d}'.",
    "Şöyle ki efendim — '{w}' '{d}' demek.",
]

_ANSWER_SYNONYM_LINES = [
    "Efendim, '{w}' kelimesi {s} gibi anlamlara gelir.",
    "'{w}' kelimesini {s} ile yakın anlamlı sayabiliriz efendim.",
]


def _build_question_answer(target, gts_index, wordnet):
    """Compose a host line that ANSWERS a definition question (no rejection)."""
    if gts_index is not None:
        d = _shorten_definition(lookup_definition(gts_index, target))
        if d:
            return random.choice(_ANSWER_DEFINITION_LINES).format(w=target, d=d)
    if wordnet is not None:
        try:
            syns = synonym_hint(wordnet, target)
        except Exception:
            syns = "None"
        if isinstance(syns, list) and syns:
            picks = random.sample(syns, min(3, len(syns)))
            return random.choice(_ANSWER_SYNONYM_LINES).format(
                w=target, s=", ".join(picks),
            )
    return None


def _build_teaching_line(raw, gts_index, wordnet):
    """Compose a host line that gently rejects `raw` and explains it.

    Tries definition first (if short enough), then synonyms. Returns None
    if the word isn't in gts.json or wordnet — caller falls back to the
    generic wrong-guess line.
    """
    if gts_index is not None:
        definition = _shorten_definition(lookup_definition(gts_index, raw))
        if definition:
            return random.choice(_TEACH_DEFINITION_LINES).format(
                w=raw, d=definition,
            )

    if wordnet is not None:
        try:
            syns = synonym_hint(wordnet, raw)
        except Exception:
            syns = "None"
        if isinstance(syns, list) and syns:
            picks = random.sample(syns, min(3, len(syns)))
            return random.choice(_TEACH_SYNONYM_LINES).format(
                w=raw, s=", ".join(picks),
            )

    return None


def react_to_guess(raw, round_idx, word, tkn, history, synonym_list,
                   cleaned_tokens, sorted_keywords, *,
                   gts_index=None, wordnet=None, in_answer_mode=False):
    """Return a host reaction string for a non-answer guess.

    Returns None if the input looks like chatter and should be handed to the
    LLM host fallback.

    Educational lines (definition / synonym lookup) fire in three cases:
      1. Player asks "X neydi?" / "X ne demek?" — fires in any phase.
      2. Player insists on the same wrong real word twice — fires in
         playing mode only (replaces the "bunu zaten söylediniz" nudge).
      3. Wrong real-word guess in answering (bb) mode — fires 50% of the
         time. Playing-mode wrong guesses get the generic brushoff.
    """
    string_familiarity = similar_word_hint(word, 3, cleaned_tokens, sorted_keywords)
    list_synonym = synonym_list[round_idx] if synonym_list[round_idx] != "None" else []

    # === Definition question — "X neydi?" / "ne demek X?" ===
    # Highest priority: if the player is explicitly asking what a word
    # means, answer the question instead of treating it as a guess.
    if _is_definition_question(tkn):
        target = _extract_target_word(tkn, gts_index)
        # Don't spoil the actual answer: if the target is the round's word,
        # fall through and let the LLM host handle it.
        if target and target.lower() != word.lower():
            ans = _build_question_answer(target, gts_index, wordnet)
            if ans:
                return ans

    if raw in string_familiarity and raw in list_synonym:
        return "Hadi bir daha, çok çok yaklaştınız..."
    if raw in string_familiarity or any(it in string_familiarity for it in tkn):
        return "Çok yaklaştınız, hadi birkaç harf değiştirin."
    if raw == "":
        return random.choice([
            "Bir harf alabilirsiniz belki...", "...", "Zamana dikkat!",
            "Zaman akıyor efendim, bir harf mi istesek..?",
        ])
    if raw in list_synonym or any(it in list_synonym for it in tkn):
        return random.choice([
            "Bu değil efendim, öteki... Eş anlamlısı lazım bize...",
            "Hadi bir daha deneyin... Bu sefer eş anlamlısını söyleyin...",
            f"{raw} değil de... Bir benzeri...\nNeydi o?\nBize eş anlamlısı lazım...",
            "Yaklaştınız... Aynı anlama gelen başka kelime daha var...\nNeydi o..?",
        ])
    if raw in history or any(it in history for it in tkn):
        # Insistence: in playing mode, if the player keeps repeating a
        # real Turkish word, teach them what it actually means instead
        # of just nudging "bunu zaten söylediniz". In answering mode the
        # 50% rule below already handles this.
        if not in_answer_mode:
            teach = _build_teaching_line(raw, gts_index, wordnet)
            if teach:
                return teach
        return "Bunu zaten söylediniz, tekrar düşünün..."

    # "Çok yaklaştınız" feedback. Two conditions, both must hold:
    #   1. Absolute distance is small enough for the word's length:
    #      - len ≤ 5 → distance must be ≤ 1 (a single typo)
    #      - len 6-8 → distance ≤ 2
    #      - len 9+  → distance ≤ 3
    #   2. Distance/length ratio ≤ 0.4 (so 'olun' vs 'ozan' at 50% won't
    #      qualify even though absolute is 2). This is the key fix —
    #      the original "≤2 flat" rule called every short word with two
    #      different letters "close", which felt cheap.
    if len(tkn) == 1 and len(raw) >= 3 and len(word) >= 3:
        dist = editdistance.distance(raw, word)
        if len(word) <= 5:
            abs_max = 1
        elif len(word) <= 8:
            abs_max = 2
        else:
            abs_max = 3
        ratio = dist / len(word)
        if dist <= abs_max and ratio <= 0.4:
            return random.choice([
                "Çok yaklaştınız, acaba bir iki harf mi değiştirsek..?",
                f"\"{raw}\" doğru muydu yoksa birkaç harf mi farklıydı?",
                "Yaklaştınız efendim, harflere dikkat...",
            ])

    # Short conversational acknowledgments — these are NOT guesses. Let
    # the LLM handle them with full chat context (e.g. "ver" after the
    # host just offered an example sentence).
    SHORT_CONVERSATIONAL = {
        "ver", "evet", "olur", "tamam", "hayır", "yok", "belki",
        "neden", "niye", "yani", "yine", "iyi", "peki", "tabii",
    }
    if raw in SHORT_CONVERSATIONAL:
        return None

    # Real guess attempts: 4+ chars, single token. Generic "wrong guess".
    if len(tkn) == 1 and " " not in raw and 4 <= len(raw) <= 15:
        # In answering (bb) mode, 50% chance to teach the player what
        # their wrong guess actually means. In playing mode we save the
        # educational lines for explicit questions ("X neydi?") or for
        # repeated insistence — those branches fire above. A first-time
        # wrong guess in playing mode just gets the generic brushoff.
        if in_answer_mode and random.random() < 0.5:
            teach = _build_teaching_line(raw, gts_index, wordnet)
            if teach:
                return teach
        return random.choice([
            "Süre akıyor, tekrar deneyin...",
            "Biraz daha düşünün isterseniz...",
            "Ah, ah! Keşke bir harf daha alsaydınız...",
            "Zamana dikkat! Zamana dikkat..!",
            "Değil, değil... Zaman akıyor efendim...",
            "Hayır, hayır... Dikkatlice tekrar okuyun isterseniz soruyu...",
        ])

    return None  # → driver routes to LLM host fallback


# --------------------------------------------------------------------------
# Pre-round flavor lines
# --------------------------------------------------------------------------


# Atmospheric pre-round lines that don't depend on per-word metadata.
# Used in demo mode when batch_word_metadata couldn't fill function /
# structure / origin (all "None"), so the patter doesn't deflate to just
# "round N / N points / hmm".
_NEUTRAL_PRE_ROUND_TEASERS = [
    "Bakalım bu sefer ne çıkacak karşımıza efendim...",
    "Bu kelime üzerinde biraz duralım, bakalım açacak mı kendini...",
    "Hadi şöyle bir bakalım buna efendim...",
    "Sıradaki kelimemiz biraz oyunbaz olabilir, dikkatli olun...",
    "Bakalım hangi gizemi saklıyor bu sefer...",
    "Sıkı durun efendim, sıradaki kelime ilginç...",
    "Bu kelime de bir başka türlü efendim, hazır olun...",
    "Kalem kâğıt yanınızda olsun derim, bakalım ne çıkacak...",
    "Hazır mısınız efendim, sahne sizin...",
    "Şöyle bir nefes alalım, sonra dalıyoruz kelimeye...",
]


def pre_info_messages(question_number, total_score, round_idx,
                      function_list, structure_list, origin_list):
    """Return a list of (text, sleep_after) tuples for the pre-round chatter."""
    letter_count = ((question_number - 1) // 2) + 4
    question_point = letter_count * 100

    list_1 = [
        f"{letter_count} harfli sorular ile devam ediyoruz efendim...",
        f"{question_number}. sorudayız...",
        f"{question_number}. soruya geldik...",
    ]
    list_2 = [
        f"Şu an {total_score} puandasınız, bu soru ile {total_score + question_point} puana ulaşabilirsiniz...",
        f"Sıradaki soru ile {question_point} puan sizi bekliyor efendim...",
        f"Sıradaki soru {question_point} puan değerinde...",
    ]
    mumbling = ["Hmm...", "Bakalım...", "Tamam...", "Şimdi bakalım...", "Şöyle ki...", "Hıh...", "Peki..."]
    list_first = [
        "Tertemiz bir 400 puanla başlayabiliriz efendim...",
        "Güzel bir başlangıç yaparız umarım bu soruyla, dur bakalım...",
        "Şöyle silkinelim ve ilk soruyla başlayalım...",
    ]

    f_type = function_list[round_idx]
    s_type = structure_list[round_idx]
    root = origin_list[round_idx]

    function_phrases = [
        f"Bu kelime bir {f_type}...",
        f"Sıradaki kelime bir {f_type}...",
        f"Bu bir {f_type}...",
    ]
    structure_phrases = [
        f"Hmm, {s_type}den oluşan bir sözcük ile devam ediyoruz...",
        f"Sıradaki bir {s_type}, görelim neymiş...",
        f"Bu bir {s_type}... Bakalım neymiş...",
        f"Sonraki sözcük, {s_type}den oluşmakta...",
    ]
    question_info = [
        f"Sıradaki kelime {root}",
        f"Bu kelime sanırım {root}.. Dur bakalım çıkarabilecek misiniz...",
        f"Kelimenin kökenine baktığımda...\nhmm sanırım {root} olmalı",
        f"Bu kelime, dilimize {root} bir kelimeden yerleşmiş.",
    ]

    msgs: list[tuple[str, float]] = []

    if question_number == 1:
        msgs.append((random.choice(list_first), 0.5))
        if f_type != "None":
            msgs.append((f"Bu kelime bir {f_type}...", 0.5))
        msgs.append((random.choice(mumbling), 1.0))
        if s_type != "None":
            msgs.append((f"Bu bir {s_type}... Bakalım neymiş...", 0))
        elif f_type == "None":
            # No per-word metadata at all (demo mode) — add one atmospheric
            # teaser so the opening doesn't feel skeletal.
            msgs.append((random.choice(_NEUTRAL_PRE_ROUND_TEASERS), 0))
        return msgs

    msgs.append((random.choice(list_1), 1.0))
    msgs.append((random.choice(list_2), 1.2))
    msgs.append((random.choice(mumbling), 1.0))
    if f_type != "None":
        msgs.append((random.choice(function_phrases), 0))
    elif random.random() < 0.5:
        # Demo fallback: half the time, fill the function-phrase slot
        # with a content-free teaser so patter has texture without
        # claiming anything about the word.
        msgs.append((random.choice(_NEUTRAL_PRE_ROUND_TEASERS), 0))

    hint_chance = random.randint(1, 5)
    if hint_chance % 4 == 0 and root != "None":
        msgs.append((random.choice(question_info), 1.0))
    if hint_chance % 2 == 0 and s_type != "None":
        msgs.append((random.choice(structure_phrases), 1.0))

    return msgs


# --------------------------------------------------------------------------
# Round-end scoring
# --------------------------------------------------------------------------


def score_for_correct_answer(word, revealed_letters):
    """Points awarded for a correct answer: 100 per UNREVEALED letter.

    Mathematically equivalent to the legacy formula
        (LetterRequest(word).count("_  ") + 1) * 100
    where LetterRequest reveals one extra letter as a side effect, then
    counts blanks, then adds 1. The side-effect-reveal subtracts one
    blank; the +1 adds it back. Net: blank_count * 100 (using the
    pre-call value).

    Examples (word "enik", 4 letters):
      - 0 letters revealed → 4 blanks → 400 pts
      - 1 letter revealed  → 3 blanks → 300 pts
      - 3 letters revealed → 1 blank  → 100 pts
    """
    if not revealed_letters:
        return len(word) * 100
    blank_count = revealed_letters.count("_  ")
    return blank_count * 100


def correct_answer_celebration(word, round_score, *, clean: bool = False):
    """Host's win line. `clean=True` means the player got the answer
    without ever revealing a letter — fires a richer 'tek hamlede!'
    bank so the moment lands.
    """
    if clean:
        return random.choice([
            f"İşte bu efendim! Tek harf bile almadan {word} — alkışlıyorum, {round_score} puan tertemiz!",
            f"Helal valla efendim! Hiç yardım almadan {round_score} puan — böyle olmalı işte...",
            f"Müthiş! {word}, ne bir harf ne bir ipucu — tek vuruşta {round_score} puan, harika!",
            f"Bravo bravo, resital gibi! {round_score} puan ve hiç harf harcamadınız efendim...",
            f"Tek hamlede {round_score} efendim — bu nasıl bir keskinlik, doğrusu hayran kaldım...",
            f"İşte usta işi! {word}, tek seferde — {round_score} puanı saygıyla kasaya...",
        ])
    return random.choice([
        f"Tebrik ederim efendim {word} doğru cevap ve size {round_score} puan kazandırıyor...",
        f"Bir {round_score} puan geliyor...",
        f"Bu soruyla birlikte toplam puanınıza bir {round_score} puan daha eklediniz...",
        f"{round_score} puan cepte",
        f"Tertemiz bir {round_score} puan...",
        f"{round_score} puanı kasamıza ekliyoruz...",
        f"{word}, size {round_score} kazandırıyor",
    ])


def round_timeout_lines(word, round_score, total_score):
    """Lines shown when 45-s round timer expires."""
    return [
        "Üzgünüm süreniz bitti, bakalım neymiş yanıt...",
        word,
        random.choice([
            f"Bu soru size {round_score} puan kaybettirdi... Ama olsun toparlayabiliriz hâlâ...",
            f"Ah, ah... {total_score} puana geriledik...\nMoral bozmak yok devam edelim...",
        ]),
    ]


# Tier 1: gentle teases for the first couple of reminders.
_ALMOST_HAD_IT_GENTLE = [
    "Çoktan söylediniz bile efendim, bir tek \"bb\" basmanız kalmıştı...",
    "Az önce ne demiştiniz hatırlıyor musunuz..?",
    "Az önce çıktı sanki ağzınızdan, bir daha gelir mi acaba?",
    "Hatırlayın, biraz önce ucundan dönmüştü...",
    "İpin ucunu bir kere yakaladınız efendim, bırakmayın...",
    "Söylediğinizi söylemiştiniz, bir de \"bb\" deyiverin...",
]

# Tier 2: pointed insistence, when the player keeps ignoring the answer
# they typed several turns ago.
_ALMOST_HAD_IT_INSISTENT = [
    "Az önce ne dediniz, bir daha söyleyin..?",
    "Fazla uzaklaşmayın efendim, çok yakındaydık...",
    "Başka yere gitmeyin, doğru kelimeyi söylediniz az önce...",
    "Sırf \"bb\" demek için bekliyorum efendim, hadi şu kelimeyi tekrarlayın...",
    "Bir daha söyleyin lütfen, ben \"bb\"yi duyacağım...",
    "İpin ucu hâlâ elinizde efendim — bırakmayın da kaçırmayın...",
    "Ah, ah, az önce söylediğiniz şey... Hatırlamaya çalışın...",
]


def almost_had_it_reminder(reminded_count: int = 0):
    """Teasing line for the player who said the answer but didn't press bb.

    reminded_count: how many times we've already reminded them this round.
    0-2 → gentle bank. 3+ → insistent bank.
    """
    bank = _ALMOST_HAD_IT_INSISTENT if reminded_count >= 2 else _ALMOST_HAD_IT_GENTLE
    return random.choice(bank)


# Meme/absurd replies for when the player types gibberish (≤3 chars, not a
# game keyword, not a conversational ack). Kept rare on purpose — the
# comedy is in the surprise.
_NONSENSE_MEMES = [
    "Cemil olabilir mi?",
    "Ne dersiniz, Cemil olabilir mi?",
    "Belki Yıldız Tilbe'den bir şarkı arıyorsunuzdur..?",
    "Hmm, klavyenize bir şey mi düştü efendim?",
    "Kedinin pati izi mi bu, yoksa stratejik bir tahmin mi?",
    "Şifrenizi mi giriyorsunuz, yoksa cevabı mı arıyorsunuz?",
    "Aman ha, telefonunuzu sallamadan yazın efendim...",
    "Köpek mi geçti klavyeden..?",
    "Bu bir Mors alfabesi mi, yoksa şifre mi?",
    "Klavyeyi yumruklamak çözüm değil efendim...",
    "Yorgunluktan herhalde, bir kahve içip dönelim mi?",
]


def nonsense_meme():
    """Funny absurd reply for repeated gibberish input."""
    return random.choice(_NONSENSE_MEMES)


_REPETITION_NUDGES = [
    "Kurtulun ondan efendim, başka bir kelime düşünün...",
    "Bu değil işte, unutun gitsin onu...",
    "Aynı kelimeyle çıkış yok efendim, başka bir şey deneyin...",
    "Israrcı oldu epey... Vazgeçin de bir başka kelime düşünelim...",
    "Israr etmeyin efendim, bu o değil...",
]


def repetition_nudge():
    """Reply when the player keeps typing the same wrong thing (3+ times)."""
    return random.choice(_REPETITION_NUDGES)


def end_game_lines(score, username, ran_out_of_time):
    if ran_out_of_time:
        return random.choice([
            f"Süremiz doldu efendim. Yarışmayı {score} puanla tamamladınız.",
            f"Ah, zaman acımasız... {score} puanda kaldık efendim.",
        ])
    if score >= 8500:
        return random.choice([
            f"Tebrik ederim efendim yarışmayı {score} gibi harika bir puanla tamamladınız...",
            f"Kasamız {score} puana çıkıyor ve {username} yarışmayı bu müthiş puanla bitiriyor...\nTebrikler efendim...",
        ])
    if score >= 7000:
        return random.choice([
            f"Sizi tebrik ederim efendim... Belli ki bugün zor sorular denk gelmiş...\nYine de yarışmayı {score} gibi güzel bir puanla tamamladınız...",
            f"{score} puan... Bu zor sorular için gayet iyi bir sonuçla yarışmayı tamamladınız...\nTebrik ederim...",
        ])
    return random.choice([
        f"Son soru ile birlikte puanımızı {score} puana çıkarttık...\nBelki hedeflediğimiz değildi ancak üzülmeyin tekrar denersiniz...\n\nKapımız size her zaman açık...",
        f"Yarışmayı tamamladık...\n{score} puanın suçunu basiret bağlanmasına atabiliriz\nve sizi aramızda tekrar görmeyi çok isteriz...",
    ])
