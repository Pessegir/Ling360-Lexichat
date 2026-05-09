"""One-shot synthesizer for the Lexi-Chat sound bank.

Generates 9 short WAV files into ../static/sounds/. Run by hand from
the repo root:

    conda activate lexichat
    python scripts/synthesize_sounds.py

Each sound is a numpy-synthesized starter — clean sine + envelope work,
nothing fancy. They're committed to the repo so end users don't need to
run this; replace any file in static/sounds/ with a curated sample of
the same name to upgrade the audio without touching code.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


SR = 44100
OUT = Path(__file__).resolve().parent.parent / "static" / "sounds"


def _save(name: str, samples: np.ndarray) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)
    path = OUT / f"{name}.wav"
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())
    ms = len(pcm) / SR * 1000
    print(f"  → {path.name:18s} {ms:6.0f} ms")


def envelope(n: int, *, attack_ms: float = 2, release_ms: float = 80) -> np.ndarray:
    env = np.ones(n)
    a = int(attack_ms * SR / 1000)
    r = int(release_ms * SR / 1000)
    if a > 0:
        env[:a] = np.linspace(0.0, 1.0, a)
    if 0 < r < n:
        # Quadratic falloff — softer tail than linear
        env[-r:] = np.linspace(1.0, 0.0, r) ** 2
    return env


def sine(freq: float, dur_ms: float, *, amp: float = 0.5,
         attack_ms: float = 2, release_ms: float = 80) -> np.ndarray:
    n = int(dur_ms * SR / 1000)
    t = np.arange(n) / SR
    return amp * np.sin(2 * np.pi * freq * t) * envelope(n, attack_ms=attack_ms, release_ms=release_ms)


def sweep(f0: float, f1: float, dur_ms: float, *, amp: float = 0.4,
          attack_ms: float = 2, release_ms: float = 80) -> np.ndarray:
    n = int(dur_ms * SR / 1000)
    freq = np.linspace(f0, f1, n)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return amp * np.sin(phase) * envelope(n, attack_ms=attack_ms, release_ms=release_ms)


def noise(dur_ms: float, *, amp: float = 0.3, attack_ms: float = 1,
          release_ms: float = 50, seed: int | None = None) -> np.ndarray:
    n = int(dur_ms * SR / 1000)
    rng = np.random.default_rng(seed)
    return amp * rng.standard_normal(n) * envelope(n, attack_ms=attack_ms, release_ms=release_ms)


def lowpass(s: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """Vectorized 1-pole RC lowpass."""
    rc = 1.0 / (2 * np.pi * cutoff_hz)
    dt = 1.0 / SR
    alpha = dt / (rc + dt)
    out = np.empty_like(s)
    out[0] = s[0] * alpha
    for i in range(1, len(s)):
        out[i] = out[i - 1] + alpha * (s[i] - out[i - 1])
    return out


# --------------------------------------------------------------------------
# Individual sounds
# --------------------------------------------------------------------------


def make_tile_reveal() -> np.ndarray:
    # Soft warm pop on letter reveal
    return sine(820, 90, amp=0.45, release_ms=75)


def make_correct() -> np.ndarray:
    # Two-note bell-ish — perfect fifth (C5 + G5)
    a = sine(523.25, 600, amp=0.32, release_ms=520)
    b = sine(783.99, 600, amp=0.22, release_ms=520)
    # Gentle 3rd harmonic for warmth
    c = sine(1046.50, 600, amp=0.10, release_ms=520)
    return a + b + c


def make_wrong() -> np.ndarray:
    # Low descending sweep — dusty rose feel, not buzzer-harsh
    return sweep(220, 110, 420, amp=0.45, release_ms=320)


def make_score_up() -> np.ndarray:
    # Quick ascending chime
    return sweep(620, 990, 280, amp=0.32, release_ms=200)


def make_score_down() -> np.ndarray:
    # Soft descending — score drop on timeout
    return sweep(700, 380, 380, amp=0.32, release_ms=300)


def make_timer_tick() -> np.ndarray:
    # Short clock tick — lowpassed noise burst + a brief high sine
    n = int(50 * SR / 1000)
    rng = np.random.default_rng(42)
    s = 0.30 * rng.standard_normal(n)
    s += 0.35 * np.sin(2 * np.pi * 2400 * np.arange(n) / SR)
    s = lowpass(s, 4500)
    return s * envelope(n, attack_ms=1, release_ms=35)


def make_game_start() -> np.ndarray:
    # Mic tap → silence → warm pad fade-in
    tap = noise(80, amp=0.55, attack_ms=1, release_ms=60, seed=1)
    tap = lowpass(tap, 800)
    silence = np.zeros(int(40 * SR / 1000))
    pad = sine(220, 380, amp=0.22, attack_ms=120, release_ms=200)
    return np.concatenate([tap, silence, pad])


def make_game_end() -> np.ndarray:
    # Major arpeggio C–E–G–C high, then a soft applause-noise tail
    parts = [
        sine(261.63, 280, amp=0.30, release_ms=240),
        sine(329.63, 280, amp=0.30, release_ms=240),
        sine(392.00, 280, amp=0.30, release_ms=240),
        sine(523.25, 480, amp=0.32, release_ms=420),
    ]
    arp = np.concatenate(parts)
    tail = noise(700, amp=0.13, attack_ms=120, release_ms=600, seed=7)
    tail = lowpass(tail, 3500)
    return np.concatenate([arp, tail])


def make_new_record() -> np.ndarray:
    # Bright multi-octave bell — sparkle for new high score
    a = sine(1500, 1100, amp=0.26, release_ms=1000)
    b = sine(750, 1100, amp=0.18, release_ms=1000)
    c = sine(2250, 1100, amp=0.10, release_ms=1000)
    return a + b + c


SOUNDS = {
    "tile-reveal": make_tile_reveal,
    "correct":     make_correct,
    "wrong":       make_wrong,
    "score-up":    make_score_up,
    "score-down":  make_score_down,
    "timer-tick":  make_timer_tick,
    "game-start":  make_game_start,
    "game-end":    make_game_end,
    "new-record":  make_new_record,
}


def main() -> None:
    print(f"Synthesizing {len(SOUNDS)} sounds → {OUT}/")
    for name, fn in SOUNDS.items():
        _save(name, fn())
    print("Done.")


if __name__ == "__main__":
    main()
