"""Home page — upload, clean, and stage the data for every other page.

The uploader lives here (a global precondition), and the cleaned DataFrame is
written to ``session_state`` so the Story and Insights pages become pure
consumers via ``state.require_data()``. The pipeline is wrapped in
``@st.cache_data`` keyed on the file *bytes*, so re-parsing happens only when a
genuinely new file is uploaded — dropdown clicks and page switches are free.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src import consts, state
from src.pipeline.ingest import IngestError, run_pipeline
from src.ui import components

SAMPLE_FILE = Path(__file__).resolve().parent / "data" / "Ticket Data (2).txt"

st.set_page_config(page_title="System Ticket Data Summary", page_icon="🎫",
                   layout="wide")


@st.cache_data(show_spinner="Processing ticket file…")
def load_pipeline(file_bytes: bytes):
    """Cache-keyed on file content: ingest -> clean -> map."""
    return run_pipeline(file_bytes)


components.theme_hint()

st.title("🎫 System Ticket Data Summary")
st.caption("Upload a ticket export, then explore the five-phase story per "
           "product on the **Story Summary** page and trends on **Insights**.")

col_up, col_sample = st.columns([3, 1])
uploaded = col_up.file_uploader("Ticket data file (.txt / .csv)",
                                type=["txt", "csv"])
with col_sample:
    st.write("")
    st.write("")
    use_sample = st.button("Load bundled sample", width="stretch")

file_bytes, source_name = None, ""
if uploaded is not None:
    file_bytes, source_name = uploaded.getvalue(), uploaded.name
elif use_sample and SAMPLE_FILE.exists():
    file_bytes, source_name = SAMPLE_FILE.read_bytes(), SAMPLE_FILE.name

if file_bytes is not None:
    try:
        df, report = load_pipeline(file_bytes)
    except IngestError as exc:
        
        st.error(f"**{source_name or 'That file'}** could not be loaded. {exc}")
    else:
        state.set_clean_df(df, report, source_name)
        if report.rows_after == 0:
            st.warning(
                f"**{source_name}** was read successfully, but none of its "
                f"{report.rows_before} rows are in scope — every row belongs to "
                f"a category outside {', '.join(consts.KEEP_CATEGORIES)}. "
                "There is nothing to summarise.")

if not state.has_data():
    st.info("👆 Upload a ticket file or click **Load bundled sample** to begin.")
    st.stop()

df = state.get_clean_df()
report = state.get_report()
st.success(f"Loaded **{state.get_source_name()}** — "
           f"{report.rows_after} tickets across {df[consts.OUT_PRODUCT].nunique()} products.")

m1, m2, m3 = st.columns(3)
m1.metric("Tickets kept", report.rows_after)
m2.metric("Customers", df[consts.OUT_CUSTOMER].nunique())
m3.metric("Products", df[consts.OUT_PRODUCT].nunique())

components.removal_report(report)

st.subheader("Cleaned data preview")
st.dataframe(df, width="stretch", height=320)

components.download_buttons(df)
