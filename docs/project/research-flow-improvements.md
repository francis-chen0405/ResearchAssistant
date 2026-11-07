# ResearchAssistant search and progress improvements

## Overview

ResearchAssistant still runs a full investigation and produces a validated report.
The changes bring promising sources onto the progress page earlier and reduce
time spent waiting between search, screening, capture, and evidence assessment.

## 1. Give each search provider a first pass

- Give each eligible provider one results-page opportunity before deeper paging.
- Reserve some shared result capacity for providers still waiting for their turn.
- Treat a search and its required metadata lookup as one logical page.
- Save completed pages and continuation positions so deeper retrieval can resume.
- Continue past empty pages and known failures within the existing budgets.
- A request with an unknown outcome keeps its reservation and stops new dispatch.

On a tight cap, a shortened SERP Search page may end that query to avoid skipping
results. Other queries can use any capacity that remains.

## 2. Rank sources for the exact claim

- Favor sources that appear to measure the right outcome in the relevant population,
  setting, or intervention, with a meaningful comparison when the claim needs one.
- Give original data and public reports the same opportunity as research papers.
- Apply the same relevance standard to supporting, null, and contrary findings.
- Treat a search direction as a record of how the source was found.

Scout screens titles, abstracts, and other discovery metadata.

| Decision | Meaning |
| --- | --- |
| Retrieve | The metadata gives concrete reasons to expect direct evidence. |
| Maybe | The source could help, but the metadata leaves something material unclear. |
| Skip | The metadata shows little plausible value for the exact claim. |

Promising Maybes and credible counterevidence can move up the capture queue.
Verified copies share a publication identity. Distinct publications retain their
own citations, and the report identifies confirmed shared data where available.
A verified fuller copy can replace a truncated capture before final analysis.
The old assessment and the new quotation each retain their original snapshot.

## 3. Overlap search, capture, and early assessment

- Scout can start from saved first-page results while deeper pages are still running.
- Capture starts after the first eligible Scout batch. Later results can improve
  the priority of work that has yet to start.
- Three capture slots are the starting default. Five slots were exercised offline.
- Each capture opens a link, extracts readable page or PDF text, and checks that
  there is enough usable text to proceed.
- Reuse verified HTML when it already contains the article. Use browser rendering
  or an eligible fallback when needed, with separate limits on browser work.
- Up to three early assessment workers take readable sources as they become ready.
  Each extracts an exact passage and then assesses that passage for the claim.
- Save per-attempt capture timings, outcomes, and source ownership for restart
  and later benchmarking.

One initial Gap Analysis call looks at the ranked early set of up to four sources.
It can start while unrelated captures are still running. Follow-up search waits
for those captures to settle. A plausible late match defers only the matching
gap for assessment, so other authorized gaps can still get their own search.

Rounds without a yielded text page, graph-only rounds, and previously bound
serial runs use the complete search pool.

## 4. Show sources while the investigation runs

- Replace the **Discovery so far** diagnostics block with **Sources found so far**.
- Show up to seven unique works in a compact layout that matches the progress page.
- Aim for four strongest matches, two distinct angles, and one promising newcomer.
- Start with ranked leads and update cards as durable records become available.
- Show **Lead**, **Screened**, **Text captured**, **Full text**, **Assessed**, or
  **Admitted** according to the latest recorded state.
- Hold the list in place during hover, keyboard focus, or open source details.
- Use **All sources** to revisit earlier finds during and after the run.
- Keep exact passages in the evidence views, where they can be read with their
  original citation and context.

## Verification and remaining work

All four changes passed independent offline review. Production fixtures
covered page ordering, quota sharing, capture and assessment overlap, Gap
Analysis, cancellation, restart, and exact quotation provenance.

The shortlist passed the browser smoke test at desktop and narrow widths.
A regression confirms that conflicting DOI records stay separate across rounds.
Verified mirrors still share a card and can upgrade its readable link.

In the October 30 baseline run, providers returned leads in about 23 seconds,
the first Scout batch finished in about a minute, and the report took 11:09.
Those are observations from the earlier workflow. The new flow's live speed
and source quality remain to be measured in the comparative benchmark.

The comparison will track time to a source a reviewer would actually cite,
time to a completed report, and the usefulness of independent sources found.
Google Search or Scholar and ChatGPT Deep Research are the planned comparisons.
Use the same claims and review time, with the tool names hidden during source
grading.

See [project status](STATUS.md) for the latest verification and release state.
