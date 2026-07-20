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
