"""End-to-end robustness: the whole path over inputs that are not the sample.

Every test here drives ingest -> clean -> map -> summarise -> render -> export
on a deliberately awkward file. The contract is not "it works" — several of
these files genuinely have nothing to say. The contract is that the user always
gets a clear message or an empty state, and never a traceback.

Three of these cases were real crashes before this module existed: a file whose
rows all filter out produced a column-less frame that KeyError'd on the first
groupby, an empty upload surfaced a raw ``EmptyDataError``, and the repeat-contact
chart died concatenating two empty string columns.
"""

import io

import pandas as pd
import pytest

from src import consts
from src.analysis import exec_summary, insights
from src.engine import fallback
from src.pipeline import mapping
from src.pipeline.ingest import IngestError, run_pipeline
from src.report import insights_report, story_report
from src.ui import story_view


@pytest.fixture(scope="module")
def raw_rows(sample_bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(sample_bytes), encoding="utf-8-sig", dtype=str,
                       keep_default_na=False, engine="python")


def _bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def _exercise(data: bytes) -> pd.DataFrame:
    """Everything the user can trigger, in the order the app triggers it."""
    df, report = run_pipeline(data)

    kpis = insights.headline_kpis(df)
    items = insights.compute_all(df)
    assert {i.key for i in items} == {"repeat_contacts", "root_cause", "escalation",
                                      "resolution_time", "handoffs",
                                      "episode_timeline"}
    assert all(i.takeaway.strip() for i in items)
    html = insights_report.build(kpis, items,
                                 exec_summary._deterministic(kpis, items, ""),
                                 "case.txt")
    assert html.rstrip().endswith("</html>")

    if len(df):
        customer = str(df[consts.OUT_CUSTOMER].iloc[0])
        cust_df = df[df[consts.OUT_CUSTOMER].astype(str) == customer]
        summaries = {
            p: fallback.deterministic_summary(
                p, cust_df[cust_df[consts.OUT_PRODUCT] == p]
                if len(cust_df[cust_df[consts.OUT_PRODUCT] == p]) else None)
            for p in consts.PRODUCTS
        }
        cats = mapping.ticket_categories(cust_df)
        for language in ("English", "German"):
            assert story_report.build(summaries, customer, language,
                                      cats).rstrip().endswith("</html>")
            story_view.to_markdown(summaries, customer, cats, language)
    return df



def test_different_customer_ids(raw_rows):
    renamed = raw_rows.copy()
    renamed[consts.CUSTOMER_COL] = renamed[consts.CUSTOMER_COL].map(
        {"123": "900001", "456": "900002", "789": "900003"})
    df = _exercise(_bytes(renamed))
    assert set(df[consts.OUT_CUSTOMER]) == {"900001", "900002", "900003"}


def test_a_product_missing_entirely(raw_rows):
    df = _exercise(_bytes(raw_rows[raw_rows[consts.CATEGORY_COL] != "HDW"]))
    assert "Hardware" not in set(df[consts.OUT_PRODUCT])
    assert len(df)


def test_one_customer_has_only_one_product(raw_rows):
    keep = ((raw_rows[consts.CUSTOMER_COL] != "123")
            | (raw_rows[consts.CATEGORY_COL] == "HDW"))
    df = _exercise(_bytes(raw_rows[keep]))
    products = set(df[df[consts.OUT_CUSTOMER] == "123"][consts.OUT_PRODUCT])
    assert products == {"Hardware"}          


def test_every_row_filtered_out(raw_rows):
    out_of_scope = raw_rows.copy()
    out_of_scope[consts.CATEGORY_COL] = "NTF"
    df = _exercise(_bytes(out_of_scope))
    assert len(df) == 0
    assert set(consts.CLEAN_COLUMNS) <= set(df.columns)
    assert consts.OUT_PRODUCT in df.columns


def test_headers_but_no_rows(sample_bytes):
    header = sample_bytes.decode("utf-8-sig").splitlines()[0]
    df = _exercise((header + "\n").encode("utf-8"))
    assert len(df) == 0


def test_no_signal_insights_still_render(raw_rows):
    out_of_scope = raw_rows.copy()
    out_of_scope[consts.CATEGORY_COL] = "NTF"
    empty, _ = run_pipeline(_bytes(out_of_scope))
    items = insights.compute_all(empty)
    assert not any(i.has_signal for i in items)   
    assert all(i.takeaway for i in items)         
    assert insights.headline_kpis(empty)["tickets"] == 0

def test_empty_upload_is_refused_with_a_sentence():
    with pytest.raises(IngestError, match="empty"):
        run_pipeline(b"")


def test_a_file_without_the_spine_columns_is_refused():
    with pytest.raises(IngestError, match="missing the column"):
        run_pipeline(b"a,b,c\n1,2,3\n")


def test_the_refusal_names_what_is_missing():
    with pytest.raises(IngestError) as err:
        run_pipeline(b"ORDER_NUMBER,CUSTOMER_NUMBER\n1,2\n")
    assert consts.CATEGORY_COL in str(err.value)

def _shift(values: list, columns: list) -> list:
    """Drop one column from the free-text block so NZ moves one place left."""
    cat = columns.index(consts.CATEGORY_COL)
    anchor = values.index("NZ")
    shifted = values[:cat + 1] + values[cat + 2:anchor + 1] + [""] + values[anchor + 1:]
    return shifted[:len(columns)]


def test_no_rows_shifted(raw_rows):
    cols = list(raw_rows.columns)
    aligned = cols.index(consts.ANCHOR_COL)
    rows = [v for v in raw_rows.values.tolist() if list(v).index("NZ") == aligned]
    df, report = run_pipeline(_bytes(pd.DataFrame(rows, columns=cols)))
    assert report.shifted_rows == 0
    assert (df[consts.OUT_OUTCOME] != "").all()
    _exercise(_bytes(pd.DataFrame(rows, columns=cols)))


def test_all_rows_shifted(raw_rows):
    cols = list(raw_rows.columns)
    aligned = cols.index(consts.ANCHOR_COL)
    rows = []
    for values in raw_rows.values.tolist():
        values = list(values)
        rows.append(_shift(values, cols) if values.index("NZ") == aligned else values)
    data = _bytes(pd.DataFrame(rows, columns=cols))
    df, report = run_pipeline(data)
    assert report.shifted_rows == len(df)        
    assert set(df[consts.OUT_OUTCOME]) <= {consts.OUTCOME_OK, consts.OUTCOME_ERROR,
                                           consts.OUTCOME_UNKNOWN}
    assert df[consts.OUT_CAUSE].notna().any()    
    _exercise(data)
