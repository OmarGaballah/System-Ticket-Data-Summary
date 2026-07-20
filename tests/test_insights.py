"""Block D — deterministic insight tests (real sample + generality checks)."""

import pandas as pd

from src import consts
from src.analysis import insights


def _tiny(**over) -> pd.DataFrame:
    """A minimal cleaned-schema frame: two one-off tickets, no escalation."""
    base = dict(
        outcome=consts.OUTCOME_OK, reference_result=None, resolver=None, team="T1",
    )
    rows = [
        {consts.OUT_ORDER: "1", consts.OUT_CUSTOMER: "A", consts.OUT_PRODUCT: "Voice",
         consts.OUT_ACCEPT: pd.Timestamp("2024-01-01 10:00"),
         consts.OUT_COMPLETE: pd.Timestamp("2024-01-01 10:30"),
         consts.OUT_CAUSE: "invoice_query", consts.OUT_ACTION: "Explained", **base},
        {consts.OUT_ORDER: "2", consts.OUT_CUSTOMER: "B", consts.OUT_PRODUCT: "TV",
         consts.OUT_ACCEPT: pd.Timestamp("2024-01-02 10:00"),
         consts.OUT_COMPLETE: pd.Timestamp("2024-01-02 10:30"),
         consts.OUT_CAUSE: "signal_weak", consts.OUT_ACTION: "Adjusted", **base},
    ]
    df = pd.DataFrame(rows)
    for k, v in over.items():
        df[k] = v
    return df


# --- real sample -----------------------------------------------------------

def test_compute_all_returns_every_finding_with_takeaways(clean_df):
    out = insights.compute_all(clean_df)
    assert len(out) == 6
    assert out[-1].key == "episode_timeline"    # the timeline closes the report
    for ins in out:
        assert ins.takeaway.strip()
        assert isinstance(ins.data, pd.DataFrame)
        assert ins.key and ins.title and ins.question


def test_repeat_contacts_detects_the_ladder(clean_df):
    ins = insights.repeat_contacts(clean_df)
    assert ins.has_signal
    assert "contact" in ins.takeaway.lower()
    assert "→" in ins.takeaway            # the remediation ladder is rendered


def test_root_cause_pareto_groups_themes(clean_df):
    ins = insights.root_cause_pareto(clean_df)
    assert ins.has_signal
    # themes collapse EN/DE spellings, so the top bucket beats any raw cause code.
    assert ins.data["pct"].iloc[0] >= 0.15
    assert abs(ins.data["cum_pct"].iloc[-1] - 1.0) < 1e-9


def test_escalation_uses_actions_not_just_outcome(clean_df):
    # Outcome is ~all OK; the signal comes from replacement/technician actions.
    ins = insights.escalation_by_product(clean_df)
    assert ins.has_signal
    assert "escalation_rate" in ins.data.columns


# --- generality: no-signal cases must degrade, not crash --------------------

def test_repeat_contacts_no_signal(clean_df):
    ins = insights.repeat_contacts(_tiny())
    assert not ins.has_signal
    assert "first-and-only" in ins.takeaway


def test_escalation_no_signal_reports_data_gap():
    df = _tiny()
    df[consts.OUT_OUTCOME] = consts.OUTCOME_UNKNOWN
    ins = insights.escalation_by_product(df)
    assert not ins.has_signal
    assert "no outcome logged" in ins.takeaway.lower() or "no escalations" in ins.takeaway.lower()


def test_handoffs_single_team_no_signal():
    ins = insights.handoffs(_tiny())
    assert not ins.has_signal
    assert "single team" in ins.takeaway.lower()


# --- repeat contacts are measured in occasions, not tickets -----------------

def test_tickets_raised_together_are_one_contact_occasion():
    # Two tickets two hours apart is a customer reporting once, not twice.
    # Counting them as a repeat contact answers "did they have to come back?"
    # with "yes" about someone who never left.
    base = pd.Timestamp("2024-01-01 09:00")
    df = pd.DataFrame([{
        consts.OUT_ORDER: f"T{i}", consts.OUT_CUSTOMER: "A",
        consts.OUT_PRODUCT: "Hardware", consts.OUT_CATEGORY: "HDW",
        consts.OUT_ACCEPT: base + pd.Timedelta(hours=h),
        consts.OUT_COMPLETE: base + pd.Timedelta(hours=h + 1),
        consts.OUT_OUTCOME: consts.OUTCOME_OK, consts.OUT_CAUSE: "x",
        consts.OUT_ACTION: "did a thing", consts.OUT_REFERENCE: None,
        consts.OUT_RESOLVER: None, consts.OUT_TEAM: "T",
    } for i, h in enumerate([0, 2])])

    pairs = insights.contact_occasions(df)
    assert pairs.iloc[0]["tickets"] == 2
    assert pairs.iloc[0]["occasions"] == 1
    assert insights.headline_kpis(df)["repeat_rate"] == 0.0
    assert not insights.repeat_contacts(df).has_signal


def test_a_return_after_a_gap_is_a_repeat_contact():
    base = pd.Timestamp("2024-01-01 09:00")
    gap = consts.EPISODE_GAP_HOURS + 1
    df = pd.DataFrame([{
        consts.OUT_ORDER: f"T{i}", consts.OUT_CUSTOMER: "A",
        consts.OUT_PRODUCT: "Hardware", consts.OUT_CATEGORY: "HDW",
        consts.OUT_ACCEPT: base + pd.Timedelta(hours=h),
        consts.OUT_COMPLETE: base + pd.Timedelta(hours=h + 1),
        consts.OUT_OUTCOME: consts.OUTCOME_OK, consts.OUT_CAUSE: "x",
        consts.OUT_ACTION: "did a thing", consts.OUT_REFERENCE: None,
        consts.OUT_RESOLVER: None, consts.OUT_TEAM: "T",
    } for i, h in enumerate([0, gap])])

    assert insights.contact_occasions(df).iloc[0]["occasions"] == 2
    assert insights.headline_kpis(df)["repeat_rate"] == 0.5


def test_repeat_rate_denominator_is_occasions_not_tickets(clean_df):
    k = insights.headline_kpis(clean_df)
    assert k["contact_occasions"] < k["tickets"]        # tickets cluster
    assert k["repeat_rate"] == k["repeat_occasions"] / k["contact_occasions"]


def test_the_worst_offender_is_reported_in_occasions_and_tickets(clean_df):
    # Customer 123's Hardware: 5 tickets, but 4 times they came back.
    ins = insights.repeat_contacts(clean_df)
    top = ins.data.iloc[0]
    assert (top["occasions"], top["tickets"]) == (4, 5)
    assert "came back 4 times" in ins.takeaway
    assert "from 5 tickets" in ins.takeaway


# --- the contact timeline ---------------------------------------------------

def test_timeline_has_one_mark_per_episode(clean_df):
    ins = insights.episode_timeline(clean_df)
    assert ins.has_signal and ins.chart == "timeline"
    # One row per episode, matching what the repeat-contact metric counted.
    assert len(ins.data) == insights.headline_kpis(clean_df)["contact_occasions"]
    assert set(ins.data.columns) >= {"pair", "date", "tickets"}


def test_timeline_shows_the_clustering_that_makes_the_story(clean_df):
    # The headline arc: three occasions bunched 5-7 Nov, a gap, then the 13th.
    ins = insights.episode_timeline(clean_df)
    top = ins.data[ins.data["pair"] == "123 · Hardware"].sort_values("date")
    days = [d.strftime("%m-%d") for d in top["date"]]
    assert days == ["11-05", "11-06", "11-07", "11-13"]
    assert list(top["tickets"]) == [1, 2, 1, 1]        # the 6th carries two
    assert ins.highlight == "123 · Hardware"           # the busiest arc is spotlit


def test_timeline_keeps_single_episode_rows(clean_df):
    # The contrast is the point: a one-mark row next to a four-mark row is what
    # makes the clustering legible.
    ins = insights.episode_timeline(clean_df)
    counts = ins.data.groupby("pair").size()
    assert (counts == 1).any() and (counts > 1).any()


def test_timeline_degrades_without_dates(clean_df):
    undated = clean_df.copy()
    undated[consts.OUT_ACCEPT] = pd.NaT
    ins = insights.episode_timeline(undated)
    assert not ins.has_signal
    assert "no timeline" in ins.takeaway.lower()
