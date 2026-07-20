# Implementation notes

Findings about the source export that shaped the code. Everything here was
measured against `data/Ticket Data (2).txt` (42 rows, 32 after category
filtering) — no claim in this file is inferred from column names alone.

## The NZ anchor

`NETWORK_LEVEL` is the constant `"NZ"` in every row, and about half the rows are
shifted one column left in the free-text block. Locating `"NZ"` and reading the
surrounding fields by fixed offset recovers them in both layouts:

| Offset | Field | Cleaned column |
|---|---|---|
| NZ-4 | team / queue | `team` |
| NZ-3 | remediation action | `action` |
| NZ-2 | escalation / follow-up marker | `reference_result` |
| NZ-1 | outcome | `outcome` |
| NZ+1 | root-cause code | `cause` |
| NZ+2 | resolver | `resolver` |

See `src/pipeline/clean.py` and `consts.ANCHOR_OFFSETS`.

## Task-type rows record completion differently (not a column shift)

**Measured:** the string `TSC#KCC` appears in the outcome slot (NZ-1) in **6 of
42 rows — exactly the 6 Task-type rows** (`Task` ×5, `Aufgabe` ×1) and **none of
the 36 Short Ticket rows**. The correlation is total in both directions. Three of
the six survive category filtering (GIGA ×2, KAV ×1); the other three are `SOP`
and are dropped.

**It is not an anchor-ladder shift.** The anchor sits in the same place and the
offsets still line up; what differs is the *vocabulary* the Task workflow writes
into those slots:

| Slot | Short Ticket row | Task row |
|---|---|---|
| NZ-3 action | `WLAN settings optimized` | `SIT12` |
| NZ-2 reference | *(blank)* | `New BI order created` |
| NZ-1 outcome | `OK` | `TSC#KCC` |
| NZ+1 cause | `URS_KIP_Reset_WLAN_Settings` | `SIT11` |
| NZ+2 resolver | *(blank)* | `BI order closed` |

So Task rows **never record an OK/Error outcome at all**. `TSC#KCC` is a queue
code; the closest thing to an outcome for those rows is the resolver text
(`BI order closed`, `Problem Solved`, `Techniker behebt Fehler`).

**Consequences in the code.** `clean._norm_outcome` maps anything that is not
`OK` or `Error` to `Unknown`, so `TSC#KCC` never reaches a reader as though it
were an outcome. That is correct, but it sets a trap: ticket `001-0670933/24`
then carries `outcome=Unknown` alongside `resolver="Problem Solved"`, and a model
handed both wrote *"resolved with the problem marked as solved, though the final
outcome was not recorded"* — a sentence that contradicts itself. The prompt now
forbids asserting resolution and unknown outcome together
(`src/engine/prompts.py`): if the outcome is Unknown but an action or resolver
shows the work was done, describe the work and say nothing about the outcome.

**Not done, deliberately:** deriving a synthetic outcome for Task rows from the
resolver text. That would be a guess dressed as data, and the resolver strings
are free text in two languages. If a future export keeps this convention, the
honest fix is a Task-specific outcome mapping agreed with whoever owns the
workflow — not a keyword search over prose.

## The CAUSE column often names a remedy, not a cause

**Measured:** `URS_KIP_Reset_WLAN_Settings` and `URS_KIP_WLAN-Settings_Reset`
both appear in the `cause` slot (NZ+1). Read literally they name an *action*
support took, not a fault the customer experienced.

**Proof it is a misread, not a judgment call:** ticket `001-0671177/24`
(customer 123) and the 11-09 / 11-12 Hardware tickets for customers 456 and 789
carry the same code with the description "WLAN / No Connection". A model narrated
123's as an action — *"Support optimized the Wi-Fi settings"* — and 789's as a
cause — *"no Wi-Fi connection, attributed to Wi-Fi settings being reset"*. The
second inverts causation: it blames the remedy for the fault. One reading of the
same code must be wrong, and the action reading is the right one.

The prompt now forbids attributing causation to a cause code that names a
remediation (reset, optimize, replace, change, restart); causation is only
asserted when the field names a fault condition such as a hardware defect.

This is the same gap the Insights page already quantifies from the other end:
28% of tickets fall into the residual **Other** root-cause bucket because their
code carries no usable fault meaning. Opaque and remediation-shaped codes are one
finding, not two — the taxonomy records *what was done* more reliably than *what
was wrong*, which is a real limit on root-cause analysis of this export.

## Episode boundaries

Story chapters are cut on measured silence, not on relatedness — see the module
docstring in `src/engine/episodes.py` for why. The threshold
(`consts.EPISODE_GAP_HOURS = 12`) is **not tuned**: all 14 intra-story gaps in
the sample fall into three bands — 2h, 19–26h and 69–143h — with nothing between
2 and 19, so every threshold in that range yields identical episodes.
`tests/test_episodes.py::test_the_sample_bands_are_far_from_the_threshold` fails
if a future export closes that band, which is the signal to re-measure rather
than re-guess.

### Phase assignment is positional, not semantic

Episodes fill phases from the front, by count alone:

| Episodes | Phases populated |
|---|---|
| 1 | `initial_issue` |
| 2 | `initial_issue`, `recent_events` |
| 3 | `initial_issue`, `follow_ups`, `recent_events` |
| 4 | `initial_issue`, `follow_ups`, `developments`, `recent_events` |
| 5 | all five, in order |

**Why the semantic rule was withdrawn.** The model used to pick each middle
episode's phase by character — a further report → `follow_ups`, recorded progress
→ `developments`, a new problem after a gap → `later_incidents`. Three
near-identical Hardware escalation stories came back with three different
structures: 123 used `follow_ups` + `later_incidents`, 456 used `later_incidents`
alone, 789 used `follow_ups` + `developments`. 123 had previously matched 789 and
changed pattern on unchanged data.

That is not judgment, it is per-call variance, and it has a real cost to the
reader: three customers with the same router-fault arc produced three reports
that could not be compared side by side. Predictable structure was chosen over
per-case nuance, because the nuance was not reproducible. The model now writes
narratives only; `episodes.phase_slots` is the single authority on placement, and
`validate.py` asserts equality against it rather than accepting any in-order
arrangement. All three Hardware stories now read
`initial_issue / follow_ups / developments / recent_events`, and 456 (3 episodes)
reads `initial_issue / follow_ups / recent_events`.

**The trade-off, stated plainly.** `later_incidents` is now reachable only by a
five-episode story. No product in this export has five, so the phase is unused —
where before it was unused for a semantic reason, it is now unused for a
structural one. A genuinely new problem after a long gap in a 3- or 4-episode
story will be titled "Follow-ups" or "Developments" rather than "Later
Incidents". That mislabels the chapter's *character* while keeping its *contents*
and its *position in time* exactly right, which is the cheaper error: the tickets
and dates under the heading still say what happened.

An empty chapter remains a claim the data supports, not a gap to fill. A
summariser that populated all five phases regardless would be asserting a
recurrence that never happened.

## German output

Verified against a real model run (customer 123, all six products, Gemini with a
DeepSeek fallback), not just by reading the code. Narratives come back in German,
the `language` field round-trips, and phase headings, timeframes and
ticket/category labels are language-independent so they render unchanged. Rows
that are already German in the source are not re-translated into something odd.

`consts.NO_ACTIVITY` (`"No activity."`) is a **contract sentinel, not display
text**. It stays English in every language because it is what the prompt asks the
model to emit and what `facts.assert_consistent` compares against; making it
language-dependent would make a structural invariant depend on a user setting,
and a German story returning the English sentinel would fail an assert that has
nothing to do with language. Translation happens once, at the edge, in
`consts.no_activity_text` — called by the three renderers and nowhere else. No
German string for it exists outside `consts.NO_ACTIVITY_DISPLAY`.

**Known gap.** The LLM-free fallback view (`engine/fallback.py`) always writes
English — "4 tickets, all resolved. Causes: WLAN / Wi-Fi (3)" — regardless of the
selected language, because it is templated prose rather than generated text. A
German user with no provider configured therefore gets German headings around
English sentences. Fixing it means a per-language phrase table plus a decision
about the cause themes, which are deliberately shared with the Insights page:
translating them there would desync the story vocabulary from the analysis
vocabulary. Left as-is and recorded here rather than half-done.

## Repeat contacts are counted in occasions

The metric answers "did the customer have to come back", so its unit is the
contact occasion — the same episode clustering above, imported from
`engine/episodes.py` rather than reimplemented in `analysis/insights.py`.

Counting tickets overstated it: customer 456 raised two Hardware tickets two
hours apart on 11-08, which is one report, not a customer returning. Recounting
moves the headline rate from **44% of tickets to 38% of occasions (11 of 29)**,
and customer 123's Hardware from "5 contacts" to **4 contact occasions across 5
tickets**. Both figures are shown together everywhere the metric appears, so the
smaller number never looks like missing tickets.

Escalation rate, resolution time, the root-cause Pareto and team load are all
per-ticket measures and are unchanged.
