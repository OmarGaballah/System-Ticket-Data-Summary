"""Prompt construction for the summarizer — provider-agnostic text.

Adapters wrap the returned ``system`` / ``user`` strings into their own message
format. The phase spec and JSON shape are built from ``consts.PHASES`` so the
prompt and the wire schema (``engine/schema.py``) can never diverge.

The user prompt lists the allowed ticket numbers explicitly — this helps a real
model ground its citations (and lets an offline fake do the same in tests).
"""

from __future__ import annotations

import json

from src import consts
from src.engine import episodes

_SYSTEM_TEMPLATE = """You are a support-operations analyst. You summarize a single \
product's support tickets for one customer into a five-phase story.

The tickets have ALREADY been grouped into episodes for you, by the gaps between
them, and each episode has ALREADY been assigned its phase. You do not decide the
groupings and you do not decide the phases. You write the narratives. That is
your only task.

Rules:
- Use ONLY ticket numbers that appear in the provided data. NEVER invent a ticket number.
- Put each episode in the phase the data section assigns it, whole. Never split
  an episode across two phases, never merge two episodes into one phase, and
  never move a ticket out of the episode it was given in. Every ticket is cited
  exactly once.
- The number of episodes fixes which phases are populated. This table is not a
  guideline and there is no judgment in it:
    1 episode  -> "initial_issue"
    2 episodes -> "initial_issue", "recent_events"
    3 episodes -> "initial_issue", "follow_ups", "recent_events"
    4 episodes -> "initial_issue", "follow_ups", "developments", "recent_events"
    5 episodes -> all five, in order
  Episodes fill those phases in chronological order. Every other phase stays
  empty. An empty phase is not a gap to fill: it is a true statement that this
  stretch of the story had nothing in it.
- Phases are CHRONOLOGICAL, not causal. Do NOT write that one ticket caused,
  triggered, or followed from another unless they share a "service_category" OR a
  field explicitly links them (a "reference" naming a follow-up order, the same
  "cause", the same "action"). One product can cover several unrelated fault types
  — a Broadband story mixes "KAI" and "NET" tickets. Unrelated tickets in the same
  episode are CONCURRENT: narrate them as separate issues handled in the same
  period ("separately", "also"), never as one developing story.
- Write for a service-desk manager, not an operator: describe causes and actions in
  plain language. NEVER quote a raw code such as "URS_KIP_Reset_WLAN_Settings",
  "SIT11" or "k03" — say what it means ("the Wi-Fi settings were reset") instead.
- The "cause" field often names a REMEDIATION, not a root cause — reset,
  optimize, replace, change, restart. Never write that such a cause caused the
  problem: "no Wi-Fi connection, caused by the Wi-Fi settings being reset" blames
  the fix for the fault. Describe it as what was DONE. Attribute causation only
  when the field names an actual fault condition, such as a hardware defect.
- Where a description reads awkwardly or ungrammatically in English, it is a
  truncated or abbreviated source field ("WLAN / Stable" is a clipped
  "stability"). Render its evident meaning in plain language — "a Wi-Fi stability
  issue", not "a stable Wi-Fi issue". Phrase the recorded terms sensibly; never
  add detail that is not there.
- Match the tense of the field. A resolver such as "Techniker behebt Fehler"
  (present tense) records an assignment, not a completion: write "was assigned to
  a technician", not "a technician fixed it". Do not imply an outcome the field
  does not state.
- Never describe the classification system itself. Do not say a cause was
  "categorized", "classified", "recorded under", "unspecified" or "general", and
  never name a theme label. If a cause is not meaningfully recorded, omit any
  mention of cause entirely — do not report its absence.
- Never assert both that an issue was resolved and that its outcome is unknown.
  If "outcome" is Unknown but an "action" or "resolver" indicates the work was
  done, describe what was done and say nothing about the outcome.
- NEVER quote a raw "outcome" value. "OK" and "Error" are stored codes, not
  English: "completed with OK outcomes" is not a sentence a reader can use. Say
  the issue was resolved, or say nothing about the outcome — never the literal
  word OK or Error.
- NEVER write a ticket number inside a narrative. Not in brackets, not as an
  aside, not as "(ticket 001-0670953/24)". Every phase lists its tickets
  separately beneath the prose; repeating them in the sentence is duplication
  the reader has to skip. Write "a firmware update was applied", not "a firmware
  update (ticket ...)".
- Write the events, never the shape of the story. No "the most recent ticket
  reported...", no "the first issue was...", no "in this phase". The phase
  heading and the dates already say where the reader is; a narrative that
  narrates its own position wastes the only sentences it has.
- If a ticket has no acceptance date, say its date is not recorded. Never let it
  read as though it happened alongside the tickets before it.
- A phase's tickets and its narrative are ONE unit: if you cite tickets, write
  about those tickets; if you cite none, the narrative is exactly this and
  nothing else -> {no_activity}
- Write every narrative in {language}.
- Set the top-level "language" field to exactly "{language}".
- Do NOT include timeframes — those are computed automatically from the data.
- Return ONLY a JSON object matching the schema below. No prose, no markdown fences.
- Describe ONLY what the ticket fields record. Never infer customer sentiment,
  satisfaction, or frustration — no such field exists. Never speculate about
  what a code or field might mean. Where a field is empty, write around it: say
  less, never guess, and do not narrate the emptiness itself.
- Never name internal teams, queues, tools, or grouping labels (e.g. TSCW2,
  TITAN, "Other"). The product name is a grouping header, not a fact from the
  data — do not weave it into the narrative.

The five phases (JSON keys), in order:
{phase_spec}

JSON shape:
{{
  "language": "{language}",
{schema_hint}
}}"""


def _phase_spec() -> str:
    return "\n".join(f'- "{p.id}" ({p.title}): {p.guidance}' for p in consts.PHASES)


def build_system(language: str) -> str:
    schema_hint = ",\n".join(
        f'  "{p.id}": {{"ticket_numbers": ["..."], "narrative": "..."}}'
        for p in consts.PHASES
    )
    return _SYSTEM_TEMPLATE.format(
        language=language, phase_spec=_phase_spec(), schema_hint=schema_hint,
        no_activity=consts.NO_ACTIVITY,
    )


_FIELD_LEGEND = """Field meanings:
- "episode": the computed episode this ticket belongs to — not yours to change.
- "phase": the phase key this ticket must be cited under — already decided, not
  a suggestion. Cite the ticket there and nowhere else.
- "service_category": the fault type. Tickets in DIFFERENT categories are unrelated
  problems that merely share a product — never narrate one as following the other.
- "outcome": how the ticket closed (OK / Error / Unknown).
- "cause": the recorded root-cause code — internal, never quote it to the reader.
- "cause_theme": that code in plain business language — use THIS when writing.
- "action": what support actually DID to fix it — the remediation step.
- "reference": a follow-up / escalation marker (a further order was raised).
- "resolver": who or what finally resolved it.
- "team": the queue that handled the ticket; a change of team across tickets is a handoff.
- "details": free-text description and notes.
A null value means the field was empty in the source — say nothing about it."""


def build_user(product: str, valid_tickets: list[str], payload: list[dict],
               eps: list | None = None) -> str:
    """The data half of the prompt: the tickets, and the episodes they form.

    The episodes are stated as fact and followed by the exact placement this
    story requires, so the model *assigns* rather than infers. Without the
    explicit instruction a model reads five phases in the schema and tries to
    fill five phases.
    """
    eps = eps or []
    return (
        f"Product: {product}\n"
        f"You may cite ONLY these ticket numbers: {', '.join(valid_tickets)}\n\n"
        f"{episodes.describe(eps)}\n\n"
        f"{episodes.instruction(eps)}\n\n"
        f"{_FIELD_LEGEND}\n\n"
        f"Tickets (chronological):\n{json.dumps(payload, indent=2, default=str)}"
    )


def build_revision(result) -> str:
    """Correction feedback appended to the prompt when grounding fails.

    Accepts a ``ValidationResult`` and reports every kind of grounding error —
    invented citations, omitted tickets, and duplicates — so the model can
    converge on a clean one-ticket-per-phase partition.
    """
    lines = ["\n\nYOUR PREVIOUS RESPONSE HAD GROUNDING ERRORS."]
    invented = result.invented_tickets()
    if invented:
        lines.append(
            f"These cited ticket numbers do NOT exist in the data: "
            f"{', '.join(invented)} — remove them."
        )
    if result.missing:
        lines.append(
            f"These tickets were left out and must each be assigned to exactly one "
            f"phase: {', '.join(result.missing)}."
        )
    if result.duplicated:
        lines.append(
            f"These tickets were cited by more than one phase — keep each in only "
            f"one: {', '.join(result.duplicated)}."
        )
    if getattr(result, "unnarrated", None):
        lines.append(
            f"These phases cite tickets but say nothing about them: "
            f"{', '.join(result.unnarrated)} — write the narrative for those "
            f"tickets, or move the tickets to the phase you did narrate."
        )
    if getattr(result, "bad_start", ""):
        lines.append(
            f"The story starts at '{result.bad_start}' — the earliest episode "
            f"belongs in '{consts.PHASE_IDS[0]}'."
        )
    for problem in getattr(result, "episode_errors", []) or []:
        lines.append(f"Episode placement is wrong: {problem}.")
    lines.append(
        "Return the COMPLETE corrected JSON object — all five phases, rewritten "
        "in full. Do NOT return a patch, a diff, or only the phases you changed: "
        "a partial answer moves tickets while their narratives stay behind. If "
        "you move a ticket to a different phase, rewrite that phase's narrative "
        "so it describes the tickets it now cites. Cite ONLY the allowed ticket "
        "numbers above, each exactly once, and return ONLY the JSON object.")
    return "\n".join(lines)


def build_structure_retry(error: str) -> str:
    """Correction feedback appended when a response fails structural validation."""
    return (
        "\n\nYOUR PREVIOUS RESPONSE WAS STRUCTURALLY INVALID.\n"
        f"The error was: {error}.\n"
        'Return ONLY a JSON object with a top-level "language" field and exactly '
        'the five phase keys above, each an object with a string "narrative" and a '
        'list-of-strings "ticket_numbers". No prose, no markdown fences.'
    )
