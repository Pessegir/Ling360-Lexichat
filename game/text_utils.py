"""Turkish-aware text helpers. Pure functions, no I/O."""
from __future__ import annotations

import re


class UnicodeTr(str):
    """Turkish-aware string. Default str.lower() turns 'İ' into 'i̇'
    (Latin i + combining dot above), which breaks regex \\b matching. This
    class normalizes I/İ to ı/i first, then defers to str.lower().
    """
    CHARMAP = {"to_lower": {"I": "ı", "İ": "i"}}

    def lower(self):
        s = self
        for k, v in self.CHARMAP["to_lower"].items():
            s = s.replace(k, v)
        return str.lower(s)


def apply_unicode_transform(words):
    return [UnicodeTr(w).lower() for w in words]


def clean_string(text):
    return re.sub(r'[^\w\s]', "", text)
