"""Tier 1 — structural validation (guarantee: absolute).

Every LLM response must parse against the pydantic ``SummaryModel`` in
``schema.py``: exactly five phases, correct field types, and a ``language`` field
matching the request. This is the layer that catches the *boring* failures — a
dropped phase, a stringified list, prose instead of JSON — that would otherwise
crash rendering.

The contract:

* ``validate_structure`` — pure check. Parse against the schema and verify the
  language field. Raises ``StructureError`` (with a readable message) on any
  structural problem; never renders garbage.
* ``complete_structured`` — the retry-once-then-fail-loud wrapper. Malformed
  output triggers ONE retry with the exact error fed back into the prompt; if it
  is still broken we fail loudly with ``StructureError`` rather than pass garbage
  downstream. ``TransportError`` is deliberately *not* caught here — availability
  is a separate concern (the summarizer degrades to the deterministic view).

No LLM, no Streamlit — pure and offline-testable.
"""

from __future__ import annotations

from pydantic import ValidationError

from src.engine import prompts
from src.engine.providers.base import ContentError, LLMProvider
from src.engine.schema import SummaryModel

STRUCTURE_RETRIES = 1


class StructureError(Exception):
    """A response failed structural validation and could not be repaired."""


def validate_structure(raw: dict, language: str) -> dict:
    """Validate ``raw`` against the schema and the requested language.

    Returns the normalized dict (schema-shaped, numbers coerced to strings) on
    success. Raises ``StructureError`` with a readable message otherwise.
    """
    if not isinstance(raw, dict):
        raise StructureError("response is not a JSON object")
    try:
        model = SummaryModel.model_validate(raw)
    except ValidationError as e:
        raise StructureError(_format_errors(e)) from e

    data = model.model_dump()
    got = str(data.get("language", "")).strip()
    if got.lower() != language.strip().lower():
        raise StructureError(
            f"language field is '{got}' but '{language}' was requested"
        )
    return data


def complete_structured(provider: LLMProvider, system: str, user: str,
                        language: str, *,
                        retries: int = STRUCTURE_RETRIES) -> dict:
    """Get a structurally valid five-phase summary, or fail loudly.

    One retry on malformed output, with the exact parse/validation error appended
    to the prompt so the model can self-correct. Still broken after the retry ->
    ``StructureError``. ``TransportError`` is not caught (it propagates so the
    caller can fall over to another provider / the deterministic view).
    """
    last_error: str | None = None
    for _ in range(retries + 1):
        prompt = user if last_error is None else user + prompts.build_structure_retry(last_error)
        try:
            raw = provider.complete_json(system, prompt)
        except ContentError as e:
            last_error = f"response was not valid JSON ({e})"
            continue
        try:
            return validate_structure(raw, language)
        except StructureError as e:
            last_error = str(e)
            continue

    raise StructureError(
        f"LLM output failed structural validation after {retries + 1} attempt(s): "
        f"{last_error}"
    )


def _format_errors(exc: ValidationError) -> str:
    """Compact, model-friendly summary of a pydantic validation error."""
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ())) or "(root)"
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    return "; ".join(parts) or "schema validation failed"
