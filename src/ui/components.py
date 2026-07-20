"""Reusable Streamlit widgets — keeps the pages thin.

The download buttons live here (UI), while the serialization they call lives in
``pipeline/export.py`` (pure bytes). Selectors read their options from the
cleaned DataFrame and from ``consts`` so labels never drift.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import consts
from src.pipeline.export import to_csv_bytes, to_excel_bytes
from src.structs import CleanReport

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def customer_selector(df: pd.DataFrame, key: str = "customer") -> str:
    """Dropdown of customers present in the data. Drives everything downstream."""
    customers = sorted(df[consts.OUT_CUSTOMER].dropna().unique())
    return st.selectbox("Customer", customers, key=key)


def language_toggle(key: str = "language") -> str:
    """English (default) / German toggle for the summary language."""
    langs = list(consts.LANGUAGES.keys())
    default_idx = langs.index(consts.DEFAULT_LANGUAGE)
    label = st.radio("Language", langs, index=default_idx, horizontal=True, key=key)
    return consts.LANGUAGES[label]


def download_buttons(df: pd.DataFrame, basename: str = "cleaned_tickets") -> None:
    """CSV + Excel download buttons for the given DataFrame."""
    c1, c2 = st.columns(2)
    c1.download_button(
        "⬇ Download CSV", data=to_csv_bytes(df),
        file_name=f"{basename}.csv", mime="text/csv",
    )
    c2.download_button(
        "⬇ Download Excel", data=to_excel_bytes(df),
        file_name=f"{basename}.xlsx", mime=_XLSX_MIME,
    )


def removal_report(report: CleanReport) -> None:
    """Transparency panel: what the cleaning stage removed and why."""
    with st.expander("What was cleaned (transparency)"):
        for line in report.as_lines():
            st.write("•", line)
