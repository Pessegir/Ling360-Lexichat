"""NLP helpers — synonyms, POS, morphology, edit-distance.

Heavy imports are lazy so callers (esp. the web app) can defer them or
opt out entirely.
"""
from __future__ import annotations

import random
import re
import warnings
from collections import OrderedDict

# Silence the pkg_resources deprecation that Zemberek triggers.
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import editdistance
import nltk


def ensure_nltk():
    """Download punkt models if missing. Call once at startup."""
    for resource in ("tokenizers/punkt", "tokenizers/punkt_tab"):
        try:
            nltk.data.find(resource)
        except LookupError:
            nltk.download(resource.split("/")[1], quiet=True)


def load_morphology():
    from zemberek import TurkishMorphology
    return TurkishMorphology.create_with_defaults()


def load_wordnet():
    from WordNet.WordNet import WordNet
    return WordNet()


def synonym_hint(wordnet, word):
    """List of synonyms for `word` from TurkishWordNet, or 'None'."""
    try:
        synset = wordnet.getSynSetWithLiteral(word.lower(), 1)
        synonyms = re.sub(r'â', 'a', str(synset.getSynonym()))
        items = [x for x in synonyms.split() if x != word]
        return items if items else "None"
    except Exception:
        return "None"


def get_synonym_phrase(synonym_list, round_idx):
    entry = synonym_list[round_idx]
    if entry == "None":
        return "None"
    n = min(3, len(entry))
    chosen = random.sample(entry, n)
    return random.choice([
        f"Belki bunlar size yardımcı olabilir: {', '.join(chosen)}...\nBu kelimeler eş anlamlı olarak kullanılır diyebilirim...",
        f"{', '.join(chosen)}... Bunlara dikkat! Yardımcı olabilir...",
        f"{', '.join(chosen)}... Bu kelimeler bir şeyler anımsatabilir...",
        f"{', '.join(chosen)}... Bu kelimeleri düşünün...",
    ])


_POS_DICT = {
    'ADJECTIVE': 'sıfat', 'VERB': 'fiil', 'ADVERB': 'zarf', 'NOUN': 'isim',
    'INTERJECTION': 'nida/ünlem', 'CONJUNCTION': 'bağlaç',
    'PREPOSTION': 'edat', 'PRONOUN': 'zamir',
}


def get_pos(wordnet, word):
    try:
        synset = wordnet.getSynSetWithLiteral(word.lower(), 1)
        pos = re.sub('Pos.', '', str(synset.getPos()))
        return _POS_DICT.get(pos, "None")
    except Exception:
        return "None"


def function_of_words(wordnet, word_list):
    return [get_pos(wordnet, w) if get_pos(wordnet, w) != "None" else "None" for w in word_list]


def analyze_word(morphology, word):
    """Return the morphological root of `word` (best analysis)."""
    results = morphology.analyze(word)
    analyzed = [str(r) for r in results]
    output = re.findall(r'\[(.*?)\]', ', '.join(analyzed))
    output = [e.split(":")[0].strip("'") for e in output]
    output = list(OrderedDict.fromkeys(output))
    return output[0] if output else ""


def get_example_sentence(wordnet, morphology, word):
    """Find an example sentence in WordNet, blanked-out. Used as a fallback when
    gts.json doesn't have one."""
    try:
        synset = wordnet.getSynSetWithLiteral(word, 1)
    except Exception:
        return "None"
    if synset is None or synset.getExample() is None:
        return "None"

    new_example = ""
    other_example = ""
    example_sentences = "".join(synset.getExample()).lower()

    tokens = nltk.word_tokenize(example_sentences)
    stem_dict = {t: analyze_word(morphology, t) for t in tokens}
    for tok, stem in stem_dict.items():
        if stem == word:
            new_example = re.sub(tok, "______", example_sentences)

    s_hints = synonym_hint(wordnet, word)
    if isinstance(s_hints, list):
        for syn in s_hints:
            example_sentences = "".join(synset.getExample()).lower()
            hint_re = r"\b{}(?:\w+)?(?=\b)".format(re.escape(syn))
            if re.findall(hint_re, example_sentences):
                tokens = nltk.word_tokenize(example_sentences)
                stem_dict = {t: analyze_word(morphology, t) for t in tokens}
                for tok, stem in stem_dict.items():
                    if stem == syn:
                        new_example = re.sub(tok, lambda m: m.group(0).upper(), example_sentences)
                        other_example = re.sub(tok, "______", example_sentences)

    if not new_example:
        return "None"
    return f"{new_example}\nDeğiştirin bu kısmı... Tekrar ediyorum...,\n{other_example}..."


def similar_word_hint(word, n_suggestions, cleaned_tokens, sorted_keywords):
    """Words that are 1-2 edits away from the target, useful for 'almost there' hints."""
    if word in cleaned_tokens:
        return [word]

    distances = [editdistance.distance(word, t) for t in cleaned_tokens]
    if not distances:
        return []
    min_dist = min(distances)

    suggestions = []
    for candidate, _freq in sorted_keywords:
        d = editdistance.distance(word, candidate)
        if min_dist - 1 < d <= min_dist and len(candidate) == len(word):
            suggestions.append(candidate)
            if len(suggestions) == n_suggestions:
                return suggestions
    return suggestions
