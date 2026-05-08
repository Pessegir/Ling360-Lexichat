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


# --------------------------------------------------------------------------
# OpenAI-compatible HTTP clients (Deepseek, Hugging Face, OpenRouter)
#
# All three providers expose a /v1/chat/completions endpoint that accepts
# the standard OpenAI request shape. One shared base class handles HTTP,
# error mapping, circuit-breaker + model-chain fallback; subclasses just
# configure base_url, model_chain, and any provider-specific headers.
# --------------------------------------------------------------------------


# Default fallback chains. Subclasses override at construction.
DEEPSEEK_MODEL_CHAIN = ["deepseek-v4-flash", "deepseek-v4-pro"]
HUGGINGFACE_DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct"
OPENROUTER_FREE_CHAIN = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-chat:free",
    "qwen/qwen-2.5-72b-instruct:free",
]


class OpenAICompatibleClient(LLMClient):
    """Shared HTTP client for any /v1/chat/completions endpoint.

    Tries models in `model_chain` order. 429/503 → fall through to next.
    All models exhausted → open the circuit breaker for `cb_max` seconds;
    subsequent calls raise LLMError immediately so the host can fall back
    to scripted lines without waiting on the network.
    """

    def __init__(self, *, api_key: str, base_url: str,
                 model_chain: list[str], extra_headers: dict | None = None,
                 provider_name: str = "openai",
                 timeout: float = 30.0,
                 cb_max: float = CIRCUIT_BREAKER_DEFAULT_COOLDOWN):
        if not api_key:
            raise LLMError(f"Missing {provider_name} API key.")
        if not model_chain:
            raise LLMError(f"{provider_name}: model_chain cannot be empty.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_chain = list(model_chain)
        self.extra_headers = dict(extra_headers or {})
        self.provider_name = provider_name
        self.timeout = timeout
        self._preferred = 0
        self._cb_until: float = 0.0
        self._cb_max = cb_max

    def chat(self, system: str, messages: list[dict], max_tokens: int = 200) -> str:
        # Lazy import — keep `requests` optional at module-load time
        # (importing llm_client shouldn't fail just because requests is
        # missing; only fails when an OpenAI-compat client is actually used).
        import requests

        now = time.monotonic()
        if now < self._cb_until:
            remaining = self._cb_until - now
            raise LLMError(
                f"{self.provider_name} quota exhausted; retrying in ~{remaining:.0f}s"
            )

        oai_messages: list[dict] = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        oai_messages.extend(messages)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)

        last_err: str | None = None
        suggested_retry: float | None = None

        for model_idx in range(self._preferred, len(self.model_chain)):
            model = self.model_chain[model_idx]
            payload = {
                "model": model,
                "messages": oai_messages,
                "max_tokens": max_tokens,
                "temperature": 0.9,
            }
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                raise LLMError(f"{self.provider_name} network error: {e}") from e

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    text = (data["choices"][0]["message"]["content"] or "").strip()
                except (ValueError, KeyError, IndexError) as e:
                    raise LLMError(
                        f"{self.provider_name} returned unparseable response: {e}"
                    ) from e
                self._preferred = model_idx
                return text

            err_text = resp.text[:300]
            last_err = f"{resp.status_code} {err_text}"
            if resp.status_code in (429, 502, 503, 504, 500):
                # Quota / overload / transient — try next model in chain.
                # Try to read a Retry-After header (seconds or HTTP date).
                ra = resp.headers.get("Retry-After")
                if ra:
                    try:
                        rs = float(ra)
                        if suggested_retry is None or rs < suggested_retry:
                            suggested_retry = rs
                    except ValueError:
                        pass  # HTTP-date format — ignore, use default cooldown
                # Or parse from JSON error body
                rs = _parse_retry_seconds(err_text)
                if rs is not None and (suggested_retry is None or rs < suggested_retry):
                    suggested_retry = rs
                continue

            # 4xx (auth, malformed, etc.) — non-transient, propagate.
            raise LLMError(f"{self.provider_name} {resp.status_code}: {err_text}")

        cooldown = min(suggested_retry or self._cb_max, self._cb_max)
        self._cb_until = time.monotonic() + cooldown
        raise LLMError(
            f"All {self.provider_name} models unavailable; backing off "
            f"{cooldown:.0f}s. Last error: {last_err}"
        )


class DeepseekClient(OpenAICompatibleClient):
    """Deepseek API (deepseek.com). Cheapest commercial tier as of 2026-05;
    new accounts get 5 M signup tokens. OpenAI-compatible.
    """

    def __init__(self, api_key: str, model_chain: list[str] | None = None):
        super().__init__(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            model_chain=model_chain or DEEPSEEK_MODEL_CHAIN,
            provider_name="Deepseek",
        )


class HuggingFaceClient(OpenAICompatibleClient):
    """Hugging Face Inference Providers via the unified router endpoint.
    Routes to whichever downstream provider HF picks (Together, Fireworks,
    etc.). Free tier exists but monthly credits exhaust quickly.
    """

    def __init__(self, api_key: str, model: str = HUGGINGFACE_DEFAULT_MODEL,
                 model_chain: list[str] | None = None):
        super().__init__(
            api_key=api_key,
            base_url="https://router.huggingface.co/v1",
            model_chain=model_chain or [model],
            provider_name="Hugging Face",
        )


class OpenRouterClient(OpenAICompatibleClient):
    """OpenRouter aggregator. Free tier uses :free-suffixed models with
    rate limits around 20 rpm / 50 rpd — good fallback, not a daily driver.
    Requires HTTP-Referer / X-Title headers per OpenRouter docs.
    """

    def __init__(self, api_key: str, model_chain: list[str] | None = None,
                 referer: str = "https://github.com/lexi-chat",
                 title: str = "Lexi-Chat"):
        super().__init__(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            model_chain=model_chain or OPENROUTER_FREE_CHAIN,
            extra_headers={"HTTP-Referer": referer, "X-Title": title},
            provider_name="OpenRouter",
        )
