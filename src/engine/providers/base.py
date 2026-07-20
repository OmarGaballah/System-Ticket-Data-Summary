"""Provider interface + shared helpers.

Every provider adapter normalizes its own structured-output mechanism to the
SAME thing: ``complete_json(system, user, schema=None) -> dict``. The optional
``schema`` is the JSON shape to enforce; when omitted, adapters default to the
five-phase summary schema (the Story engine's contract). The rest of the app
never branches on provider — that difference dies inside each adapter.

Two failure classes, deliberately distinct (see providers/__init__ fallback):
- ``TransportError``  -> availability failure (timeout / 429 / 5xx / missing key).
  These are safe to fall over to another provider.
- ``ContentError``    -> the model replied but we couldn't parse JSON from it.
  NOT a transport failure; do not silently swap voices mid-report.
"""

from __future__ import annotations

import json
import re
from typing import Protocol, runtime_checkable


class TransportError(Exception):
    """Availability failure — eligible for provider fallback."""


class ContentError(Exception):
    """Model replied but the response wasn't parseable JSON."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict:
        """Return a parsed JSON object conforming to ``schema`` (default: phases)."""
        ...


def sdk_available(module: str) -> bool:
    """True if an SDK module can be imported, without importing it."""
    import importlib.util
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def extract_json(text) -> dict:
    """Best-effort parse of a JSON object from a model response.

    Handles the common cases (already-parsed dict, ```json fences, leading/
    trailing prose) before giving up with ``ContentError``.
    """
    if isinstance(text, dict):
        return text
    s = str(text).strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", s, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise ContentError("could not parse a JSON object from the model response")
