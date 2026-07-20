"""Block C — the grounded self-correction step (the agentic core).

For one product's tickets: build a compact payload -> ask the provider for a
five-phase JSON -> verify grounding deterministically -> if anything is off, feed
the exact error back and let the model regenerate **once**. This is the Reflexion
pattern with a deterministic verifier as the environment: it closes the loop on
hallucination, which is the whole credibility story.

Why exactly one retry, and why it exists at all:

* It is not what makes the output correct — ``facts.enforce`` is, unconditionally
  and without the model. The retry exists for *coherence*. When the model omits a
  ticket, ``facts._place_omitted`` repairs coverage by appending that ticket to a
  phase by date, but it cannot write prose: the phase then cites N tickets while
  its narrative describes N-1. ``assert_consistent`` cannot see that — both
  halves are non-empty — and no deterministic layer can fix it, because only
  whoever chose the tickets can describe them. Regeneration is the only repair.
* One and no more: the second request carries the exact errors from the first. A
  model that still fails with the answer in hand is failing systematically, and
  further attempts spend money to arrive at the same place the facts layer
  already guarantees.

Pure module — NO Streamlit import — so it is testable offline with a fake
provider. The page layer adds ``@st.cache_data`` keyed on
(data subset, customer, product, language, provider, model); the retry lives
*inside* that cached call, so a cached story never re-triggers it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src import consts, taxonomy
from src.engine import episodes, facts, fallback, prompts, structure
from src.engine.providers.base import LLMProvider, TransportError
from src.engine.schema import empty_summary
from src.engine.validate import validate_summary
from src.structs import PhaseSummary, ProductSummary


@dataclass
class RetryReport:
    """Whether the grounding check forced a regeneration, and how it went.

    Reported next to ``FactsReport`` rather than kept quiet: a story the model
    wrote twice is a different provenance claim from one it got right first
    time, and the reader is entitled to both.
    """
    attempted: bool = False
    succeeded: bool = False
    reason: str = ""        

    def note(self) -> str:
        if not self.attempted:
            return ""
        if self.succeeded:
            return "Regenerated once after a grounding check."
        return ("Regenerated once after a grounding check; the second draft was "
                "still ungrounded.")


def build_payload(subset: pd.DataFrame, eps: list | None = None) -> list[dict]:
    """Compact, chronological, real-fields-only payload for the LLM.

    Carries every field the NZ anchor recovers (see ``consts.ANCHOR_OFFSETS``),
    not just outcome/cause: ``action`` is the recorded remediation, ``reference``
    the escalation / follow-up marker, ``resolver`` who closed it, and ``team``
    the queue that handled it. Those are what make the middle phases concrete —
    without them the model can only infer process from free text and tends to
    fall back on "No activity".
    """
    ordered = subset.sort_values(consts.OUT_ACCEPT)
    episode_of = {t: e.index for e in (eps or []) for t in e.ticket_numbers}
    phase_of = {t: pid for e, pid in episodes.assignment(eps or [])
                for t in e.ticket_numbers}
    return [
        {
            "ticket": row[consts.OUT_ORDER],
            "episode": episode_of.get(str(row[consts.OUT_ORDER])),
            "phase": phase_of.get(str(row[consts.OUT_ORDER])),
            "service_category": _opt(row[consts.OUT_CATEGORY]),
            "accepted": _iso(row[consts.OUT_ACCEPT]),
            "completed": _iso(row[consts.OUT_COMPLETE]),
            "outcome": row[consts.OUT_OUTCOME],
            "cause": _opt(row[consts.OUT_CAUSE]),
            "cause_theme": (taxonomy.theme(row[consts.OUT_CAUSE])
                            if _opt(row[consts.OUT_CAUSE]) else None),
            "action": taxonomy.redact_internal(_opt(row[consts.OUT_ACTION])),
            "reference": taxonomy.redact_internal(_opt(row[consts.OUT_REFERENCE])),
            "resolver": taxonomy.redact_internal(_opt(row[consts.OUT_RESOLVER])),
            "team": _opt(row[consts.OUT_TEAM]),
            "details": row[consts.OUT_DETAILS],
        }
        for _, row in ordered.iterrows()
    ]


def _iso(value) -> str:
    return "" if pd.isna(value) else pd.Timestamp(value).isoformat()


def _opt(value):
    """Missing / blank -> ``None`` so the model sees an explicit absence."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def summarize_product(
    subset: pd.DataFrame | None,
    product: str,
    language: str,
    provider: LLMProvider,
) -> ProductSummary:
    """Summarize one product's tickets with grounded self-correction."""
    if subset is None or len(subset) == 0:
        return _to_summary(product, empty_summary(), provider,
                           note="No tickets for this product.")

    eps = episodes.compute(subset)
    payload = build_payload(subset, eps)
    valid = [str(x) for x in subset[consts.OUT_ORDER].tolist()]
    valid_set = set(valid)
    system = prompts.build_system(language)
    base_user = prompts.build_user(product, valid, payload, eps)

    try:
        draft = structure.complete_structured(provider, system, base_user, language)
    except TransportError:
        return fallback.deterministic_summary(
            product, subset,
            note="No LLM provider available — showing a factual, "
                 "non-narrated view built directly from the tickets.")

    result = validate_summary(draft, valid_set, eps)
    retry = RetryReport()
    if not result.ok:
        draft, result, retry = _regenerate_once(
            provider, system, base_user, language, valid_set, eps, draft, result)

    if result.episode_errors:
        return fallback.deterministic_summary(
            product, subset,
            note=" ".join(b for b in (
                retry.note(),
                f"The model did not keep the computed episodes intact "
                f"({result.episode_errors[0]}) — showing a factual, "
                f"non-narrated view built directly from the tickets.") if b))

    try:
        enforced, report = facts.enforce(draft or empty_summary(language), subset)
    except structure.StructureError as exc:
        return fallback.deterministic_summary(
            product, subset,
            note=f"The model's summary could not be reconciled with the tickets "
                 f"({exc}) — showing a factual, non-narrated view built directly "
                 f"from the tickets.")
    return _to_summary(product, enforced, provider,
                       note=_compose_note(retry, report))


def _regenerate_once(provider: LLMProvider, system: str, base_user: str,
                     language: str, valid_set: set[str], eps: list,
                     draft: dict, result) -> tuple[dict, object, RetryReport]:
    """Ask for ONE corrected draft, handing back the exact validator complaint.

    The request is for a COMPLETE object, never a patch: a partial update would
    let ticket assignments move while narratives stayed where they were, which
    is precisely the decoupling ``facts.assert_consistent`` exists to catch.

    If the second draft is also ungrounded we keep the FIRST. A retry earns its
    result by passing; swapping in an equally ungrounded draft would just churn
    the prose, and either way ``facts.enforce`` produces the same correct facts.
    """
    retry = RetryReport(attempted=True, reason=result.message)
    user = base_user + prompts.build_revision(result)
    try:
        second = structure.complete_structured(provider, system, user, language)
    except TransportError:
        return draft, result, retry

    second_result = validate_summary(second, valid_set, eps)
    if not second_result.ok:
        return draft, result, retry
    retry.succeeded = True
    return second, second_result, retry


def _to_summary(product: str, data: dict, provider, note: str = "") -> ProductSummary:
    phases = {
        pid: PhaseSummary(
            timeframe=data.get(pid, {}).get("timeframe", ""),
            ticket_numbers=[str(n) for n in data.get(pid, {}).get("ticket_numbers", [])],
            narrative=data.get(pid, {}).get("narrative", ""),
        )
        for pid in consts.PHASE_IDS
    }
    return ProductSummary(
        product=product, phases=phases,
        provider=getattr(provider, "name", ""), model=getattr(provider, "model", ""),
        note=note,
    )


def _compose_note(retry: RetryReport, report: facts.FactsReport) -> str:
    """Provenance note: whether it took a second pass + what code had to correct."""
    return " ".join(b for b in (retry.note(), report.note()) if b)
