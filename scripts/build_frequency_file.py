"""One-time script: Bilkent corpus CSV -> small Turkish frequency JSON.

Run once from repo root:
    python scripts/build_frequency_file.py

Produces data/turkish_frequencies.json, which lexichat_game.py loads at startup.
The raw CSV is not needed after this.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import nltk
import pandas as pd

ROOT = Path(__file__).parent.parent
RAW_CSV = ROOT / "data" / "_bilkent_raw.csv"
OUT = ROOT / "data" / "turkish_frequencies.json"
MIN_FREQ = 2  # drop hapax legomena (single-occurrence words)


def main():
    if not RAW_CSV.exists():
        raise SystemExit(f"Missing {RAW_CSV}. Download from Bilkent dataset first.")

    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt")
    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab")

    print(f"Reading {RAW_CSV} ({RAW_CSV.stat().st_size // 1024 // 1024} MB)...")
    df = pd.read_csv(RAW_CSV)
    # v1 schema: columns = ["Unnamed: 0", "text"]
    text_col = "text" if "text" in df.columns else df.columns[-1]
    text = " ".join(df[text_col].dropna().astype(str).tolist()).lower()
    text = re.sub(r"<[^<]Wd>", "", text)

    print("Tokenizing...")
    tokens = nltk.word_tokenize(text)
    cleaned = [t for t in tokens if t.isalpha() and len(t) > 1]
    counts = Counter(cleaned)

    filtered = {w: c for w, c in counts.items() if c >= MIN_FREQ}

    print(f"Kept {len(filtered):,} unique tokens (freq >= {MIN_FREQ}) out of {len(counts):,}")
    OUT.write_text(json.dumps(filtered, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
