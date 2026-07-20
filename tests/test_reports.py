"""Exported HTML reports — self-containment, grounding, and escaping."""

import pandas as pd
import pytest

from src import consts, taxonomy
from src.analysis import exec_summary, insights
from src.engine import fallback, prompts, summarizer
from src.pipeline import mapping
from src.report import insights_report, layout, story_report
from src.ui import story_view


@pytest.fixture(scope="module")
def computed(clean_df):
    return insights.headline_kpis(clean_df), insights.compute_all(clean_df)


@pytest.fixture(scope="module")
def stories(clean_df):
    customer = str(clean_df[consts.OUT_CUSTOMER].iloc[0])
    cust_df = clean_df[clean_df[consts.OUT_CUSTOMER].astype(str) == customer]
    return customer, {
        p: fallback.deterministic_summary(p, cust_df[cust_df[consts.OUT_PRODUCT] == p])
        for p in consts.PRODUCTS
    }

@pytest.mark.parametrize("kind", ["insights", "story"])
def test_report_is_a_standalone_document(kind, computed, stories):
    kpis, items = computed
    html = (insights_report.build(kpis, items)
            if kind == "insights" else story_report.build(stories[1], stories[0], "English"))
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    for forbidden in ("<script", "src=", "http://", "https://", "@import"):
        assert forbidden not in html.lower()


def test_insights_report_contains_every_finding(computed):
    kpis, items = computed
    html = insights_report.build(kpis, items, source_name="sample.txt")
    for ins in items:
        assert layout.escape(ins.title) in html
        assert layout.escape(ins.takeaway)[:60] in html
    assert f"{kpis['tickets']:,}" in html
    assert "sample.txt" in html


def test_insights_report_charts_match_the_screen(computed):
    _, items = computed
    pareto = next(i for i in items if i.key == "root_cause")
    frame = pareto.plot_frame()
    assert frame[pareto.x].iloc[-1] == taxonomy.RESIDUAL_THEME
    assert frame[pareto.x].iloc[0] == pareto.highlight
    html = layout.bar_chart(pareto)
    assert 'class="row residual"' in html         
    assert "pinned last and never ranked" in html 
    
    assert html.count('class="row spot"') == 1
    assert "Highlighted:" not in html


def test_repeat_contacts_chart_excludes_single_contacts(computed):
    _, items = computed
    repeat = next(i for i in items if i.key == "repeat_contacts")
    assert (repeat.data["occasions"] > 1).all()    
    assert (repeat.data["tickets"] >= repeat.data["occasions"]).all()


def test_story_report_keeps_provenance_and_tickets(stories):
    customer, summaries = stories
    html = story_report.build(summaries, customer, "English")
    assert f"Customer {customer}" in html
    assert "no model was involved" in html         
    assert "deterministic ·" not in html           
    cited = [n for s in summaries.values()
             for ps in s.phases.values() for n in ps.ticket_numbers]
    assert cited and all(n in html for n in cited) 


def test_exec_summary_is_attributed_not_templated(computed):
    kpis, items = computed
    det = exec_summary._deterministic(kpis, items, "")
    assert "Written by deterministic" not in det.attribution()
    assert det.attribution() in insights_report.build(kpis, items, det)

    llm = exec_summary.ExecSummary("All fine.", ["Do X"], "gemini")
    assert "Narrated by gemini" in llm.attribution()


def test_exec_actions_are_not_repeated_verbatim(computed):

    kpis, items = computed
    det = exec_summary._deterministic(kpis, items, "")
    assert det.top_actions                       
    html = insights_report.build(kpis, items, det)
    for action in det.top_actions:
        assert html.count(layout.inline(action)) == 1

def test_model_written_text_cannot_inject_markup(computed):
    kpis, items = computed
    hostile = exec_summary.ExecSummary(
        "<script>alert('x')</script> **bold** stays bold", [], "gemini")
    html = insights_report.build(kpis, items, hostile)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<strong>bold</strong>" in html       


def test_empty_chart_frame_renders_nothing():
    empty = insights.Insight("k", "T", "Q?", "takeaway",
                             pd.DataFrame({"cat": [], "val": []}),
                             has_signal=True, x="cat", y="val")
    assert layout.bar_chart(empty) == ""



def test_story_shows_each_ticket_service_category(clean_df, stories):

    customer, summaries = stories
    cust_df = clean_df[clean_df[consts.OUT_CUSTOMER].astype(str) == customer]
    categories = mapping.ticket_categories(cust_df)
    html = story_report.build(summaries, customer, "English", categories)
    md = story_view.to_markdown(summaries, customer, categories)

    broadband = summaries["Broadband"]
    cited = [n for ps in broadband.phases.values() for n in ps.ticket_numbers]
    assert {categories[n] for n in cited} == {"KAI", "NET"}   
    for number in cited:
        assert f"{number} ({categories[number]})" in html
        assert f"{number} ({categories[number]})" in md


def test_label_ticket_degrades_without_a_mapping():
    assert mapping.label_ticket("001-1/24", {"001-1/24": "NET"}) == "001-1/24 (NET)"
    assert mapping.label_ticket("001-1/24", {}) == "001-1/24"
    assert mapping.label_ticket("001-1/24", None) == "001-1/24"


def test_payload_carries_the_category_and_a_readable_cause(clean_df):
    cust = clean_df[consts.OUT_CUSTOMER].iloc[0]
    subset = clean_df[(clean_df[consts.OUT_CUSTOMER] == cust)
                      & (clean_df[consts.OUT_PRODUCT] == "Broadband")]
    payload = summarizer.build_payload(subset)
    assert {row["service_category"] for row in payload} == {"KAI", "NET"}
    assert any(row["cause_theme"] for row in payload)


def test_prompt_forbids_inventing_causal_links():
    system = prompts.build_system("English")
    assert "CHRONOLOGICAL, not causal" in system
    assert "service_category" in system
    assert "CONCURRENT" in system
    assert "URS_KIP_Reset_WLAN_Settings" in system and "plain language" in system


def test_prompt_leaves_the_model_no_say_in_phase_assignment():
    system = prompts.build_system("English")
    assert "You write the narratives" in system
    for delegating in ("by its CHARACTER", "you choose", "ONE middle phase",
                       "TWO middle phases"):
        assert delegating not in system
        assert '"initial_issue", "follow_ups", "developments", "recent_events"' in system


def test_prompt_forbids_the_three_narrative_leaks():
    system = prompts.build_system("English")
    assert "NEVER write a ticket number inside a narrative" in system
    assert "never the literal\n  word OK or Error" in system
    assert "never the shape of the story" in system



def test_rates_always_span_a_full_axis(computed):
    _, items = computed
    esc = next(i for i in items if i.key == "escalation")
    assert esc.unit == "pct"
    top, ticks = esc.axis()
    assert top == 1.0
    assert ticks == [0.0, 0.25, 0.5, 0.75, 1.0]

    html = layout.bar_chart(esc)
    frame = esc.plot_frame()
    leader = float(frame[esc.y].max())
    assert leader < 0.5                                   
    assert f'style="width:{leader * 100:.4f}%"' in html   
    assert "fixed 0–100% axis" in html


def test_counts_scale_to_a_rounded_maximum(computed):
    _, items = computed
    handoffs = next(i for i in items if i.key == "handoffs")
    top, ticks = handoffs.axis()
    peak = float(handoffs.plot_frame()[handoffs.y].max())
    assert top >= peak                       
    assert ticks[0] == 0 and ticks[-1] == top
    assert len(ticks) >= 3                   
    assert "Axis runs 0 to" in layout.bar_chart(handoffs)


def test_every_rate_shows_its_denominator(computed):
    _, items = computed
    esc = next(i for i in items if i.key == "escalation")
    frame = esc.plot_frame()
    assert all(esc.support(row) for _, row in frame.iterrows())

    html = layout.bar_chart(esc)
    for _, row in frame.iterrows():
        assert f'<div class="den">{esc.support(row)}</div>' in html
    assert "Denominators shown" in html


def test_zero_renders_as_a_label_not_a_bar_stub(computed):
    _, items = computed
    esc = next(i for i in items if i.key == "escalation")
    frame = esc.plot_frame()
    assert (frame[esc.y] == 0).any()
    html = layout.bar_chart(esc)
    assert 'style="width:0.0000%"' in html
    assert html.count("<span class=\"val\">0%</span>") >= 1


def test_gridlines_are_drawn_with_a_stronger_end(computed):
    _, items = computed
    esc = next(i for i in items if i.key == "escalation")
    html = layout.bar_chart(esc)
    assert html.count("<i ") == 5                      
    assert 'class="end" style="left:100.0000%"' in html


def test_escalation_takeaway_leads_with_the_absolute_count(computed):

    _, items = computed
    esc = next(i for i in items if i.key == "escalation")
    assert "absolute terms" in esc.takeaway
    assert "directional" in esc.takeaway
    assert "genuinely failing" not in esc.takeaway      
    by_count = esc.data.sort_values("escalated", ascending=False, kind="stable")
    assert esc.highlight == by_count.iloc[0][consts.OUT_PRODUCT]


def test_report_has_print_furniture_and_contents(computed):
    kpis, items = computed
    html = insights_report.build(kpis, items)
    assert "@page" in html and "counter(page)" in html
    assert 'class="running"' in html                    
    for i, ins in enumerate(items, start=1):
        assert f"<b>{i:02d}</b> {layout.escape(ins.title)}" in html
        assert f'<span class="numeral">{i:02d}</span>' in html


def test_kpi_strip_is_four_numbers_plus_a_typed_statement(computed):
    kpis, items = computed
    html = insights_report.build(kpis, items)
    assert html.count('<div class="kpi">') == 4         
    assert 'class="lede"' in html                       
    assert f"Leading root cause" in html


def test_count_axes_use_whole_number_ticks(computed):
    _, items = computed
    for insight in items:
        if insight.unit != "count":
            continue
        _, ticks = insight.axis()
        assert all(float(t).is_integer() for t in ticks), insight.key
        labels = [insight.format_value(t) for t in ticks]
        assert labels == sorted(labels, key=lambda s: float(s.replace(",", "")))
        assert len(labels) == len(set(labels))      

def test_internal_tool_names_are_stripped_from_the_payload(clean_df):
    assert clean_df[consts.OUT_ACTION].astype(str).str.contains("TITAN").any()
    payload = summarizer.build_payload(clean_df)
    blob = " ".join(str(v) for row in payload for v in row.values())
    assert "TITAN" not in blob.upper()
    assert any(row["action"] == "Successful" for row in payload)


def test_redaction_keeps_the_readers_own_vocabulary():
    from src import taxonomy
    for keep in ("WLAN settings optimized", "Bandwidth Checked",
                 "New BI order created", "Austauschgerät versendet"):
        assert taxonomy.redact_internal(keep) == keep
    assert taxonomy.redact_internal("TITAN Successful") == "Successful"
    assert taxonomy.redact_internal("TSCW2") is None      
    assert taxonomy.redact_internal(None) is None


def test_action_ladder_is_redacted_too(clean_df):
    items = insights.compute_all(clean_df)
    repeat = next(i for i in items if i.key == "repeat_contacts")
    assert "TITAN" not in repeat.takeaway.upper()



def test_handoff_finding_does_not_assume_imbalance_is_a_problem(computed):
    _, items = computed
    handoffs = next(i for i in items if i.key == "handoffs")
    assert "specialisation" in handoffs.takeaway     
    assert "add cost and delay" not in handoffs.takeaway   


def test_exec_prompt_forbids_unsupported_prescriptions(computed):
    kpis, items = computed
    system, _ = exec_summary.build_prompts(kpis, items)
    assert "NOT a problem" in system
    assert "rebalancing" in system
    assert "carry that caveat" in system



class _EpisodeSplitterOnce(summarizer.LLMProvider):
    """Splits an episode across two phases on the first call, complies on the
    second — the failure the episode-partition check exists to catch."""
    name, model = "splitter", "m"

    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user, schema=None):
        import re
        self.calls += 1

        groups = [(m.group(1), [t.strip() for t in m.group(2).split(",")])
                  for m in re.finditer(
                      r'^- episode \d+ \(.*?\) -> "([^"]+)": (.+)$', user, re.M)]
        out = {"language": "English"}
        out.update({p.id: {"ticket_numbers": [], "narrative": consts.NO_ACTIVITY}
                    for p in consts.PHASES})
        if self.calls == 1:
            flat = [t for _, g in groups for t in g]
            for pid, ticket in zip(consts.PHASE_IDS, flat):
                out[pid] = {"ticket_numbers": [ticket], "narrative": "split."}
            return out
        for pid, tickets in groups:
            out[pid] = {"ticket_numbers": list(tickets), "narrative": "grounded."}
        return out


def _multi_episode_slice(clean_df):
    from src.engine import episodes as ep
    for (cust, product), sub in clean_df.groupby([consts.OUT_CUSTOMER,
                                                  consts.OUT_PRODUCT]):
        if len(ep.compute(sub)) > 2:
            return str(cust), product, sub
    raise AssertionError("fixture has no multi-episode product")


def test_a_retry_is_disclosed_in_the_rendered_report(clean_df):

    customer, product, subset = _multi_episode_slice(clean_df)
    provider = _EpisodeSplitterOnce()
    summary = summarizer.summarize_product(subset, product, "English", provider)

    assert provider.calls == 2
    assert summary.provider == "splitter"            # the retry converged
    assert "Regenerated once after a grounding check." in summary.note
    assert "Regenerated once" in summary.provenance()

    html = story_report.build({product: summary}, customer, "English")
    assert "Regenerated once after a grounding check." in html
    md = story_view.to_markdown({product: summary}, customer)
    assert "Regenerated once" in md



def test_timeline_renders_marks_on_a_shared_axis(computed):
    _, items = computed
    tl = next(i for i in items if i.key == "episode_timeline")
    html = layout.chart(tl)
    assert 'class="chart timeline' in html
    assert html.count('<span class="mark"') == len(tl.data)   
    assert html.count('class="row spot"') == 1        
    assert "gridlines" in html and "<figcaption>" in html
    assert '<span class="n">2</span>' in html
    assert html.count('<span class="n">1</span>') == 0


def test_timeline_is_in_the_report_and_its_contents(computed):
    kpis, items = computed
    html = insights_report.build(kpis, items)
    assert "Contact timeline" in html
    assert "06" in html                               
    assert 'class="chart timeline' in html
    assert html.index("First-time-fix") < html.index("Contact timeline")


def test_timeline_survives_a_single_day_of_data(clean_df):
    one_day = clean_df[clean_df[consts.OUT_ACCEPT].dt.date
                       == clean_df[consts.OUT_ACCEPT].dt.date.min()]
    tl = insights.episode_timeline(one_day)
    html = layout.chart(tl)                            
    assert 'class="chart timeline' in html


def test_every_insight_builds_an_altair_chart(computed):
    from src.ui import charts
    _, items = computed
    for ins in items:
        if ins.has_signal:
            assert charts.insight_chart(ins).to_dict()["layer"]
