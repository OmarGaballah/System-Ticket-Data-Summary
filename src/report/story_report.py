"""The Story Summary report — one customer's product stories as standalone HTML.

Reads the same ``dict[str, ProductSummary]`` the screen renders and the Markdown
export serializes, so all three views tell the same story. Two things this format
keeps that a plain Markdown dump loses: the **provenance** of every product
(which provider narrated it, and what the facts layer had to correct) and the
**code-derived** timeframes and ticket numbers printed under each chapter — so
the narrative stays auditable once it leaves the app.
"""

from __future__ import annotations

from datetime import datetime

from src import consts
from src.pipeline.mapping import label_ticket
from src.report import layout
from src.structs import ProductSummary


def build(summaries: dict[str, ProductSummary], customer: str, language: str,
          categories: dict[str, str] | None = None,
          generated_at: datetime | None = None) -> str:
    """Render one customer's stories to a standalone HTML document.

    ``categories`` maps ticket number -> SERVICE_CATEGORY (see
    ``pipeline.mapping.ticket_categories``). It is printed next to every ticket
    so a Broadband story visibly spans KAI and NET rather than reading as one
    continuous fault.
    """
    when = (generated_at or datetime.now()).strftime("%d %b %Y, %H:%M")
    active = [p for p in consts.PRODUCTS if _has_content(summaries.get(p))]
    silent = [p for p in consts.PRODUCTS if p not in active]
    tickets = sum(_count(summaries.get(p)) for p in active)

    title = f"Story Summary — Customer {customer}"
    subtitle = (f"{tickets} ticket{'s' if tickets != 1 else ''} across "
                f"{len(active)} of {len(consts.PRODUCTS)} products · {language} · "
                f"generated {when}")

    parts = [_product(p, summaries[p], categories, language) for p in active]
    if not active:
        parts.append("<p>This customer has no tickets in any product.</p>")
    elif silent:
        parts.append(
            f'<p class="method">No activity recorded for: '
            f"{layout.escape(', '.join(silent))}. These products are reported as "
            f"silent rather than omitted, so the story covers the full portfolio.</p>")

    return layout.document(
        title, subtitle, "\n".join(parts),
        footer=f"System Ticket Data Summary · Customer {customer} · {language}")


def _product(product: str, summary: ProductSummary,
             categories: dict[str, str] | None = None,
             language: str | None = None) -> str:
    provenance = summary.provenance()
    head = (f"<h2>{layout.escape(product)}</h2>"
            + (f'<p class="prov">{layout.inline(provenance)}</p>' if provenance else "")
            + "<hr>")
    return (f'<section class="product">{head}'
            f'{_chapters(summary, categories, language)}</section>')


def _narrative(ps, language: str | None) -> str:
    """The no-activity sentinel shown in the report's language; see
    ``consts.no_activity_text``. Everything else is passed through untouched."""
    text = (ps.narrative or "").strip()
    return consts.no_activity_text(language) if text in ("", consts.NO_ACTIVITY) else text


def _chapters(summary: ProductSummary,
              categories: dict[str, str] | None = None,
              language: str | None = None) -> str:
    out = []
    for phase in consts.PHASES:
        ps = summary.phases.get(phase.id)
        if ps is None:
            continue
        when = f'<p class="when">{layout.escape(ps.timeframe)}</p>' if ps.timeframe else ""
        narrative = layout.inline(_narrative(ps, language))
        tickets = ""
        if ps.ticket_numbers:
            labelled = [label_ticket(t, categories) for t in ps.ticket_numbers]
            tickets = ('<p class="tickets">Tickets: '
                       + layout.escape("   ".join(labelled)) + "</p>")
        css = "chapter" if ps.ticket_numbers else "chapter quiet"
        out.append(f'<div class="{css}"><h3>{layout.escape(phase.title)}</h3>'
                   f"{when}<p>{narrative}</p>{tickets}</div>")
    return "".join(out)


def _has_content(summary: ProductSummary | None) -> bool:
    return summary is not None and summary.has_content()


def _count(summary: ProductSummary | None) -> int:
    return summary.ticket_count() if summary is not None else 0
