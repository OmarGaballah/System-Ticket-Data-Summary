"""The Insights report — the on-screen analysis as a standalone HTML file.

Same source of truth as the page: it consumes the very ``Insight`` objects
``analysis/insights.py`` computed, and draws each chart from the same
``plot_frame`` the on-screen chart uses — so a ranking can never differ between
screen and export. Streamlit-free, so it is testable offline and could just as
easily be produced by a scheduled job.

Structure: masthead -> KPI strip -> executive summary (when one was written) ->
one numbered finding per insight (question, chart, the "so what", the data
behind it) -> a method note. That last part is deliberate: a report someone
forwards should state what its numbers do and don't support.
"""

from __future__ import annotations

from datetime import datetime

from src import consts
from src.report import layout

METHOD_NOTE = (
    "<strong>Method.</strong> Every figure above is computed deterministically in "
    "pandas from the cleaned export — nothing is estimated or modelled. Repeat "
    f"contacts count contact <em>occasions</em>, not tickets: tickets raised "
    f"together are one occasion, and only a return after a gap of "
    f"{consts.EPISODE_GAP_HOURS:.0f} hours or more counts as coming back — the "
    "same grouping the story summaries cut their chapters on. Every other figure "
    "here is per ticket. "
    "Escalation is detected from the recorded action, reference result, and "
    "resolver fields (technician dispatch, device replacement, follow-up order). "
    "Root causes are grouped into themes so the German and English spellings of "
    "one problem do not fragment the ranking; the residual <em>Other</em> bucket "
    "is charted last and never headlines a finding. Resolution time is the median "
    "of completion minus acceptance. At small sample sizes treat the rankings as "
    "directional rather than conclusive."
)


def build(kpis: dict, insights: list, summary=None, source_name: str = "",
          generated_at: datetime | None = None) -> str:
    """Render the insights report to a standalone HTML document.

    ``summary`` is an optional ``ExecSummary``; without one the report contains
    no model-written text at all.
    """
    when = (generated_at or datetime.now()).strftime("%d %b %Y, %H:%M")
    source = source_name or "ticket export"
    title = "Ticket Insights"
    subtitle = (f"Operational analysis of {kpis['tickets']:,} tickets across "
                f"{kpis['customers']} customers · source: {source} · generated {when}")

    parts = [layout.kpis(
        [(f"{kpis['tickets']:,}", "Tickets"),
         (f"{kpis['customers']}", "Customers"),
         (f"{kpis['repeat_rate']:.0%}",
          f"Repeat contacts ({kpis['repeat_occasions']}/{kpis['contact_occasions']} "
          f"occasions)"),
         (f"{kpis['escalation_rate']:.0%}", "Escalated")],
        lede=(f"Leading root cause: **{kpis['top_theme']}**, behind "
              f"{kpis['top_theme_pct']:.0%} of all tickets."
              if kpis["top_theme"] != "—" else
              "No single root-cause theme leads in this data."),
    )]

    if summary is not None:
        parts.append(_exec_summary(summary, insights))
    parts.append(layout.contents([i.title for i in insights]))
    for i, insight in enumerate(insights, start=1):
        parts.append(_finding(i, insight))
    parts.append(f'<p class="method">{METHOD_NOTE}</p>')

    return layout.document(
        title, subtitle, "\n".join(parts),
        footer=f"System Ticket Data Summary · Insights · {source}")


def _exec_summary(summary, insights: list) -> str:
    seen = {i.takeaway.strip() for i in insights}
    actions = [a for a in summary.top_actions if a.strip() not in seen]
    body = layout.callout(summary.summary, tag="Executive summary", lead=True,
                          items=actions)
    note = summary.attribution() + (f" {summary.note}" if summary.note else "")
    return (f'<section class="section">{body}'
            f'<p class="attrib">{layout.inline(note)}</p></section>')


def _finding(number: int, insight) -> str:
    """One insight: question -> chart -> recommendation -> the frame behind it."""
    head = layout.section_head(number, insight.title, insight.question)
    chart = layout.chart(insight) if insight.has_signal else ""
    takeaway = layout.callout(insight.takeaway)
    data = layout.details("Show the data behind this finding",
                          layout.table(insight.data))
    return f'<section class="section">{head}{chart}{takeaway}{data}</section>'
