"""Deterministic grounded fallback — the honest, LLM-free view (Block C)."""

import pandas as pd

from src import consts, taxonomy
from src.engine.fallback import deterministic_summary


def _frame(hours: list[float], cause: str = "URS_KIP_Reset_WLAN_Settings",
           outcome: str | None = None) -> pd.DataFrame:
    """Tickets accepted at the given hour-offsets.

    Hours, not days: episode boundaries are a fixed
    ``consts.EPISODE_GAP_HOURS`` threshold, so the gaps between these offsets
    are the whole input to the grouping.
    """
    base = pd.Timestamp("2024-01-01 09:00")
    return pd.DataFrame([{
        consts.OUT_ORDER: f"T{i}",
        consts.OUT_CUSTOMER: "A", consts.OUT_PRODUCT: "Hardware",
        consts.OUT_CATEGORY: "HDW",
        consts.OUT_ACCEPT: base + pd.Timedelta(hours=h),
        consts.OUT_COMPLETE: base + pd.Timedelta(hours=h + 1),
        consts.OUT_OUTCOME: outcome or consts.OUTCOME_OK,
        consts.OUT_CAUSE: cause,
    } for i, h in enumerate(hours)])


_SPLIT = consts.EPISODE_GAP_HOURS + 1
_SAME = consts.EPISODE_GAP_HOURS - 1


def _chapters(summary) -> list:
    return [ph for ph in summary.phases.values() if ph.ticket_numbers]


def _one_product(clean_df):
    cust = clean_df[consts.OUT_CUSTOMER].iloc[0]
    df = clean_df[clean_df[consts.OUT_CUSTOMER] == cust]
    product = df[consts.OUT_PRODUCT].iloc[0]
    return df[df[consts.OUT_PRODUCT] == product], product


def test_deterministic_summary_is_grounded(clean_df):
    subset, product = _one_product(clean_df)
    s = deterministic_summary(product, subset)
    assert s.provider == "deterministic"
    valid = [str(x) for x in subset[consts.OUT_ORDER]]
    cited = [n for ph in s.phases.values() for n in ph.ticket_numbers]
    assert set(cited) <= set(valid)           
    assert sorted(cited) == sorted(valid)     


def test_deterministic_summary_empty_product(clean_df):
    s = deterministic_summary("GIGA", None)
    assert s.provider == "deterministic"
    assert all(ph.ticket_numbers == [] for ph in s.phases.values())
    assert all(ph.narrative == "No activity." for ph in s.phases.values())


def test_deterministic_narrative_has_no_fabrication(clean_df):

    subset, product = _one_product(clean_df)
    s = deterministic_summary(product, subset)
    text = " ".join(ph.narrative for ph in s.phases.values())
    assert "ticket" in text.lower()




def test_tickets_in_one_burst_stay_one_chapter():
    s = deterministic_summary("Hardware", _frame([0, 2, 4, 6, 8]))
    assert len(_chapters(s)) == 1
    assert len(_chapters(s)[0].ticket_numbers) == 5


def test_a_quiet_spell_starts_a_new_chapter():
    s = deterministic_summary("Hardware", _frame([0, 2, 4, 4 + _SPLIT, 6 + _SPLIT]))
    chapters = _chapters(s)
    assert len(chapters) == 2
    assert [len(c.ticket_numbers) for c in chapters] == [3, 2]
    assert s.phases[consts.PHASE_IDS[0]].ticket_numbers
    assert not s.phases[consts.PHASE_IDS[2]].ticket_numbers


def test_tickets_inside_the_threshold_are_never_split():
    assert len(_chapters(deterministic_summary("Hardware", _frame([0, 0, 0])))) == 1
    assert len(_chapters(deterministic_summary("Hardware", _frame([0, _SAME])))) == 1


def test_episodes_never_exceed_the_five_phases():
    s = deterministic_summary("Hardware", _frame([h * _SPLIT for h in range(7)]))
    assert len(_chapters(s)) == len(consts.PHASES)
    cited = [n for ph in s.phases.values() for n in ph.ticket_numbers]
    assert len(cited) == 7                       


def test_episode_count_decides_the_chapter_count():
    for n in range(1, len(consts.PHASES) + 1):
        s = deterministic_summary("Hardware", _frame([i * _SPLIT for i in range(n)]))
        chapters = [p for p in consts.PHASE_IDS if s.phases[p].ticket_numbers]
        assert len(chapters) == n
        assert chapters[0] == consts.PHASE_IDS[0]
        if n > 1:
            assert chapters[-1] == consts.PHASE_IDS[-1]


def test_raw_cause_codes_never_reach_the_reader():
    s = deterministic_summary("Hardware", _frame([0, 1]))
    text = " ".join(ph.narrative for ph in s.phases.values())
    assert "URS_KIP" not in text
    assert "WLAN / Wi-Fi" in text                


def test_unmapped_codes_are_reported_as_unclassified():
    s = deterministic_summary("Hardware", _frame([0], cause="k03"))
    text = _chapters(s)[0].narrative
    assert "k03" not in text
    assert taxonomy.UNCLASSIFIED in text


def test_outcome_wording_is_readable():
    one = _chapters(deterministic_summary("Hardware", _frame([0])))[0].narrative
    assert one.startswith("1 ticket, resolved.")     

    unknown = _chapters(deterministic_summary(
        "Hardware", _frame([0], outcome=consts.OUTCOME_UNKNOWN)))[0].narrative
    assert "no outcome recorded" in unknown          




def test_provenance_never_reads_as_a_template_variable(clean_df):
    subset, product = _one_product(clean_df)
    line = deterministic_summary(product, subset, note="Some note.").provenance()
    assert "Narrated by deterministic" not in line
    assert line.startswith("Built directly from the tickets")
    assert "Some note." in line




def test_last_episode_closes_the_arc():
    s = deterministic_summary("Hardware", _frame([0, 2, 4, 4 + _SPLIT, 6 + _SPLIT]))
    first, last = consts.PHASE_IDS[0], consts.PHASE_IDS[-1]
    assert len(s.phases[first].ticket_numbers) == 3
    assert len(s.phases[last].ticket_numbers) == 2
    assert not any(s.phases[p].ticket_numbers for p in consts.PHASE_IDS[1:-1])


def test_a_single_episode_stays_at_the_opening():
    s = deterministic_summary("Hardware", _frame([0, 2, 4]))
    assert s.phases[consts.PHASE_IDS[0]].ticket_numbers
    assert not s.phases[consts.PHASE_IDS[-1]].ticket_numbers


def test_an_undated_ticket_says_so_instead_of_joining_the_previous_group():
    frame = _frame([0, 2])
    frame.loc[1, consts.OUT_ACCEPT] = pd.NaT
    s = deterministic_summary("Hardware", frame)
    chapters = _chapters(s)
    assert len(chapters) == 2
    assert chapters[-1].ticket_numbers == ["T1"]
    assert "No acceptance date is recorded" in chapters[-1].narrative
