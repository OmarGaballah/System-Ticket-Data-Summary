"""Gemini adapter (google-genai SDK).

Uses ``response_mime_type = application/json`` and relies on the prompt's schema
description; our flat five-phase shape is well within what Gemini enforces. (A
``response_schema`` can be added once validated against the installed SDK — kept
prompt-driven here so it's robust across google-genai versions.) SDK imported
lazily.
"""

from __future__ import annotations

from src import consts
from src.engine.providers.base import TransportError, extract_json, sdk_available


class GeminiProvider:
    name = consts.PROVIDER_GEMINI

    def __init__(self, api_key: str | None, model: str | None = None) -> None:
        if not api_key:
            raise TransportError("missing Gemini API key")
        if not sdk_available("google.genai"):
            raise TransportError("google-genai SDK not installed")
        self._key = api_key
        self.model = model or consts.PROVIDER_MODELS[self.name]
        self._client = None

    def _client_(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self._key)
        return self._client

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict:
        from google.genai import errors as gerr
        try:
            resp = self._client_().models.generate_content(
                model=self.model,
                contents=user,
                config={"system_instruction": system,
                        "response_mime_type": "application/json"},
            )
        except gerr.APIError as e:
            raise TransportError(str(e)) from e
        return extract_json(resp.text)
