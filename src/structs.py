"""Typed in-process data structures (dataclasses).

Distinct from ``engine/schema.py`` (the JSON *wire* contract the LLM returns):
these are the Python objects the app passes around. ``consts.py`` builds its
``PHASES`` list from the ``Phase`` struct defined here, so the dependency runs
structs -> consts -> everything else (no cycles).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Phase:
    """One phase of the five-chapter storytelling arc.

    ``id`` is the JSON key in the schema and the key returned by the LLM.
    ``title`` is the human chapter heading. ``guidance`` is injected into the
    prompt so the model knows what belongs in this phase.
    """
    id: str
    title: str
    guidance: str


@dataclass
class CleanReport:
    """The 'what got removed and why' summary emitted by the cleaning stage."""
    rows_before: int
    rows_after: int
    dropped_by_category: dict[str, int]
    columns_before: int
    columns_after: int
    shifted_rows: int  

    def as_lines(self) -> list[str]:
        """Human-readable bullet lines for the UI transparency panel."""
        dropped = ", ".join(f"{k}={v}" for k, v in self.dropped_by_category.items()) or "none"
        return [
            f"Rows: {self.rows_before} -> {self.rows_after} "
            f"(dropped {self.rows_before - self.rows_after})",
            f"Dropped categories: {dropped}",
            f"Columns trimmed: {self.columns_before} -> {self.columns_after}",
            f"Column-shifted rows realigned via NZ anchor: {self.shifted_rows}",
        ]


@dataclass
class ValidationResult:
    """Result of the grounding check — the self-correction loop's feedback signal.

    Beyond invented citations (hallucination), this also flags omission — a
    ticket in the slice that no phase cites — and duplication (a ticket cited by
    two phases), so the loop can nudge the model toward a clean partition.
    """
    ok: bool
    invented: dict[str, list[str]]      
    structural_errors: list[str]        
    message: str
    missing: list[str] = field(default_factory=list)     
    duplicated: list[str] = field(default_factory=list)  
    unnarrated: list[str] = field(default_factory=list)  
    bad_start: str = ""
    episode_errors: list[str] = field(default_factory=list)

    def invented_tickets(self) -> list[str]:
        seen: list[str] = []
        for nums in self.invented.values():
            for n in nums:
                if n not in seen:
                    seen.append(n)
        return seen


@dataclass
class PhaseSummary:
    """One phase's summarized content for a single product (matches the schema)."""
    timeframe: str
    ticket_numbers: list[str] = field(default_factory=list)
    narrative: str = ""


DETERMINISTIC_PROVIDER = "deterministic"


@dataclass
class ProductSummary:
    """A product's full five-chapter story, plus provenance for transparency."""
    product: str
    phases: dict[str, PhaseSummary]
    provider: str = ""
    model: str = ""
    note: str = "" 

    def has_content(self) -> bool:
        """True when any phase cites a ticket (i.e. there is a story to tell)."""
        return any(ps.ticket_numbers for ps in self.phases.values())

    def ticket_count(self) -> int:
        """Distinct tickets across all phases. The facts layer guarantees each
        appears exactly once, but de-duplicating keeps the count honest anyway."""
        seen: set[str] = set()
        for ps in self.phases.values():
            seen.update(ps.ticket_numbers)
        return len(seen)

    def provenance(self) -> str:
        """Who produced this story, as one sentence — the single formatting of
        it, shared by the screen, the Markdown export, and the HTML report.

        The LLM-free path gets its own sentence rather than being dropped into
        the "Narrated by <vendor>" template, where "deterministic" read as a
        template variable landing in the wrong slot.
        """
        if self.provider == DETERMINISTIC_PROVIDER:
            line = "Built directly from the tickets — no model was involved"
        elif self.provider:
            line = "Narrated by " + " · ".join(
                b for b in (self.provider, self.model) if b)
        else:
            line = ""
        if self.note:
            return f"{line} · {self.note}" if line else self.note
        return line
