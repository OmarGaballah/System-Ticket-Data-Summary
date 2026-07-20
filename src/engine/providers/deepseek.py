"""DeepSeek adapter — OpenAI-compatible client against the DeepSeek base URL.

DeepSeek offers only ``json_object`` mode (valid JSON, but no schema
enforcement) — the weakest of the four. That's exactly why the self-correction
loop matters most here: the adapter returns best-effort JSON and the loop /
validator absorb the difference. Model names use the v4 IDs (deepseek-chat /
deepseek-reasoner retired 2026-07-24).
"""

from __future__ import annotations

from src import consts
from src.engine.providers.base import TransportError, extract_json, sdk_available

_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider:
    name = consts.PROVIDER_DEEPSEEK

    def __init__(self, api_key: str | None, model: str | None = None) -> None:
        if not api_key:
            raise TransportError("missing DeepSeek API key")
        if not sdk_available("openai"):
            raise TransportError("openai SDK not installed (DeepSeek uses the "
                                 "OpenAI-compatible client)")
        self._key = api_key
        self.model = model or consts.PROVIDER_MODELS[self.name]
        self._client = None

    def _client_(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._key, base_url=_BASE_URL)
        return self._client

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict:
        import openai
        try:
            resp = self._client_().chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                response_format={"type": "json_object"},
            )
        except (openai.APITimeoutError, openai.APIConnectionError,
                openai.RateLimitError, openai.InternalServerError) as e:
            raise TransportError(str(e)) from e
        except openai.APIStatusError as e:
            raise TransportError(str(e)) from e
        return extract_json(resp.choices[0].message.content)
