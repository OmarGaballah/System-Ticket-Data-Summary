"""Block C2 — registry, fallback, and JSON-normalization tests (no network)."""

import pytest

from src.engine.providers import (FallbackProvider, available_providers,
                                   build_with_fallback, get_provider)
from src.engine.providers.base import ContentError, TransportError, extract_json

_KEYS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"]


@pytest.fixture
def no_keys(monkeypatch):
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)
    import src.engine.providers as providers
    monkeypatch.setattr(providers, "get_api_key", lambda provider: None)
    import src.engine.providers.ollama as ol

    def _down(base_url):
        raise TransportError("ollama down (test)")
    monkeypatch.setattr(ol, "_installed_models", _down)


def test_no_real_providers_without_keys(no_keys):
    assert available_providers() == []


def test_ollama_skipped_when_unreachable(no_keys):
    with pytest.raises(TransportError):
        get_provider("ollama")


def test_ollama_builds_and_picks_configured_model(monkeypatch):
    import src.engine.providers.ollama as ol
    monkeypatch.setattr(ol, "_installed_models",
                        lambda base_url: ["gemma3:4b", "qwen3:8b"])
    p = get_provider("ollama")
    assert p.name == "ollama"
    assert p.model == "gemma3:4b"          


def test_ollama_auto_falls_back_to_installed_model(monkeypatch):
    import src.engine.providers.ollama as ol
    monkeypatch.setattr(ol, "_installed_models", lambda base_url: ["qwen3:8b"])
    p = get_provider("ollama")
    assert p.model == "qwen3:8b"


def test_real_provider_without_key_raises(no_keys):
    with pytest.raises(TransportError):
        get_provider("anthropic")


def test_unknown_provider():
    with pytest.raises(KeyError):
        get_provider("does-not-exist")


def test_fallback_skips_transport_errors():
    class Boom:
        name, model = "boom", "m1"
        def complete_json(self, s, u, schema=None):
            raise TransportError("down")

    class Good:
        name, model = "good", "m2"
        def complete_json(self, s, u, schema=None):
            return {"served": True}

    fb = FallbackProvider([Boom(), Good()])
    assert fb.complete_json("", "") == {"served": True}
    assert fb.name == "good"                
    assert any("boom" in t for t in fb.trace)


def test_fallback_does_not_catch_content_error():
    
    class BadJSON:
        name, model = "bad", "m"
        def complete_json(self, s, u, schema=None):
            raise ContentError("unparseable")

    class Good:
        name, model = "good", "m2"
        def complete_json(self, s, u, schema=None):
            return {}

    fb = FallbackProvider([BadJSON(), Good()])
    with pytest.raises(ContentError):
        fb.complete_json("", "")


def test_build_with_fallback_without_keys_fails_as_transport(no_keys):
    fb = build_with_fallback("anthropic")
    assert isinstance(fb, FallbackProvider)
    with pytest.raises(TransportError):
        fb.complete_json("", "")


def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure, here it is: {"a": 1} — done') == {"a": 1}
    assert extract_json({"already": "parsed"}) == {"already": "parsed"}
    with pytest.raises(ContentError):
        extract_json("no json here")
