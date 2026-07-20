"""Block D — deterministic analytics. Pure pandas, no Streamlit.

Each insight is a business QUESTION -> a METRIC computed from the data -> a
data-derived "so what" RECOMMENDATION. Nothing is hardcoded to this file: the
takeaways re-derive from whatever is dropped in (top cause, worst product,
repeat rate), and every metric has a graceful readout when a dimension has no
signal. General over the cleaned schema, not over arbitrary CSVs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from src import consts, taxonomy
from src.engine import episodes


@dataclass
class Insight:
    """One computed insight: numbers to chart + a recommendation sentence."""
    key: str
    title: str
    question: str
    takeaway: str          
    data: pd.DataFrame     
    has_signal: bool = True
    chart: str = "bar"      
    x: str = ""             
    y: str = ""             
    highlight: str = ""     
    unit: str = "count"     
    residual: str = ""      
    numerator: str = ""     
    denominator: str = ""   

    def plot_frame(self, max_bars: int = 10) -> pd.DataFrame:
        """The rows to draw, in display order — shared by every renderer.

        Ranked by magnitude, capped at ``max_bars``, with a residual bucket
        pushed to the bottom. Living on the Insight (rather than in one chart
        module) is what keeps the on-screen chart and the exported report from
        ever disagreeing about what the top category is.
        """
        columns = [c for c in (self.x, self.y, self.numerator, self.denominator) if c]
        d = self.data[list(dict.fromkeys(columns))].copy()
        d[self.x] = d[self.x].astype(str)
        d = d.sort_values(self.y, ascending=False, kind="stable").head(max_bars)
        if self.residual:
            d = (d.assign(_res=d[self.x].eq(self.residual))
                  .sort_values("_res", kind="stable").drop(columns="_res"))
        return d.reset_index(drop=True)

    def support(self, row) -> str:
        """The denominator behind one bar, e.g. ``"5/14"`` — "" when there is
        none. A rate without its denominator invites the reader to treat 36%
        (5 of 14) and 33% (1 of 3) as comparable measurements. They aren't."""
        if not (self.numerator and self.denominator):
            return ""
        return f"{int(row[self.numerator]):,}/{int(row[self.denominator]):,}"

    def axis(self, frame: pd.DataFrame | None = None) -> tuple[float, list[float]]:
        """``(axis_max, tick_values)`` for the value axis.

        A **rate always spans a full 0–100%**, never the data's own maximum.
        Scaling a rate to its max is the single most misleading thing a bar
        chart can do: it renders 36% as a full-width bar and 33% at 92%, so a
        three-point gap — well inside the noise at these denominators — looks
        decisive. Counts and durations have no such natural ceiling, so they
        scale to a rounded-up maximum. The two are never mixed on one chart.
        """
        if self.unit == "pct":
            return 1.0, [0.0, 0.25, 0.5, 0.75, 1.0]
        frame = self.plot_frame() if frame is None else frame
        peak = float(frame[self.y].max()) if len(frame) else 0.0

        step = _nice_step(peak / 4 if peak > 0 else 1.0,
                          integral=(self.unit == "count"))
        top = step * max(1, math.ceil(peak / step)) if peak > 0 else step
        return top, [step * i for i in range(int(round(top / step)) + 1)]

    def format_value(self, value: float) -> str:
        """Render one measure the way its unit demands."""
        if self.unit == "pct":
            return f"{value:.0%}"
        if self.unit == "hours":
            return f"{value:.2f}h"
        return f"{value:,.0f}"


def _nice_step(rough: float, integral: bool = False) -> float:
    """Round a rough interval up to a human one (1, 2, 2.5, 5 x 10^n).

    ``integral`` restricts the result to whole numbers, for axes counting
    things — you cannot have 2.5 tickets, and rendering that step under a
    count format would print gridlines labelled 0, 2, 5, 8.
    """
    if rough <= 0:
        return 1.0 if integral else 0.25
    magnitude = 10 ** math.floor(math.log10(rough))
    for multiple in (1, 2, 2.5, 5, 10):
        step = multiple * magnitude
        if integral and step != int(step):
            continue
        if rough <= step:
            return max(1.0, step) if integral else step
    return 10 * magnitude



ESCALATION_KEYWORDS: list[str] = [
    "replace", "austausch", "technician", "techniker", "forwarded",
    "weitergeleit", "appointment", "termin", "ordered", "bestellt",
    "commissioned", "beauftragt", "on site", "vor ort", "bi order", "technik",
]


def _hours(df: pd.DataFrame) -> pd.Series:
    acc = pd.to_datetime(df[consts.OUT_ACCEPT], errors="coerce")
    comp = pd.to_datetime(df[consts.OUT_COMPLETE], errors="coerce")
    return (comp - acc).dt.total_seconds() / 3600.0


def contact_occasions(df: pd.DataFrame) -> pd.DataFrame:
    """One row per customer x product: tickets raised, and *occasions* raised on.

    A contact occasion is an episode — the same clustering the storytelling
    engine cuts chapters on (``engine/episodes.py``, ``EPISODE_GAP_HOURS``),
    imported rather than reimplemented so the analysis and the stories can never
    disagree about what counts as "coming back".

    The distinction matters to the metric's own headline. Customer 456 raised
    two Hardware tickets two hours apart on 11-08; counting those as a repeat
    contact says the customer had to come back when they never left. Tickets
    raised together are one occasion; only a return after a real gap is a repeat.
    """
    rows = []
    for (customer, product), sub in df.groupby([consts.OUT_CUSTOMER,
                                                consts.OUT_PRODUCT]):
        rows.append({
            consts.OUT_CUSTOMER: customer,
            consts.OUT_PRODUCT: product,
            "occasions": len(episodes.compute(sub)),
            "tickets": len(sub),
        })
    return pd.DataFrame(rows, columns=[consts.OUT_CUSTOMER, consts.OUT_PRODUCT,
                                       "occasions", "tickets"])


def _repeat_rate(df: pd.DataFrame) -> tuple[int, int, float]:
    """``(repeat occasions, total occasions, rate)`` — one unit throughout.

    The rate is repeat occasions over *occasions*, not over tickets: mixing the
    two would answer "how often did a customer come back" with a denominator
    counting things that are not comings-back.
    """
    pairs = contact_occasions(df)
    total = int(pairs["occasions"].sum())
    repeats = int((pairs["occasions"] - 1).clip(lower=0).sum())
    return repeats, total, (repeats / total if total else 0.0)


def _is_escalated(row) -> bool:
    txt = " ".join(str(row.get(col) or "") for col in
                   (consts.OUT_ACTION, consts.OUT_REFERENCE, consts.OUT_RESOLVER)).lower()
    return any(k in txt for k in ESCALATION_KEYWORDS)



def repeat_contacts(df: pd.DataFrame) -> Insight:
    """#1 — Are we fixing issues on the first contact?

    Measured in contact *occasions*, not tickets: see :func:`contact_occasions`.
    The ticket count travels beside every bar so the two are never confused —
    "4/5" reads as four occasions across five tickets.
    """
    data = contact_occasions(df).sort_values(
        ["occasions", "tickets"], ascending=False, kind="stable")

    data["pair"] = [f"{c} · {p}" for c, p in
                    zip(data[consts.OUT_CUSTOMER], data[consts.OUT_PRODUCT])]
    
    repeated = data[data["occasions"] > 1]
    repeats, occasions, rate = _repeat_rate(df)
    has_signal = repeats > 0

    if has_signal:
        top = data.iloc[0]
        ladder_df = df[(df[consts.OUT_CUSTOMER] == top[consts.OUT_CUSTOMER])
                       & (df[consts.OUT_PRODUCT] == top[consts.OUT_PRODUCT])
                       ].sort_values(consts.OUT_ACCEPT)
        ladder = [step for step in
                  (taxonomy.redact_internal(a) for a in ladder_df[consts.OUT_ACTION])
                  if step]
        acc = pd.to_datetime(ladder_df[consts.OUT_ACCEPT])
        span = int((acc.max() - acc.min()).days)
        n, n_tickets = int(top["occasions"]), int(top["tickets"])
        raised = ("" if n == n_tickets
                  else f" (from {n_tickets} tickets, some raised together)")
        takeaway = (
            f"{rate:.0%} of contact occasions are repeats — {repeats} of "
            f"{occasions} times a customer came back about the same product. "
            f"Worst: customer {top[consts.OUT_CUSTOMER]}'s {top[consts.OUT_PRODUCT]} "
            f"came back {n} times over {span} days{raised} ("
            + " → ".join(ladder) +
            f") — the first {n - 1} were escalating attempts before the final fix. "
            f"Earlier escalation criteria would have deflected them."
        )
    else:
        takeaway = ("Every contact is a first-and-only one for its product — "
                    "no repeat-contact / first-time-fix problem in this data.")

    return Insight("repeat_contacts", "First-time-fix / repeat contacts",
                   "Are we fixing issues on the first contact?", takeaway,
                   repeated[["pair", "occasions", "tickets"]], has_signal, "bar",
                   "pair", "occasions",
                   highlight=(str(repeated.iloc[0]["pair"]) if has_signal else ""),
                   unit="count", numerator="occasions", denominator="tickets")


def root_cause_pareto(df: pd.DataFrame) -> Insight:
    """#4 — What should we fix upstream? (deflection)"""
    themes = df[consts.OUT_CAUSE].map(taxonomy.theme)
    counts = themes.value_counts().reset_index()
    counts.columns = ["theme", "tickets"]
    counts["pct"] = counts["tickets"] / counts["tickets"].sum()

   
    counts["_residual"] = counts["theme"] == taxonomy.RESIDUAL_THEME
    counts = (counts.sort_values(["_residual", "tickets"],
                                 ascending=[True, False], kind="stable")
                    .drop(columns="_residual").reset_index(drop=True))
    counts["cum_pct"] = counts["pct"].cumsum()

    named = counts[counts["theme"] != taxonomy.RESIDUAL_THEME]
    other_pct = float(counts.loc[counts["theme"] == taxonomy.RESIDUAL_THEME, "pct"].sum())
    has_signal = len(named) > 0 and float(named["pct"].iloc[0]) >= 0.15

    if has_signal:
        top = named.iloc[0]
        takeaway = (
            f"The top root-cause theme, {top['theme']}, drives {top['pct']:.0%} of "
            f"all tickets. Fixing it upstream — once — instead of answering each "
            f"ticket is the single biggest deflection opportunity."
        )
        if other_pct >= 0.15:
            takeaway += (
                f" Separately, {other_pct:.0%} of tickets carry opaque cause codes "
                f"that map to no theme — a taxonomy gap to close before trusting "
                f"any root-cause reporting."
            )
    else:
        takeaway = ("Root causes are evenly spread — no single upstream fix "
                    "dominates, so prioritise by cost per cause instead.")

    return Insight("root_cause", "Root-cause concentration (Pareto)",
                   "What should we fix upstream?", takeaway,
                   counts, has_signal, "pareto", "theme", "tickets",
                   highlight=(str(named.iloc[0]["theme"]) if has_signal else ""),
                   unit="count", residual=taxonomy.RESIDUAL_THEME)


def escalation_by_product(df: pd.DataFrame) -> Insight:
    """#2 — Where does the support process actually fail/escalate?"""
    d = df.copy()
    d["_esc"] = d.apply(_is_escalated, axis=1)
    grp = (d.groupby(consts.OUT_PRODUCT)
             .agg(tickets=(consts.OUT_ORDER, "size"), escalated=("_esc", "sum")))
    grp["escalation_rate"] = grp["escalated"] / grp["tickets"]
    grp = grp.sort_values("escalation_rate", ascending=False).reset_index()
    has_signal = int(d["_esc"].sum()) > 0

    if has_signal:
        
        by_volume = grp.sort_values("escalated", ascending=False, kind="stable")
        biggest = by_volume.iloc[0]
        total = int(grp["escalated"].sum())
        n = int(biggest["escalated"])
        rest = total - n
        takeaway = (
            f"{biggest[consts.OUT_PRODUCT]} produces the most escalations in "
            f"absolute terms — {n} of {total}, "
            + ("more than every other product combined" if n > rest
               else f"against {rest} across all other products") +
            ". These are tickets that needed a technician, a replacement, or a "
            "follow-up order rather than a first-line fix."
        )
        spread = float(grp["escalation_rate"].max() - grp["escalation_rate"].min())
        smallest = int(grp["tickets"].min())
        if smallest < 10 or spread < 0.10:
            takeaway += (
                f" Treat the *rate* ranking as directional only: the smallest "
                f"product here has {smallest} tickets, so one ticket moves it "
                f"several points."
            )
    else:
        unknown = int((df[consts.OUT_OUTCOME] == consts.OUTCOME_UNKNOWN).sum())
        takeaway = (
            f"No escalations or failures recorded. {unknown} tickets have no outcome "
            f"logged — a data-completeness gap to close before trusting success rates."
        )

    return Insight("escalation", "Escalation rate by product",
                   "Where does the support process actually fail?", takeaway,
                   grp, has_signal, "bar", consts.OUT_PRODUCT, "escalation_rate",
                   highlight=(str(grp.sort_values("escalated", ascending=False,
                                                  kind="stable")
                                     .iloc[0][consts.OUT_PRODUCT])
                              if has_signal else ""),
                   unit="pct", numerator="escalated", denominator="tickets")


def resolution_time(df: pd.DataFrame) -> Insight:
    """#3 — Where are we slow? (presented with restraint at this sample size)"""
    d = df.copy()
    d["_h"] = _hours(d)
    by_prod = (d.groupby(consts.OUT_PRODUCT)["_h"].median()
                 .sort_values(ascending=False)
                 .reset_index(name="median_hours"))
    med = float(d["_h"].median())
    has_signal = len(by_prod) > 1

    if has_signal:
        slow = by_prod.iloc[0]
        takeaway = (
            f"Median resolution is ~{med:.2f}h. In this sample {slow[consts.OUT_PRODUCT]} "
            f"is nominally slowest ({slow['median_hours']:.2f}h) — but with only "
            f"{len(d)} rows this is a *demonstration* of what the metric surfaces at "
            f"scale (slowest product × ticket type), not a conclusion to act on."
        )
    else:
        takeaway = f"Median resolution ~{med:.2f}h; not enough segments to compare here."

    return Insight("resolution_time", "Resolution time by product",
                   "Where are we slow?", takeaway, by_prod, has_signal,
                   "bar", consts.OUT_PRODUCT, "median_hours", highlight="", unit="hours")


def handoffs(df: pd.DataFrame) -> Insight:
    """#5 — How much work bounces between teams?"""
    per_team = df[consts.OUT_TEAM].value_counts().reset_index()
    per_team.columns = ["team", "tickets"]
    teams_per_cust = df.groupby(consts.OUT_CUSTOMER)[consts.OUT_TEAM].nunique()
    multi = int((teams_per_cust > 1).sum())
    total_cust = int(teams_per_cust.shape[0])
    spawned = int(df[consts.OUT_REFERENCE].fillna("").astype(str)
                    .str.contains("order|weitergeleit|technik|BI ", case=False, regex=True).sum())
    has_signal = multi > 0 or len(per_team) > 1

    if has_signal and len(per_team):
        share = per_team.iloc[0]["tickets"] / per_team["tickets"].sum()
        spawn_note = ""
        if spawned:
            noun = "ticket" if spawned == 1 else "tickets"
            spawn_note = f"; {spawned} {noun} spawned a follow-up order"
        takeaway = (
            f"{multi}/{total_cust} customers had tickets handled by ≥2 teams"
            f"{spawn_note} — each handoff is a point where context has to be "
            f"rebuilt. Team {per_team.iloc[0]['team']} handles {share:.0%} of the "
            f"volume; check whether that reflects specialisation before reading "
            f"it as an imbalance."
        )
    else:
        takeaway = "Tickets stay within a single team — no handoff overhead detected."

    return Insight("handoffs", "Team load & handoffs",
                   "How much work bounces between teams?", takeaway,
                   per_team, has_signal, "bar", "team", "tickets",
                   highlight=(str(per_team.iloc[0]["team"])
                              if has_signal and len(per_team) else ""),
                   unit="count")


def episode_timeline(df: pd.DataFrame) -> Insight:
    """#6 — When did the contacts actually happen?

    The only non-categorical view in the report, and the only one that shows
    *shape*: three episodes bunched over 5-7 Nov, a six-day silence, then a
    device failure on the 13th. Every other chart can tell you customer 123's
    Hardware took four contacts; only this one shows that they escalated and
    then stopped.

    Deliberately not a volume-over-time series. Thirty-two tickets across two
    weeks cannot support a trend line — a weekly bucket here would be three
    points, and drawing a slope through them would invent a direction the data
    does not contain. Episodes are events with real dates, so plotting them as
    events claims nothing beyond what was recorded.
    """
    rows = []
    for (customer, product), sub in df.groupby([consts.OUT_CUSTOMER,
                                                consts.OUT_PRODUCT]):
        for episode in episodes.compute(sub):
            rows.append({
                "pair": f"{customer} · {product}",
                "date": episode.start,
                "tickets": len(episode.ticket_numbers),
                "episode": episode.index,
            })
    data = pd.DataFrame(rows, columns=["pair", "date", "tickets", "episode"])
    data = data.dropna(subset=["date"])
    has_signal = not data.empty

    order = (data.groupby("pair")
                 .agg(episodes=("episode", "count"), tickets=("tickets", "sum"))
                 .sort_values(["episodes", "tickets"], ascending=False)
             if has_signal else pd.DataFrame(columns=["episodes", "tickets"]))
    highlight = str(order.index[0]) if len(order) else ""

    if has_signal:
        top = order.iloc[0]
        span = (data["date"].max() - data["date"].min()).days + 1
        takeaway = (
            f"Contacts arrive in bursts, not a steady stream: {len(data)} contact "
            f"occasions across {span} days, and the busiest arc — {highlight} — "
            f"is {int(top['episodes'])} occasions covering {int(top['tickets'])} "
            f"tickets. Reading left to right shows repeat contacts clustering "
            f"first and thinning after, which is what a fix that finally held "
            f"looks like. Staffing should follow the clusters, not the average."
        )
    else:
        takeaway = "No dated tickets, so there is no timeline to draw."

    return Insight("episode_timeline", "Contact timeline",
                   "When did the contacts actually happen?", takeaway,
                   data.sort_values(["pair", "date"]), has_signal, "timeline",
                   "date", "pair", highlight=highlight, unit="date")


def headline_kpis(df: pd.DataFrame) -> dict:
    """A few top-line numbers for the KPI row (all derived from the data)."""
    total = len(df)
    repeats, occasions, repeat_rate = _repeat_rate(df)
    escalated = int(df.apply(_is_escalated, axis=1).sum()) if total else 0
    named = df[consts.OUT_CAUSE].map(taxonomy.theme)
    named = named[named != taxonomy.RESIDUAL_THEME].value_counts()
    return {
        "tickets": total,
        "customers": int(df[consts.OUT_CUSTOMER].nunique()),
        "repeat_rate": repeat_rate,
        "repeat_occasions": repeats,
        "contact_occasions": occasions,
        "escalation_rate": escalated / total if total else 0.0,
        "top_theme": str(named.index[0]) if len(named) else "—",
        "top_theme_pct": float(named.iloc[0] / total) if len(named) and total else 0.0,
    }


def compute_all(df: pd.DataFrame) -> list[Insight]:
    """Every insight, ordered strongest-story first.

    The timeline goes last on purpose: it is the only chart that needs the
    others' vocabulary (episodes, repeat contacts) to be read properly, so it
    closes the report rather than opening it.
    """
    return [
        repeat_contacts(df),
        root_cause_pareto(df),
        escalation_by_product(df),
        resolution_time(df),
        handoffs(df),
        episode_timeline(df),
    ]
