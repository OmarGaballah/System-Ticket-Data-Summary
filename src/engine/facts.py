"""Tier 2 — facts (guarantee: absolute, because we made it structural).

The model groups tickets into phases and writes the prose; *code* guarantees the
facts. Given the model's draft and the real customer/product slice, ``enforce``
returns a corrected summary that always satisfies four invariants, whatever the
model did:

1. Closed set — every cited ticket exists in the slice; invalid citations are
   dropped and flagged.
2. Coverage — every ticket in the slice is assigned to exactly one phase. The
   union of the phases equals the slice, with no duplicates. Omitted tickets are
   placed by date; duplicates are resolved to their first phase.
3. Timeframes — never model-generated. Each phase's timeframe is computed from
   its assigned tickets' real acceptance/completion timestamps.
4. Ordering — a phase's tickets should not predate the previous phase's. This is
   a monotonicity check on the model's grouping judgment; violations are flagged
   (not silently reshuffled — the semantic grouping is the point of the LLM).

Pure module: pandas + consts only, no Streamlit, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src import consts
from src.engine.structure import StructureError


@dataclass
class FactsReport:
    """What the deterministic enforcement had to correct (empty = clean)."""
    dropped: dict[str, list[str]] = field(default_factory=dict)   
    deduped: list[str] = field(default_factory=list)              
    assigned: list[str] = field(default_factory=list)             
    order_violations: list[str] = field(default_factory=list)     

    def clean(self) -> bool:
        return not (self.dropped or self.deduped or self.assigned or self.order_violations)

    def note(self) -> str:
        parts: list[str] = []
        n_drop = sum(len(v) for v in self.dropped.values())
        if n_drop:
            parts.append(f"{n_drop} invented citation{_s(n_drop)} removed")
        if self.assigned:
            parts.append(f"{len(self.assigned)} unassigned ticket{_s(len(self.assigned))} "
                         "placed by date")
        if self.deduped:
            parts.append(f"{len(self.deduped)} duplicate citation{_s(len(self.deduped))} "
                         "resolved")
        if self.order_violations:
            parts.append("phase ordering flagged as non-chronological")
        if not parts:
            return ""
        return "Deterministic grounding: " + ", ".join(parts) + "."


def enforce(draft: dict, slice_df: pd.DataFrame) -> tuple[dict, FactsReport]:
    """Return a facts-guaranteed summary (+ a report of what was corrected)."""
    times = _ticket_times(slice_df)          
    valid = set(times)
    report = FactsReport()

    
    assignment: dict[str, list[str]] = {pid: [] for pid in consts.PHASE_IDS}
    seen: set[str] = set()
    for pid in consts.PHASE_IDS:
        block = draft.get(pid) or {}
        for n in block.get("ticket_numbers", []) or []:
            t = str(n)
            if t not in valid:
                report.dropped.setdefault(pid, []).append(t)
            elif t in seen:
                report.deduped.append(t)
            else:
                seen.add(t)
                assignment[pid].append(t)

    
    omitted = [t for t in valid if t not in seen]
    if omitted:
        report.assigned = sorted(omitted, key=lambda t: _sort_key(times[t]))
        _place_omitted(report.assigned, assignment, times)

    
    for pid in consts.PHASE_IDS:
        assignment[pid].sort(key=lambda t: _sort_key(times[t]))

    
    report.order_violations = _order_violations(assignment, times)

    
    summary: dict = {"language": draft.get("language", consts.DEFAULT_LANGUAGE)}
    for pid in consts.PHASE_IDS:
        tickets = assignment[pid]
        narrative = str((draft.get(pid) or {}).get("narrative", "")).strip()
        if not tickets:
            narrative = consts.NO_ACTIVITY
        summary[pid] = {
            "ticket_numbers": tickets,
            "timeframe": _phase_timeframe(tickets, times),
            "narrative": narrative,
        }
    assert_consistent(summary)
    return summary, report


def assert_consistent(summary: dict) -> None:
    """Post-condition: every phase's tickets and prose describe the same thing.

    A phase is a pair — the tickets it covers and the words about them — and the
    two must only ever move together. This asserts they did:

    * tickets present  -> the narrative must say something;
    * no tickets       -> the narrative must be the no-activity string.

    It exists because of a real defect: an earlier version re-anchored ticket
    numbers across phases *after* generation while the narratives stayed on
    their original keys, producing a chapter dated 2024-11-07 whose prose
    described an event from 2024-11-13, and a chapter holding that later ticket
    under the words "No activity". Both halves were individually plausible, so
    nothing else caught it. This check would have, immediately — which is why it
    raises rather than repairs: a mismatch here means code moved one half of a
    phase without the other, and there is no honest way to guess the rest.
    """
    for phase in consts.PHASES:
        block = summary.get(phase.id) or {}
        tickets = block.get("ticket_numbers") or []
        narrative = str(block.get("narrative", "")).strip()
        if tickets and not narrative:
            raise StructureError(
                f"phase '{phase.id}' cites {len(tickets)} ticket(s) but has no "
                f"narrative — tickets and prose have been separated")
        if tickets and narrative == consts.NO_ACTIVITY:
            raise StructureError(
                f"phase '{phase.id}' cites {len(tickets)} ticket(s) yet narrates "
                f"'{consts.NO_ACTIVITY}' — its tickets belong to another phase's prose")
        if not tickets and narrative and narrative != consts.NO_ACTIVITY:
            raise StructureError(
                f"phase '{phase.id}' has no tickets but narrates "
                f"{narrative[:60]!r} — prose without tickets to support it")



def format_timeframe(accepts: list, completes: list) -> str:
    """A 'YYYY-MM-DD' or 'YYYY-MM-DD – YYYY-MM-DD' span from real timestamps."""
    starts = [a for a in accepts if a is not None and not pd.isna(a)]
    ends = [c for c in completes if c is not None and not pd.isna(c)]
    lo = min(starts) if starts else None
    hi = max(ends) if ends else (max(starts) if starts else None)
    if lo is None and hi is None:
        return ""
    fmt = "%Y-%m-%d"
    if lo is not None and hi is not None and lo.strftime(fmt) != hi.strftime(fmt):
        return f"{lo.strftime(fmt)} – {hi.strftime(fmt)}"
    return (lo or hi).strftime(fmt)



def _ticket_times(df: pd.DataFrame) -> dict[str, tuple]:
    out: dict[str, tuple] = {}
    for _, row in df.iterrows():
        a = pd.to_datetime(row[consts.OUT_ACCEPT], errors="coerce")
        c = pd.to_datetime(row[consts.OUT_COMPLETE], errors="coerce")
        out[str(row[consts.OUT_ORDER])] = (None if pd.isna(a) else a,
                                           None if pd.isna(c) else c)
    return out


def _sort_key(tc: tuple):
    """Sort by acceptance time; undated tickets sort last."""
    a = tc[0]
    return (a is None, a if a is not None else pd.Timestamp.max)


def _phase_timeframe(tickets: list[str], times: dict[str, tuple]) -> str:
    return format_timeframe([times[t][0] for t in tickets],
                            [times[t][1] for t in tickets])


def _place_omitted(omitted: list[str], assignment: dict[str, list[str]],
                   times: dict[str, tuple]) -> None:
    """Assign each omitted ticket to a phase, in place.

    If the model assigned nothing at all, spread the tickets across the arc by a
    front-loaded chronological split. Otherwise slot each omitted ticket into the
    latest phase that already started at or before it (bracket by date), which
    keeps the partition chronological.
    """
    if not any(assignment.values()):
        for pid, bucket in zip(consts.PHASE_IDS,
                               _split(omitted, len(consts.PHASE_IDS))):
            assignment[pid].extend(bucket)
        return

    starts = [(pid, _phase_start(assignment[pid], times))
              for pid in consts.PHASE_IDS if assignment[pid]]
    for t in omitted:
        a = times[t][0]
        target = starts[0][0]                       
        if a is not None:
            for pid, start in starts:
                if start is not None and start <= a:
                    target = pid                    
        assignment[target].append(t)


def _phase_start(tickets: list[str], times: dict[str, tuple]):
    accepts = [times[t][0] for t in tickets if times[t][0] is not None]
    return min(accepts) if accepts else None


def _order_violations(assignment: dict[str, list[str]],
                      times: dict[str, tuple]) -> list[str]:
    violations: list[str] = []
    prev = None
    for pid in consts.PHASE_IDS:
        start = _phase_start(assignment[pid], times)
        if start is None:
            continue
        if prev is not None and start < prev:
            violations.append(pid)
        prev = max(prev, start) if prev is not None else start
    return violations


def _split(items: list, n: int) -> list[list]:
    """Front-loaded chronological split (matches the deterministic fallback)."""
    k = len(items)
    base, extra = divmod(k, n)
    out, i = [], 0
    for b in range(n):
        size = base + (1 if b < extra else 0)
        out.append(items[i:i + size])
        i += size
    return out


def _s(n: int) -> str:
    return "" if n == 1 else "s"
