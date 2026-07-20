"""Block A3 — map: add the PRODUCT column from the category code.

Pure spine operation (category is never shifted), so this is fully reliable.
After this, every kept ticket belongs to exactly one of the six products.
"""

from __future__ import annotations

import pandas as pd

from src import consts


def add_product(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with an ``OUT_PRODUCT`` column added."""
    out = df.copy()
    out[consts.OUT_PRODUCT] = out[consts.OUT_CATEGORY].map(consts.PRODUCT_MAP)
    return out


def ticket_categories(df: pd.DataFrame) -> dict[str, str]:
    """Ticket number -> its SERVICE_CATEGORY.

    The mapping collapses categories into products, which is the right unit for
    a story but loses information the reader needs: Broadband covers KAI *and*
    NET, two unrelated fault types. Carrying the category back out to the story
    lets the reader see that an arc spans two of them, so adjacency in a phase
    is never mistaken for causation.
    """
    return {str(number): str(category) for number, category
            in zip(df[consts.OUT_ORDER], df[consts.OUT_CATEGORY])}


def label_ticket(number: str, categories: dict[str, str] | None) -> str:
    """``"001-0670955/24 (NET)"`` — the number with its category, when known."""
    category = (categories or {}).get(str(number))
    return f"{number} ({category})" if category else str(number)
