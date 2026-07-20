"""OpenAI adapter — normalizes strict json_schema structured outputs to our dict.

Also used as the base client shape for DeepSeek (OpenAI-compatible). SDK imported
lazily.
"""

from __future__ import annotations

from src import consts
from src.engine.providers.base import TransportError, extract_json, sdk_available
from src.engine.schema import phase_json_schema


class OpenAIProvider:
    name = consts.PROVIDER_OPENAI

    def __init__(self, api_key: str | None, model: str | None = None,
                 base_url: str | None = None) -> None:
        if not api_key:
            raise TransportError("missing OpenAI API key")
        if not sdk_available("openai"):
            raise TransportError("openai SDK not installed")
        self._key = api_key
        self._base_url = base_url
        self.model = model or consts.PROVIDER_MODELS[self.name]
        self._client = None

    def _client_(self):
        if self._client is None:
            from openai import OpenAI
            kwargs = {"api_key": self._key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict:
        import openai
        try:
            resp = self._client_().chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "structured_output", "strict": True,
                                    "schema": schema or phase_json_schema()},
                },
            )
        except (openai.APITimeoutError, openai.APIConnectionError,
                openai.RateLimitError, openai.InternalServerError) as e:
            raise TransportError(str(e)) from e
        except openai.APIStatusError as e:
            raise TransportError(str(e)) from e
        return extract_json(resp.choices[0].message.content)
