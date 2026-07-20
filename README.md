# 🎫 System Ticket Data Summary

A Streamlit app that turns a raw system-ticket export into two things a
support manager can actually use: a **five-phase written story per customer
per product**, and a **deterministic operational analysis** (repeat-contact
rate, escalation rate, root-cause Pareto, team load) with one recommendation
per finding.

It works with **zero configuration and zero API keys** — the built-in
deterministic engine produces a grounded, factual view straight from the
tickets. Adding a provider key upgrades that view to narrated prose; nothing
else changes.

## What it does

Upload a ticket export (`.txt` / `.csv`) on the **Home** page, or click
**Load bundled sample** to try it with the sample file in `data/`. The
pipeline ingests, cleans, and category-filters the file once, caches the
result, and stages it for the other two pages:

- **📖 Story Summary** — pick a customer, a language (English/German), and a
  provider. For each product that customer has tickets in, the tickets are
  clustered into episodes by time gap and written up across up to five
  phases (Initial Issue → Follow-ups → Developments → Later Incidents →
  Recent Events). Every phase is grounded in real ticket numbers, dates, and
  outcomes — the model narrates, it does not invent. Downloadable as a
  standalone HTML report (prints straight to PDF) or Markdown.
- **📊 Insights** — KPIs and per-finding cards (chart + "So what →"
  recommendation) computed directly in pandas, so it scales from the 32-row
  sample to a full export unchanged. An optional LLM-written executive
  summary sits on top of the same numbers. Downloadable as a standalone HTML
  report.
- **🏠 Home** — upload, see the cleaning/removal report, preview the cleaned
  table, and download it as CSV or Excel.

## Getting started

This project uses [uv](https://docs.astral.sh/uv/) for dependency management
(there's a committed `uv.lock`).

```bash
uv sync                        # core deps only — app runs fully, LLM-free
streamlit run app.py
```

Then open the URL Streamlit prints, upload a file (or load the bundled
sample), and move to **Story Summary** / **Insights** in the sidebar.

To enable real narrated storytelling, install the LLM extra and configure at
least one provider (see below):

```bash
uv sync --extra llm
```

### Running the tests

```bash
uv run pytest
```

## Configuring an LLM provider (optional)

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in
your key(s). `secrets.toml` is gitignored — never commit real keys:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
OPENAI_API_KEY    = "sk-..."
GEMINI_API_KEY    = "..."
DEEPSEEK_API_KEY  = "..."
```

Environment variables of the same name work too (e.g. for Docker/cloud
deployment) and are used as a fallback if `secrets.toml` doesn't set them. A
provider only shows up in the dropdown once its key **and** SDK are both
present — a missing one is silently skipped, never an error.

Supported providers: **Anthropic**, **OpenAI**, **Gemini**, **DeepSeek**, and
**Ollama** (local, free, no key — just have `ollama serve` running with a
model pulled). Fallback between providers is **transport-only**: a timeout,
rate-limit, or missing key moves to the next provider in the chain; a content
problem does not silently swap voices. With no provider available at all, the
app renders its deterministic grounded view instead of failing.

## Project layout

```
app.py                  Home page — upload, clean, stage the data
pages/
  1_Story_Summary.py    Per-customer, per-product five-phase stories
  2_Insights.py          Deterministic KPIs, findings, executive summary
src/
  pipeline/              ingest -> clean -> map (raw export -> tidy DataFrame)
  engine/                episodes, prompts, schema, validation, providers,
                         LLM-free fallback — the storytelling engine
  analysis/              insights.py (pandas-only business analysis)
  report/                standalone HTML report builders
  ui/                    Streamlit widgets, charts, story rendering
  consts.py              single source of truth for column names, category
                         codes, phases, provider models, business rules
tests/                   pytest suite covering cleaning, episodes, providers,
                         validation, reports, and more
docs/
  implementation.md      measured findings about the source export that
                         shaped the code (anchor columns, phase logic, etc.)
data/                    bundled sample export
```

## Notes on the data

The source export has quirks that are documented — with evidence, not
guesses — in [`docs/implementation.md`](docs/implementation.md): a fixed
anchor column used to realign shifted rows, why the `CAUSE` field often names
a remedy rather than a fault, why story phases are assigned positionally
rather than "semantically," and how repeat contacts are counted in occasions
rather than raw ticket counts. Read that file before changing anything in
`src/pipeline/clean.py`, `src/engine/episodes.py`, or `src/analysis/insights.py`.
