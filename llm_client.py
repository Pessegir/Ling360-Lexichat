"""Thin LLM client abstraction so the game can swap providers in one place.

Currently ships a Gemini implementation (new google-genai SDK). Adding Hugging
Face / local Ollama later means writing another subclass with the same signature.
"""
from __future__ import annotations

import json
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


class GeminiClient(LLMClient):
    """Google Gemini via the google-genai SDK.

    Tries models in GEMINI_MODEL_CHAIN in order. If one returns 429 (quota) or
    503 (overloaded), falls through to the next. Remembers which model last
    worked to avoid re-probing dead ones.
    """

    def __init__(self, api_key: str, model_chain: list[str] | None = None):
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
        self._preferred = 0  # index into self._chain

    def chat(self, system: str, messages: list[dict], max_tokens: int = 200) -> str:
        types = self._types
        contents = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))

        # Disable model "thinking" for short conversational replies. The 2.5
        # Flash family otherwise spends most of max_output_tokens on internal
        # reasoning, leaving only a few tokens for the visible reply.
        config_kwargs = dict(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=0.9,
        )
        try:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except (AttributeError, TypeError):
            # Older SDK / models without thinking control — skip silently.
            pass
        config = types.GenerateContentConfig(**config_kwargs)

        last_err: Exception | None = None
        for model_idx in range(self._preferred, len(self._chain)):
            model = self._chain[model_idx]
            for attempt in range(2):
                try:
                    response = self._client.models.generate_content(
                        model=model, contents=contents, config=config,
                    )
                    self._preferred = model_idx
                    return (response.text or "").strip()
                except Exception as e:
                    last_err = e
                    msg = str(e).lower()
                    # Fall through to next model on quota or availability issues
                    if any(k in msg for k in ("429", "quota", "resource_exhausted",
                                              "503", "unavailable", "500", "internal")):
                        break  # stop retrying this model; try next one
                    # Non-transient: propagate immediately
                    raise LLMError(f"Gemini call failed on {model}: {e}") from e
            # short pause before trying the next model
            time.sleep(1)

        raise LLMError(f"All Gemini models unavailable. Last error: {last_err}")


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
