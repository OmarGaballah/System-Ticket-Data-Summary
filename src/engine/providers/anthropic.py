"""Anthropic adapter — normalizes native structured outputs to our JSON dict.

Uses ``output_config.format`` (real JSON-Schema enforcement, supported on
claude-sonnet-5). SDK is imported lazily so a missing ``anthropic`` package never
breaks the app.
"""

from __future__ import annotations

from src import consts
from src.engine.providers.base import TransportError, extract_json, sdk_available
from src.engine.schema import phase_json_schema


class AnthropicProvider:
    name = consts.PROVIDER_ANTHROPIC

    def __init__(self, api_key: str | None, model: str | None = None) -> None:
        if not api_key:
            raise TransportError("missing Anthropic API key")
        if not sdk_available("anthropic"):
            raise TransportError("anthropic SDK not installed")
        self._key = api_key
        self.model = model or consts.PROVIDER_MODELS[self.name]
        self._client = None

    def _client_(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._key)
        return self._client

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict:
        import anthropic
        try:
            resp = self._client_().messages.create(
                model=self.model,
                max_tokens=8000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema",
                                          "schema": schema or phase_json_schema()}},
            )
        except (anthropic.APIConnectionError, anthropic.RateLimitError,
                anthropic.InternalServerError) as e:
            raise TransportError(str(e)) from e
        except anthropic.APIStatusError as e:
            raise TransportError(str(e)) from e
        text = "".join(getattr(b, "text", "") for b in resp.content
                       if getattr(b, "type", "") == "text")
        return extract_json(text)
