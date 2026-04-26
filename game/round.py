"""Round mechanics: letter requests, hint dispatch, guess reactions.

These functions return what the host SAYS, not print it. Drivers (CLI / web)
decide how to display the result.
"""
from __future__ import annotations

import random

import editdistance
import nltk

from .nlp import get_synonym_phrase, similar_word_hint


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


def give_hint(chance_list, round_idx, word, example_sentences, compound_list,
              additional_defs, definition_list, synonym_list):
    """Dispatch a hint based on a randomized chance_list. Mutates chance_list.

    Returns a list of message strings. Driver prints them with whatever
    pacing/formatting it wants.
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
        msgs.append("Örnek cümle verebilirim belki...")
        msgs.append(example_sentences[round_idx])
        for v in (3, 9):
            if v in chance_list:
                chance_list.remove(v)

    elif chance_num % 5 == 0:
        if compound_list[round_idx] != "None":
            msgs.append(f"Efendim buna dikkat... {compound_list[round_idx]}")
        elif additional_defs[round_idx] and additional_defs[round_idx] != "None":
            msgs.append(f"Şöyle de tanımlanabilir...\n{additional_defs[round_idx]}")
        else:
            msgs.append(f"Biraz daha düşünün efendim, tekrar okuyun soruyu...\n{definition_list[round_idx]}")
        for v in (5, 25, 65):
            if v in chance_list:
                chance_list.remove(v)

    elif chance_num % 2 == 0:
        msgs.append("Hmm...")
        syn_phrase = get_synonym_phrase(synonym_list, round_idx)
        if syn_phrase != "None":
            msgs.append(syn_phrase)
        for v in (2, 4):
            if v in chance_list:
                chance_list.remove(v)
        msgs.append("Düşünün biraz daha...")

    elif chance_num % 7 == 0:
        msgs.append("Hmm... Belki bu yardımcı olabilir...")
        msgs.append(example_sentences[round_idx])
        msgs.append("Ayrıca...")
        syn_phrase = get_synonym_phrase(synonym_list, round_idx)
        if syn_phrase != "None":
            msgs.append(syn_phrase)
        if 7 in chance_list:
            chance_list.remove(7)
        msgs.append("Odaklanırsanız bulursunuz bence... Tekrar okuyun...")

    return msgs


# --------------------------------------------------------------------------
# Guess reaction (returns string OR None — None means "not handled, fall through to LLM")
# --------------------------------------------------------------------------


def react_to_guess(raw, round_idx, word, tkn, history, synonym_list,
                   cleaned_tokens, sorted_keywords):
    """Return a host reaction string for a non-answer guess.

    Returns None if the input looks like chatter and should be handed to the
    LLM host fallback.
    """
    string_familiarity = similar_word_hint(word, 3, cleaned_tokens, sorted_keywords)
    list_synonym = synonym_list[round_idx] if synonym_list[round_idx] != "None" else []

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
        return "Bunu zaten söylediniz, tekrar düşünün..."

    if len(tkn) == 1 and editdistance.distance(raw, word) <= 2 and round_idx >= 6:
        return random.choice([
            "Çok yaklaştınız, acaba bir iki harf mi değiştirsek..?",
            f"{raw} doğru muydu yoksa birkaç harf mi farklıydı?",
        ])

    if len(tkn) == 1 and " " not in raw and len(raw) <= 15:
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
        return msgs

    msgs.append((random.choice(list_1), 1.0))
    msgs.append((random.choice(list_2), 1.2))
    msgs.append((random.choice(mumbling), 1.0))
    if f_type != "None":
        msgs.append((random.choice(function_phrases), 0))

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
    """Points awarded when player answers correctly: (unrevealed letters + 1) * 100."""
    # +1 because an unanswered word with no letters revealed = full points
    blank_count = revealed_letters.count("_  ")
    return (blank_count + 1) * 100 if revealed_letters else len(word) * 100


def correct_answer_celebration(word, round_score):
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
