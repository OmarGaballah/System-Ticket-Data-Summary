"""Tier 1 — structural validation tests (schema parse + language + retry/fail-loud)."""

import pytest

from src import consts
from src.engine.providers.base import ContentError, TransportError
from src.engine.schema import empty_summary
from src.engine.structure import (StructureError, complete_structured,
                                  validate_structure)


def _valid(language: str = "English") -> dict:
    return empty_summary(language)


def test_valid_summary_passes_and_is_normalized():
    data = validate_structure(_valid(), "English")
    assert data["language"] == "English"
    assert set(data) == {"language", *consts.PHASE_IDS}


def test_language_match_is_case_insensitive():
    assert validate_structure(_valid("english"), "English")["language"] == "english"


def test_language_mismatch_is_rejected():
    with pytest.raises(StructureError, match="language"):
        validate_structure(_valid("German"), "English")


def test_missing_phase_is_rejected():
    broken = _valid()
    del broken[consts.PHASE_IDS[2]]
    with pytest.raises(StructureError, match=consts.PHASE_IDS[2]):
        validate_structure(broken, "English")


def test_extra_phase_is_rejected():
    extra = _valid()
    extra["sixth_phase"] = {"timeframe": "", "ticket_numbers": [], "narrative": "x"}
    with pytest.raises(StructureError):
        validate_structure(extra, "English")


def test_wrong_field_type_is_rejected():
    bad = _valid()
    bad[consts.PHASE_IDS[0]]["ticket_numbers"] = "not-a-list"
    with pytest.raises(StructureError):
        validate_structure(bad, "English")


def test_integer_ticket_numbers_are_coerced():
    ok = _valid()
    ok[consts.PHASE_IDS[0]]["ticket_numbers"] = [12345, 678]
    data = validate_structure(ok, "English")
    assert data[consts.PHASE_IDS[0]]["ticket_numbers"] == ["12345", "678"]


def test_non_dict_is_rejected():
    with pytest.raises(StructureError):
        validate_structure("not json", "English")

class _Scripted:
    """Returns queued responses in order; a response may be a dict or an Exception."""
    name, model = "scripted", "m"

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    def complete_json(self, system, user, schema=None):
        self.calls += 1
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_retries_once_then_succeeds():
    broken = empty_summary("English")
    del broken[consts.PHASE_IDS[1]]
    p = _Scripted(broken, empty_summary("English"))
    data = complete_structured(p, "sys", "user", "English")
    assert p.calls == 2
    assert data["language"] == "English"


def test_parse_failure_triggers_retry():
    p = _Scripted(ContentError("no json"), empty_summary("English"))
    data = complete_structured(p, "sys", "user", "English")
    assert p.calls == 2
    assert data["language"] == "English"


def test_fails_loudly_after_retry():
    bad = empty_summary("English")
    del bad[consts.PHASE_IDS[0]]
    p = _Scripted(bad, bad)
    with pytest.raises(StructureError):
        complete_structured(p, "sys", "user", "English")
    assert p.calls == 2


def test_transport_error_propagates():
    p = _Scripted(TransportError("down"))
    with pytest.raises(TransportError):
        complete_structured(p, "sys", "user", "English")
