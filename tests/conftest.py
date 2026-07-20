"""Shared fixtures for the test suite."""

from pathlib import Path

import pytest

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "Ticket Data (2).txt"


@pytest.fixture(scope="session")
def sample_bytes() -> bytes:
    return DATA_FILE.read_bytes()


@pytest.fixture(scope="session")
def clean_df(sample_bytes):
    from src.pipeline.ingest import run_pipeline
    df, _ = run_pipeline(sample_bytes)
    return df
