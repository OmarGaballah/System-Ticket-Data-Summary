"""Traceability view — the audit mapping from a chapter to its source rows."""

from src import consts
from src.ui.story_view import AUDIT_COLUMNS, source_rows


def _slice(clean_df):
    cust = clean_df[consts.OUT_CUSTOMER].iloc[0]
    df = clean_df[clean_df[consts.OUT_CUSTOMER] == cust]
    product = df[consts.OUT_PRODUCT].iloc[0]
    return df[df[consts.OUT_PRODUCT] == product]


def test_source_rows_returns_requested_tickets_in_order(clean_df):
    subset = _slice(clean_df)
    wanted = [str(t) for t in subset[consts.OUT_ORDER].astype(str)][:3]
    wanted.reverse()                      
    rows = source_rows(subset, wanted)
    assert [str(t) for t in rows[consts.OUT_ORDER]] == wanted


def test_source_rows_ignores_unknown_tickets(clean_df):
    subset = _slice(clean_df)
    real = str(subset[consts.OUT_ORDER].astype(str).iloc[0])
    rows = source_rows(subset, [real, "999-9999999/99"])
    assert [str(t) for t in rows[consts.OUT_ORDER]] == [real]


def test_source_rows_empty_selection(clean_df):
    assert source_rows(_slice(clean_df), []).empty


def test_audit_columns_exist_in_the_cleaned_frame(clean_df):
    assert set(AUDIT_COLUMNS) <= set(clean_df.columns)
