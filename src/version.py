"""A fingerprint of the source that produces results — the cache's real key.

``st.cache_data`` invalidates an entry when the *decorated* function's own body
changes. It cannot see inside the functions that one calls, so a page like::

    @st.cache_data
    def _analyse(data):
        return insights.headline_kpis(data), insights.compute_all(data)

keeps serving results computed by an older ``compute_all`` for as long as the
app is running — every fix to the analysis is invisible, and the app quietly
disagrees with its own source. That failure is silent, survives a hot reload,
and looks exactly like a regression.

Passing :func:`code_fingerprint` as an argument to those cached functions makes
the code itself part of the cache key, so editing any module under ``src/``
evicts every stale result. Computed once per process from files already on disk
(tens of milliseconds), and it is only a cache key — nothing depends on the
value's meaning.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def code_fingerprint() -> str:
    """A short hash over every ``src/**/*.py`` file, stable within a process."""
    digest = hashlib.sha256()
    for path in sorted(_SOURCE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]
