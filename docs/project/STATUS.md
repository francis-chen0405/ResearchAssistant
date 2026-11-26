# Project status

## What the app does

ResearchAssistant is a local desktop app for investigating a precise claim. It searches
for supporting and challenging sources, captures source text, checks exact quotations,
and produces evidence-backed reports within configured budgets. Saved research can be
inspected and released reports exported. Credentials stay in the operating system's
credential store; research data stays outside the application bundle.

## What currently works

Current source uses assessed findings to guide further searches, replaces unusable
sources within existing limits, captures later PDF pages with explicit omissions,
and performs a bounded follow-up when analysis leaves evidence gaps. Each fresh
post-analysis finding sample retains distinct recorded evidence relationships before
repeating a relationship, within the existing four-finding bound and failed-source
slots. Preferred late sources retain priority within each relationship. Each fresh
search round gives providers with eligible text queries a first-page opportunity
before deeper retrieval and reserves space for their results within the shared
retention cap. Reports retain source provenance, quotation checks and conservative
cost accounting. Fresh source ranking considers claim fit and study design, and Scout
receives the exact claim and available material gaps. Capture gives strong gap leads
and credible counterevidence an early chance within the same limits. A verified fuller
mirror can replace a truncated capture before final analysis, with both snapshots
retained. The report discloses confirmed shared data across distinct publications.
Model response reads recheck their original request and read-phase deadlines using
one-second socket waits, including after system wake. These waits never resend an
HTTP request. Fixed provider-capability failures stop bounded stage retries; invalid
model output remains eligible for the existing bounded repair.
Pending final-analysis sources receive a bounded preference for specific unresolved
material-gap leads from the latest completed coverage assessment. Movement is at most
two slots, within existing direction/recommendation/family constraints and comparable
preview relevance/type priorities. The decision is saved before dispatch and replayed
on resume; it adds no model calls and does not establish coverage or evidence quality.
Final source selection skips its model call when the complete validated survivor pool
fits the existing conservative analysis queue calculation before selection spending.
The saved queue records `selection_skip_reason=all_survivors_fit`, zero selection
attempts and no recommendations or fallback. Its empty attempt records reserve zero
selection calls, tokens and cost. Saved decisions replay without reconsidering the
branch; existing selection checkpoints retain their model/recovery path. Downstream
dispatch still checks current durable budgets. Early assessment now exposes ranked
Retrieve candidates within half its source allowance before Scout settles, retaining
the rest for later results and protecting pending higher-ranked capture slots. Final
analysis and post-analysis backfill refill independent Extraction and Analysis queues
as individual tasks settle. Full active source envelopes remain held through durable settlement;
versioned dispatch/result records preserve snapshot identity and execution order on
restart. Stage journals consume unknown outcomes without repeat, and cancellation
drains active work without aggregate completion. Offline regressions cover rolling
dispatch, durable source assignment order, cancellation and interrupted replay.
Later Search Agent requests now include deterministic, bounded per-gap observations
from saved query receipts, discovery provenance, acquisition attempts and assessed
findings. Explicit assessment links and discovery leads remain distinct; unknown
requests and provider errors never establish absent research. One immutable planning
input freezes the context, prompt guidance, lanes and query modes for adaptive and
Round-4 replay. Round 4 journals its existing single planning call; adaptive planning
keeps its two-attempt repair bound. Historical prompt files are unchanged. Frozen
legacy, conceptual and neighborhood inputs preserve their exact serialized variant
on replay; failed query receipts never establish that research is absent.
Stage concurrency is now controlled independently from ready demand: Scout 4–6,
Capture 4–6, Extraction 4–6 and Analysis 5–8, with sustained-demand expansion,
downstream backpressure and non-cancelling shrink. One run owner shares ten model
request slots, prioritizes pending Planner/Gap decisions, rotates other stages and
reduces/rebuilds provider capacity on explicit overload. Capacity waits precede new
attempt journals. Capture retains a separate six-transport ceiling and one browser.
New Scout plans use at most six candidates; recorded 8/15/20-source layouts remain
unchanged. Source allowances remain held through queued dependent Analysis. Offline
regressions exercise demand timing, shared admission, overload recovery, source
reservations and cancellation before dispatch. Atomic Analyst reservation can reuse
a completed result after a capacity wait without another physical request. The
all-fit selection branch preserves recorded same-direction gap targets without
creating recommendations. Live throughput and human research-quality acceptance
remain open; [review navigation](../../.agent/plans/fix-5-adaptive-concurrency.md).
The CLI defaults
remain 20 sources per direction and metadata search depth 50. The old native execution
engine is retired; historical inspection, evidence browsing and released exports
retain their original validation and hashes.

Fresh ranked rounds with optional text pagination give Scout the combined first-page
pool as soon as its receipts are durable. A screened work keeps its original discovery
identity and provenance. A verified late location can improve unstarted capture or
recover an incomplete snapshot under a separate owner. Rounds with no yielded text
page, graph-only rounds, and previously bound serial runs use the complete search pool.

Round 1 starts Gap Analysis when its ranked early set is settled. Outstanding captures
are explicit in that input, and the original input is replayed on restart. Follow-up
search waits for capture to settle. If a late source contains terms specific to a
proposed gap in the same direction, the existing post-analysis review assesses that
gap before searching for it again. Other authorized gaps remain eligible for adaptive search.

The desktop progress page shows up to seven promising works as soon as a ranked
first pass is saved. The cards show what Scout, capture, assessment and admission have
recorded so far. All sources keeps earlier finds available during and after the run.

In current source the renderer is redesigned (light and dark themes). Results lead
with a conservative evidence-picture label (rules in DECISIONS.md), then findings
grouped by relationship to the claim, sources, and a Method audit view; mirrors of one
publication merge for display. Released briefs export as Markdown, PDF or Word from the
result page through a read-only route. Runs that did not complete offer Resume and
Retry. Settings is one dialog. The redesign has passed offline renderer checks and
has a local packaged build; human acceptance remains open. Notifications were not added because
the app denies browser permission requests.

Progress screens preserve the last confirmed state when the connection fails and let
the user reconnect to the same run. Cancellation is confirmed by the backend before
the screen reports it as requested. Recorded source, renderer, browser and distribution
checks passed; see the [integration](../../.agent/plans/source-loss-recovery-2026-10-19.md#master-integration--october-23)
and [progress recovery](../../.agent/plans/recoverable-progress-polling-2026-10-23.md)
evidence. These are previously recorded results, not new installation or quality acceptance.

## Known problems and limits

The Apple Silicon ZIP candidate under `desktop/dist/` contains the combined scheduling
and search changes. Its archive integrity and all 298 packaged Python source files
match the reviewed working tree. Isolated wheel/editable installation, prompt resources,
worker cleanup and credential-free API construction are verified. Packaged startup
could not complete the OS credential-store roundtrip in this session; browser smokes
could not bind loopback ports, and DMG creation was blocked by the disk-image service.
The ZIP is unsigned and has not replaced the installed application.

The installed unsigned Mac build, `20261024.3`, includes the later PDF, post-analysis,
final CLI and progress recovery changes, plus the gap-analysis validation repair.
Harmless claim-label capitalization and whitespace differences bind to the original
coverage dimension; substantive validation failures use bounded retry/degraded handling.
Fresh selection corrects Cambridge review metadata only when the captured article's
title and DOI confirm its identity. Connection failures before HTTP dispatch retain
their reservations without blocking independent searches. Truly unknown outcomes
still block further dispatch and are disclosed as an interrupted search.
The packaged app passed isolated backend, settings, acquisition and window checks.
Saved research and provider preferences were unchanged through replacement. Human
research-quality acceptance and clean-machine testing remain open.

Comparative live evaluation of the new ranking and Scout remains pending. Actual IPBES PDF recapture and
human evaluation remain outstanding. An earlier Planner rejection remains an open
investigation. [The retry review](../verification/extinction-risk-retry-review-2026-10-21.md)
and [subsequent reporting repairs](../verification/selection-coverage-repairs-2026-10-21.md)
explain the evidence and partial progress. Current source reports an unknown later-page
outcome even when earlier pages returned results. First-page scheduling and this
reporting repair are current-source changes. [Manual asset review](../audits/2026-10-15/remaining-file-review.json)
also remains incomplete.

Windows packaging is manual-only. Its acquisition startup failure, interrupted-upgrade
repair and remaining native acceptance checks are open. Public release, Mac signing
and notarization, clean-machine/minimum-OS testing, and physical power-loss durability
remain unverified. [Windows evidence](../verification/windows-ci-durability-2026-10-13.md)
and [desktop operations](../../desktop/README.md) retain the specific gates.

## What comes next

Continue broader desktop acceptance and human research-quality testing on the installed
Mac build. Packaging and isolated acquisition readiness are verified, with the existing
deadline unchanged. Controlled live recapture and human evaluation remain needed;
the previous paid-test allowance is exhausted, so further paid work needs new explicit
authorization. Windows acceptance remains a separate delivery effort.

Preserve saved research, credentials, historical policies and exact resume compatibility
throughout. Unknown request outcomes must retain their reservations and must not
trigger duplicate calls. [Work navigation](../../.agent/PLANS.md) links follow-up owners;
[conventions](CONVENTIONS.md) govern changes and verification.
