"""Provider registry, key resolution, and transport-only fallback.

This is the client layer (the old ``llm_client.py`` folded in). Real adapters are
built lazily so a missing SDK or key never breaks import — an unavailable
provider is simply skipped. Only providers with a working key + SDK are offered.
When none can serve, the chain fails as a ``TransportError`` and the summarizer
renders the deterministic grounded view (``engine/fallback.py``) — we never
fabricate.

Fallback is **transport-only**: ``FallbackProvider`` moves to the next provider on
``TransportError`` (timeout / 429 / 5xx / missing key) but lets ``ContentError``
propagate — we never silently swap providers (voices) on a content failure. The
grounded self-correction loop retries the *same* provider on a grounding failure.
"""

from __future__ import annotations

import os

from src import consts
from src.engine.providers.base import (ContentError, LLMProvider, TransportError,
                                       extract_json)

__all__ = ["get_provider", "available_providers", "get_api_key",
           "FallbackProvider", "build_with_fallback",
           "TransportError", "ContentError", "extract_json"]

#: Ollama is absent on purpose: it runs locally and takes no key.
_ENV = {
    consts.PROVIDER_ANTHROPIC: "ANTHROPIC_API_KEY",
    consts.PROVIDER_OPENAI: "OPENAI_API_KEY",
    consts.PROVIDER_GEMINI: "GEMINI_API_KEY",
    consts.PROVIDER_DEEPSEEK: "DEEPSEEK_API_KEY",
}


def get_api_key(provider: str) -> str | None:
    """Resolve a key from st.secrets (if in a Streamlit context) then env."""
    env_name = _ENV.get(provider)
    if not env_name:
        return None
    try:
        import streamlit as st
        if env_name in st.secrets:
            return st.secrets[env_name]
    except Exception:
        pass  
    return os.environ.get(env_name)



def _build_anthropic():
    from src.engine.providers.anthropic import AnthropicProvider
    return AnthropicProvider(get_api_key(consts.PROVIDER_ANTHROPIC))


def _build_openai():
    from src.engine.providers.openai import OpenAIProvider
    return OpenAIProvider(get_api_key(consts.PROVIDER_OPENAI))


def _build_gemini():
    from src.engine.providers.gemini import GeminiProvider
    return GeminiProvider(get_api_key(consts.PROVIDER_GEMINI))


def _build_deepseek():
    from src.engine.providers.deepseek import DeepSeekProvider
    return DeepSeekProvider(get_api_key(consts.PROVIDER_DEEPSEEK))


def _build_ollama():
    from src.engine.providers.ollama import OllamaProvider
    return OllamaProvider()


_BUILDERS = {
    consts.PROVIDER_ANTHROPIC: _build_anthropic,
    consts.PROVIDER_OPENAI: _build_openai,
    consts.PROVIDER_GEMINI: _build_gemini,
    consts.PROVIDER_DEEPSEEK: _build_deepseek,
    consts.PROVIDER_OLLAMA: _build_ollama,
}

assert set(_BUILDERS) == set(consts.PROVIDER_MODELS), (
    "_BUILDERS must cover exactly the providers declared in consts")


def get_provider(name: str) -> LLMProvider:
    """Build one provider by name. Raises TransportError if unavailable."""
    if name not in _BUILDERS:
        raise KeyError(f"unknown provider: {name}")
    return _BUILDERS[name]()


def available_providers() -> list[str]:
    """Real providers that can actually be built right now (key + SDK present).

    Empty when no key is configured — the page then shows the deterministic
    grounded view rather than any synthetic output.
    """
    out: list[str] = []
    for name in consts.FALLBACK_ORDER:
        try:
            get_provider(name)
            out.append(name)
        except Exception:
            pass
    return out


class _UnavailableProvider:
    """Stands in when no real provider can be built.

    Fails as a ``TransportError`` on call, which the summarizer catches to render
    the deterministic grounded view. Keeps the summarizer's interface uniform
    (it always receives a provider) without special-casing "no LLM" upstream.
    """
    name = "none"
    model = ""

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict:
        raise TransportError("no LLM provider configured")


class FallbackProvider:
    """Tries providers in order; falls over on TransportError ONLY.

    ``name``/``model`` update to whichever provider actually served the last
    call, so a ProductSummary records the real provider (and mixed runs are
    visible rather than hidden).
    """

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("FallbackProvider needs at least one provider")
        self._providers = providers
        self.name = providers[0].name
        self.model = providers[0].model
        self.trace: list[str] = []

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict:
        last: Exception | None = None
        for provider in self._providers:
            try:
                result = provider.complete_json(system, user, schema)
                self.name, self.model = provider.name, provider.model
                return result
            except TransportError as e:  # availability only -> try next
                self.trace.append(f"{provider.name} unavailable ({e})")
                last = e
        raise TransportError(f"all providers failed; last error: {last}")


def build_with_fallback(primary: str | None) -> FallbackProvider:
    """Build a FallbackProvider preferring ``primary``, then the rest in order.

    Real providers only. When none can be built, the chain contains a single
    ``_UnavailableProvider`` that fails as a ``TransportError`` — the summarizer
    then renders the deterministic grounded view. The chain never dead-ends and
    never fabricates.
    """
    order = [primary] + [p for p in consts.FALLBACK_ORDER if p != primary]
    built: list[LLMProvider] = []
    for name in order:
        if not name:
            continue
        try:
            built.append(get_provider(name))
        except Exception:
            pass
    if not built:
        built.append(_UnavailableProvider())
    return FallbackProvider(built)
