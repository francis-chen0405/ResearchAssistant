# ResearchAssistant

ResearchAssistant is a source-backed research engine for examining a user claim. It searches for relevant material, preserves where evidence came from, tests whether it supports a narrow proposition, identifies gaps, and releases only validated conclusions.

Its core philosophy is simple: **search broadly, inspect evidence, identify gaps, adapt research, and release only validated conclusions.**

Fresh website and CLI runs use the production ResearchAssistant v2 pipeline. Historical runs remain readable under the pipeline version that produced them.

## Working copy

The current Codex checkout is under the synced OneDrive `GitHub/ResearchAssistant`
folder. Work from the repository root provided by the task; application data and runtime
paths must remain platform-appropriate and must not depend on this local checkout path.

## Desktop application

Phase 1 adds a packaged local macOS/Windows application using the existing research UI
and Python engine. See [desktop installation, data and build notes](desktop/README.md)
for artifacts, supported targets, history import and outstanding release checks. The
source-based launcher instructions below remain useful for development.

## Features

- **Research directions:** choose Support, Challenge, or both. A disabled direction is not researched or implied by the result.
- **Adaptive research:** an initial search is followed by evidence inspection, gap analysis, and targeted follow-up rounds when useful and within budget.
- **Evidence pipeline:** discovery → acquisition → immutable snapshots → passage extraction → Luna evidence analysis → deterministic admission → Ledger-backed synthesis.
- **Provenance:** source tracking, immutable hashes, evidence locations, research-round context, and stated limitations travel with the result.
- **Reliability:** restart-safe execution, deterministic validation, bounded model budgets, and compatibility with historical runs.

## Architecture

```text
Claim
  ↓
Planner
  ↓
Discovery
  ↓
Scout
  ↓
Acquisition
  ↓
Probe
  ↓
Gap Analysis
  ↓
Adaptive Search
  ↓
Evidence Analysis
  ↓
Analyzer Admission
  ↓
Synthesis
  ↓
Validated Result
```

Fresh v2 evidence is analyzer-admitted after deterministic checks and is explicitly labeled as not independently reviewer-approved. Historical Reviewer-backed runs remain readable.

## Models

| Task | Model |
| --- | --- |
| Planner / Search / Selection | MiMo-v2.5-Pro |
| Scout | MiMo-v2.5 |
| Gap Analysis / Evidence Analyst | GPT-5.6 Luna |
| Synthesis | Deterministic Python assembly |

## Providers

**LLM** OpenAI, Xiaomi

**Discovery:** OpenAlex, arXiv, PubMed, Exa, and SerpSearch.

**Metadata:** Crossref. Crossref provides metadata only; it is not evidence.

**Acquisition:** Wigolo, with Firecrawl as a fallback.

## Running locally

The local product consists of the loopback API and the Next.js web app in `web/`. Configure provider credentials through the local interface, start the local acquisition service when prompted, and submit a public, non-sensitive claim.

The repository also includes the CLI for local runs and inspection. See `--help` for available commands.

## Verification

Run the repository checks before shipping changes:

```bash
pytest
ruff check .
ruff format --check .
```

For the web app:

```bash
cd web
pnpm lint
pnpm build
```
