"""Block D — grounded executive summary tests (offline)."""

from src.analysis import exec_summary
from src.analysis.insights import compute_all, headline_kpis
from src.engine.providers.base import TransportError


def test_deterministic_fallback_when_llm_unavailable(clean_df, monkeypatch):
    k, items = headline_kpis(clean_df), compute_all(clean_df)

    class Down:  
        name, model = "none", ""
        def complete_json(self, s, u, schema=None):
            raise TransportError("no provider")

    monkeypatch.setattr(exec_summary, "build_with_fallback", lambda name: Down())
    es = exec_summary.generate(k, items, None)      
    assert es.provider == "deterministic"
    assert es.summary.strip()
    assert 1 <= len(es.top_actions) <= 3


def test_build_prompts_are_grounded(clean_df):
    k, items = headline_kpis(clean_df), compute_all(clean_df)
    system, user = exec_summary.build_prompts(k, items)
    assert "ONLY the findings" in system
    assert items[0].title in user                   


def test_llm_path_uses_provider_and_schema(clean_df, monkeypatch):
    k, items = headline_kpis(clean_df), compute_all(clean_df)

    class Fake:
        name, model = "fake", "m"
        def complete_json(self, s, u, schema=None):
            assert schema is exec_summary.EXEC_SCHEMA   
            return {"summary": "All good.", "top_actions": ["Do X", "Do Y"]}

    monkeypatch.setattr(exec_summary, "build_with_fallback", lambda name: Fake())
    es = exec_summary.generate(k, items, "fake")
    assert es.provider == "fake"
    assert es.summary == "All good."
    assert es.top_actions == ["Do X", "Do Y"]


def test_llm_empty_summary_falls_back(clean_df, monkeypatch):
    k, items = headline_kpis(clean_df), compute_all(clean_df)

    class Empty:
        name, model = "empty", "m"
        def complete_json(self, s, u, schema=None):
            return {"summary": "  ", "top_actions": []}

    monkeypatch.setattr(exec_summary, "build_with_fallback", lambda name: Empty())
    es = exec_summary.generate(k, items, "empty")
    assert es.provider == "deterministic"


def test_stray_number_is_flagged(clean_df, monkeypatch):
    k, items = headline_kpis(clean_df), compute_all(clean_df)

    class Invent:
        name, model = "invent", "m"
        def complete_json(self, s, u, schema=None):
            return {"summary": "The team wasted 424242 hours last year.",
                    "top_actions": []}

    monkeypatch.setattr(exec_summary, "build_with_fallback", lambda name: Invent())
    es = exec_summary.generate(k, items, "invent")
    assert "424242" in es.note
    assert "could not be traced" in es.note


def test_grounded_numbers_are_not_flagged(clean_df, monkeypatch):
    k, items = headline_kpis(clean_df), compute_all(clean_df)

    class Echo:
        name, model = "echo", "m"
        def complete_json(self, s, u, schema=None):
            return {"summary": f"There are {k['tickets']} tickets in scope.",
                    "top_actions": []}

    monkeypatch.setattr(exec_summary, "build_with_fallback", lambda name: Echo())
    es = exec_summary.generate(k, items, "echo")
    assert es.note == ""
