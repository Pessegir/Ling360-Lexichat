"""Data loading: word files, gts.json, Bilkent frequency map. Pure I/O at startup,
then everything's in memory."""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

from .config import FREQ_PATH, GTS_PATH


def select_words_and_meanings(file_list, word_lengths):
    """Read the .letters.txt files, pick 2 words per length, return them and
    up to 3 alternative meanings per word."""
    words, meanings = [], []
    for path in file_list:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ": " not in line:
                    continue
                word, meaning = line.split(": ", 1)
                if len(word) in word_lengths:
                    words.append(word)
                    meanings.append(meaning)

    selected = []
    for length in word_lengths:
        pool = [w for w in words if len(w) == length]
        selected.extend(random.sample(pool, 2))

    m1, m2, m3 = [], [], []
    for w in selected:
        idx = [i for i, x in enumerate(words) if x == w]
        m1.append(meanings[idx[0]])
        m2.append(meanings[idx[1]] if len(idx) >= 2 else None)
        m3.append(meanings[idx[2]] if len(idx) >= 3 else None)
    return selected, m1, m2, m3


def load_gts(path: Path = GTS_PATH):
    """Index gts.json by 'madde' (headword). 91 MB file loaded once at startup."""
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    index = {}
    for entry in entries:
        key = entry.get("madde", "").lower()
        if key:
            index.setdefault(key, []).append(entry)
    return index


def lookup_definition(gts_index, word):
    """First anlam (definition) for `word` from gts.json, or None.

    Picks the first meaning of the first matching entry — gts.json orders
    them by frequency / canonicality, so this is the one a player would
    most likely have meant.
    """
    for entry in gts_index.get(word.lower(), []):
        for anlam in entry.get("anlamlarListe", []) or []:
            text = anlam.get("anlam")
            if text:
                return text.strip()
    return None


def compound_hints(gts_index, words):
    """For each word, find a compound form like 'kara ____' from gts.json.
    Returns 'None' for words without compound entries."""
    out = []
    for word in words:
        found = None
        for entry in gts_index.get(word.lower(), []):
            birlesikler = entry.get("birlesikler")
            if not birlesikler:
                continue
            for birlesik in birlesikler.split(", "):
                pattern = r'\b' + re.escape(word) + r'(\w*)\b'
                m = re.search(pattern, birlesik, flags=re.IGNORECASE)
                if m:
                    suffix = m.group(1)
                    found = re.sub(pattern, "______" + suffix, birlesik, flags=re.IGNORECASE)
                    break
            if found:
                break
        out.append(found if found else "None")
    return out


def example_sentences_from_gts(gts_index, words):
    """For each word, find an example sentence in gts.json with the word
    blanked out."""
    out = []
    for word in words:
        found = None
        for entry in gts_index.get(word.lower(), []):
            for anlam in entry.get("anlamlarListe", []) or []:
                for ornek in anlam.get("orneklerListe", []) or []:
                    sentence = ornek.get("ornek")
                    if not sentence:
                        continue
                    pattern = r'\b' + re.escape(word) + r'(\w*)\b'
                    m = re.search(pattern, sentence, flags=re.IGNORECASE)
                    if m:
                        suffix = m.group(1)
                        found = re.sub(pattern, "______" + suffix, sentence, flags=re.IGNORECASE)
                        break
                if found:
                    break
            if found:
                break
        out.append(found if found else "None")
    return out


def load_corpus_tokens(path: Path = FREQ_PATH):
    """Load the prebuilt Bilkent frequency map. No network."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run: python scripts/build_frequency_file.py"
        )
    with path.open("r", encoding="utf-8") as f:
        freq = json.load(f)
    cleaned = list(freq.keys())
    sorted_keywords = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return cleaned, sorted_keywords


def merge_lists(a, b):
    merged = []
    for i in range(len(a)):
        if a[i] != "None":
            merged.append(a[i])
        elif b[i] != "None":
            merged.append(b[i])
        else:
            merged.append("None")
    return merged
