"""Render a customer's six product stories (five chapters each) — pure view.

Takes the ``dict[str, ProductSummary]`` the engine produces and lays it out:
one expander per product (active ones open, silent ones collapsed), five phase
chapters inside, plus a provenance line that shows which provider actually served
and any self-correction note. No engine or Streamlit-state logic lives here — the
page owns data + caching, this module owns pixels — so it stays trivially
reusable and the story can also be exported to Markdown from the same source.

Traceability: when the raw slice is passed in, each product also gets a "Source
tickets" tab pairing every chapter with exactly the rows it was built from, plus
the verbatim payload the model received. That makes the Tier 1/2 guarantees
*auditable in one click* — claim against source — rather than merely asserted.
(Streamlit forbids nested expanders, hence tabs inside the product expander.)
"""

from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd
import streamlit as st

from src import consts
from src.engine.summarizer import build_payload
from src.pipeline.mapping import label_ticket, ticket_categories
from src.structs import ProductSummary

AUDIT_COLUMNS: list[str] = [
    consts.OUT_ORDER, consts.OUT_ACCEPT, consts.OUT_COMPLETE,
    consts.OUT_OUTCOME, consts.OUT_CAUSE, consts.OUT_ACTION,
    consts.OUT_REFERENCE, consts.OUT_RESOLVER, consts.OUT_TEAM,
    consts.OUT_DETAILS,
]


def render_header(customer: str, active: list[str], total: int) -> None:
    """Customer heading + a one-line summary. Derivable from data alone, so the
    page can show it *before* any LLM call."""
    st.subheader(f"Customer {customer}")
    if active:
        st.caption(f"{total} tickets · active products: {', '.join(active)}")
    else:
        st.info("This customer has no tickets in any product.")


def render_product_section(product: str, summary: ProductSummary | None,
                           tickets_df: pd.DataFrame | None = None,
                           language: str | None = None) -> None:
    """One product's expander (active open, silent collapsed). Called per product
    so the page can stream results in as each finishes.

    ``tickets_df`` is the raw slice this story was built from; pass it to get the
    traceability tab.
    """
    has = _has_content(summary)
    count = _ticket_count(summary)
    icon = "📖" if has else "—"
    tail = f"{count} ticket{'s' if count != 1 else ''}" if has else "no activity"
    with st.expander(f"{icon}  {product}  ·  {tail}", expanded=has):
        _render_product(summary, tickets_df, language)


def _render_product(summary: ProductSummary | None,
                    tickets_df: pd.DataFrame | None = None,
                    language: str | None = None) -> None:
    if summary is None:
        st.write("_No data._")
        return

    _provenance(summary)

    if not _has_content(summary):
        st.write("_No tickets recorded for this product._")
        return

    if tickets_df is None or tickets_df.empty:
        _render_chapters(summary, language=language)
        return

    categories = ticket_categories(tickets_df)
    story_tab, source_tab = st.tabs(
        ["Story", f"🔍 Source tickets ({len(tickets_df)})"])
    with story_tab:
        _render_chapters(summary, categories, language)
    with source_tab:
        _render_traceability(summary, tickets_df)


def _narrative(ps, language: str | None, italic: bool = False) -> str:
    """A phase's prose as the reader should see it.

    The stored narrative is the model's (or the deterministic view's) text; the
    only substitution is the no-activity sentinel, which is a contract value in
    English and has to be shown in the report's language. See
    ``consts.no_activity_text`` — this is the one place that translation happens.
    """
    text = (ps.narrative or "").strip()
    if not text or text == consts.NO_ACTIVITY:
        text = consts.no_activity_text(language)
        return f"_{text}_" if italic else text
    return text


def _render_chapters(summary: ProductSummary,
                     categories: dict[str, str] | None = None,
                     language: str | None = None) -> None:
    for phase in consts.PHASES:
        ps = summary.phases.get(phase.id)
        if ps is None:
            continue
        st.markdown(f"#### {phase.title}")
        if ps.timeframe:
            st.caption(f"🗓 {ps.timeframe}")
        st.write(_narrative(ps, language, italic=True))
        if ps.ticket_numbers:

            chips = "  ".join(f"`{label_ticket(t, categories)}`"
                              for t in ps.ticket_numbers)
            st.markdown(f"<small>Tickets: {chips}</small>", unsafe_allow_html=True)


def _render_traceability(summary: ProductSummary, tickets_df: pd.DataFrame) -> None:
    """Each chapter against the exact rows behind it — claim vs. source."""
    st.caption(
        "Every chapter above, paired with the rows it was built from. Ticket "
        "numbers and timeframes are **code-derived** from these rows — the model "
        "only wrote the prose."
    )
    cols = [c for c in AUDIT_COLUMNS if c in tickets_df.columns]

    shown: set[str] = set()
    for phase in consts.PHASES:
        ps = summary.phases.get(phase.id)
        if ps is None or not ps.ticket_numbers:
            continue
        shown.update(ps.ticket_numbers)
        n = len(ps.ticket_numbers)
        head = f"**{phase.title}** · {n} ticket{'s' if n != 1 else ''}"
        if ps.timeframe:
            head += f" · 🗓 {ps.timeframe}"
        st.markdown(head)
        rows = source_rows(tickets_df, ps.ticket_numbers)
        st.dataframe(rows[cols] if cols else rows, hide_index=True, width="stretch")

    total = len(tickets_df)
    st.caption(
        f"**Coverage:** {len(shown)}/{total} tickets assigned to exactly one "
        "chapter — guaranteed by the facts layer, not by the model."
    )

    if st.checkbox("Show the exact payload sent to the model",
                   key=f"payload_{summary.product}"):
        st.caption("Verbatim — this is all the model ever saw about these tickets.")
        st.code(json.dumps(build_payload(tickets_df), indent=2, default=str),
                language="json")


def _provenance(summary: ProductSummary) -> None:
    """One caption naming who produced the story; notes elevated when they matter."""
    note = summary.note or ""
    lowered = note.lower()
    if any(k in lowered for k in ("incomplete", "unparseable", "removed", "flagged")):
        line = replace(summary, note="").provenance()
        if line:
            st.caption(line)
        st.warning(note)
    elif summary.provenance():
        st.caption(summary.provenance())

def to_markdown(summaries: dict[str, ProductSummary], customer: str,
                categories: dict[str, str] | None = None,
                language: str | None = None) -> str:
    """Render the whole story to Markdown for download."""
    out: list[str] = [f"# Story Summary — Customer {customer}\n"]
    for product in consts.PRODUCTS:
        summary = summaries.get(product)
        if not _has_content(summary):
            continue
        out.append(f"\n## {product}\n")
        if summary.provenance():
            out.append(f"_{summary.provenance()}_\n")
        for phase in consts.PHASES:
            ps = summary.phases.get(phase.id)
            if ps is None:
                continue
            out.append(f"\n### {phase.title}\n")
            if ps.timeframe:
                out.append(f"*{ps.timeframe}*\n")
            out.append(_narrative(ps, language) + "\n")
            if ps.ticket_numbers:
                labelled = [label_ticket(t, categories) for t in ps.ticket_numbers]
                out.append(f"\nTickets: {', '.join(labelled)}\n")
    return "\n".join(out)


def source_rows(tickets_df: pd.DataFrame, ticket_numbers: list[str]) -> pd.DataFrame:
    """The slice's rows for ``ticket_numbers``, in that exact order.

    Pure (no Streamlit) so the traceability mapping is unit-testable: what the
    audit view shows must be the real rows, in the phase's chronological order.
    """
    order = {str(t): i for i, t in enumerate(ticket_numbers)}
    keyed = tickets_df[tickets_df[consts.OUT_ORDER].astype(str).isin(order)].copy()
    keyed["_order"] = keyed[consts.OUT_ORDER].astype(str).map(order)
    return keyed.sort_values("_order").drop(columns="_order")


def _has_content(summary: ProductSummary | None) -> bool:
    return summary is not None and summary.has_content()


def _ticket_count(summary: ProductSummary | None) -> int:
    return summary.ticket_count() if summary is not None else 0
