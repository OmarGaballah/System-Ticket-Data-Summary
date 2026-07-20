"""Block A — export: pure serialization of a DataFrame to CSV / Excel bytes.

Kept pure (df -> bytes, no Streamlit): the actual ``st.download_button`` lives
in ``src/ui/components.py``. This satisfies the brief's "download as CSV/Excel"
without a disk round-trip.
"""

from __future__ import annotations

import io

import pandas as pd


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialize to UTF-8 CSV bytes (BOM included so Excel opens umlauts right)."""
    return df.to_csv(index=False).encode("utf-8-sig")


def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "tickets") -> bytes:
    """Serialize to .xlsx bytes via openpyxl."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buffer.getvalue()
