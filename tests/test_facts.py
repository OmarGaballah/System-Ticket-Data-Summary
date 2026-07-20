"""Tier 2 — deterministic facts enforcement tests (closed set / coverage /
timeframes / ordering). Built on a tiny controlled frame so timestamps are known."""

import pandas as pd

import pytest

from src import consts
from src.engine import facts, prompts
from src.engine.structure import StructureError

P = consts.PHASE_IDS


def _df(rows):
    """rows: list of (order, accept_iso, complete_iso)."""
    return pd.DataFrame([
        {consts.OUT_ORDER: o, consts.OUT_ACCEPT: a, consts.OUT_COMPLETE: c}
        for o, a, c in rows
    ])


def _draft(**assign):
    d = {"language": "English"}
    for pid in P:
        d[pid] = {"ticket_numbers": list(assign.get(pid, [])), "narrative": "x"}
    return d


def _cited(summary):
    return [t for pid in P for t in summary[pid]["ticket_numbers"]]


_TWO = _df([
    ("T1", "2024-01-01 09:00", "2024-01-01 10:00"),
    ("T2", "2024-02-01 09:00", "2024-02-01 10:00"),
])


def test_closed_set_drops_invalid_citation():
    summary, report = facts.enforce(_draft(**{P[0]: ["T1", "BOGUS"], P[1]: ["T2"]}), _TWO)
    assert report.dropped[P[0]] == ["BOGUS"]
    assert sorted(_cited(summary)) == ["T1", "T2"]        


def test_coverage_places_omitted_ticket():
    summary, report = facts.enforce(_draft(**{P[0]: ["T1"]}), _TWO)  
    assert "T2" in report.assigned
    cited = _cited(summary)
    assert sorted(cited) == ["T1", "T2"]                   
    assert len(cited) == len(set(cited))                   


def test_duplicate_citation_is_resolved_to_one_phase():
    summary, report = facts.enforce(_draft(**{P[0]: ["T1", "T2"], P[1]: ["T1"]}), _TWO)
    assert report.deduped == ["T1"]
    cited = _cited(summary)
    assert sorted(cited) == ["T1", "T2"]
    assert len(cited) == len(set(cited))


def test_timeframe_is_computed_from_timestamps():
    summary, _ = facts.enforce(_draft(**{P[0]: ["T1", "T2"]}), _TWO)
    assert summary[P[0]]["timeframe"] == "2024-01-01 – 2024-02-01"


def test_total_omission_spreads_across_the_arc():
    df = _df([
        ("A", "2024-01-01 09:00", "2024-01-01 10:00"),
        ("B", "2024-02-01 09:00", "2024-02-01 10:00"),
        ("C", "2024-03-01 09:00", "2024-03-01 10:00"),
    ])
    summary, report = facts.enforce(_draft(), df)          
    assert sorted(report.assigned) == ["A", "B", "C"]
    cited = _cited(summary)
    assert sorted(cited) == ["A", "B", "C"]
    assert summary[P[0]]["ticket_numbers"] == ["A"]
    assert summary[P[1]]["ticket_numbers"] == ["B"]
    assert summary[P[2]]["ticket_numbers"] == ["C"]


def test_non_monotonic_ordering_is_flagged():
    
    df = _df([
        ("EARLY", "2024-01-01 09:00", "2024-01-01 10:00"),
        ("LATE", "2024-03-01 09:00", "2024-03-01 10:00"),
    ])
    _, report = facts.enforce(_draft(**{P[0]: ["LATE"], P[1]: ["EARLY"]}), df)
    assert report.order_violations                          


def test_clean_partition_reports_nothing():
    summary, report = facts.enforce(_draft(**{P[0]: ["T1"], P[1]: ["T2"]}), _TWO)
    assert report.clean()
    assert report.note() == ""
    assert summary[P[0]]["ticket_numbers"] == ["T1"]
    assert summary[P[1]]["ticket_numbers"] == ["T2"]
    assert summary[P[0]]["timeframe"] and summary[P[1]]["timeframe"]


def test_reshuffling_tickets_without_narratives_is_caught():
    """The exact defect this check exists for.

    An earlier version re-anchored ticket numbers across phases after
    generation while the narratives stayed on their original keys. The result
    read plausibly in both halves — a chapter dated 2024-11-07 narrating an
    event from 2024-11-13, and a chapter holding that later ticket under the
    words "No activity" — so nothing else caught it.
    """
    desynced = {
        P[0]: {"ticket_numbers": ["A"], "narrative": "The router was replaced."},
        P[-1]: {"ticket_numbers": ["B"], "narrative": consts.NO_ACTIVITY},
    }
    for pid in P[1:-1]:
        desynced[pid] = {"ticket_numbers": [], "narrative": consts.NO_ACTIVITY}

    with pytest.raises(StructureError, match="No activity|narrat"):
        facts.assert_consistent(desynced)


def test_tickets_without_a_narrative_are_caught():
    summary = {pid: {"ticket_numbers": [], "narrative": consts.NO_ACTIVITY}
               for pid in P}
    summary[P[0]] = {"ticket_numbers": ["A"], "narrative": "  "}
    with pytest.raises(StructureError, match="no narrative"):
        facts.assert_consistent(summary)


def test_prose_without_tickets_is_caught():
    summary = {pid: {"ticket_numbers": [], "narrative": consts.NO_ACTIVITY}
               for pid in P}
    summary[P[2]] = {"ticket_numbers": [], "narrative": "Things improved."}
    with pytest.raises(StructureError, match="no tickets"):
        facts.assert_consistent(summary)


def test_enforce_normalises_empty_phases_and_passes_its_own_check():
    draft = _draft(**{P[0]: ["T1", "T2"]})
    draft[P[3]]["narrative"] = "Some unsupported prose."
    summary, _ = facts.enforce(draft, _TWO)
    assert summary[P[3]]["narrative"] == consts.NO_ACTIVITY
    facts.assert_consistent(summary)    


def test_unnarrated_phase_is_flagged_for_self_correction():
    
    from src.engine.validate import validate_summary
    draft = _draft(**{P[0]: ["T1"], P[1]: ["T2"]})
    draft[P[1]]["narrative"] = ""
    result = validate_summary(draft, {"T1", "T2"})
    assert not result.ok
    assert result.unnarrated == [P[1]]
    assert P[1] in prompts.build_revision(result)
