"""Deterministic, LLM-free grounded summary — the honest fallback.

When no LLM can serve (no key configured, or every provider failed at call
time), we do NOT fabricate narrative prose. Instead we render the same
five-phase structure directly from the real tickets: sort chronologically, split
into up to five temporal buckets (Initial Issue -> Recent Events) and describe
each phase with only real fields — timeframe, ticket numbers, and factual
outcome/cause counts. Zero invented content.

This is the universal safety net for when no LLM can serve. Pure module — no
Streamlit, no network.
"""

from __future__ import annotations

import pandas as pd

from src import consts, taxonomy
from src.engine import episodes
from src.engine.facts import assert_consistent, format_timeframe
from src.structs import DETERMINISTIC_PROVIDER, PhaseSummary, ProductSummary

PROVIDER_LABEL = DETERMINISTIC_PROVIDER
MODEL_LABEL = "grounded"



def deterministic_summary(product: str, subset: pd.DataFrame | None,
                          note: str = "") -> ProductSummary:
    """A five-phase summary built purely from the data — no LLM, no fabrication."""
    return ProductSummary(
        product=product,
        phases=_build_phases(subset),
        provider=PROVIDER_LABEL,
        model=MODEL_LABEL,
        note=note,
    )


def _build_phases(subset: pd.DataFrame | None) -> dict[str, PhaseSummary]:
    phases = {
        p.id: PhaseSummary(timeframe="", ticket_numbers=[],
                           narrative=consts.NO_ACTIVITY)
        for p in consts.PHASES
    }
    if subset is None or len(subset) == 0:
        return phases

    eps = episodes.compute(subset)
    by_ticket = subset.set_index(subset[consts.OUT_ORDER].astype(str))
    for pid, episode in zip(episodes.phase_slots(len(eps)), eps):
        rows = by_ticket.loc[list(episode.ticket_numbers)]
        phases[pid] = PhaseSummary(
            timeframe=_timeframe(rows),
            ticket_numbers=list(episode.ticket_numbers),
            narrative=_narrative(rows),
        )
    assert_consistent({pid: {"ticket_numbers": ph.ticket_numbers,
                             "narrative": ph.narrative}
                       for pid, ph in phases.items()})
    return phases


def _timeframe(rows: pd.DataFrame) -> str:
    starts = pd.to_datetime(rows[consts.OUT_ACCEPT], errors="coerce").dropna().tolist()
    ends = pd.to_datetime(rows[consts.OUT_COMPLETE], errors="coerce").dropna().tolist()
    return format_timeframe(starts, ends)


def _narrative(rows: pd.DataFrame) -> str:
    """A factual sentence from real fields only, written for the business reader:
    outcomes in plain words and causes as themes rather than the internal codes
    (``URS_KIP_Reset_WLAN_Settings``) that mean nothing outside the ticketing
    system. The raw codes stay one click away in the source-tickets view."""
    k = len(rows)
    outcomes = rows[consts.OUT_OUTCOME].fillna(consts.OUTCOME_UNKNOWN)
    n_ok = int((outcomes == consts.OUTCOME_OK).sum())
    n_err = int((outcomes == consts.OUTCOME_ERROR).sum())
    n_unknown = k - n_ok - n_err

    tallies = []
    if n_ok:
        tallies.append(f"{n_ok} resolved")
    if n_err:
        tallies.append(f"{n_err} closed with an error")
    if n_unknown:
        tallies.append(f"{n_unknown} with no outcome recorded")

    sentence = f"{k} ticket{'s' if k != 1 else ''}"
    if len(tallies) == 1 and k == 1:
        sentence += f", {tallies[0].split(' ', 1)[1]}."       
    elif len(tallies) == 1:
        sentence += f", all {tallies[0].split(' ', 1)[1]}."   
    elif tallies:
        sentence += " — " + ", ".join(tallies) + "."
    else:
        sentence += "."

    causes = taxonomy.describe(rows[consts.OUT_CAUSE].dropna().tolist())
    if causes:
        sentence += f" Cause{'s' if ',' in causes else ''}: {causes}."

    n_undated = int(pd.to_datetime(rows[consts.OUT_ACCEPT], errors="coerce").isna().sum())
    if n_undated:
        sentence += (" No acceptance date is recorded"
                     + ("." if n_undated == len(rows)
                        else f" for {n_undated} of these tickets."))
    return sentence
