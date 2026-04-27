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
