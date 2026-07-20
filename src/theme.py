"""The house palette and type stacks — one source of truth for every surface.

The on-screen Altair charts (``ui/charts.py``) and the exported HTML report
(``report/layout.py``) are deliberately the same picture: same ordering, same
single accent, same "emphasis, not decoration" rule. Both modules say so in
their own docstrings — but they used to each carry their own copy of the hex
values, so keeping the two in agreement was a manual job that a single missed
edit would quietly break. The colours live here instead.

Top-level module with no ``src`` imports (like ``taxonomy``), so any layer can
use it without a cycle.
"""

from __future__ import annotations

# Core palette — shared by the report stylesheet and the charts.
INK = "#16181d"
INK_SOFT = "#3f434a"
MUTED = "#77736c"
ACCENT = "#1d5c63"
NEUTRAL = "#d5d2cc"
NEUTRAL_DARK = "#b9b5ad"
RULE = "#e4e0d9"
GRID = "#ebe7e0"
GRID_END = "#cfcac1"
PAPER = "#ffffff"
SHELL = "#f7f5f1"
TINT = "#f4f2ed"

# Chart-only shades. The screen draws bars a touch cooler than the report's
# block fills and needs a dimmer step for the residual ("Other") bucket, so
# these have no stylesheet counterpart — but they are still house style.
CHART_NEUTRAL = "#c9c5be"
CHART_RESIDUAL = "#e0ddd7"
AXIS = "#8a857e"
ROW_GRID = "#f2efea"

SERIF = 'Iowan Old Style, "Palatino Linotype", Palatino, Georgia, "Times New Roman", serif'
SANS = ('-apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif')
MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'


# ---------------------------------------------------------------------------
# Chart palettes for the on-screen Altair charts (``ui/charts.py``) only.
#
# The printable HTML report (``report/layout.py``) always renders on paper —
# white/cream, dark ink — regardless of the app's theme, so it keeps the
# colours above unconditionally. The Streamlit charts, however, sit on
# whatever background the *user* picked (Light/Dark/System in the app's
# Settings menu), and the paper palette's near-black label colour and warm
# beige "neutral" bar both lose their intended contrast on a dark background:
# the label reads as washed-out grey instead of legible text, and the
# "neutral" bar — meant to recede — becomes one of the loudest marks on
# screen. A second, dark-background-tuned palette fixes that without
# touching the report.
class ChartPalette:
    """One named set of chart colours — light or dark."""

    def __init__(self, *, accent: str, neutral: str, residual: str,
                 neutral_dark: str, ink_soft: str, axis: str, grid: str,
                 row_grid: str, label_on_mark: str) -> None:
        self.accent = accent                  # the one bar/point a finding acts on
        self.neutral = neutral                # ordinary bars
        self.residual = residual              # dimmer still — the "Other" bucket
        self.neutral_dark = neutral_dark      # timeline: plain (non-highlighted) point
        self.ink_soft = ink_soft              # category / y-axis labels
        self.axis = axis                      # secondary tick labels (smaller, dimmer)
        self.grid = grid                      # gridlines
        self.row_grid = row_grid              # timeline row gridlines (subtler than grid)
        self.label_on_mark = label_on_mark    # text drawn on top of a filled marker


CHART_LIGHT = ChartPalette(
    accent=ACCENT, neutral=CHART_NEUTRAL, residual=CHART_RESIDUAL,
    neutral_dark=NEUTRAL_DARK, ink_soft=INK_SOFT, axis=AXIS,
    grid=GRID, row_grid=ROW_GRID, label_on_mark=PAPER,
)

CHART_DARK = ChartPalette(
    accent="#2dd4bf", neutral="#475569", residual="#334155",
    neutral_dark="#64748b", ink_soft="#cbd5e1", axis="#94a3b8",
    grid="#1e293b", row_grid="#161f2e", label_on_mark="#f8fafc",
)


def active_chart_palette() -> ChartPalette:
    """The palette matching the user's live Light/Dark choice, light by default.

    ``st.context.theme.type`` reflects the *actual* rendered theme (it is
    inferred from the background colour), not just what ``config.toml``
    declares, so this tracks the Settings-menu switcher live. Outside a
    running app (e.g. a test building a chart directly) there is no script
    context and it resolves to ``None``, which falls back to light — the
    same chart the printable report already uses.
    """
    try:
        import streamlit as st
        if st.context.theme.type == "dark":
            return CHART_DARK
    except Exception:
        pass
    return CHART_LIGHT
