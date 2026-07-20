# Implementation

A Streamlit application that ingests a raw system ticket export, cleans and maps it,
and generates a five-phase storytelling summary per customer and product using an LLM,
alongside a deterministic operational insights report.

This document records **what was built and why**, the reasoning behind each decision,
the alternatives considered, and the places where the specification was ambiguous or
where the data contradicted it. Every constant referenced here lives in `src/consts.py`,
which is the single source of truth for business rules.

**Pipeline in one line:** upload → parse and realign → filter and normalise → map to
products → cluster into episodes → assign phases in code → narrate with an LLM →
validate and enforce → render and export.

---

## 1. Data preprocessing

### 1.1 What the source file actually is

The brief describes a "text file", implying extraction work. In practice the export is
already a well-formed CSV: comma-delimited, 38 columns, one header row, 42 data rows in
the sample, covering 3 customers over November 2024. Parsing is therefore straightforward, but four properties of the file will silently corrupt the output if missed.

**Byte-order mark.** The file opens with a UTF-8 BOM. Read naively, the first column name
becomes `\ufeffORDER_NUMBER`, so every later lookup by name fails. Read as `utf-8-sig`.

**Mixed English and German.** Rows are bilingual,  `Short Ticket`/`Kurzticket`,
`Completed`/`ab`, and free text containing `erhöht`, `geprüft`, `Kundenportal`. The
category *codes* are stable across both languages, so filtering is safe, but encoding is
not optional: reading with the wrong codec produces mojibake that then propagates into
the LLM narratives. Status and order type are normalised through
`consts.STATUS_NORMALIZE` and `consts.ORDER_TYPE_NORMALIZE` so reporting never splits one
concept into two labels.

**US month-first timestamps.** `consts.DATETIME_FORMAT` is `%m/%d/%Y %H:%M`, so
`11/05/2024 11:00` is 5 November. This is the single most dangerous trap in the file: if
a parser infers day-first, the entire timeline silently reorders and the phase arc comes
out scrambled with no error raised. The format is pinned explicitly rather than inferred.

**Two flavours of missing.** Blank cells and the literal string `N/A` both mean absent and
both occur. `consts.NA_TOKENS` collapses them to a single null so downstream logic checks
one condition, not two.

Parsing uses a real CSV reader rather than a string split. Nothing in the sample contains
an embedded comma, but the description fields are free text and easily could.

### 1.2 The column shift, and why it is invisible to the obvious check

**About 45% of rows are shifted one column left within the free-text block.**

This is easy to miss and was initially missed. The natural check, do all rows have the
same number of fields?, passes: every row splits into exactly 38 fields, header
included, with no stray or missing delimiters. Equal field *count* does not imply aligned
field *values*, because the shift occurs inside the free-text block with a compensating
field elsewhere in the row.

The evidence is in the value distributions. `NETWORK_LEVEL` is a constant `NZ` in every
row and should sit at index 20; it sits at index 20 in 23 rows and at index 19 in the
other 19. Consequently `COMPLETION_NOTE_MAXIMUM`, nominally the outcome,  contains `OK`
in 19 rows and the literal string `NZ` in 19 others, and `PLANNING_GROUP_KB` contains
action codes such as `SIT12` in rows where it should hold a team.

**The fix: anchor on `NZ` and read by offset.** Because `NETWORK_LEVEL` is constant, its
actual position in each row can be located directly, and the surrounding fields form a
fixed ladder around it. `consts.ANCHOR_OFFSETS` records the mapping:

| Offset from `NZ` | Field | Source column (aligned rows) |
|---|---|---|
| −4 | team | `PLANNING_GROUP_KB` |
| −3 | action | `COMPLETION_RESULT_KB` |
| −2 | reference | `REFERENCE_COMPLETION_RESULT` |
| −1 | outcome | `COMPLETION_NOTE_MAXIMUM` |
| +1 | cause | `CAUSE` |
| +2 | resolver | `REFERENCE_ERROR_CAUSE` |

Reading by offset recovers all six fields correctly in both aligned and shifted rows.
Implemented in `src/pipeline/clean.py`.

These six are promoted to first-class columns rather than bundled into free text. That
decision is what makes the Insights analysis possible at all, escalation detection,
root-cause concentration and team load all read from them.

### 1.3 Filtering, trimming and normalisation

**Category filter.** `consts.KEEP_CATEGORIES` retains seven codes, HDW, NET, KAI, KAV,
GIGA, VOD, KAD, and drops everything else. In the sample this removes NTF (4 rows) and
SOP (6 rows), leaving 32 of 42. The remaining distribution is HDW 14 and three each of
NET, KAI, KAV, GIGA, VOD and KAD, which makes HDW 44% of the usable data, a fact that
drives the mapping decision in section 2.

**Column trimming.** Of 38 source columns, the pipeline keeps the ticket number, both
timestamps, customer, order type, status, category, the six anchored fields, and a
bundled `details` field of descriptive free text (`consts.DETAILS_COLS`) for the
narrative. The remaining columns are discarded. Canonical output names are the `OUT_*`
constants.

**Outcome normalisation.** The outcome slot does not always contain `OK` or `Error`. On
Task-type rows it can hold a team code, ticket `001-0670933/24` has `TSC#KCC`, while
the resolver field separately reads `Problem Solved`. Left unnormalised, the model
faithfully reported both and produced the contradiction *"resolved with the problem
marked as solved, though the final outcome was not recorded."* Any value that is not `OK`
or `Error` now normalises to `Unknown`, and a prompt rule forbids asserting both
resolution and an unknown outcome in the same sentence.

**Timestamps are complete.** All 42 rows have both `ACCEPTANCE_TIME` and
`COMPLETION_TIME`. `ASSIGNMENT_TIME` is `N/A` in all 42 and is deliberately unused. The
undated-ticket path in the episode logic therefore exists for robustness on future
exports, not for the sample.

**Export.** The cleaned table is downloadable as CSV/Excel, satisfying the brief's
conversion requirement. Both the raw parsed table and the cleaned table are offered so
the effect of filtering is visible rather than implicit.

---

## 2. Category mapping

### 2.1 The ambiguity in the brief, and how it was resolved

The specification says the summary is produced **"for each category"** and then supplies a
**category → product** mapping in which Broadband covers both KAI and NET. Those two
statements point at different units of summarisation: seven category stories per customer,
or six product stories.

**Resolution: product is the unit of summarisation; category is surfaced per ticket.**

The reasoning: the mapping section exists for a reason and must do something, and
per-category summarisation makes an already sparse dataset sparser, most categories hold
one to three tickets per customer, which produces five-phase arcs that are almost entirely
empty. Product-level grouping gives the narrative enough material to be a narrative.

The cost is that Broadband merges two unrelated fault types, and merging must not imply
that one caused the other. Three mitigations, all still in place:

- each ticket's `SERVICE_CATEGORY` travels into the model payload;
- the prompt forbids narrating unrelated tickets as cause and effect, requiring
  concurrent phrasing ("separately", "also") unless the tickets share a category or a
  field explicitly links them;
- the category is printed next to every ticket number in the rendered story, so the
  reader can see the story spans two categories.

This is a judgment call on an ambiguous specification. A reviewer reading "for each
category" literally would expect seven stories; the mapping is what makes product the
better reading.

### 2.2 HDW is a deliberate addition

The brief's mapping table has **no row for HDW**, yet HDW is in the retained category list
and is the single largest category in the sample at 14 of 32 tickets.

Following the table literally would silently discard 44% of the usable data, including
the router and WLAN tickets that produce the most valuable operational finding in the
dataset. Folding HDW into an existing product would misattribute it. It therefore gets its
own product, **Hardware**. This is the only product not named by the brief and is recorded
as a deviation.

### 2.3 The mapping does not match the ticket descriptions

The code labels and the free-text descriptions disagree throughout the sample:

- **KAV** is mapped to *Voice*, but every KAV row describes TV picture problems
  (`HD Channel / Blurred`, `Sender / kein Empfang`).
- **KAD** is mapped to *TV*, but the KAD rows are account-portal issues
  (`Password / Forgotten`, `Customer Portal / Invoice Problem`).
- **KAI** groups under *Broadband*, but the rows concern CI modules and smartcards ,
  TV-viewing hardware.

The likeliest explanation is synthetic sample data: real category codes populated with
placeholder descriptions. **The brief's mapping is followed exactly**, on the grounds that
the codes are presumably the client's real taxonomy and the instruction is explicit. The
discrepancy is documented rather than silently corrected.

One consequence required a prompt rule: the product name is a grouping header, not a fact
from the data. Without that constraint the model wrote *"the TV customer portal"* when the
underlying field said only *Kundenportal*, importing the mapping label into the narrative
as though it were recorded.

`consts.PRODUCT_MAP` holds the mapping; `consts.PRODUCTS` derives the ordered product list.

---

## 3. Summary generation

### 3.1 Design principle: code owns facts, the model owns wording

The architecture separates what can be guaranteed from what cannot.

| Owned by code (deterministic) | Owned by the model |
|---|---|
| Episode boundaries | Narrative wording |
| Phase placement | Relating tickets within a phase |
| Timeframes (from real timestamps) | Choice of plain language for codes |
| Ticket coverage and validity | |

The model never writes a date and never chooses which phase a ticket belongs to. Those
were the two largest hallucination surfaces, and removing the model's authority over them
eliminates the failure mode rather than policing it.

### 3.2 Episodes

Tickets are clustered into **episodes** before any phase logic runs. Consecutive tickets
separated by less than `consts.EPISODE_GAP_HOURS` belong to the same episode; a larger gap
starts a new one.

`consts.EPISODE_GAP_HOURS` is **12.0** , chosen from a gap in the data, not fitted to it.
All 14 intra-story gaps in the sample fall into three bands with nothing between them:

- **2 hours** , three cases, all same-day pairs
- **19–26 hours** , eight cases, all next-day
- **69–143 hours** , three cases, multi-day

Nothing lies between 2 and 19 hours, so every threshold in that range yields identical
episodes. This is a real cluster boundary rather than a tuned parameter, and
`test_the_sample_bands_are_far_from_the_threshold` fails if a future export closes the
band , turning the assumption into something that breaks loudly rather than drifting
silently.

**Why time and not relatedness.** Relatedness was considered and rejected as the boundary
rule. Customer 123's five Hardware tickets are all, loosely, the same router problem ,
slow WLAN, no internet, unstable WLAN, no connection, dead router. Clustering by
relatedness would collapse them into one or two episodes and destroy the escalating
first-time-fix failure that is the most valuable finding in the dataset. Time-based
boundaries are also deterministic, which means they can be validated; relatedness would
require model judgment, which is exactly what kept drifting during development.

Relatedness still matters , it governs how tickets *within* an episode are narrated
(concurrent versus continuing) , but it does not set boundaries.

An undated ticket forms its own episode ordered last, with its missing date stated in the
narrative rather than silently absorbed into the preceding episode. No such rows exist in
the sample.

### 3.3 Phase assignment

Episodes map onto the brief's five phases **positionally, in code**:

| Episodes | Phases used |
|---|---|
| 1 | `initial_issue` |
| 2 | `initial_issue`, `recent_events` |
| 3 | `initial_issue`, `follow_ups`, `recent_events` |
| 4 | `initial_issue`, `follow_ups`, `developments`, `recent_events` |
| 5 | all five, in order |
| >5 | closest episodes merged down to five; first stays `initial_issue`, last stays `recent_events` |

`episodes.phase_slots` is the single authority: the deterministic fallback builds from it,
the prompt states the placement as fact, and `validate.py` asserts equality against it.

**This replaced an earlier rule that let the model choose middle phases by character**
(same problem continuing → follow-ups, recorded progress → developments, new problem after
a gap → later incidents). That rule produced three different phase patterns for three
near-identical Hardware escalation stories across the three customers. Consistency for
equivalent data was judged more valuable than per-case semantic nuance.

**The cost, stated plainly:** a genuinely new problem after a long gap in a three-episode
story will now be titled "Follow-ups". The heading misdescribes the chapter's character
while its contents and its position in time remain exactly right. That is the cheaper
error , the tickets and dates under the heading still say what happened , but it is a real
one, and it is the price of the trade. A related consequence: `later_incidents` is now
reachable only by a five-episode story, and appears in none of the sample's 18 stories.
Both are pinned by tests so they stay deliberate.

**The underlying principle** worth carrying forward: *an empty phase is a claim that time
passed with nothing to report.* Time-based episodes make that claim true by construction.
An earlier iteration placed two tickets one day apart into `initial_issue` and
`recent_events` with three empty phases between them, asserting an elapsed interval that
had not occurred.

### 3.4 Prompt design

The system prompt is assembled in `src/engine/prompts.py` from `consts.PHASES`, so the
prompt and the JSON schema cannot drift apart. It supplies the payload with each episode's
computed phase already assigned, and closes by narrowing the task: the model's only job is
the wording of each narrative.

Every constraint in the prompt is traceable to an observed failure:

| Constraint | Failure it prevents |
|---|---|
| Only cite supplied ticket numbers | Invented citations |
| Describe only what the fields record; never infer sentiment | Invented customer satisfaction (see 3.7) |
| Never quote raw codes, team names, tools, or bucket labels | `SIT12`, `TSCS2`, `TITAN`, `"Other"` leaking into prose |
| Never describe the classification system itself | Paraphrase evasion , "recorded under a general classification" |
| Do not assert causation from a cause code naming an action | Causation inversion (see 3.8) |
| Unrelated tickets in a phase are concurrent, not causal | Broadband's merged KAI/NET arc |
| Never write ticket numbers inside prose | Duplication with the ticket line beneath |
| Never quote literal `OK`/`Error` | Raw outcome values in business narrative |
| No commentary on the story's own shape | "The most recent ticket reported…" |
| Product name is a header, not a fact | "the TV customer portal" |

Output is strict JSON matching `engine/schema.py`. Structured output is what makes both
validation and clean rendering possible; free prose would make grounding unverifiable.

### 3.5 Validation and enforcement

Three tiers, distinguished by the strength of guarantee achievable.

**Tier 1 , structure (absolute).** The response must parse against the schema: five
phases, correct types, language field matching the request. Malformed output fails loudly
rather than rendering.

**Tier 2 , facts (absolute, because made structural).** `validate.py` detects and
`facts.py` enforces:

- **invented** , cited tickets not in the customer × product slice;
- **missing** , slice tickets no phase cites (omission, hallucination's quiet twin);
- **duplicated** , a ticket cited by more than one phase;
- **unnarrated** , a phase citing tickets but writing nothing about them;
- **bad start** , the first populated phase is not `initial_issue`;
- **episode partition** , the phase assignment does not equal the computed slots.

Timeframes are computed from real timestamps and never model-generated, so they cannot be
wrong.

**Tier 3 , narrative faithfulness (no absolute guarantee; be honest about this).** No
deterministic check proves prose faithful to source. Three mitigations in priority order:
prevention through prompt constraints; traceability, since every phase lists the tickets
it was built from so any claim can be audited in one click; and, as the production path,
an LLM-as-judge groundedness scorer , described here as the monitoring approach at scale
rather than implemented, since judges are probabilistic and belong in the tier that
monitors rather than the tier that guarantees.

One Tier-3 problem turned out to have a Tier-2 solution: raw-code leakage is fully
deterministic to detect, because every cause, action, team and tool value in the slice is
known and can be searched for verbatim in the narrative. A comparable check for ticket
numbers appearing in prose is a small, honest addition and is noted in section 7.

### 3.6 Why `assert_consistent` raises rather than repairs

`facts.assert_consistent` enforces that a phase's tickets and its prose are one unit: if
tickets are present the narrative must say something; if absent it must be exactly
`consts.NO_ACTIVITY`; and a phase holding tickets may never narrate no-activity.

It exists because of a real defect. An earlier fix re-anchored ticket numbers across
phases *after* generation while the narratives stayed on their original keys. The result
was a chapter dated 2024-11-07 whose prose described an event from 2024-11-13, and a
chapter holding that later ticket under the words "No activity". Both halves were
individually plausible, so nothing else caught it , the coverage check passed, because
every ticket still appeared exactly once.

The check raises rather than repairs because a mismatch means code moved one half of a
phase without the other, and there is no honest way to guess the rest. The general lesson,
which shaped the rest of the design: **post-processing that reassigns tickets after
generation silently invalidates the narrative's grounding**, and membership checks cannot
see it. Where a coherence gap is detected, the remedy is regeneration, not repair.

### 3.7 A deviation from the brief: the phase descriptions ask for data that does not exist

The brief's five phase descriptions each ask the narrative to include the customer's
feedback , *"the customer's first feedback"*, *"additional feedback"*, *"changes in
customer experiences"*, *"the customer's ongoing feedback"*, *"the customer's final
feedback"*.

**No feedback or sentiment field exists anywhere in the 38 source columns.**

Transcribed faithfully into the prompt, this instruction caused exactly the failure it
implies. A small model (qwen2.5:3b) complied and invented sentiment , *"the customer's
feedback post-resolution was positive, indicating the issue had been resolved
satisfactorily"*, *"the customer experience remained stable without any further
feedback"*. A stronger model largely ignored it, which meant grounding depended on the
model's disposition rather than on the instruction.

The phase guidance in `consts.PHASES` was therefore rewritten in terms of what the data
records , issues reported, actions taken, outcomes recorded , and an explicit prohibition
on inferring sentiment was added. This is a documented deviation from the specification,
made because the specification asks for content the data cannot support.

### 3.8 Data quality findings surfaced during narration

**Cause codes frequently name remediations, not causes.** `URS_KIP_WLAN-Settings_Reset`
appears as the `CAUSE` on tickets whose description is `WLAN / No Connection`. Read
literally, the model produced *"the customer again experienced no Wi-Fi connection,
attributed to Wi-Fi settings being reset"* , blaming the remedy for the fault. The same
code was elsewhere narrated as an action (*"Support optimized the Wi-Fi settings"*),
proving the ambiguity. A prompt rule now forbids asserting causation when the cause code
names an action. This is the same taxonomy gap the Insights page quantifies as the 28%
"Other" bucket.

**Team codes in the outcome slot.** See 1.3 , `TSC#` values in the outcome field on
Task-type rows, now normalised to `Unknown`.

**Malformed description text.** The description pair `WLAN / Stable` is almost certainly a
truncation of the German *Stabilität*; transcribed literally it produced "a stable Wi-Fi
issue". The model is now instructed to render evident meaning in plain language without
inventing detail.

### 3.9 Model selection and provider handling

Providers are configured in `consts.PROVIDER_MODELS` with a transport-only fallback order
(`consts.FALLBACK_ORDER`) , triggered by timeouts, rate limits and missing keys, never by
content or validation failures, which are handled by the retry described below.

**qwen2.5:3b is a smoke-test model only.** Measured on the real sample it invented
customer sentiment, corrupted *Kundenportal* into the non-existent *Kadenportal*, omitted
a ticket entirely, and leaked `SIT12` and `TSCS2` into prose. It is useful for exercising
the pipeline cheaply and offline; it is not grounded enough for narrative output. Larger
models (DeepSeek v4 Flash, Gemini 3.5 Flash) produced clean, restrained narratives ,
including the desirable behaviour of declining to speculate, e.g. *"the outcome of this
ticket is not recorded."*

One observed operational issue: when transport fallback fires mid-report, a single
document can carry narratives from two providers with noticeably different voice. Since
phase placement moved into code, structure no longer varies by provider , two providers
produced identical arcs for the same data , but wording still does.

### 3.10 Self-correction: one retry, not an agentic loop

When validation fails on the raw draft, the summariser makes **exactly one** retry,
sending the original prompt, the failed draft and the exact validator message, and asking
for a complete corrected JSON object rather than a patch. A patch would risk moving ticket
assignments while narratives stayed put , the defect described in 3.6.

**The retry is not what makes the output correct.** `facts.enforce` is, unconditionally
and without the model. The retry exists for *coherence*: `facts._place_omitted` can repair
a ticket's placement but cannot write the sentence describing it, so the phase would cite
a ticket its prose ignores. Only regeneration closes that gap.

A multi-step agentic loop with tool calls was considered and deliberately rejected. Since
the deterministic layer already guarantees correctness regardless of whether the model
converges, additional iterations buy coherence, not safety; and if a model fails with
explicit error feedback in hand, a second failure is usually systematic.

Four tests pin the contract: it recovers an omitted ticket (`provider.calls == 2`), it is
attempted exactly once when retrying does not help, it never fires on a transport failure,
and it discloses itself in the provenance note.

Retrieval tools were also rejected. The entire customer × product slice already fits in
the prompt, so a tool call to fetch data the model was handed would be ceremony rather
than capability.

Whether a retry occurred is recorded and surfaced in the rendered provenance line.
Silent retries would defeat the purpose; the disclosure is the point.

### 3.11 Language

English is the default; German is a toggle (`consts.LANGUAGES`). The chosen language is
interpolated into the prompt and returned as a top-level field so it round-trips.
Generating a full German report for one customer across all six products confirmed that
narratives return in German, the language field round-trips, and phase headings,
timeframes and ticket labels are language-independent and render unchanged. Rows already
written in German are not re-translated into something odd.

**`consts.NO_ACTIVITY` is deliberately left in English.** It is a contract sentinel , the
exact string the prompt asks the model to emit for an empty phase, and the string
`facts.assert_consistent` compares against. Making it language-dependent would make a
structural invariant depend on a user setting, and a German story returning the English
sentinel would fail an assertion that has nothing to do with language. Translation happens
once at the edge, in `consts.no_activity_text`, called by the three renderers and nowhere
else.

One known gap is recorded in section 7: the deterministic fallback narrator always emits
English.

---

## 4. Insights (bonus task)

Every figure is computed deterministically in pandas from the cleaned export. Where the
narrative summary is LLM-written, the insights are not: the model, where used at all,
rephrases computed findings and never produces a number.

### 4.1 Scope

Insights are **global across all customers in the uploaded file**, while stories are
per-customer. This is deliberate. The repeat-contact finding compares customer × product
pairs and only exists at global scope; at 10–11 tickets per customer, per-customer rates
would be quantities like one-in-three, which is noise; and the questions asked ,
first-time-fix, root-cause concentration, escalation, handoffs , are about the support
operation, not about one customer. A customer filter was considered and rejected because
it would degenerate the metrics and invite exactly the small-sample conclusions the method
note warns against.

### 4.2 The sections, and what decision each supports

1. **First-time-fix / repeat contacts** , are we fixing issues on the first contact?
2. **Root-cause concentration (Pareto)** , what should we fix upstream?
3. **Escalation rate by product** , where does the support process fail?
4. **Resolution time by product** , where are we slow?
5. **Team load and handoffs** , how much work bounces between teams?
6. **Contact timeline** , episodes plotted on a shared date axis.

Each carries a written "so what" stating a recommendation rather than describing the
chart. A chart without an action it supports was treated as not worth showing.

### 4.3 Methodological decisions

**Repeat contacts count occasions, not tickets.** Once episodes existed, the original
per-ticket count was measurably overstated: two tickets raised two hours apart are one
contact occasion, not a repeat contact. Recomputing on episodes moved the headline from
44% to **38% (11 of 29 occasions)**. The lower figure is the honest one, and it keeps the
story page and the insights page agreeing on what counts as a distinct contact. Ticket
counts remain displayed alongside so nothing is hidden.

**Percentages use a fixed 0–100% axis; counts may scale to maximum.** Never mixed. The
escalation chart originally scaled to maximum, rendering a three-point gap (36% versus
33%) as full-width versus 92% and implying a large difference. On a true axis the products
sit at roughly a third each.

**Every displayed rate shows its denominator.** `5/14`, `2/6`, `1/3` beside the label. This
is the single highest-value addition to the report: a reader calibrates their own trust
without a statistics footnote, and it forced a correction to the accompanying claim ,
Hardware's escalation *rate* is statistically indistinguishable from Broadband's, so the
defensible statement is the absolute count (5 escalations, more than every other product
combined), not the rate ranking.

**"Other" is pinned last in the Pareto.** It is a residual bucket, not a ranked category.
Sorting it by magnitude put it first and visually contradicted the report's own headline
finding. Its size , 28% of tickets carrying cause codes matching no theme , is itself
reported as a taxonomy gap to close before trusting root-cause reporting.

**Escalation is detected from recorded actions, not from the outcome field.** The outcome
is `OK` on almost every row and therefore carries no signal. Instead `analysis/insights.py`
concatenates three free-text fields , action, reference result and resolver , lowercases
them, and matches against a fifteen-term bilingual list (replace/austausch,
technician/techniker, forwarded/weitergeleitet, appointment/termin, ordered/bestellt,
commissioned/beauftragt, on site/vor ort, BI order, technik). This is keyword matching, so
the honest claim is narrower than the section heading suggests: it detects that **a heavier
intervention than a first-line fix was recorded**, not that the process formally escalated.

**Causes are grouped into themes** so German and English spellings of one problem do not
fragment the ranking. `src/taxonomy.py` defines six themes , WLAN / Wi-Fi, Connectivity,
Bandwidth / Speed, Hardware defect, Contract / Billing, Signal / Reception , matched
first-wins over case-insensitive substrings, with anything unmatched falling to
`RESIDUAL_THEME` ("Other"), which never headlines a finding and is charted last.

The taxonomy lives in a **top-level module with no `consts` import**, deliberately. The
storytelling engine, the deterministic fallback and the analysis therefore name a cause to
the reader with the same word , a story that says "Wi-Fi" and a chart that says "WLAN"
would read as two different systems. It began inside the insights module and was moved out
for exactly that reason.

The 28% of tickets landing in "Other" is the taxonomy-gap finding, and it is the same
finding as the cause-codes-name-remedies problem in 3.8, seen from the other end: the
cause column is not reliably a cause column.

**Small-sample honesty.** Resolution time and escalation rankings are presented as
directional. The method note states this, and the executive summary is constrained to
findings the computed data supports , an earlier version recommended redistributing team
load on the basis of concentration alone, which is not evidence of misallocation, since
the busiest team may simply be the correct specialist team.

---

## 5. Project structure and tests

```
app.py  conftest.py  pyproject.toml  uv.lock  Dockerfile  README.md
.streamlit/config.toml
data/Ticket Data (2).txt
docs/          implementation.md  user_guide.md
pages/         1_Story_Summary.py  2_Insights.py
src/
  consts.py  state.py  structs.py  taxonomy.py  version.py
  pipeline/    ingest.py  clean.py  mapping.py  export.py
  engine/      episodes.py  prompts.py  summarizer.py  structure.py
               validate.py  facts.py  fallback.py  schema.py
    providers/ base.py  anthropic.py  openai.py  gemini.py  deepseek.py  ollama.py
  analysis/    insights.py  exec_summary.py
  report/      story_report.py  insights_report.py  layout.py
  ui/          charts.py  components.py  story_view.py
tests/         15 files
```

Two boundaries are load-bearing. `src/taxonomy.py` sits above everything and imports
nothing from `consts`, so cause vocabulary is shared between the narrative and the
analysis (4.3). `src/engine/` is pure , pandas and constants only, no Streamlit , so the
whole storytelling pipeline is testable without a browser or a running app.

**178 tests, all offline** , no API key, no cost, no network:

| | | | |
|---|---|---|---|
| `test_reports.py` | 34 | `test_facts.py` | 12 |
| `test_validate.py` | 16 | `test_structure.py` | 12 |
| `test_fallback.py` | 15 | `test_summarizer.py` | 12 |
| `test_insights.py` | 15 | `test_providers.py` | 10 |
| `test_episodes.py` | 14 | `test_clean.py` | 9 |
| `test_robustness.py` | 11 | `test_exec_summary.py` | 6 |
| `test_ingest.py` | 4 | `test_story_view.py` | 4 |
| `test_mapping.py` | 3 | | |

The LLM path is exercised through inline fake providers that read the allowed tickets and
the assigned phases back out of the prompt, so the fakes are held to the same contract a
real model is asked to meet , a fake that ignored the payload would pass tests a real
model would fail.

---

## 6. Deviations and judgment calls

Consolidated for review; each is explained in context above.

| Decision | Rationale | Section |
|---|---|---|
| Product, not category, as summarisation unit | Brief is ambiguous; mapping must do something; per-category is too sparse | 2.1 |
| HDW added as its own product | Absent from the brief's table; 44% of usable data; dropping or folding both wrong | 2.2 |
| Brief's mapping followed despite description mismatch | Codes are presumably the real taxonomy; discrepancy documented not corrected | 2.3 |
| Customer feedback removed from phase guidance | No feedback field exists in 38 columns; the instruction caused invented sentiment | 3.7 |
| Positional phase assignment | Semantic choice produced different structures for equivalent data | 3.3 |
| One retry rather than an agentic loop | Deterministic layer already guarantees correctness; extra iterations buy coherence, not safety | 3.10 |
| Insights global, not per-customer | Key findings only exist at global scope; per-customer rates are noise | 4.1 |
| Repeat contacts recounted on episodes | Per-ticket count conflated concurrent tickets with genuine repeat contacts | 4.3 |

---

## 7. Known limitations and next steps

- **The deterministic fallback narrator always writes English.** `engine/fallback.py`
  produces templated prose ("4 tickets, all resolved. Causes: WLAN / Wi-Fi (3)"), so a
  German user with no provider configured gets German headings around English sentences.
  Fixing it needs a per-language phrase table plus a decision about the cause themes,
  which are deliberately shared with the Insights page , translating them there would
  desynchronise story vocabulary from analysis vocabulary (4.3). Left undone and recorded
  rather than half-done.
- **Escalation detection is keyword-based** across three free-text fields, so it supports
  the claim that a heavier intervention was recorded rather than that the process formally
  escalated (4.3).
- **Narrative faithfulness has no absolute guarantee.** The production path is an
  LLM-as-judge groundedness scorer per narrative sentence, described in 3.5 and not
  implemented at this sample size.
- **`later_incidents` is unreachable below five episodes**, and a new problem after a long
  gap may be titled "Follow-ups". Accepted trade-off; see 3.3.
- **Sample size.** 32 tickets across 3 customers over roughly two weeks. Resolution time
  and escalation rankings are directional; the metrics are built to be correct at scale
  rather than conclusive here.
- **Wording still varies by provider** when transport fallback fires mid-report, even
  though structure no longer does.
- **The column-shift anchor depends on `NETWORK_LEVEL` being constant `NZ`.** If a future
  export changes that column, the ladder needs revisiting; the constant and offsets are
  isolated in `consts.py` for exactly that reason.