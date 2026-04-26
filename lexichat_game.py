# -*- coding: utf-8 -*-
"""LEXI-CHAT — CLI driver.

Game engine lives in `game/`. This file is the terminal-specific I/O layer:
- print/input/threading
- input queue for non-blocking reads
- countdown timer thread
- screen banner

The web app (Phase 4) reuses everything in `game/` and provides its own driver.
The legacy 2023 version is preserved at lexichat_game_legacy.py.

Run with:  python lexichat_game.py
"""
from __future__ import annotations

import os
import queue
import random
import sys
import threading
import time

import nltk

from llm_client import LLMError, load_client

from game import host
from game.config import (
    APP_NAME, ROUND_TIME_SECONDS, SILENCE_MAX_SECONDS, SILENCE_MIN_SECONDS,
    STUCK_KEYWORDS, TOTAL_GAME_TIME, TOTAL_ROUNDS, WORD_FILES, WORD_LENGTHS,
)
from game.data import (
    compound_hints, example_sentences_from_gts, load_corpus_tokens, load_gts,
    merge_lists, select_words_and_meanings,
)
from game.nlp import (
    ensure_nltk, function_of_words, get_synonym_phrase, load_morphology,
    load_wordnet, synonym_hint,
)
from game.round import (
    correct_answer_celebration, end_game_lines, give_hint, letter_request,
    pre_info_messages, react_to_guess, round_timeout_lines,
    score_for_correct_answer,
)
from game.state import GameState
from game.text_utils import apply_unicode_transform


# --------------------------------------------------------------------------
# Non-blocking stdin: one thread reads input() forever and enqueues lines.
# --------------------------------------------------------------------------


_INPUT_QUEUE: "queue.Queue[str]" = queue.Queue()
_INPUT_THREAD_STARTED = False


def _stdin_reader_loop():
    while True:
        try:
            line = input()
        except (EOFError, Exception):
            time.sleep(0.1)
            continue
        _INPUT_QUEUE.put(line)


def _ensure_input_thread():
    global _INPUT_THREAD_STARTED
    if _INPUT_THREAD_STARTED:
        return
    threading.Thread(target=_stdin_reader_loop, daemon=True).start()
    _INPUT_THREAD_STARTED = True


def _wait_for_input(prompt, timeout=None):
    """Print prompt, wait up to `timeout` seconds for a line. Returns str or None."""
    _ensure_input_thread()
    while not _INPUT_QUEUE.empty():
        try:
            _INPUT_QUEUE.get_nowait()
        except queue.Empty:
            break
    print(prompt, end="", flush=True)
    try:
        return _INPUT_QUEUE.get(timeout=timeout)
    except queue.Empty:
        return None


# --------------------------------------------------------------------------
# Pretty-print helpers
# --------------------------------------------------------------------------


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def show_head():
    head = r"""

  _        _______          _________     _______           _______ _________
  ( \      (  ____ \|\     /|\__   __/    (  ____ \|\     /|(  ___  )\__   __/
  | (      | (    \/( \   / )   ) (       | (    \/| )   ( || (   ) |   ) (
  | |      | (__     \ (_) /    | | _____ | |      | (___) || (___) |   | |
  | |      |  __)     ) _ (     | |(_____)| |      |  ___  ||  ___  |   | |
  | |      | (       / ( ) \    | |       | |      | (   ) || (   ) |   | |
  | (____/\| (____/\( /   \ )___) (___    | (____/\| )   ( || )   ( |   | |
  (_______/(_______/|/     \|\_______/    (_______/|/     \||/     \|   )_(

    """
    for _ in range(10):
        print(head)
        time.sleep(0.3)
        clear_screen()
    print(head)


def start_command():
    instructions = f"""
                                                        {APP_NAME} Kelime Oyununa Hoşgeldiniz.

{APP_NAME}, basit doğal dil işleme teknikleriyle ve Google Gemini yapay zekası ile desteklenmiş bir kelime tahmin etme oyunudur.

Oyuna başlamadan önce lütfen kuralları okuyunuz:

1- Bu oyun "Kelime Oyunu"ndan ilham alınarak hazırlanmıştır.
2- 5 dakika içinde 4 harfliden 10 harfliye toplam 14 soru.
3- Her harf 100 puan; maksimum 9800 puan.
4- "h" yazarak harf talep edebilirsiniz (her harf -100 puan).
5- Mesaj kutusundan kelime hakkında bilgi talep edebilirsiniz.
6- Tahminleriniz ya da puan durumunuza göre sunucu ek ipuçları verebilir.
7- Yanıt vermek için önce "bb" yazıp süreyi durdurun.
8- 14 soru bittikten ya da süre dolduktan sonra oyun sonlanır.

                                                                    KEYİFLİ OYUNLAR
"""
    print(instructions)
    time.sleep(2)
    print("\nOyunu başlatmak için \"Ve kayıt\" yazabilirsiniz.\n")
    while True:
        start_com = input("->: ")
        if start_com.strip().lower() == "ve kayıt":
            break
        print("Henüz oyunda değilsiniz, başlamak için \"Ve kayıt\" yazınız.")
    name = input("Lütfen isminizi girin: ")
    address = input(f"Size nasıl hitap etmemi istersiniz? {name} (hanım/bey): ")
    return name + " " + address.lower()


# --------------------------------------------------------------------------
# Prologue (small talk before round 1)
# --------------------------------------------------------------------------


def cli_prologue(llm, username):
    print(f"Merhaba {username}, {APP_NAME}'e hoşgeldiniz!")
    messages = [{"role": "user", "content": "Merhaba"}]
    reply = host.prologue_reply(llm, messages)
    print(reply)

    print("Hazır olduğunuzda \"hazırım\" yazmanız yeterli, oyun otomatik başlayacak.")

    while True:
        text = _wait_for_input("--> ", timeout=None) or ""
        if host.is_ready_signal(text):
            print("Öyleyse başlayabiliriz... Şöyle derin bir nefes alın...")
            break
        messages.append({"role": "user", "content": text})
        reply = host.prologue_reply(llm, messages)
        print(reply)
        messages.append({"role": "assistant", "content": reply})

    time.sleep(1)
    print("\nİlk soruyla başlıyorum öyleyse...\n")


# --------------------------------------------------------------------------
# Round mechanics — CLI driver wraps the pure logic in `game/round.py`
# --------------------------------------------------------------------------


def cli_round_time(state, round_idx, word, word_list, origin_list, compound_list,
                   additional_defs, example_sentences, definition_list, synonym_list,
                   cleaned_tokens, sorted_keywords, llm, round_ctx):
    """45-second answer-submission phase after user typed 'bb'.

    Polls a queue so the silence timer and user input can coexist. When the
    5-min game timer fires mid-round, we let this round finish (per spec:
    grace only if user pressed bb).
    """
    state.active_input_bb = ""
    deadline = time.time() + ROUND_TIME_SECONDS
    next_silence = time.time() + random.uniform(SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS)
    chance_list = [2, 3, 4, 7, 9, 5, 25, 65]
    list_active_input_bb = []

    print("\n")
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            round_score = score_for_correct_answer(word, state.revealed_letters)
            for line in round_timeout_lines(word_list[round_idx], round_score, state.total_score - round_score):
                print(line)
                time.sleep(1)
            state.total_score -= round_score
            return

        wait_for = min(remaining, max(0.1, next_silence - time.time()))
        line = _wait_for_input("-BB> ", timeout=wait_for)

        if line is None:
            if time.time() >= next_silence:
                print("\n" + host.llm_silence_reply(llm, state, round_ctx))
                next_silence = time.time() + random.uniform(SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS)
            continue

        next_silence = time.time() + random.uniform(SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS)
        state.active_input_bb = line
        raw = line.lower().strip()
        tkn = nltk.word_tokenize(raw)

        if raw == word:
            if state.chosen_phrase == "Bana mı soruyorsunuz, cevap mı veriyorsunuz?..":
                print("\n", random.choice([
                    "Cevap veriyorlar..!",
                    "Sanırım cevap veriyorsunuz ve doğru olanı yapıyorsunuz",
                ]))
            elif state.chosen_phrase == f"{word} sığıyor mu oraya?":
                print("\nEyvah, eyvah! Efendim sığıyor mu ki?...")
                time.sleep(3)
                print("Tabii ki sığıyor! Yalnızca biraz heyecanlandırmak istedim ancak buna kanmadılar kendileri...")

            round_score = score_for_correct_answer(word, state.revealed_letters)
            print("\n", correct_answer_celebration(word, round_score))
            state.total_score += round_score
            return

        elif raw == "h" or ("harf" in tkn and ("alabilir" in tkn or "alayım" in tkn)):
            print("\nEfendim, harf alamazsınız artık, süreyi durdurdunuz.")

        elif any(it in ["kök", "köken", "kökenli", "kökeni"] for it in tkn):
            if origin_list[round_idx] != "None":
                print("\n", random.choice([
                    f"Sanırım {origin_list[round_idx]} olmalı",
                    f"Hmm... Bu, sanıyorum {origin_list[round_idx]}",
                    f"{origin_list[round_idx]}",
                    f"{origin_list[round_idx]} olma ihtimali yüksek",
                ]))
            else:
                print("\nMaalesef kökeninden emin değilim...")

        elif any(it in STUCK_KEYWORDS for it in tkn):
            for msg in give_hint(chance_list, round_idx, word, example_sentences,
                                 compound_list, additional_defs, definition_list, synonym_list):
                print("\n", msg)
                time.sleep(1)

        else:
            reaction = react_to_guess(raw, round_idx, word, tkn, list_active_input_bb,
                                       synonym_list, cleaned_tokens, sorted_keywords)
            if reaction is not None:
                print("\n", reaction)
            else:
                state.round_history.append(("user", line))
                reply = host.llm_host_reply(llm, state, round_ctx, line, state.round_history)
                print("\n" + reply)
                state.round_history.append(("assistant", reply))

        list_active_input_bb.append(raw)


def cli_main_game(state, word_list, definition_list, origin_list, function_list,
                  structure_list, compound_list, additional_defs, example_sentences,
                  synonym_list, cleaned_tokens, sorted_keywords, llm):
    def countdown_timer():
        while state.total_time > 0 and not state.game_over:
            if state.is_paused:
                time.sleep(1)
                continue
            time.sleep(1)
            state.total_time -= 1
        if state.total_time <= 0:
            state.game_over = True

    def process(round_idx, word, round_ctx):
        state.chosen_phrase = ""
        list_active_input = []
        chance_list = [2, 3, 4, 7, 9, 5, 25, 65]
        next_silence = time.time() + random.uniform(SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS)
        print()
        while True:
            if state.game_over or state.total_time <= 0:
                state.game_over = True
                return

            line = _wait_for_input("\n-> ", timeout=max(0.1, next_silence - time.time()))

            if line is None:
                if state.game_over or state.total_time <= 0:
                    state.game_over = True
                    return
                if time.time() >= next_silence:
                    print(host.llm_silence_reply(llm, state, round_ctx))
                    next_silence = time.time() + random.uniform(SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS)
                continue

            next_silence = time.time() + random.uniform(SILENCE_MIN_SECONDS, SILENCE_MAX_SECONDS)
            raw = line.lower().strip()
            tkn = nltk.word_tokenize(raw)

            if raw == word.lower() or word in tkn:
                state.chosen_phrase = random.choice([
                    f"{word} sığıyor mu oraya?",
                    "Bana mı soruyorsunuz, cevap mı veriyorsunuz?..",
                    "Haydi, şöyle bir cesaret... ",
                    "Efendim bana sormayın... Ben bir şey diyemem ki...",
                    "Ben bilmem...",
                    "... emin misiniz..?",
                    "Risk alacak mısınız..?",
                    "Buton... Buton..., Unutuyorsunuz basmayı ya da risk almak mı istemiyorsunuz..?",
                    "",
                ])
                print("\n", state.chosen_phrase)

            elif any(it in ["kök", "köken", "kökenli", "kökeni"] for it in tkn):
                if origin_list[round_idx] != "None":
                    print("\n", random.choice([
                        f"Sanırım {origin_list[round_idx]} olmalı",
                        f"Hmm... Bu, sanıyorum {origin_list[round_idx]}",
                        f"{origin_list[round_idx]}",
                        f"{origin_list[round_idx]} olma ihtimali yüksek",
                    ]))
                else:
                    print("\nMaalesef kökeninden emin değilim...")

            elif raw == "bb":
                state.is_paused = True
                state.resume_time = state.total_time
                cli_round_time(state, round_idx, word, word_list, origin_list, compound_list,
                               additional_defs, example_sentences, definition_list, synonym_list,
                               cleaned_tokens, sorted_keywords, llm, round_ctx)
                if state.total_time <= 0 or state.game_over:
                    state.game_over = True
                    return
                state.is_paused = False
                state.total_time = state.resume_time
                state.reset_revealed()
                return

            elif raw == "h" or ("harf" in tkn and ("alabilir" in tkn or "alayım" in tkn)) or "harf" in tkn:
                _, status = letter_request(word, state.revealed_letters)
                current = " ".join(state.revealed_letters)
                print("\n", current, "\n")
                if status == "all-revealed" or "_  " not in state.revealed_letters:
                    print("\nÜzgünüm, bu sorudan puan alamadınız!\nOlsun! Üzülmeyin, rakiplerinizin de puan kaybetmeyeceği ne malum...\nBiz sıradaki soru ile devam edelim...\n")
                    state.reset_revealed()
                    return

            elif any(it in STUCK_KEYWORDS for it in tkn):
                for msg in give_hint(chance_list, round_idx, word, example_sentences,
                                     compound_list, additional_defs, definition_list, synonym_list):
                    print("\n", msg)
                    time.sleep(1)

            elif (("eş" in tkn and ("anlamlı" in tkn or "anlamlısı" in tkn or "anlam" in tkn or "anlamı" in tkn))
                  or ("benzer" in tkn and ("anlamda" in tkn or "anlamlı" in tkn))):
                syn_phrase = get_synonym_phrase(synonym_list, round_idx)
                if syn_phrase != "None":
                    print("\n", syn_phrase)
                else:
                    print("\nMaalesef aklıma bir şey gelmedi şu an...")

            else:
                reaction = react_to_guess(raw, round_idx, word, tkn, list_active_input,
                                          synonym_list, cleaned_tokens, sorted_keywords)
                if reaction is not None:
                    print("\n", reaction)
                else:
                    state.round_history.append(("user", line))
                    reply = host.llm_host_reply(llm, state, round_ctx, line, state.round_history)
                    print("\n" + reply)
                    state.round_history.append(("assistant", reply))

            list_active_input.append(raw)

    state.is_paused = True
    threading.Thread(target=countdown_timer, daemon=True).start()

    for round_idx in range(TOTAL_ROUNDS):
        state.reset_revealed()
        state.reset_round_history()

        if state.game_over or state.total_time <= 0:
            break

        if round_idx != 0:
            ready = _wait_for_input(
                "\nSıradaki soru ile devam etmek için \"d\" yazınız\n"
                "Toplam skorunuzu görmek için \"puan\" yazınız: ",
                timeout=None,
            ) or ""
            if ready.lower().strip() == "puan":
                print(f"\nŞuanki toplam puanınız: {state.total_score}")
                ready = _wait_for_input(
                    "\nSıradaki soru ile devam etmek için \"d\" yazınız: ", timeout=None,
                ) or ""
            if ready.lower().strip() != "d":
                continue

        question_number = round_idx + 1
        word = word_list[round_idx]
        round_ctx = {
            "word": word,
            "clue": definition_list[round_idx],
            "synonyms": synonym_list[round_idx] if synonym_list[round_idx] != "None" else [],
        }

        for msg, sleep_after in pre_info_messages(question_number, state.total_score, round_idx,
                                                  function_list, structure_list, origin_list):
            print("\n", msg)
            if sleep_after:
                time.sleep(sleep_after)

        time.sleep(2.3)
        letter_count = ((question_number - 1) // 2) + 4
        print("\n" + "_  " * letter_count + "\n")
        print(definition_list[round_idx])
        state.is_paused = False
        process(round_idx, word, round_ctx)
        state.is_paused = True
        state.reset_revealed()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def run():
    ensure_nltk()
    try:
        llm = load_client()
    except LLMError as e:
        print(f"[LLM devre dışı — oyun azaltılmış modda çalışacak]  {e}\n")
        llm = None

    show_head()
    username = start_command()

    print("\nOyun hazırlanıyor, bir kaç saniye sürebilir...\n")
    morphology = load_morphology()
    wordnet = load_wordnet()
    gts_index = load_gts()
    cleaned_tokens, sorted_keywords = load_corpus_tokens()

    while True:
        selected, d1, d2, d3 = select_words_and_meanings(WORD_FILES, WORD_LENGTHS)
        word_list = apply_unicode_transform(selected)
        try:
            example_gts = example_sentences_from_gts(gts_index, word_list)
            break
        except Exception:
            continue

    definition_list = d1
    additional_defs = merge_lists([x or "None" for x in d2], [x or "None" for x in d3])
    synonym_list = [synonym_hint(wordnet, w) for w in word_list]
    function_list = function_of_words(wordnet, word_list)
    compound_list = compound_hints(gts_index, word_list)

    if llm is not None:
        print("Kelime bilgileri hazırlanıyor...")
        origin_list, structure_list, example_gpt = host.batch_word_metadata(llm, word_list)
    else:
        origin_list = ["None"] * TOTAL_ROUNDS
        structure_list = ["None"] * TOTAL_ROUNDS
        example_gpt = ["None"] * TOTAL_ROUNDS

    example_sentences = merge_lists(example_gts, example_gpt)

    if llm is not None:
        cli_prologue(llm, username)
    else:
        print(f"Merhaba {username}, haydi başlayalım...")

    time.sleep(1)
    state = GameState(username=username)

    cli_main_game(state, word_list, definition_list, origin_list, function_list,
                  structure_list, compound_list, additional_defs, example_sentences,
                  synonym_list, cleaned_tokens, sorted_keywords, llm)

    time.sleep(2)
    print(end_game_lines(state.total_score, username, state.game_over))
    time.sleep(3)
    print("\nTekrar görüşmek üzere...\n\nSağlıcakla kalın bizi de öksüz bırakmayın...")
    print("\nAnketimizi doldurmak için: https://forms.gle/xhRYD5doZLKxumAw7")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n\nOyun kullanıcı tarafından sonlandırıldı. Sağlıcakla kalın.")
        sys.exit(0)
