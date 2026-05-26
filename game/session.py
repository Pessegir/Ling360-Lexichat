"""High-level helpers a driver calls to start a new game.

These functions wrap the existing data + nlp + host modules into single-call
operations. The Streamlit app calls them inside @st.cache_resource so heavy
NLP loads happen once per server, not per session.
"""
from __future__ import annotations

from .config import (
    TOTAL_ROUNDS, WORD_FILES, WORD_LENGTHS,
)
from .daily import DAILY_ROUNDS, select_daily_words
from .data import (
    compound_hints, example_sentences_from_gts, load_corpus_tokens, load_gts,
    merge_lists, select_words_and_meanings,
)
from .nlp import (
    ensure_nltk, function_of_words, load_morphology, load_wordnet, synonym_hint,
)
from . import host
from .text_utils import apply_unicode_transform


def load_static_resources():
    """Load the heavy NLP + dictionary + corpus assets. Cache-friendly:
    Streamlit's @st.cache_resource will only call this once per server.

    Returns a dict of resources the per-game setup needs.
    """
    ensure_nltk()
    return {
        "morphology": load_morphology(),
        "wordnet": load_wordnet(),
        "gts_index": load_gts(),
        "corpus": load_corpus_tokens(),  # (cleaned_tokens, sorted_keywords)
    }


def build_new_game(resources, llm, *, mode: str = "free"):
    """Pick N words, compute all per-round metadata, return a payload
    the GameState driver can use directly.

    mode='free' (default): 14 random words across all letter-lengths,
      legacy behavior preserved exactly.
    mode='daily': 5 date-seeded words, one per length 4..8. Every
      player on the same TR-local date gets the same words. Bypasses
      the retry loop since the seeded selection is deterministic.

    Returns dict with: word_list, definition_list, additional_defs,
    synonym_list, function_list, compound_list, origin_list, structure_list,
    example_sentences, total_rounds.
    """
    gts_index = resources["gts_index"]
    wordnet = resources["wordnet"]

    if mode == "daily":
        # Deterministic — no retry needed. If example_sentences_from_gts
        # raises on a daily word, that's a real bug worth surfacing.
        selected, d1, d2, d3 = select_daily_words(WORD_FILES)
        word_list = apply_unicode_transform(selected)
        example_gts = example_sentences_from_gts(gts_index, word_list)
        total_rounds = DAILY_ROUNDS
    else:
        # Retry loop: occasionally select_words_and_meanings + example
        # combination raises (rare, when a chosen word can't be processed).
        for _ in range(5):
            selected, d1, d2, d3 = select_words_and_meanings(WORD_FILES, WORD_LENGTHS)
            word_list = apply_unicode_transform(selected)
            try:
                example_gts = example_sentences_from_gts(gts_index, word_list)
                break
            except Exception:
                continue
        else:
            raise RuntimeError("Could not assemble a word list after 5 attempts.")
        total_rounds = TOTAL_ROUNDS

    definition_list = d1
    additional_defs = merge_lists(
        [x or "None" for x in d2], [x or "None" for x in d3]
    )
    synonym_list = [synonym_hint(wordnet, w) for w in word_list]
    function_list = function_of_words(wordnet, word_list)
    compound_list = compound_hints(gts_index, word_list)

    if llm is not None:
        origin_list, structure_list, example_gpt = host.batch_word_metadata(llm, word_list)
    else:
        origin_list = ["None"] * total_rounds
        structure_list = ["None"] * total_rounds
        example_gpt = ["None"] * total_rounds

    example_sentences = merge_lists(example_gts, example_gpt)

    return {
        "word_list": word_list,
        "definition_list": definition_list,
        "additional_defs": additional_defs,
        "synonym_list": synonym_list,
        "function_list": function_list,
        "compound_list": compound_list,
        "origin_list": origin_list,
        "structure_list": structure_list,
        "example_sentences": example_sentences,
        "total_rounds": total_rounds,
    }
