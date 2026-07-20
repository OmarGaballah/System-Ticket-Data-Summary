"""The house style for exported reports: one stylesheet, a few components.

Everything is inline and dependency-free — no CDN, no script, no web font — so
the downloaded file is a genuine artefact the user owns. Charts are drawn with
CSS: they stay sharp at any zoom, survive "Print to PDF" at any paper size, and
every number in them is selectable text for anyone using a screen reader or
copying a figure out.

Two rules the chart enforces, because they are the difference between a chart
that informs and one that flatters:

* **A rate spans a fixed 0–100% axis; a count may scale to its maximum.** The
  two are never mixed. Scaling a rate to the data's own maximum turns a
  three-point gap into a full-width-versus-92% comparison.
* **Every rate carries its denominator** beside the label, so 36% (5 of 14) is
  never read as the same kind of measurement as 33% (1 of 3).

Colour does one job: the bar the recommendation acts on takes the accent, every
other bar is neutral. Bars are not the brand colour — a chart where everything
is coloured says nothing about what matters. Because the accent alone carries
the emphasis, the takeaway beneath always names the highlighted category in
words too, so the meaning never depends on colour perception.
"""

from __future__ import annotations

import re
from html import escape as _escape

import pandas as pd

from src.theme import (ACCENT, GRID, GRID_END, INK, INK_SOFT, MONO, MUTED,
                       NEUTRAL, NEUTRAL_DARK, PAPER, RULE, SANS, SERIF, SHELL,
                       TINT)

STYLESHEET = f"""
:root {{
  --ink: {INK}; --ink-soft: {INK_SOFT}; --muted: {MUTED};
  --accent: {ACCENT}; --neutral: {NEUTRAL}; --neutral-dark: {NEUTRAL_DARK};
  --rule: {RULE}; --grid: {GRID}; --grid-end: {GRID_END};
  --paper: {PAPER}; --tint: {TINT};
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 40px 24px 64px; background: {SHELL};
  font: 15px/1.62 {SANS}; color: var(--ink);
  -webkit-font-smoothing: antialiased;
  font-variant-numeric: tabular-nums;
}}
.sheet {{
  max-width: 840px; margin: 0 auto; background: var(--paper);
  border: 1px solid var(--rule); padding: 48px 52px 44px;
}}

/* --- masthead ------------------------------------------------------------ */
header.masthead {{ border-top: 2px solid var(--ink); padding-top: 20px; }}
h1 {{
  font: 400 34px/1.15 {SERIF}; margin: 0 0 10px; letter-spacing: -0.2px;
}}
.sub {{ color: var(--muted); font-size: 13px; margin: 0; letter-spacing: 0.1px; }}

/* --- section headings ---------------------------------------------------- */
.section {{ margin-top: 46px; }}
.head {{ display: flex; align-items: baseline; gap: 14px; }}
.numeral {{
  font: 400 30px/1 {SERIF}; color: var(--neutral-dark);
  letter-spacing: 0.5px; flex: none;
}}
h2 {{ font: 400 23px/1.2 {SERIF}; margin: 0; letter-spacing: -0.1px; }}
.q {{ color: var(--muted); font-size: 13.5px; margin: 4px 0 22px 44px; }}
h3 {{
  font: 600 11px/1.4 {SANS}; margin: 0 0 3px; color: var(--muted);
  text-transform: uppercase; letter-spacing: 1.1px;
}}
p {{ margin: 0 0 11px; }}

/* --- KPI strip: four numbers, then a separate typed statement ------------ */
.kpis {{ display: flex; flex-wrap: wrap; gap: 1px; background: var(--rule);
         border: 1px solid var(--rule); margin: 28px 0 0; }}
.kpi {{ flex: 1 1 120px; background: var(--paper); padding: 14px 16px; }}
.kpi .v {{ font: 400 27px/1.05 {SERIF}; color: var(--ink); }}
.kpi .l {{ font-size: 10px; letter-spacing: 1px; text-transform: uppercase;
           color: var(--muted); margin-top: 6px; }}
.lede {{
  border: 1px solid var(--rule); border-top: 0; padding: 12px 16px;
  font-size: 13.5px; color: var(--ink-soft); background: var(--tint);
}}
.lede strong {{ font-weight: 600; color: var(--ink); }}

/* --- contents ------------------------------------------------------------ */
.attrib {{ font-size: 11.5px; color: var(--muted); margin: 10px 0 0; }}
.contents {{
  margin: 26px 0 0; padding: 12px 0 0; border-top: 1px solid var(--rule);
  font-size: 12px; color: var(--muted); letter-spacing: 0.2px;
}}
.contents b {{ color: var(--ink-soft); font-weight: 600; }}
.contents span {{ white-space: nowrap; }}

/* --- chart --------------------------------------------------------------- */
/* Counts have no denominator, so that column collapses rather than leaving a
   gutter between the label and the bar. */
.chart.nodenom {{ --den: 0px; }}
.chart.nodenom .row, .chart.nodenom .ticks {{
  grid-template-columns: var(--lab) 1fr; }}
.chart.nodenom .scale {{ grid-column: 2; }}
.chart {{ --lab: 128px; --den: 44px; --gap: 10px;
          --plot: calc(var(--lab) + var(--den) + var(--gap) * 2);
          margin: 0 0 20px; }}
.plot {{ position: relative; }}
.gridlines {{ position: absolute; top: 0; bottom: 0; left: var(--plot); right: 0;
              pointer-events: none; }}
.gridlines i {{ position: absolute; top: 0; bottom: 0; width: 1px;
                background: var(--grid); }}
.gridlines i.end {{ background: var(--grid-end); }}
.row {{ display: grid; grid-template-columns: var(--lab) var(--den) 1fr;
        gap: var(--gap); align-items: center; padding: 3px 0; }}
.lab {{ font-size: 13px; text-align: right; color: var(--ink-soft);
        overflow-wrap: anywhere; }}
.den {{ font-size: 11px; text-align: right; color: var(--muted); font-family: {MONO}; }}
.track {{ display: flex; align-items: center; height: 19px; position: relative; }}
.bar {{ height: 19px; background: var(--neutral);
        border-radius: 0 2px 2px 0; }}   /* square at the baseline, radius on the data end */
.val {{ font-size: 12.5px; color: var(--ink-soft); margin-left: 9px;
        white-space: nowrap; }}
.row.spot .lab {{ color: var(--ink); font-weight: 600; }}
.row.spot .bar {{ background: var(--accent); }}
.row.spot .val {{ color: var(--ink); font-weight: 600; }}
.row.residual .lab {{ font-style: italic; color: var(--muted); }}
.row.residual .bar {{ background: var(--neutral); opacity: 0.55; }}
.ticks {{ display: grid; grid-template-columns: var(--lab) var(--den) 1fr;
          gap: var(--gap); margin-top: 6px; }}
.scale {{ grid-column: 3; position: relative; height: 15px; }}
.scale span {{ position: absolute; font-size: 10.5px; color: var(--muted);
               transform: translateX(-50%); }}
.scale span.first {{ transform: none; }}
.scale span.last {{ transform: translateX(-100%); }}
figcaption {{ font-size: 11.5px; color: var(--muted); margin-top: 14px; }}

/* --- timeline (episodes on a shared date axis) --------------------------- */
.timeline .row {{ padding: 5px 0; }}
.timeline .track {{ height: 22px; }}
/* The baseline is the row's spine: marks sit ON a date, so the rule has to run
   the full width even where nothing happened. */
.timeline .track::before {{ content: ""; position: absolute; left: 0; right: 0;
                            top: 50%; height: 1px; background: var(--grid-end); }}
.timeline .mark {{ position: absolute; top: 50%; transform: translate(-50%, -50%);
                   border-radius: 50%; background: var(--neutral-dark);
                   border: 1px solid var(--paper); display: flex;
                   align-items: center; justify-content: center; }}
.timeline .mark .n {{ font-size: 9px; color: var(--paper); font-weight: 600;
                      line-height: 1; }}
.timeline .row.spot .mark {{ background: var(--accent); }}

/* --- callout ------------------------------------------------------------- */
.callout {{ background: var(--tint); border-left: 2px solid var(--accent);
            padding: 15px 18px; margin: 6px 0 18px; }}
.callout .tag {{ font: 600 10.5px/1 {SANS}; letter-spacing: 1.2px;
                 text-transform: uppercase; color: var(--accent);
                 display: block; margin-bottom: 7px; }}
.callout p {{ margin-bottom: 0; font-size: 14px; }}
.callout ol {{ margin: 11px 0 0; padding-left: 18px; }}
.callout ol li {{ margin-bottom: 7px; font-size: 13.5px; }}
.callout.lead p {{ font: 400 16px/1.55 {SERIF}; }}

/* --- data table ---------------------------------------------------------- */
details {{ margin-top: 6px; }}
summary {{ cursor: pointer; font-size: 12.5px; color: var(--muted); }}
table {{ border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 12.5px; }}
th {{ font-weight: 600; text-align: left; color: var(--muted); font-size: 10.5px;
      text-transform: uppercase; letter-spacing: 0.8px;
      border-bottom: 1px solid var(--ink); }}
th, td {{ padding: 6px 10px; }}
td {{ border-bottom: 1px solid var(--rule); }}
td.num, th.num {{ text-align: right; }}

/* --- story chapters ------------------------------------------------------ */
.product {{ margin-top: 40px; }}
.product > .prov {{ color: var(--muted); font-size: 12.5px; margin: 4px 0 0; }}
.product > hr {{ border: 0; border-top: 1px solid var(--ink); margin: 12px 0 22px; }}
.chapter {{ margin-bottom: 22px; }}
.chapter.quiet {{ margin-bottom: 12px; }}
.chapter.quiet h3, .chapter.quiet p {{ color: var(--muted); }}
.chapter .when {{ color: var(--muted); font-size: 12.5px; margin: 0 0 5px; }}
.tickets {{ font-family: {MONO}; font-size: 11px; color: var(--muted); margin: 7px 0 0; }}
.method {{ margin-top: 46px; padding-top: 16px; border-top: 1px solid var(--rule);
           font-size: 11.5px; line-height: 1.6; color: var(--muted); }}
footer {{ max-width: 840px; margin: 14px auto 0; color: var(--muted); font-size: 11.5px; }}

/* --- print furniture ----------------------------------------------------- */
/* The @page margin boxes below are honoured by print engines that implement
   CSS Paged Media (Prince, WeasyPrint). Browsers ignore them, so the running
   header is *also* provided as a position:fixed element, which Chrome and Edge
   repeat on every printed sheet. Page numbering has no browser equivalent —
   there is no way to read the page counter outside a @page margin box — so it
   appears only in a paged-media renderer rather than being faked. */
@page {{
  size: A4; margin: 18mm 16mm 20mm;
  @top-left {{ content: string(doctitle); font-size: 9pt; color: {MUTED}; }}
  @bottom-right {{ content: "Page " counter(page) " of " counter(pages);
                   font-size: 9pt; color: {MUTED}; }}
}}
h1 {{ string-set: doctitle content(); }}
.running {{ display: none; }}
@media print {{
  body {{ background: {PAPER}; padding: 0; font-size: 10.5pt; }}
  .sheet {{ border: 0; padding: 0; max-width: none; }}
  .running {{
    display: block; position: fixed; top: 0; left: 0; right: 0;
    font-size: 8.5pt; color: {MUTED};
    padding-bottom: 4pt; border-bottom: 0.5pt solid {RULE};
  }}
  .sheet {{ padding-top: 22pt; }}
  .section, .product, .chapter, .callout, .chart {{ break-inside: avoid; }}
  h2, .head {{ break-after: avoid; }}
  details {{ display: none; }}   /* the appendix tables are screen-only */
  footer {{ display: none; }}
}}
"""


def escape(text) -> str:
    return _escape("" if text is None else str(text))


_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", re.S)
_CODE = re.compile(r"`([^`]+?)`")


def inline(text) -> str:
    """Escape, then apply the small Markdown vocabulary the app's strings use.

    Order matters: escaping first means user or model text can never inject
    markup, and the only tags that can appear are the ones produced below.
    """
    out = _BOLD.sub(r"<strong>\1</strong>", escape(text))
    out = _ITALIC.sub(r"<em>\1</em>", out)
    return _CODE.sub(r"<code>\1</code>", out)


def document(title: str, subtitle: str, body: str, footer: str) -> str:
    """Wrap the body in the full standalone HTML document."""
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>{STYLESHEET}</style>\n</head><body>\n"
        f'<div class="running">{escape(title)} · {escape(footer)}</div>\n'
        f'<div class="sheet">\n<header class="masthead">\n'
        f'<h1>{escape(title)}</h1>\n<p class="sub">{escape(subtitle)}</p>\n'
        "</header>\n"
        f"{body}\n</div>\n"
        f"<footer>{escape(footer)}</footer>\n</body></html>\n"
    )


def section_head(number: int, title: str, question: str) -> str:
    """A decorative numeral beside a serif title, then the question it answers."""
    return (f'<div class="head"><span class="numeral">{number:02d}</span>'
            f"<h2>{escape(title)}</h2></div>"
            f'<p class="q">{escape(question)}</p>')


def kpis(numbers: list[tuple[str, str]], lede: str = "") -> str:
    """Four numeric tiles, and any qualitative headline as a separate typed
    statement below — a word set in a numeric tile is the weakest thing on a
    page of numbers, because it invites a comparison it can't support."""
    cards = "".join(
        f'<div class="kpi"><div class="v">{escape(v)}</div>'
        f'<div class="l">{escape(label)}</div></div>'
        for v, label in numbers)
    strip = f'<div class="kpis">{cards}</div>'
    return strip + (f'<div class="lede">{inline(lede)}</div>' if lede else "")


def contents(titles: list[str]) -> str:
    """A one-line table of contents — orientation for a printed hand-out."""
    if not titles:
        return ""
    items = " &nbsp;&nbsp; ".join(
        f"<span><b>{i:02d}</b> {escape(t)}</span>"
        for i, t in enumerate(titles, start=1))
    return f'<p class="contents">{items}</p>'


def callout(text: str, tag: str = "So what", lead: bool = False,
            items: list[str] | None = None) -> str:
    cls = "callout lead" if lead else "callout"
    inner = f"<p>{inline(text)}</p>"
    if items:
        inner += "<ol>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ol>"
    tag_html = f'<span class="tag">{escape(tag)}</span>' if tag else ""
    return f'<div class="{cls}">{tag_html}{inner}</div>'


def bar_chart(insight, max_bars: int = 10) -> str:
    """A CSS bar chart drawn from the insight's own display frame and axis."""
    frame = insight.plot_frame(max_bars)
    if frame.empty:
        return ""
    top, ticks = insight.axis(frame)
    top = top or 1.0

    lines = "".join(
        f'<i class="{"end" if t >= top else ""}" style="left:{t / top * 100:.4f}%"></i>'
        for t in ticks)

    has_denominator = bool(insight.numerator and insight.denominator)

    rows = []
    for _, row in frame.iterrows():
        label = str(row[insight.x])
        value = float(row[insight.y])
        classes = ["row"]
        if insight.residual and label == insight.residual:
            classes.append("residual")
        elif insight.highlight and label == insight.highlight:
            classes.append("spot")
        width = max(0.0, min(value / top, 1.0)) * 100.0 if value > 0 else 0.0
        denominator = (f'<div class="den">{escape(insight.support(row))}</div>'
                       if has_denominator else "")
        rows.append(
            f'<div class="{" ".join(classes)}">'
            f'<div class="lab">{escape(label)}</div>{denominator}'
            f'<div class="track"><div class="bar" style="width:{width:.4f}%"></div>'
            f'<span class="val">{escape(insight.format_value(value))}</span></div>'
            f"</div>")

    scale = "".join(
        f'<span class="{_tick_class(t, ticks)}" style="left:{t / top * 100:.4f}%">'
        f"{escape(insight.format_value(t))}</span>"
        for t in ticks)

    figure_class = "chart" if has_denominator else "chart nodenom"
    return (f'<figure class="{figure_class}"><div class="plot">'
            f'<div class="gridlines">{lines}</div>{"".join(rows)}</div>'
            f'<div class="ticks"><div class="scale">{scale}</div></div>'
            f"{_chart_note(insight, frame)}</figure>")


def chart(insight, max_bars: int = 10) -> str:
    """Render whichever chart this insight calls for."""
    return timeline(insight) if insight.chart == "timeline" else bar_chart(insight, max_bars)


_TIMELINE_TICKS = 6


def timeline(insight) -> str:
    """Episodes as marks on a shared date axis — one row per customer x product.

    Same furniture as the bar charts (fixed axis, gridlines, tick labels, one
    accent row) so the two read as one family. The mark's size carries the
    episode's ticket count, and any episode of more than one ticket also prints
    the number: size alone is a comparison a reader cannot make precisely, so it
    ranks, and the label states.
    """
    data = insight.data
    if data.empty:
        return ""

    start, end = data["date"].min(), data["date"].max()
    span = max((end - start).total_seconds(), 86400.0)
    ticks = [start + pd.Timedelta(seconds=span * i / (_TIMELINE_TICKS - 1))
             for i in range(_TIMELINE_TICKS)]

    lines = "".join(
        f'<i class="{"end" if i == len(ticks) - 1 else ""}" '
        f'style="left:{i / (len(ticks) - 1) * 100:.4f}%"></i>'
        for i in range(len(ticks)))

    
    counts = data.groupby("pair").size().sort_values(ascending=False, kind="stable")
    rows = []
    for pair in counts.index:
        marks = []
        for _, row in data[data["pair"] == pair].iterrows():
            left = (row["date"] - start).total_seconds() / span * 100.0
            n = int(row["tickets"])
            size = 9 + min(n - 1, 4) * 3          
            label = f'<span class="n">{n}</span>' if n > 1 else ""
            marks.append(
                f'<span class="mark" style="left:{left:.4f}%;'
                f'width:{size}px;height:{size}px" '
                f'title="{escape(row["date"].strftime("%d %b %Y"))} · {n} ticket'
                f'{"s" if n != 1 else ""}">{label}</span>')
        classes = "row spot" if pair == insight.highlight else "row"
        rows.append(f'<div class="{classes}"><div class="lab">{escape(pair)}</div>'
                    f'<div class="track">{"".join(marks)}</div></div>')

    scale = "".join(
        f'<span class="{_tick_class(float(i), [0.0, float(len(ticks) - 1)])}" '
        f'style="left:{i / (len(ticks) - 1) * 100:.4f}%">'
        f'{escape(t.strftime("%d %b"))}</span>'
        for i, t in enumerate(ticks))

    note = (f"One mark per contact occasion, placed on the date it opened; larger "
            f"marks carry more tickets and print the count. Axis runs "
            f"{escape(start.strftime('%d %b %Y'))} to "
            f"{escape(end.strftime('%d %b %Y'))}, shared by every row.")
    return (f'<figure class="chart timeline nodenom"><div class="plot">'
            f'<div class="gridlines">{lines}</div>{"".join(rows)}</div>'
            f'<div class="ticks"><div class="scale">{scale}</div></div>'
            f"<figcaption>{note}</figcaption></figure>")


def _tick_class(value: float, ticks: list[float]) -> str:
    if value == ticks[0]:
        return "first"
    return "last" if value == ticks[-1] else ""


def _chart_note(insight, frame: pd.DataFrame) -> str:
    """What the reader needs to know to read the chart correctly — never a
    restatement of which bar is coloured (the takeaway already names it)."""
    notes = []
    if insight.numerator and insight.denominator:
        notes.append("Denominators shown beside each label")
    top, _ = insight.axis(frame)
    notes.append("Bars share a fixed 0–100% axis" if insight.unit == "pct"
                 else f"Axis runs 0 to {insight.format_value(top)}")
    if insight.residual and (frame[insight.x] == insight.residual).any():
        notes.append(f"{escape(insight.residual)} collects causes matching no "
                     "theme — a reporting gap, so it is pinned last and never ranked")
    return f"<figcaption>{'. '.join(notes)}.</figcaption>"


def table(df: pd.DataFrame, max_rows: int = 25) -> str:
    """A compact rendering of the frame behind a chart."""
    if df is None or df.empty:
        return ""
    shown = df.head(max_rows)
    numeric = {c: pd.api.types.is_numeric_dtype(shown[c]) for c in shown.columns}

    head = "".join(
        f'<th class="num">{escape(_title(c))}</th>' if numeric[c]
        else f"<th>{escape(_title(c))}</th>" for c in shown.columns)
    body = []
    for _, row in shown.iterrows():
        cells = "".join(
            f'<td class="num">{escape(_cell(c, row[c]))}</td>' if numeric[c]
            else f"<td>{escape(_cell(c, row[c]))}</td>" for c in shown.columns)
        body.append(f"<tr>{cells}</tr>")

    more = (f'<p class="method">{len(df) - max_rows} further rows omitted.</p>'
            if len(df) > max_rows else "")
    return (f"<table><thead><tr>{head}</tr></thead>"
            f'<tbody>{"".join(body)}</tbody></table>{more}')


def details(summary_text: str, inner: str) -> str:
    if not inner:
        return ""
    return f"<details><summary>{escape(summary_text)}</summary>{inner}</details>"


def _title(column) -> str:
    return str(column).replace("_", " ").strip().title()


def _cell(column, value) -> str:
    name = str(column).lower()
    if isinstance(value, float):
        if "pct" in name or "rate" in name:
            return f"{value:.0%}"
        return f"{value:,.2f}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return "" if pd.isna(value) else str(value)
