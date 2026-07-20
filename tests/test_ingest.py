"""Block A1 — ingest tests."""

import pandas as pd

from src import consts
from src.pipeline.ingest import parse_bytes


def test_parses_full_shape(sample_bytes):
    df = parse_bytes(sample_bytes)
    assert df.shape == (42, 38)


def test_bom_stripped(sample_bytes):
    df = parse_bytes(sample_bytes)
    assert df.columns[0] == "ORDER_NUMBER"


def test_datetime_columns_parsed(sample_bytes):
    df = parse_bytes(sample_bytes)
    for col in consts.DATETIME_COLUMNS:
        assert pd.api.types.is_datetime64_any_dtype(df[col])
    first = df[consts.ACCEPTANCE_COL].iloc[0]
    assert (first.month, first.day) == (11, 5)


def test_na_tokens_become_missing(sample_bytes):
    df = parse_bytes(sample_bytes)
    assert df["ORDER_UNIT_ID"].isna().all()
