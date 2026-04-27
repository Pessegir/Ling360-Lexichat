"""Thin LLM client abstraction so the game can swap providers in one place.

Currently ships a Gemini implementation (new google-genai SDK). Adding Hugging
Face / local Ollama later means writing another subclass with the same signature.
"""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path


class LLMError(RuntimeError):
    pass


class LLMClient(ABC):
    @abstractmethod
    def chat(self, system: str, messages: list[dict], max_tokens: int = 200) -> str:
        """Send a chat-style conversation and return the assistant's reply text."""


# Models tried in order. First-available wins. Order picked for:
# 1. Cheapest/fastest on free tier that actually works
# 2. Fallbacks for when the primary is overloaded or quota-exhausted
GEMINI_MODEL_CHAIN = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
]

# When ALL models return 429/503 in one call, refuse to call the API again
# for this many seconds. Keeps the UI snappy when quota is gone — calls
# return instantly with LLMError, host code falls back to scripted lines.
CIRCUIT_BREAKER_DEFAULT_COOLDOWN = 60.0


def _parse_retry_seconds(error_str: str) -> float | None:
    """Extract Google's suggested retry delay from an error message, if any."""
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", error_str, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m = re.search(r"retryDelay'?:\s*'?(\d+(?:\.\d+)?)s", error_str)
    if m:
        return float(m.group(1))
    return None


class GeminiClient(LLMClient):
    """Google Gemini via the google-genai SDK.

    Tries models in GEMINI_MODEL_CHAIN in order. If one returns 429 (quota) or
    503 (overloaded), falls through to the next. Remembers which model last
    worked to avoid re-probing dead ones.

    Circuit breaker: when ALL models fail with quota/availability errors in
    one call, future calls within the cooldown window raise LLMError
    immediately without hitting the network. Cooldown is set from Google's
    own retryDelay hint when present, capped to a sensible max.
    """

    def __init__(self, api_key: str, model_chain: list[str] | None = None,
                 circuit_breaker_max_cooldown: float = CIRCUIT_BREAKER_DEFAULT_COOLDOWN):
        if not api_key:
            raise LLMError(
                "Missing Gemini API key. Copy datakey.example.json to datakey.json "
                "and fill in GEMINI_API_KEY (free key at https://aistudio.google.com/apikey)."
            )
        from google import genai
        from google.genai import types
        self._client = genai.Client(api_key=api_key)
        self._types = types
        self._chain = model_chain or list(GEMINI_MODEL_CHAIN)
        self._preferred = 0
        self._cb_until: float = 0.0  # circuit-breaker open until this monotonic time
        self._cb_max = circuit_breaker_max_cooldown

    def chat(self, system: str, messages: list[dict], max_tokens: int = 200) -> str:
        # Circuit breaker: short-circuit if quota was just exhausted
        now = time.monotonic()
        if now < self._cb_until:
            remaining = self._cb_until - now
            raise LLMError(f"Gemini quota exhausted; retrying in ~{remaining:.0f}s")

        types = self._types
        contents = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))

        config_kwargs = dict(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=0.9,
        )
        try:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except (AttributeError, TypeError):
            pass
        config = types.GenerateContentConfig(**config_kwargs)

        last_err: Exception | None = None
        suggested_retry: float | None = None

        for model_idx in range(self._preferred, len(self._chain)):
            model = self._chain[model_idx]
            try:
                response = self._client.models.generate_content(
                    model=model, contents=contents, config=config,
                )
                self._preferred = model_idx
                return (response.text or "").strip()
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if any(k in msg for k in ("429", "quota", "resource_exhausted",
                                          "503", "unavailable", "500", "internal")):
                    # Try to read Google's "retry in Xs" hint
                    rs = _parse_retry_seconds(str(e))
                    if rs is not None and (suggested_retry is None or rs < suggested_retry):
                        suggested_retry = rs
                    continue  # try next model
                # Non-transient (auth, malformed request, etc.) — propagate
                raise LLMError(f"Gemini call failed on {model}: {e}") from e

        # All models failed. Open the circuit breaker.
        cooldown = min(suggested_retry or self._cb_max, self._cb_max)
        self._cb_until = time.monotonic() + cooldown
        raise LLMError(
            f"All Gemini models unavailable; backing off {cooldown:.0f}s. "
            f"Last error: {last_err}"
        )


def load_client(keyfile: str | Path = "datakey.json") -> LLMClient:
    """Load API key from disk and return a ready-to-use client."""
    path = Path(keyfile)
    if not path.exists():
        raise LLMError(
            f"{path} not found. Copy datakey.example.json to datakey.json and add your key."
        )
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return GeminiClient(api_key=data.get("GEMINI_API_KEY", ""))
