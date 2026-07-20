"""Block A2 — clean tests. Locks in the NZ-anchor realignment."""

from src import consts
from src.pipeline.clean import clean
from src.pipeline.ingest import parse_bytes


def _clean(sample_bytes):
    return clean(parse_bytes(sample_bytes))


def test_drops_unkept_categories(sample_bytes):
    out, report = _clean(sample_bytes)
    assert report.rows_before == 42
    assert report.rows_after == 32
    assert report.dropped_by_category == {"SOP": 6, "NTF": 4}
    assert set(out[consts.OUT_CATEGORY].unique()) <= set(consts.KEEP_CATEGORIES)


def test_realignment_detects_shifted_rows(sample_bytes):
    _, report = _clean(sample_bytes)
    assert report.shifted_rows == 19


def test_aligned_row_outcome_and_cause(sample_bytes):
    out, _ = _clean(sample_bytes)
    row = out[out[consts.OUT_ORDER] == "001-0671177/24"].iloc[0]
    assert row[consts.OUT_OUTCOME] == consts.OUTCOME_OK
    assert row[consts.OUT_CAUSE] == "URS_KIP_Reset_WLAN_Settings"
    assert row[consts.OUT_ACTION] == "WLAN settings optimized"
    assert row[consts.OUT_TEAM] == "TSCW2"


def test_shifted_row_reads_correct_fields(sample_bytes):
    out, _ = _clean(sample_bytes)
    row = out[out[consts.OUT_ORDER] == "001-0682299/24"].iloc[0]
    assert row[consts.OUT_OUTCOME] == consts.OUTCOME_OK
    assert row[consts.OUT_CAUSE] == "CM_BERA_KD_Bandbreite"
    assert row[consts.OUT_TEAM] == "TSCKT"
    assert row[consts.OUT_ACTION].startswith("Bandbreite")
    assert "Downloadgeschwindigkeit gering" in row[consts.OUT_DETAILS]


def test_extracted_fields_are_columns_not_in_details(sample_bytes):
    out, _ = _clean(sample_bytes)
    for col in (consts.OUT_TEAM, consts.OUT_ACTION, consts.OUT_REFERENCE,
                consts.OUT_RESOLVER):
        assert col in out.columns
    row = out[out[consts.OUT_ORDER] == "001-0671177/24"].iloc[0]
    assert "WLAN settings optimized" not in row[consts.OUT_DETAILS]
    assert "TSCW2" not in row[consts.OUT_DETAILS]


def test_outcome_domain(sample_bytes):
    out, _ = _clean(sample_bytes)
    allowed = {consts.OUTCOME_OK, consts.OUTCOME_ERROR, consts.OUTCOME_UNKNOWN}
    assert set(out[consts.OUT_OUTCOME].unique()) <= allowed


def test_status_normalized(sample_bytes):
    out, _ = _clean(sample_bytes)
    assert "ab" not in set(out[consts.OUT_STATUS].unique())


def test_order_type_normalized(sample_bytes):
    out, _ = _clean(sample_bytes)
    types = set(out[consts.OUT_ORDER_TYPE].unique())
    assert "Kurzticket" not in types and "Aufgabe" not in types
    assert "Short Ticket" in types


def test_task_rows_never_report_a_queue_code_as_an_outcome(sample_bytes):
    out, _ = _clean(sample_bytes)
    outcomes = out[consts.OUT_OUTCOME].astype(str)
    assert not outcomes.str.contains("TSC", case=False).any()
    task_rows = out[out[consts.OUT_ORDER_TYPE].isin(["Task", "Aufgabe"])]
    assert len(task_rows)                       # the fixture still has some
    assert (task_rows[consts.OUT_OUTCOME] == consts.OUTCOME_UNKNOWN).all()
