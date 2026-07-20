"""Altair chart builder for insights — one consistent, readable bar form.

Deliberately the same rules the exported report enforces (``report/layout.py``),
because a chart that changes its argument between the screen and the hand-out is
worse than either version alone:

* **A rate spans a fixed 0–100% axis; counts scale to a rounded maximum.** The
  axis comes from ``Insight.axis()``, so the two renderers cannot disagree.
* **Emphasis, not decoration.** Bars are neutral grey; only the bar the
  recommendation acts on takes the accent, and a residual bucket is dimmer still.
  Colouring every bar says nothing about what matters. The takeaway always names
  the highlighted category in words, so meaning never rests on colour alone.
* **A rate carries its denominator** in the axis label (``Hardware  5/14``).
"""

from __future__ import annotations

import altair as alt

from src.analysis.insights import Insight
from src.theme import active_chart_palette


def _fmt(unit: str) -> str:
    return {"pct": ".0%", "hours": ".2f"}.get(unit, "d")


def insight_chart(ins: Insight, max_bars: int = 10) -> alt.LayerChart:
    """The chart this insight calls for, in the house style."""
    if ins.chart == "timeline":
        return timeline_chart(ins)
    return _bar_chart(ins, max_bars)


def timeline_chart(ins: Insight) -> alt.LayerChart:
    """Episodes as marks on a shared date axis — one row per customer x product.

    The screen twin of ``report.layout.timeline``: same ordering, same single
    accent, same "size ranks, label states" rule for the ticket count. A reader
    who compares the page with the exported PDF must not find two different
    pictures of the same fortnight.
    """
    p = active_chart_palette()
    d = ins.data.copy()
    counts = d.groupby("pair").size().sort_values(ascending=False, kind="stable")
    order = list(counts.index)

    d["_role"] = ["spot" if p_ == ins.highlight else "plain" for p_ in d["pair"]]
    color = alt.Color("_role:N", legend=None, scale=alt.Scale(
        domain=["plain", "spot"], range=[p.neutral_dark, p.accent]))

    y = alt.Y("pair:N", sort=order, title=None,
              axis=alt.Axis(labelLimit=260, domain=False, ticks=False,
                            labelColor=p.ink_soft, grid=True, gridColor=p.row_grid))
    x = alt.X("date:T", title=None,
              axis=alt.Axis(format="%d %b", grid=True, gridColor=p.grid,
                            domain=False, ticks=False, labelColor=p.axis,
                            labelFontSize=10, tickCount=6))
    tooltip = [
        alt.Tooltip("pair:N", title="Customer · product"),
        alt.Tooltip("date:T", title="Opened", format="%d %b %Y"),
        alt.Tooltip("tickets:Q", title="Tickets in this occasion"),
    ]

    marks = alt.Chart(d).mark_point(filled=True, opacity=1).encode(
        y=y, x=x, color=color, tooltip=tooltip,
        size=alt.Size("tickets:Q", legend=None,
                      scale=alt.Scale(domain=[1, 4], range=[90, 320])))
    labels = alt.Chart(d[d["tickets"] > 1]).mark_text(
        color=p.label_on_mark, fontSize=9, fontWeight="bold").encode(
        y=y, x=x, text=alt.Text("tickets:Q"))

    height = max(130, len(order) * 30)
    return (marks + labels).properties(height=height).configure_view(stroke=None)


def _bar_chart(ins: Insight, max_bars: int = 10) -> alt.LayerChart:
    """A horizontal bar chart for one insight (top ``max_bars`` categories)."""
    cat, val = ins.x, ins.y
    fmt = _fmt(ins.unit)

    p = active_chart_palette()
    d = ins.plot_frame(max_bars)
    top, ticks = ins.axis(d)

    d["_label"] = [
        f"{row[cat]}   {ins.support(row)}".strip() for _, row in d.iterrows()]
    order = list(d["_label"])

    d["_role"] = "plain"
    if ins.residual:
        d.loc[d[cat] == ins.residual, "_role"] = "residual"
    if ins.highlight:
        d.loc[d[cat] == ins.highlight, "_role"] = "spot"
    color = alt.Color("_role:N", legend=None, scale=alt.Scale(
        domain=["plain", "spot", "residual"],
        range=[p.neutral, p.accent, p.residual]))

    y = alt.Y("_label:N", sort=order, title=None,
              axis=alt.Axis(labelLimit=260, domain=False, ticks=False,
                            labelColor=p.ink_soft))
    x = alt.X(f"{val}:Q", title=None,
              scale=alt.Scale(domain=[0, top], nice=False),
              axis=alt.Axis(values=ticks, format=fmt, grid=True,
                            gridColor=p.grid, domain=False, ticks=False,
                            labelColor=p.axis, labelFontSize=10))
    tooltip = [
        alt.Tooltip(f"{cat}:N", title=cat.replace("_", " ").title()),
        alt.Tooltip(f"{val}:Q", title=val.replace("_", " ").title(), format=fmt),
    ]

    bars = alt.Chart(d).mark_bar(cornerRadiusEnd=2, height={"band": 0.62}).encode(
        y=y, x=x, color=color, tooltip=tooltip)
    labels = alt.Chart(d).mark_text(align="left", dx=6, color=p.ink_soft,
                                    fontSize=12).encode(
        y=y, x=x, text=alt.Text(f"{val}:Q", format=fmt))

    height = max(130, len(d) * 32)
    return (bars + labels).properties(height=height).configure_view(stroke=None)
