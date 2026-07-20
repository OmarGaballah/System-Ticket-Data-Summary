"""Block A3 — mapping tests."""

from src import consts
from src.pipeline.clean import clean
from src.pipeline.ingest import parse_bytes
from src.pipeline.mapping import add_product


def _mapped(sample_bytes):
    out, _ = clean(parse_bytes(sample_bytes))
    return add_product(out)


def test_every_row_has_a_product(sample_bytes):
    df = _mapped(sample_bytes)
    assert df[consts.OUT_PRODUCT].notna().all()


def test_six_products(sample_bytes):
    df = _mapped(sample_bytes)
    assert set(df[consts.OUT_PRODUCT].unique()) == set(consts.PRODUCTS)
    assert len(consts.PRODUCTS) == 6


def test_category_maps_to_expected_product(sample_bytes):
    df = _mapped(sample_bytes)
    broadband = df[df[consts.OUT_PRODUCT] == "Broadband"][consts.OUT_CATEGORY]
    assert set(broadband.unique()) == {"KAI", "NET"}
    hardware = df[df[consts.OUT_PRODUCT] == "Hardware"][consts.OUT_CATEGORY]
    assert set(hardware.unique()) == {"HDW"}
