"""Block C — summarizer / self-correction loop tests (offline, via fake providers).

The providers here are tiny inline fakes: they read the allowed ticket numbers
from the user prompt and the requested language from the system prompt, then emit
a schema-shaped response — exactly what a compliant model would return. That lets
the whole engine (Tier 1 structure -> Tier 2 grounding) run with no key or cost.
"""

import re

import pytest

from src import consts
from src.engine.providers.base import TransportError
from src.engine.structure import StructureError
from src.engine.summarizer import summarize_product

_INVENTED_TICKET = "999-9999999/99"


def _allowed_tickets(user: str) -> list[str]:
    m = re.search(r"ONLY these ticket numbers:\s*(.+)", user)
    return [t.strip() for t in m.group(1).split(",") if t.strip()] if m else []


def _requested_language(system: str) -> str:
    m = re.search(r"narrative in (\w+)", system)
    return m.group(1) if m else consts.DEFAULT_LANGUAGE


def _prompt_episodes(user: str) -> list[tuple[str, list[str]]]:
    """The episodes and their assigned phases, parsed back out of the prompt.

    A compliant model reads both its groupings *and* its placements from the
    prompt, so the fakes do too — that keeps them honest about the one thing the
    engine now checks. Placement is no longer a choice a model gets to make, and
    a fake that decided for itself would be testing the wrong contract.
    """
    return [(m.group(1), [t.strip() for t in m.group(2).split(",")])
            for m in re.finditer(r'^- episode \d+ \(.*?\) -> "([^"]+)": (.+)$',
                                 user, re.M)]


def _summary(system: str, user: str, *, invent: bool, cover: bool = True) -> dict:
    """A schema-shaped response placing each episode in its mapped phase.

    With ``cover=False`` it cites only the first ticket of the first episode,
    leaving the rest omitted — an episode-partition violation as well as an
    omission, which is what an incomplete answer really is.
    """
    valid = _allowed_tickets(user)
    out: dict = {"language": _requested_language(system)}
    out.update({
        p.id: {"ticket_numbers": [], "narrative": consts.NO_ACTIVITY}
        for p in consts.PHASES
    })
    eps = _prompt_episodes(user)
    if not eps:
        return out
    if not cover:
        eps = [(eps[0][0], eps[0][1][:1])]
    for pid, tickets in eps:
        out[pid] = {"ticket_numbers": list(tickets),
                    "narrative": f"[fake] {len(tickets)} ticket(s) summarized."}
    if invent:
        first = consts.PHASE_IDS[0]
        out[first]["ticket_numbers"] = out[first]["ticket_numbers"] + [_INVENTED_TICKET]
    return out


class GoodProvider:
    """Always returns a well-formed, grounded response."""
    name, model = "good", "m"

    def complete_json(self, system, user, schema=None):
        return _summary(system, user, invent=False)


class HallucinateOnceProvider:
    """Invents a ticket on its FIRST reply, then behaves — forces the loop to catch it."""
    name, model = "hallucinate", "m"

    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user, schema=None):
        self.calls += 1
        return _summary(system, user, invent=(self.calls == 1))


class OmitProvider:
    """Always cites only the first ticket — the rest are omissions to be covered."""
    name, model = "omit", "m"

    def complete_json(self, system, user, schema=None):
        return _summary(system, user, invent=False, cover=False)


class MalformedProvider:
    """Always returns structurally broken output (a phase is missing)."""
    name, model = "malformed", "m"

    def complete_json(self, system, user, schema=None):
        s = _summary(system, user, invent=False)
        del s[consts.PHASE_IDS[2]]
        return s


class _DownProvider:
    """A provider that is always unavailable (every call is a transport error)."""
    name, model = "down", ""

    def complete_json(self, system, user, schema=None):
        raise TransportError("down")


def _one_product(clean_df):
    """A (customer, product) subset that actually has tickets."""
    cust = clean_df[consts.OUT_CUSTOMER].iloc[0]
    df = clean_df[clean_df[consts.OUT_CUSTOMER] == cust]
    product = df[consts.OUT_PRODUCT].iloc[0]
    return df[df[consts.OUT_PRODUCT] == product], product


def test_well_behaved_provider_grounds_first_try(clean_df):
    subset, product = _one_product(clean_df)
    result = summarize_product(subset, product, "English", GoodProvider())
    assert result.note == ""  
    valid = set(subset[consts.OUT_ORDER].astype(str))
    cited = [n for ph in result.phases.values() for n in ph.ticket_numbers]
    assert cited                      
    assert set(cited) <= valid        


def test_self_correction_loop_catches_hallucination(clean_df):
    subset, product = _one_product(clean_df)
    result = summarize_product(subset, product, "English", HallucinateOnceProvider())
    valid = set(subset[consts.OUT_ORDER].astype(str))
    cited = [n for ph in result.phases.values() for n in ph.ticket_numbers]
    assert set(cited) <= valid                 
    assert _INVENTED_TICKET not in cited
    assert "Regenerated once" in result.note   


def test_empty_product_marked_no_activity(clean_df):
    result = summarize_product(None, "GIGA", "English", GoodProvider())
    assert "No tickets" in result.note
    assert all(ph.ticket_numbers == [] for ph in result.phases.values())


def test_transport_failure_falls_back_to_deterministic(clean_df):
    subset, product = _one_product(clean_df)
    result = summarize_product(subset, product, "English", _DownProvider())
    assert result.provider == "deterministic"
    valid = set(subset[consts.OUT_ORDER].astype(str))
    cited = [n for ph in result.phases.values() for n in ph.ticket_numbers]
    assert cited and set(cited) <= valid       
    assert "factual" in result.note.lower()


def test_omitted_tickets_are_covered_deterministically(clean_df):
    subset, product = _multi_ticket_product(clean_df)
    result = summarize_product(subset, product, "English", OmitProvider())
    valid = set(subset[consts.OUT_ORDER].astype(str))
    cited = [n for ph in result.phases.values() for n in ph.ticket_numbers]
    assert sorted(cited) == sorted(valid)          
    assert len(cited) == len(set(cited))           
    assert result.provider == "deterministic"


def test_computed_timeframes_are_present(clean_df):
    subset, product = _one_product(clean_df)
    result = summarize_product(subset, product, "English", GoodProvider())
    active = [ph for ph in result.phases.values() if ph.ticket_numbers]
    assert active and all(ph.timeframe for ph in active)


def test_structural_failure_fails_loudly(clean_df):
    subset, product = _one_product(clean_df)
    with pytest.raises(StructureError):
        summarize_product(subset, product, "English", MalformedProvider())


class _NoAssignmentProvider:
    """Valid JSON, but every phase is left empty — the model narrated nothing
    and cited nothing. Structurally fine, so Tier 1 passes it through."""
    name, model = "no-assignment", "m"

    def complete_json(self, system, user, schema=None):
        out = {"language": _requested_language(system)}
        out.update({p.id: {"ticket_numbers": [], "narrative": consts.NO_ACTIVITY}
                    for p in consts.PHASES})
        return out


def test_draft_assigning_no_tickets_falls_back_instead_of_crashing(clean_df):
    subset, product = _one_product(clean_df)
    result = summarize_product(subset, product, "English", _NoAssignmentProvider())
    assert result.provider == "deterministic"
    valid = set(subset[consts.OUT_ORDER].astype(str))
    cited = [n for ph in result.phases.values() for n in ph.ticket_numbers]
    assert sorted(cited) == sorted(valid)
    for ph in result.phases.values():
        assert bool(ph.ticket_numbers) != (ph.narrative == consts.NO_ACTIVITY)

class _OmitOnceProvider:
    """Omits tickets on the first call, then returns a complete draft."""
    name, model = "omit-once", "m"

    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user, schema=None):
        self.calls += 1
        return _summary(system, user, invent=False, cover=(self.calls > 1))


class _AlwaysOmitProvider:
    """Never converges — the same incomplete draft every time."""
    name, model = "always-omit", "m"

    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user, schema=None):
        self.calls += 1
        return _summary(system, user, invent=False, cover=False)


def _multi_ticket_product(clean_df):
    """A slice with enough tickets that omitting all but one actually omits."""
    for (cust, product), sub in clean_df.groupby([consts.OUT_CUSTOMER,
                                                  consts.OUT_PRODUCT]):
        if len(sub) > 1:
            return sub, product
    raise AssertionError("fixture has no multi-ticket product")


def test_retry_recovers_an_omitted_ticket_from_the_model(clean_df):
    subset, product = _multi_ticket_product(clean_df)
    provider = _OmitOnceProvider()
    result = summarize_product(subset, product, "English", provider)

    assert provider.calls == 2                      
    assert "Regenerated once after a grounding check." in result.note
    assert "placed by date" not in result.note
    valid = set(subset[consts.OUT_ORDER].astype(str))
    cited = [n for ph in result.phases.values() for n in ph.ticket_numbers]
    assert sorted(cited) == sorted(valid)


def test_retry_is_attempted_exactly_once_when_it_does_not_help(clean_df):
    subset, product = _multi_ticket_product(clean_df)
    provider = _AlwaysOmitProvider()
    result = summarize_product(subset, product, "English", provider)

    assert provider.calls == 2
    assert "still ungrounded" in result.note          
    assert "episodes intact" in result.note           
    assert result.provider == "deterministic"
    valid = set(subset[consts.OUT_ORDER].astype(str))
    cited = [n for ph in result.phases.values() for n in ph.ticket_numbers]
    assert sorted(cited) == sorted(valid)             


def test_transport_failure_never_triggers_a_retry(clean_df):
    class _CountingDown:
        name, model = "down", ""

        def __init__(self):
            self.calls = 0

        def complete_json(self, system, user, schema=None):
            self.calls += 1
            raise TransportError("down")

    subset, product = _multi_ticket_product(clean_df)
    provider = _CountingDown()
    result = summarize_product(subset, product, "English", provider)

    assert provider.calls == 1
    assert result.provider == "deterministic"
    assert "Regenerated" not in result.note
