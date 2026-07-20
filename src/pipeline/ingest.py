"""Block A1 — ingest: raw uploaded bytes -> typed DataFrame (no filtering yet).

Takes the file's **bytes** (not the Streamlit UploadedFile) so the Streamlit
layer can wrap this with ``@st.cache_data`` keyed on file *content* — the
pipeline re-runs only when a genuinely new file is uploaded.

Robust parsing: strip the BOM (utf-8-sig), treat the NA tokens as missing, keep
everything as strings (columns can drift, so don't let pandas type-guess the
free-text block), and parse the two timestamp columns with an explicit format.
"""

from __future__ import annotations

import io

import pandas as pd

from src import consts


class IngestError(Exception):
    """The upload could not be read as a ticket export.

    A distinct type so the UI can say something useful. A user who picks the
    wrong file should be told that, not shown a pandas traceback about columns.
    """


REQUIRED_COLUMNS: tuple[str, ...] = (
    consts.TICKET_COL, consts.CUSTOMER_COL, consts.CATEGORY_COL,
    consts.ACCEPTANCE_COL, consts.COMPLETION_COL,
)


def parse_bytes(file_bytes: bytes) -> pd.DataFrame:
    """Parse raw uploaded bytes into a typed DataFrame with the source columns.

    Raises :class:`IngestError` — with a sentence a user can act on — when the
    bytes are not a readable delimited file or are missing the spine columns.
    """
    try:
        df = pd.read_csv(
            io.BytesIO(file_bytes),
            encoding="utf-8-sig",          
            engine="python",
            dtype=str,                     
            keep_default_na=False,
            na_values=consts.NA_TOKENS,
        )
    except pd.errors.EmptyDataError as exc:
        raise IngestError(
            "This file is empty — there is no header row to read.") from exc
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise IngestError(
            "This file could not be read as a comma-separated ticket export. "
            "Check that it is the raw export and not a spreadsheet or archive."
        ) from exc

    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise IngestError(
            "This does not look like a ticket export — it is missing the "
            f"column{'s' if len(missing) > 1 else ''} "
            + ", ".join(missing) + ".")
    for col in consts.DATETIME_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(
                df[col], format=consts.DATETIME_FORMAT, errors="coerce"
            )
    return df


def run_pipeline(file_bytes: bytes):
    """Ingest -> clean -> map, end to end. Returns ``(clean_df, CleanReport)``.

    The Streamlit layer wraps this with ``@st.cache_data`` and passes raw bytes
    so the whole pipeline re-runs only on a new file.
    """
    from src.pipeline.clean import clean
    from src.pipeline.mapping import add_product

    raw = parse_bytes(file_bytes)
    cleaned, report = clean(raw)
    mapped = add_product(cleaned)
    return mapped, report
