"""Block C — grounding validation tests."""

from src import consts
from src.engine.schema import empty_summary
from src.engine.validate import validate_summary


def _valid_summary(tickets):
    s = empty_summary()
    s[consts.PHASE_IDS[0]] = {"ticket_numbers": list(tickets), "narrative": "y"}
    return s


def test_grounded_summary_passes():
    res = validate_summary(_valid_summary(["001-1/24", "001-2/24"]),
                           {"001-1/24", "001-2/24"})
    assert res.ok
    assert res.invented == {}


def test_invented_ticket_is_flagged():
    res = validate_summary(_valid_summary(["001-1/24", "999-9/99"]),
                           {"001-1/24"})
    assert not res.ok
    assert "999-9/99" in res.invented_tickets()


def test_omitted_ticket_is_flagged():
    res = validate_summary(_valid_summary(["001-1/24"]),
                           {"001-1/24", "001-2/24"})
    assert not res.ok
    assert "001-2/24" in res.missing


def test_duplicated_ticket_is_flagged():
    s = empty_summary()
    s[consts.PHASE_IDS[0]] = {"ticket_numbers": ["A"], "narrative": "y"}
    s[consts.PHASE_IDS[1]] = {"ticket_numbers": ["A"], "narrative": "y"}
    res = validate_summary(s, {"A"})
    assert not res.ok
    assert "A" in res.duplicated


def test_missing_phase_is_structural_error():
    broken = empty_summary()
    del broken[consts.PHASE_IDS[2]]
    res = validate_summary(broken, set())
    assert not res.ok
    assert any(consts.PHASE_IDS[2] in e for e in res.structural_errors)


def test_non_dict_input():
    res = validate_summary("not json", set())
    assert not res.ok


def test_story_must_start_at_initial_issue():
    s = empty_summary()
    s[consts.PHASE_IDS[1]] = {"ticket_numbers": ["001-1/24"], "narrative": "y"}
    res = validate_summary(s, {"001-1/24"})
    assert not res.ok
    assert res.bad_start == consts.PHASE_IDS[1]
    assert "does not start at" in res.message


def test_a_gap_between_populated_phases_is_allowed():
    s = empty_summary()
    s[consts.PHASE_IDS[0]] = {"ticket_numbers": ["001-1/24"], "narrative": "y"}
    s[consts.PHASE_IDS[-1]] = {"ticket_numbers": ["001-2/24"], "narrative": "y"}
    res = validate_summary(s, {"001-1/24", "001-2/24"})
    assert res.ok
    assert res.bad_start == ""


def test_empty_story_has_no_start_violation():
    assert validate_summary(empty_summary(), set()).ok


def _episodes(*groups):
    import pandas as pd
    from src.engine.episodes import Episode
    base = pd.Timestamp("2024-01-01 09:00")
    return [Episode(i + 1, tuple(g), base + pd.Timedelta(days=i),
                    base + pd.Timedelta(days=i, hours=1))
            for i, g in enumerate(groups)]


def _story(**phases):
    s = empty_summary()
    for pid, tickets in phases.items():
        s[pid] = {"ticket_numbers": list(tickets), "narrative": "y"}
    return s


def test_episodes_placed_correctly_pass():
    eps = _episodes(["a"], ["b", "c"])
    res = validate_summary(
        _story(initial_issue=["a"], recent_events=["b", "c"]), {"a", "b", "c"}, eps)
    assert res.ok, res.message


def test_a_middle_episode_must_take_the_mapped_phase():
    eps = _episodes(["a"], ["b"], ["c"])
    for middle, ok_expected in (("follow_ups", True), ("developments", False),
                                ("later_incidents", False)):
        res = validate_summary(
            _story(initial_issue=["a"], **{middle: ["b"]}, recent_events=["c"]),
            {"a", "b", "c"}, eps)
        assert res.ok is ok_expected, f"{middle}: {res.message}"
        if not ok_expected:
            assert res.episode_errors and "follow_ups" in res.message


def test_a_split_episode_is_caught():
    eps = _episodes(["a"], ["b", "c"])
    res = validate_summary(
        _story(initial_issue=["a"], follow_ups=["b"], recent_events=["c"]),
        {"a", "b", "c"}, eps)
    assert not res.ok
    assert res.episode_errors
    assert "must occupy exactly 2" in res.message


def test_merged_episodes_are_caught():
    eps = _episodes(["a"], ["b"])
    res = validate_summary(_story(initial_issue=["a", "b"]), {"a", "b"}, eps)
    assert not res.ok
    assert "must occupy exactly 2" in res.message


def test_right_shape_but_wrong_contents_is_caught():
    eps = _episodes(["a", "b"], ["c"])
    res = validate_summary(
        _story(initial_issue=["a"], recent_events=["b", "c"]), {"a", "b", "c"}, eps)
    assert not res.ok
    assert "kept whole" in res.message


def test_an_invented_ticket_alone_does_not_condemn_the_placement():
    eps = _episodes(["a"], ["b"])
    res = validate_summary(
        _story(initial_issue=["a", "999-9/99"], recent_events=["b"]), {"a", "b"}, eps)
    assert not res.ok                 
    assert res.episode_errors == []   


def test_without_episodes_the_check_is_skipped():
    res = validate_summary(_story(initial_issue=["a"], recent_events=["b"]), {"a", "b"})
    assert res.ok
    assert res.episode_errors == []
