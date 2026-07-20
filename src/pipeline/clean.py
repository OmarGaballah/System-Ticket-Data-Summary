"""Block A2 — clean: filter to kept categories, realign via the NZ anchor, and
produce a lean DataFrame plus a 'what got removed' report.

The free-text block drifts by one column in ~half the rows, but NETWORK_LEVEL is
the constant "NZ" in every row. Locating "NZ" lets us read the fields that matter
by fixed offset — team (NZ-4), action (NZ-3), reference/escalation (NZ-2),
outcome (NZ-1), cause (NZ+1), resolver (NZ+2) — reliably regardless of the shift.
The purely descriptive columns between the category and the team field are
bundled into one `details` string for the LLM narrative, so a shift inside that
block only reorders the bundle and never mislabels a field.

If a row has no single unambiguous "NZ", we fall back to reading by the
aligned-layout column names.
"""

from __future__ import annotations

import pandas as pd

from src import consts
from src.structs import CleanReport


def _norm_outcome(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return consts.OUTCOME_UNKNOWN
    v = str(value).strip()
    if v.upper() == "OK":
        return consts.OUTCOME_OK
    if v.lower() == "error":
        return consts.OUTCOME_ERROR
    return consts.OUTCOME_UNKNOWN


def _bundle(values) -> str:
    """Join non-empty values into one ' | '-separated details string."""
    parts = [str(v).strip() for v in values if pd.notna(v) and str(v).strip()]
    return " | ".join(parts)


def _nn(value):
    """NaN/blank -> None, otherwise the stripped string."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s or None


def _at(values: list, pos: int):
    """Positional read that never IndexErrors (out of range -> None)."""
    return values[pos] if 0 <= pos < len(values) else None


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleanReport]:
    cols = list(raw.columns)
    cat_pos = cols.index(consts.CATEGORY_COL)
    aligned_anchor_pos = cols.index(consts.ANCHOR_COL)

    rows_before = len(raw)
    kept_mask = raw[consts.CATEGORY_COL].isin(consts.KEEP_CATEGORIES)
    dropped_by_category = (
        raw.loc[~kept_mask, consts.CATEGORY_COL].value_counts().to_dict()
    )
    df = raw.loc[kept_mask].reset_index(drop=True)

    records: list[dict] = []
    shifted = 0

    for _, row in df.iterrows():
        values = list(row.values)

        
        anchor_pos = next(
            (i for i in range(cat_pos + 1, len(values))
             if str(values[i]).strip() == consts.ANCHOR_VALUE),
            None,
        )

        off = consts.ANCHOR_OFFSETS
        if anchor_pos is not None and cat_pos + 1 <= anchor_pos - 1:
            if anchor_pos != aligned_anchor_pos:
                shifted += 1
            outcome_raw = _at(values, anchor_pos + off["outcome"])
            cause = _at(values, anchor_pos + off["cause"])
            team = _at(values, anchor_pos + off["team"])
            action = _at(values, anchor_pos + off["action"])
            reference = _at(values, anchor_pos + off["reference"])
            resolver = _at(values, anchor_pos + off["resolver"])
            details = _bundle(values[cat_pos + 1: max(cat_pos + 1, anchor_pos + off["team"])])
        else:
            outcome_raw = row.get(consts.OUTCOME_SRC_COL)
            cause = row.get(consts.CAUSE_SRC_COL)
            team = row.get(consts.TEAM_SRC_COL)
            action = row.get(consts.ACTION_SRC_COL)
            reference = row.get(consts.REFERENCE_SRC_COL)
            resolver = row.get(consts.RESOLVER_SRC_COL)
            details = _bundle([row.get(c) for c in consts.DETAILS_COLS])

        records.append({
            consts.OUT_ORDER: row[consts.TICKET_COL],
            consts.OUT_ACCEPT: row[consts.ACCEPTANCE_COL],
            consts.OUT_COMPLETE: row[consts.COMPLETION_COL],
            consts.OUT_CUSTOMER: row[consts.CUSTOMER_COL],
            consts.OUT_ORDER_TYPE: consts.ORDER_TYPE_NORMALIZE.get(
                row[consts.ORDER_TYPE_COL], row[consts.ORDER_TYPE_COL]
            ),
            consts.OUT_STATUS: consts.STATUS_NORMALIZE.get(
                row[consts.STATUS_COL], row[consts.STATUS_COL]
            ),
            consts.OUT_CATEGORY: row[consts.CATEGORY_COL],
            consts.OUT_OUTCOME: _norm_outcome(outcome_raw),
            consts.OUT_CAUSE: _nn(cause),
            consts.OUT_ACTION: _nn(action),
            consts.OUT_REFERENCE: _nn(reference),
            consts.OUT_RESOLVER: _nn(resolver),
            consts.OUT_TEAM: _nn(team),
            consts.OUT_DETAILS: details,
        })

    out = pd.DataFrame.from_records(records, columns=consts.CLEAN_COLUMNS)
    report = CleanReport(
        rows_before=rows_before,
        rows_after=len(out),
        dropped_by_category={str(k): int(v) for k, v in dropped_by_category.items()},
        columns_before=len(cols),
        columns_after=out.shape[1],
        shifted_rows=shifted,
    )
    return out, report
