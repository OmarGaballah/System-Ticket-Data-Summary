"""Cross-page session state — the single set of keys both pages agree on.

The uploader lives on the Home page (``app.py``), not on a content page, so
page-visit order never matters. Pages are pure consumers: they call
``require_data()``, which stops the page with a friendly prompt if nothing has
been loaded yet. Using these helpers (instead of stringly-typed
``st.session_state["clean_df"]`` scattered around) keeps the keys defined once.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.structs import CleanReport

CLEAN_DF_KEY = "clean_df"
CLEAN_REPORT_KEY = "clean_report"
SOURCE_NAME_KEY = "source_name"


def set_clean_df(df: pd.DataFrame, report: CleanReport, source_name: str = "") -> None:
    """Store the cleaned DataFrame + removal report for every page to read."""
    st.session_state[CLEAN_DF_KEY] = df
    st.session_state[CLEAN_REPORT_KEY] = report
    st.session_state[SOURCE_NAME_KEY] = source_name


def get_clean_df() -> pd.DataFrame | None:
    return st.session_state.get(CLEAN_DF_KEY)


def get_report() -> CleanReport | None:
    return st.session_state.get(CLEAN_REPORT_KEY)


def get_source_name() -> str:
    return st.session_state.get(SOURCE_NAME_KEY, "")


def has_data() -> bool:
    return get_clean_df() is not None


def require_data() -> pd.DataFrame:
    """Return the cleaned DataFrame, or stop the page with an upload prompt.

    Call at the top of every content page so a user who deep-links here before
    uploading sees a friendly message instead of an error.
    """
    df = get_clean_df()
    if df is None:
        st.info("No data loaded yet. Open the **Home** page and upload a ticket "
                "file (or load the bundled sample) to begin.")
        st.stop()
    return df
