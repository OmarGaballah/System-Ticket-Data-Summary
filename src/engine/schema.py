"""The contract for a summary — the single shape every provider returns.

Two views of the same contract, both built from ``consts.PHASE_IDS`` so the
prompt, the wire schema, and the in-process validator can never diverge:

* ``phase_json_schema()`` — a flat JSON Schema dict handed to the providers that
  enforce structured output natively (Anthropic / OpenAI / Ollama). Kept
  deliberately flat: Gemini enforces only a subset of JSON Schema and rejects
  deep nesting, so do not add ``minLength`` / ``pattern`` / nesting.
* ``SummaryModel`` — the pydantic model every response is validated against
  post-hoc (Tier 1 structural validation, see ``engine/structure.py``). This is
  the *absolute* structural guarantee: it holds even for providers that don't
  enforce a schema natively (Gemini prompt-driven, DeepSeek ``json_object``).

Shape (one object per phase, keyed by phase id, plus a top-level ``language``)::

    {"language": "English",
     "initial_issue": {"ticket_numbers": [str], "narrative": str}, ...}

Note there is deliberately no ``timeframe`` here: timeframes are never
model-generated — code computes them from the assigned tickets' real timestamps
(Tier 2, ``engine/facts.py``). A model can't hallucinate what it never writes.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, create_model

from src.consts import DEFAULT_LANGUAGE, NO_ACTIVITY, PHASES, PHASE_IDS


def phase_json_schema() -> dict:
    """JSON Schema for one product's five-phase summary (native-enforcement view).

    Mirrors ``SummaryModel``: a top-level ``language`` string plus one object per
    phase id, each with ``ticket_numbers`` / ``narrative`` (no ``timeframe`` —
    code computes that, see the module docstring).
    """
    phase_object = {
        "type": "object",
        "properties": {
            "ticket_numbers": {"type": "array", "items": {"type": "string"}},
            "narrative": {"type": "string"},
        },
        "required": ["ticket_numbers", "narrative"],
        "additionalProperties": False,
    }
    properties: dict = {"language": {"type": "string"}}
    properties.update({pid: phase_object for pid in PHASE_IDS})
    return {
        "type": "object",
        "properties": properties,
        "required": ["language", *PHASE_IDS],
        "additionalProperties": False,
    }


class PhaseModel(BaseModel):
    """One phase block. Stray keys are dropped (``extra="ignore"``) so a model
    that volunteers a ``timeframe`` we don't want isn't a spurious failure;
    numbers are coerced to strings so integer ticket numbers are a *boring* pass.
    """

    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)

    ticket_numbers: list[str]
    narrative: str


def _build_summary_model() -> type[BaseModel]:
    """Build the top-level model from ``PHASE_IDS`` so the five phases are
    required *exactly* (``extra="forbid"`` rejects a sixth) and the ``language``
    field is mandatory.
    """
    fields: dict = {pid: (PhaseModel, ...) for pid in PHASE_IDS}
    fields["language"] = (str, ...)
    return create_model(
        "SummaryModel",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


SummaryModel = _build_summary_model()


def empty_summary(language: str = DEFAULT_LANGUAGE) -> dict:
    """A well-formed summary with every phase marked 'no activity'."""
    summary: dict = {"language": language}
    summary.update(
        {p.id: {"ticket_numbers": [], "narrative": NO_ACTIVITY} for p in PHASES}
    )
    return summary
