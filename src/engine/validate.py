"""Grounding detection — the self-correction loop's verifier (deterministic, no LLM).

Checks that a model summary is structurally complete and that its citations form
a clean partition of the customer/product slice:

* invented — a cited ticket that does not exist in the slice (hallucination);
* missing  — a ticket in the slice that no phase cites (omission, hallucination's
  quiet twin);
* duplicated — a ticket cited by more than one phase;
* unnarrated — a phase that cites tickets but writes nothing about them. A
  phase is a pair (its tickets, the words about them); half a phase is not a
  smaller story, it is a broken one.
* bad_start — the story's first populated phase is not "initial_issue".
* episode_errors — the populated phases do not reproduce the computed episodes:
  the wrong phases, or a phase whose ticket set is not exactly one episode's.
  Episodes *and their phases* come from ``engine/episodes.py`` and are handed to
  the model as fact. It has no freedom here at all: the check is an equality
  against ``episodes.phase_slots``.

Phases are still not required to be contiguous, and this is not a contiguity
check. Three episodes populate initial_issue, follow_ups and recent_events, so
two empty phases sit between the second chapter and the third — correct by
construction.

Any of these makes the result ``not ok`` so the summarizer can feed the exact
errors back to the model. This is *detection* for the loop; ``engine/facts.py``
is the deterministic *enforcement* that guarantees the invariants regardless of
whether the model ever converges — but note that facts.py deliberately does NOT
repair an episode violation. Moving a ticket between finished phases is what
separated tickets from the prose written about them once before; the answer to a
broken partition is a new draft, or the deterministic view.
"""

from __future__ import annotations

from src import consts
from src.engine import episodes as episodes_mod
from src.structs import ValidationResult


def validate_summary(summary: dict, valid_tickets: set[str],
                     eps: list | None = None) -> ValidationResult:
    structural: list[str] = []
    invented: dict[str, list[str]] = {}
    cited_counts: dict[str, int] = {}
    unnarrated: list[str] = []
    populated: list[str] = []
    phase_tickets: dict[str, list[str]] = {}

    if not isinstance(summary, dict):
        return ValidationResult(False, {}, ["summary is not a JSON object"],
                                "summary is not a JSON object")

    for phase in consts.PHASES:
        block = summary.get(phase.id)
        if not isinstance(block, dict):
            structural.append(f"missing or invalid phase '{phase.id}'")
            continue
        nums = block.get("ticket_numbers", [])
        if not isinstance(nums, list):
            structural.append(f"phase '{phase.id}' ticket_numbers is not a list")
            continue
        bad: list[str] = []
        for n in nums:
            s = str(n)
            if s not in valid_tickets:
                bad.append(s)
            else:
                cited_counts[s] = cited_counts.get(s, 0) + 1
        if bad:
            invented[phase.id] = bad
        if nums:
            populated.append(phase.id)
            phase_tickets[phase.id] = [str(n) for n in nums if str(n) in valid_tickets]
        if nums and not str(block.get("narrative", "")).strip():
            unnarrated.append(phase.id)

    duplicated = [t for t, c in cited_counts.items() if c > 1]
    missing = [t for t in valid_tickets if t not in cited_counts]
    bad_start = (populated[0] if populated and populated[0] != consts.PHASE_IDS[0]
                 else "")
    episode_errors = _episode_errors(populated, phase_tickets, eps)

    ok = (not structural and not invented and not duplicated and not missing
          and not unnarrated and not bad_start and not episode_errors)
    if ok:
        message = "grounded"
    else:
        parts = list(structural)
        parts += [f"{k}: invented {v}" for k, v in invented.items()]
        if duplicated:
            parts.append(f"duplicated: {sorted(duplicated)}")
        if missing:
            parts.append(f"missing: {sorted(missing)}")
        if unnarrated:
            parts.append(f"tickets without a narrative: {unnarrated}")
        if bad_start:
            parts.append(f"story does not start at '{consts.PHASE_IDS[0]}' "
                         f"(first populated phase is '{bad_start}')")
        parts += episode_errors
        message = "; ".join(parts)
    return ValidationResult(ok, invented, structural, message,
                            missing=sorted(missing), duplicated=sorted(duplicated),
                            unnarrated=unnarrated, bad_start=bad_start,
                            episode_errors=episode_errors)


def _episode_errors(populated: list[str], phase_tickets: dict[str, list[str]],
                    eps: list | None) -> list[str]:
    """Every way the phases fail to reproduce the computed episodes exactly.

    Two independent things are checked: the *shape* (exactly which phases carry
    tickets, against ``episodes.phase_slots``) and the *contents* (each populated
    phase, read in arc order, holds exactly the corresponding episode's tickets).
    Contents are compared as sets — order within a phase is normalised by the
    facts layer and is not the model's to get wrong.
    """
    if not eps:
        return []
    errors: list[str] = []
    shape = episodes_mod.slots_are_valid(populated, len(eps))
    if shape:
        errors.append(shape)

    for i, (pid, episode) in enumerate(zip(populated, eps), start=1):
        got = set(phase_tickets.get(pid, []))
        want = set(episode.ticket_numbers)
        if got != want:
            errors.append(
                f"phase '{pid}' holds {sorted(got)} but episode {i} is "
                f"{sorted(want)} — episodes are computed from the ticket "
                f"timestamps and must be kept whole")
    return errors
