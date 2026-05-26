"""Turkish-aware text helpers. Pure functions, no I/O."""
from __future__ import annotations

import re


class UnicodeTr(str):
    """Turkish-aware string. Default str.lower() turns 'İ' into 'i̇'
    (Latin i + combining dot above), and str.upper() turns 'i' into 'I'
    (losing the dot) and 'ş'→'S' etc. This class normalizes I/İ/i/ı
    correctly before deferring to str.lower()/str.upper().
    """
    CHARMAP = {
        "to_lower": {"I": "ı", "İ": "i"},
        "to_upper": {"ı": "I", "i": "İ"},
    }

    def lower(self):
        s = self
        for k, v in self.CHARMAP["to_lower"].items():
            s = s.replace(k, v)
        return str.lower(s)

    def upper(self):
        s = self
        for k, v in self.CHARMAP["to_upper"].items():
            s = s.replace(k, v)
        return str.upper(s)


def tr_upper(text):
    """Convenience: Turkish-correct uppercase as a plain str."""
    return UnicodeTr(text).upper()


def apply_unicode_transform(words):
    return [UnicodeTr(w).lower() for w in words]


def clean_string(text):
    return re.sub(r'[^\w\s]', "", text)


# Turkish keyboards usually don't expose circumflex vowels (â/î/û). When
# the answer is "kâkül" and the player types "kakül", we should accept
# it — the player has no way to type the â. Same for matching tokens.
# Maps both lowercase and uppercase variants in one pass.
_CIRCUMFLEX_FOLD = str.maketrans({
    "â": "a", "Â": "A",
    "î": "i", "Î": "İ",  # 'Î' lowercase is 'i' in Turkish; uppercase fold keeps the Turkish dotted İ
    "û": "u", "Û": "U",
    "ô": "o", "Ô": "O",
    "ê": "e", "Ê": "E",
})


def tr_fold(text: str) -> str:
    """Strip circumflex accents so player guesses match the canonical
    answer regardless of the â/î/û variants on Turkish keyboards.

    Use for COMPARISON only — never for display or storage.
    """
    if not text:
        return text
    return text.translate(_CIRCUMFLEX_FOLD)
