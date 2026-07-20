"""Episodes — the deterministic unit of a story chapter.

An *episode* is a burst of tickets close together in time: consecutive tickets
separated by less than ``consts.EPISODE_GAP_HOURS`` belong to the same episode,
and a larger gap starts a new one. Episodes are computed here, in code, and
handed to the model. The model never decides where one ends.

**Why boundaries are time-based and not relatedness-based.** An empty phase is a
claim — it says time passed with nothing to report. Time-based episodes make that
claim true by construction: the gap that separates two episodes is a real,
measured silence in the data. Relatedness cannot own the boundaries, because
relatedness is not a partition of time. Customer 123's five Hardware tickets are
all, truthfully, "the same router problem"; grouping by relatedness would collapse
them into one chapter and destroy the escalating-failure arc — five contacts over
seven days — that the Insights page headlines as the worst repeat-contact case in
the data. The story would contradict the analysis of the same rows.

So the split is:

* **code** decides how many chapters there are, which tickets are in each, and
  which phase each one occupies (here);
* **the model** writes the prose, and nothing else (see ``engine/prompts.py``).

Episodes map onto the five phases POSITIONALLY, by count — never by ticket
count, and never by judgment::

    1 episode  -> initial_issue
    2 episodes -> initial_issue, recent_events
    3 episodes -> initial_issue, follow_ups, recent_events
    4 episodes -> initial_issue, follow_ups, developments, recent_events
    5 episodes -> all five, in order
    >5         -> merged down to 5 (closest pair first) before mapping

**Why positional and not semantic.** The model used to choose each middle
episode's phase by character ("a further report" vs. "progress" vs. "a new
problem after a gap"). Three near-identical Hardware escalation stories — the
same router-fault arc for customers 123, 456 and 789 — came back with three
different phase patterns, and 123 changed pattern between runs on unchanged
data. A structure that varies while the data does not is not a judgment, it is
noise, and it makes two reports that should read alike incomparable. The cost is
recorded honestly: ``later_incidents`` is now reachable only by a five-episode
story. See ``docs/implementation.md``.

Pure module: pandas + consts only, no Streamlit, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src import consts

#: The middle phases, in arc order. Middle episodes fill them from the front:
#: the first and last phases are fixed points (the earliest episode is always the
#: initial issue, the latest always the most recent events), and everything
#: between them is taken in order rather than chosen.
MIDDLE_PHASE_IDS: list[str] = consts.PHASE_IDS[1:-1]


@dataclass(frozen=True)
class Episode:
    """One burst of tickets, and the window it occupies."""
    index: int                      
    ticket_numbers: tuple[str, ...]
    start: pd.Timestamp | None      
    end: pd.Timestamp | None        

    @property
    def dated(self) -> bool:
        return self.start is not None

    def label(self) -> str:
        """A short human window, or an explicit statement that there is none."""
        if not self.dated:
            return "no acceptance date recorded"
        fmt = "%Y-%m-%d"
        lo, hi = self.start.strftime(fmt), self.end.strftime(fmt)
        return lo if lo == hi else f"{lo} – {hi}"


def compute(subset: pd.DataFrame | None) -> list[Episode]:
    """Cluster a customer x product slice into chronological episodes."""
    if subset is None or len(subset) == 0:
        return []

    accepted = pd.to_datetime(subset[consts.OUT_ACCEPT], errors="coerce")
    order = accepted.sort_values(na_position="last").index
    tickets = subset.loc[order, consts.OUT_ORDER].astype(str).tolist()
    times = [None if pd.isna(t) else t for t in accepted.loc[order].tolist()]

    threshold = consts.EPISODE_GAP_HOURS * 3600.0
    groups: list[list[int]] = []
    for i, when in enumerate(times):
        if i == 0 or when is None or times[i - 1] is None:
            groups.append([i])
            continue
        if (when - times[i - 1]).total_seconds() < threshold:
            groups[-1].append(i)
        else:
            groups.append([i])

    episodes = [
        Episode(
            index=0,
            ticket_numbers=tuple(tickets[i] for i in g),
            start=next((times[i] for i in g if times[i] is not None), None),
            end=next((times[i] for i in reversed(g) if times[i] is not None), None),
        )
        for g in groups
    ]
    return _renumber(_merge_to_limit(episodes, len(consts.PHASES)))


def _merge_to_limit(episodes: list[Episode], limit: int) -> list[Episode]:
    """Merge the temporally closest neighbours until at most ``limit`` remain.

    The arc has five chapters, so a story with more episodes than that has to
    lose some boundaries. The smallest real silence is the least meaningful one,
    so it goes first. Merging adjacent pairs preserves the ends by construction:
    the earliest tickets stay in the first episode and the latest in the last.
    """
    eps = list(episodes)
    while len(eps) > limit:
        gaps = [_gap(eps[i], eps[i + 1]) for i in range(len(eps) - 1)]
        i = gaps.index(min(gaps))
        a, b = eps[i], eps[i + 1]
        eps[i:i + 2] = [Episode(0, a.ticket_numbers + b.ticket_numbers,
                                a.start or b.start, b.end or a.end)]
    return eps


def _gap(a: Episode, b: Episode) -> float:
    """Seconds between the end of ``a`` and the start of ``b``; undated last."""
    if a.end is None or b.start is None:
        return float("inf")     
    return (b.start - a.end).total_seconds()


def _renumber(episodes: list[Episode]) -> list[Episode]:
    return [Episode(i + 1, e.ticket_numbers, e.start, e.end)
            for i, e in enumerate(episodes)]


def phase_slots(n_episodes: int) -> list[str]:
    """The phase ids ``n`` episodes occupy — the single authority on placement.

    Every path reads placement from here: the deterministic summariser builds
    from it, the prompt states it as fact, and the validator asserts it exactly.
    There is no second opinion to disagree with, which is the whole point.
    """
    n = max(0, min(n_episodes, len(consts.PHASES)))
    if n == 0:
        return []
    if n == 1:
        return [consts.PHASE_IDS[0]]
    n_middle = n - 2
    return [consts.PHASE_IDS[0], *MIDDLE_PHASE_IDS[:n_middle], consts.PHASE_IDS[-1]]


def slots_are_valid(phase_ids: list[str], n_episodes: int) -> str:
    """Return "" if ``phase_ids`` is the required placement, else why it is not.

    There is exactly one correct answer for a given episode count, so this is an
    equality check against ``phase_slots``. It reports the first divergence in
    reader's terms — count before identity — because "you used four phases for
    three episodes" is a more useful correction than a list diff.
    """
    want = phase_slots(n_episodes)
    if len(phase_ids) != len(want):
        return (f"{len(phase_ids)} phase(s) carry tickets but the data contains "
                f"{n_episodes} episode(s), which must occupy exactly "
                f"{len(want)}: {', '.join(want) or 'none'}")
    if list(phase_ids) != want:
        wrong = next(g for g, w in zip(phase_ids, want) if g != w)
        return (f"the phases used are {', '.join(phase_ids)} but "
                f"{n_episodes} episode(s) must occupy exactly {', '.join(want)} "
                f"in that order (found '{wrong}' out of place)")
    return ""


def assignment(episodes: list[Episode]) -> list[tuple[Episode, str]]:
    """Each episode paired with the phase it belongs in. The placement, resolved."""
    return list(zip(episodes, phase_slots(len(episodes))))


def describe(episodes: list[Episode]) -> str:
    """The episode list as the model is shown it — with its phase already decided.

    Each line states the ticket grouping *and* its destination, so the payload
    never leaves a placement question open for the model to answer differently
    on two runs over the same data.
    """
    if not episodes:
        return "No tickets."
    lines = [f"The data contains {len(episodes)} episode(s). The grouping and the "
             f"phase for each are computed from the ticket timestamps and are NOT "
             f"yours to change:"]
    for e, pid in assignment(episodes):
        lines.append(f'- episode {e.index} ({e.label()}) -> "{pid}": '
                     + ", ".join(e.ticket_numbers))
    return "\n".join(lines)


def instruction(episodes: list[Episode]) -> str:
    """The concrete placement this story requires, spelled out for the model."""
    n = len(episodes)
    if n == 0:
        return ""
    used = phase_slots(n)
    empty = [p for p in consts.PHASE_IDS if p not in used]
    placement = "; ".join(f'episode {e.index} -> "{pid}"'
                          for e, pid in assignment(episodes))
    unused = ", ".join(f'"{p}"' for p in empty)
    tail = (f" Leave {unused} completely empty — that is correct, not a gap "
            f"to fill." if empty else "")
    return (f"Place the episodes exactly like this, and in no other way: "
            f"{placement}.{tail} Your only task is the wording of each "
            f"narrative.")
