"""Episodes — the deterministic chapter boundaries (Block C).

The rule under test is deliberately mechanical: a measured silence is a chapter
break, and the number of episodes fixes the number of populated phases. These
tests pin both halves, because the whole claim of an empty phase ("time passed
with nothing to report") rests on the boundaries being real.
"""

import pandas as pd

from src import consts
from src.engine import episodes

_SPLIT = consts.EPISODE_GAP_HOURS + 1
_SAME = consts.EPISODE_GAP_HOURS - 1


def _frame(hours: list[float | None]) -> pd.DataFrame:
    base = pd.Timestamp("2024-01-01 09:00")
    return pd.DataFrame([{
        consts.OUT_ORDER: f"T{i}",
        consts.OUT_ACCEPT: pd.NaT if h is None else base + pd.Timedelta(hours=h),
        consts.OUT_COMPLETE: base + pd.Timedelta(hours=(h or 0) + 1),
    } for i, h in enumerate(hours)])


def _sets(eps) -> list[set]:
    return [set(e.ticket_numbers) for e in eps]

def test_gap_below_the_threshold_keeps_one_episode():
    assert len(episodes.compute(_frame([0, _SAME]))) == 1


def test_gap_at_or_above_the_threshold_splits():
    assert len(episodes.compute(_frame([0, consts.EPISODE_GAP_HOURS]))) == 2
    assert len(episodes.compute(_frame([0, _SPLIT]))) == 2


def test_the_sample_bands_are_far_from_the_threshold(clean_df):
    gaps = []
    for _, sub in clean_df.groupby([consts.OUT_CUSTOMER, consts.OUT_PRODUCT]):
        t = pd.to_datetime(sub[consts.OUT_ACCEPT]).sort_values().tolist()
        gaps += [(b - a).total_seconds() / 3600 for a, b in zip(t, t[1:])]
    assert not [g for g in gaps if 2 < g < 19]
    assert 2 < consts.EPISODE_GAP_HOURS < 19


def test_episodes_are_chronological_and_cover_every_ticket():
    eps = episodes.compute(_frame([0, 1, _SPLIT * 2, _SPLIT * 4]))
    assert [t for e in eps for t in e.ticket_numbers] == ["T0", "T1", "T2", "T3"]
    assert all(a.end <= b.start for a, b in zip(eps, eps[1:]))


def test_more_than_five_episodes_merge_the_closest_pair_first():
    hours = [0, 100, 200, 300, 400, 405]
    eps = episodes.compute(_frame(hours))
    assert len(eps) == len(consts.PHASES)
    assert eps[0].ticket_numbers == ("T0",)      
    assert eps[-1].ticket_numbers == ("T4", "T5")
    assert sum(len(e.ticket_numbers) for e in eps) == 6


def test_an_undated_ticket_is_its_own_episode_ordered_last():
    eps = episodes.compute(_frame([0, None, _SAME]))
    assert _sets(eps) == [{"T0", "T2"}, {"T1"}]
    assert not eps[-1].dated
    assert eps[-1].label() == "no acceptance date recorded"


def test_empty_slice_has_no_episodes():
    assert episodes.compute(None) == []
    assert episodes.compute(_frame([])) == []

def test_phase_slots_follow_the_mapping_table():
    ids = consts.PHASE_IDS
    assert episodes.phase_slots(1) == [ids[0]]
    assert episodes.phase_slots(2) == [ids[0], ids[-1]]
    assert episodes.phase_slots(3) == [ids[0], "follow_ups", ids[-1]]
    assert episodes.phase_slots(4) == [ids[0], "follow_ups", "developments", ids[-1]]
    assert episodes.phase_slots(5) == ids
    assert episodes.phase_slots(9) == ids     


def test_only_the_mapped_placement_is_accepted():
    for n in range(1, 6):
        assert episodes.slots_are_valid(episodes.phase_slots(n), n) == ""

    ids = consts.PHASE_IDS
    
    for middle in ("developments", "later_incidents"):
        err = episodes.slots_are_valid([ids[0], middle, ids[-1]], 3)
        assert middle in err and "follow_ups" in err


def test_middle_phases_out_of_arc_order_are_rejected():
    bad = [consts.PHASE_IDS[0], "later_incidents", "follow_ups", consts.PHASE_IDS[-1]]
    assert "out of place" in episodes.slots_are_valid(bad, 4)


def test_wrong_number_of_phases_is_rejected():
    assert "must occupy exactly 2" in episodes.slots_are_valid([consts.PHASE_IDS[0]], 2)
    assert episodes.slots_are_valid(consts.PHASE_IDS[:3], 2)


def test_a_story_must_open_at_the_first_phase_and_close_at_the_last():
    ids = consts.PHASE_IDS
    assert episodes.slots_are_valid(["follow_ups", ids[-1]], 2)
    assert episodes.slots_are_valid([ids[0], "developments"], 2)
    assert episodes.slots_are_valid([ids[0]], 1) == ""


def test_later_incidents_is_reachable_only_by_a_five_episode_story():
    reached = [n for n in range(1, 6) if "later_incidents" in episodes.phase_slots(n)]
    assert reached == [5]


def test_the_payload_states_the_phase_for_every_episode():
    eps = episodes.compute(_frame([0, 40, 80]))
    text = episodes.describe(eps) + "\n" + episodes.instruction(eps)
    for e, pid in episodes.assignment(eps):
        assert f'episode {e.index} -> "{pid}"' in text
    assert "you choose" not in text.lower()
    assert "character" not in text.lower()
