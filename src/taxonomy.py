"""The one place raw cause codes become business language.

The source records causes as internal codes — ``URS_KIP_Reset_WLAN_Settings``,
``CM_BERA_KD_Bandbreite``, ``SIT11``, ``k03``. They mean something to the
ticketing system and nothing to the service-desk manager reading a story, and
the same underlying problem appears under several codes in two languages.

Mapping them to themes started inside the insights analysis, where it is what
stops the root-cause Pareto fragmenting. It belongs here instead: the
storytelling engine, the deterministic fallback, and the analysis all describe
causes to the same reader, so they must use the same vocabulary. Anything
matching no theme is a *residual* — reported as a taxonomy gap, never as a cause.

Top-level module (no ``consts`` import) so every layer can use it without a cycle.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

CAUSE_THEMES: dict[str, list[str]] = {
    "WLAN / Wi-Fi": ["wlan", "wifi", "wi-fi", "channel", "kanal"],
    "Connectivity": ["connection", "verbindung", "offline", "no_connection"],
    "Bandwidth / Speed": ["bandwidth", "bandbreite", "speed", "slow", "geschwindigkeit"],
    "Hardware defect": ["defekt", "defect", "hardware", "geraet", "modul",
                        "device", "malfunction", "funkt", "hdw"],
    "Contract / Billing": ["contract", "vertrag", "invoice", "rechnung", "bera",
                           "complaint", "kundenportal", "portal"],
    "Signal / Reception": ["sender", "signal", "reception", "empfang"],
}

RESIDUAL_THEME = "Other"

UNCLASSIFIED = "unclassified"

INTERNAL_SYSTEMS: tuple[str, ...] = ("TITAN",)

_INTERNAL_CODE = re.compile(r"\b(?=[A-Z0-9]*\d)[A-Z][A-Z0-9]{2,}\b")
_SYSTEM_NAMES = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in INTERNAL_SYSTEMS) + r")\b",
    re.IGNORECASE)


def redact_internal(text) -> str | None:
    """Strip internal system and identifier names from an operational field.

    The same principle as the cause codes above: the ticketing system's private
    vocabulary must not reach the reader. Applied to the fields handed to the
    model, so it cannot quote a name it was never shown — a filter at the source
    rather than an instruction the model may or may not follow.

    Whatever remains is returned verbatim ("TITAN Successful" -> "Successful"):
    stripping a name is honest, whereas translating it into a guessed meaning
    would be fabrication. Returns ``None`` when nothing survives, which the
    payload already represents as an absent field.
    """
    if text is None:
        return None
    cleaned = _SYSTEM_NAMES.sub(" ", str(text))
    cleaned = _INTERNAL_CODE.sub(" ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -–—:,;/")
    return cleaned or None


def theme(cause) -> str:
    """The business theme for one raw cause code."""
    text = str(cause or "").lower()
    for name, keywords in CAUSE_THEMES.items():
        if any(k in text for k in keywords):
            return name
    return RESIDUAL_THEME


def describe(causes: Iterable, max_themes: int = 3) -> str:
    """A reader-facing phrase for a set of raw codes, e.g.
    ``"WLAN / Wi-Fi (2), Hardware defect"`` — themes, ranked, with counts only
    when they add information. Returns "" when there is nothing to say.

    Unmapped codes are reported honestly as unclassified rather than quoted
    verbatim: the raw code stays in the source-ticket view, which is where an
    operator (rather than a manager) would go looking for it.
    """
    counts: dict[str, int] = {}
    for cause in causes:
        if str(cause or "").strip():
            name = theme(cause)
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return ""

    named = {k: v for k, v in counts.items() if k != RESIDUAL_THEME}
    ranked = sorted(named.items(), key=lambda kv: (-kv[1], kv[0]))[:max_themes]
    parts = [f"{name} ({n})" if n > 1 else name for name, n in ranked]

    residual = counts.get(RESIDUAL_THEME, 0)
    if residual:
        parts.append(f"{residual} {UNCLASSIFIED}")
    return ", ".join(parts)
