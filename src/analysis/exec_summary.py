"""Block D — grounded LLM executive summary.

Reads the *computed* insight findings (numbers already derived deterministically
in ``insights.py``) and asks an LLM to synthesise a short executive summary plus
prioritised actions. Grounding: the model is handed ONLY those findings and told
to invent nothing. If no LLM is available (or it fails), we fall back to a
deterministic summary built straight from the takeaways — no fabrication,
consistent with the Story engine's philosophy. Pure module (no Streamlit).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.analysis.insights import Insight
from src.engine.providers import build_with_fallback
from src.engine.providers.base import ContentError, TransportError
from src.structs import DETERMINISTIC_PROVIDER

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

EXEC_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "top_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "top_actions"],
    "additionalProperties": False,
}


@dataclass
class ExecSummary:
    summary: str
    top_actions: list[str] = field(default_factory=list)
    provider: str = DETERMINISTIC_PROVIDER
    note: str = ""

    def attribution(self) -> str:
        """One honest sentence about who wrote this — the two cases read as
        different sentences rather than the same template with a swapped noun."""
        if self.provider == DETERMINISTIC_PROVIDER:
            return ("Composed directly from the computed findings above — "
                    "no model was involved.")
        return (f"Narrated by {self.provider} from the computed findings above; "
                f"the numbers themselves are code-derived, not model-written.")


def _findings(items: list[Insight]) -> str:
    return "\n".join(f"- {i.title}: {i.takeaway}" for i in items)


def build_prompts(kpis: dict, items: list[Insight], language: str = "English") -> tuple[str, str]:
    system = (
        f"You are a support-operations analyst writing for a service-desk manager, "
        f"in {language}. Use ONLY the findings provided — never invent numbers, "
        f"causes, customers, products, or teams. Recommend only what a finding "
        f"actually states. A concentration, a ranking, or an uneven distribution "
        f"is an observation, NOT a problem: do not propose fixing, rebalancing, "
        f"or reducing something unless a finding says it is causing harm. Where a "
        f"finding calls itself directional or flags a caveat, carry that caveat "
        f"into your wording rather than dropping it. Be concrete and action-oriented. "
        f'Return JSON with exactly: "summary" (one tight paragraph, 3-5 sentences) '
        f'and "top_actions" (3-5 prioritised, specific actions).'
    )
    user = (
        f"KPIs: {kpis['tickets']} tickets, {kpis['customers']} customers, "
        # Spelled out in its own unit: handed "38%" beside a ticket count, a
        # model writes "38% of tickets", which is not what this measures.
        f"repeat-contact rate {kpis['repeat_rate']:.0%} "
        f"({kpis['repeat_occasions']} of {kpis['contact_occasions']} contact "
        f"occasions — tickets raised together count once), escalation rate "
        f"{kpis['escalation_rate']:.0%}, leading root cause {kpis['top_theme']} "
        f"({kpis['top_theme_pct']:.0%}).\n\nFindings:\n{_findings(items)}"
    )
    return system, user


def _deterministic(kpis: dict, items: list[Insight], note: str) -> ExecSummary:
    """No-LLM fallback: synthesise from the computed numbers, zero fabrication."""
    summary = (
        f"Across {kpis['tickets']} tickets from {kpis['customers']} customers, the "
        f"standout patterns are a {kpis['repeat_rate']:.0%} repeat-contact rate "
        f"({kpis['repeat_occasions']} of {kpis['contact_occasions']} contact "
        f"occasions) and "
        f"{kpis['top_theme']} as the leading root cause ({kpis['top_theme_pct']:.0%} "
        f"of tickets), with {kpis['escalation_rate']:.0%} of tickets escalating "
        f"beyond a first-line fix."
    )
    actions = [i.takeaway for i in items if i.has_signal][:3]
    return ExecSummary(summary, actions, DETERMINISTIC_PROVIDER, note)


def generate(kpis: dict, items: list[Insight], provider_name: str | None,
             language: str = "English") -> ExecSummary:
    """LLM summary grounded on the findings; deterministic fallback on failure."""
    provider = build_with_fallback(provider_name)
    system, user = build_prompts(kpis, items, language)
    try:
        data = provider.complete_json(system, user, EXEC_SCHEMA)
    except (TransportError, ContentError):
        return _deterministic(kpis, items, "LLM unavailable — deterministic summary.")

    summary = str(data.get("summary", "")).strip()
    if not summary:
        return _deterministic(kpis, items, "LLM returned no summary — deterministic fallback.")
    actions = [str(a).strip() for a in data.get("top_actions", []) if str(a).strip()]

    strays = _stray_numbers(summary + " " + " ".join(actions), system + "\n" + user)
    note = ""
    if strays:
        note = (f"⚠ {len(strays)} number{'' if len(strays) == 1 else 's'} in this "
                f"summary could not be traced to the computed data: "
                f"{', '.join(strays)}.")
    return ExecSummary(summary, actions,
                       getattr(provider, "name", provider_name or ""), note)


def _numbers(text: str) -> set[str]:
    return {m.group().replace(",", "") for m in _NUMBER.finditer(text)}


def _stray_numbers(generated: str, allowed_text: str) -> list[str]:
    """Numbers in the generated text that appear nowhere in what we gave the model."""
    allowed = _numbers(allowed_text)
    seen: set[str] = set()
    strays: list[str] = []
    for m in _NUMBER.finditer(generated):
        n = m.group().replace(",", "")
        if n not in allowed and n not in seen:
            seen.add(n)
            strays.append(n)
    return strays
