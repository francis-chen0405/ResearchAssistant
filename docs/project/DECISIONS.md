# Current decisions

This file records decisions that still govern current behavior. The exact preceding decision history is preserved in the [2026-09-26 archive](https://github.com/francis-chen0405/ResearchAssistant/blob/archive-2026-10-23-docs-baseline/docs/archive/2026-09-26-maintenance/DECISIONS.md); older complete records are indexed in [the archive guide](https://github.com/francis-chen0405/ResearchAssistant/blob/archive-2026-10-23-docs-baseline/docs/archive/INDEX.md). Completed plan files remain authoritative evidence for their implementation details.

## Research execution

- [Source recovery](../../.agent/plans/source-loss-recovery-2026-10-19.md) feeds early assessed
  findings into adaptive search, uses exact bounded extraction views and replacement candidates,
  and considers prior paper metadata as leads requiring fresh assessment. Per-source and run
  limits remain hard; unknown model usage is never refunded. Recommendations without evidence
  remain provisional, and retained counts do not establish evidence sufficiency.

- [Resume status projection](../verification/resume-status-2026-10-10.md) separates
  saved run status from this controller's worker ownership. Attempt failures remain
  in a bounded ephemeral cache; polling never writes or relabels the saved run.
  Restart drops attempt text but exposes unfinished progress as interrupted with
  no worker in this app. Active execution and committed terminal artifacts stay
  authoritative; exact resume compatibility and conservative reservations remain required.

- The approved [ALPR equity fixes](../../.agent/plans/alpr-equity-run-fixes-2026-10-02.md) require usable substantive content before fresh selection/extraction, preserving explicit legacy Probe-v1. Fresh assessment-v2 binds a terminal evidence/coverage status after analysis into the rendered release; incomplete/missing coverage or low evidence yield remains limited regardless of the earlier search stop. Historical assessment-v1 serialization and exports remain unchanged. No automatic additional paid research follows reassessment. Recognized OSF/RePEc archive identifiers produce conservative related-work notices with DOI/version safeguards; readable title fallbacks and contextual relevance labels are derived presentation and do not rewrite snapshots, source families or admitted statements.

- The approved [private-surveillance repair](../../.agent/plans/private-surveillance-run-fixes-2026-10-02.md) separates new-policy evidence relationship from search provenance. Support-directed search may encounter challenging evidence and vice versa; disabled search lanes remain disabled. Valid unrelated assessments are relevance rejections. Legacy policy meanings, immutable artifacts and existing quote/quality/budget gates are preserved. Post-analysis evidence sufficiency is assessed separately from the earlier search-yield decision.

- Fresh website, API, and ordinary CLI requests select the v2 pipeline. Historical provider execution remains available only through the explicit `legacy_runner` dependency. See [explicit pipeline selection](../../.agent/plans/explicit-pipeline-selection.md).
- Fresh v2 stages import neutral source-evidence and Analyst helpers. Historical agent imports and the historical orchestrator remain supported compatibility surfaces. See [neutral evidence ownership](../../.agent/plans/neutral-evidence-ownership.md).
- Fresh deep analysis uses deterministic priority waves of at most four sources. Dispatch only a budget-safe priority prefix, do not share SQLite connections or mutable handoffs across workers, and drain in-flight work on cancellation. See [deep-analysis concurrency](../../.agent/plans/deep-analysis-deterministic-concurrency.md).
- Each of seven active model stages has an explicit selectable route. A selected choice, route settings, price cap, stage allowance, and run configuration participate in frozen identity. Defaults and the historical Standard profile remain distinct. See [per-step model choices](../../.agent/plans/per-step-model-choices.md) and [model settings](../model-settings.md).
- Physical provider attempts reserve their calls, tokens, and conservative cost before transport. Unknown or missing usage does not erase exposure. Historical costs and run identities are not rewritten.

## ALPR review fixes — 2026-10-01

The user-approved [A–G fixes](../../.agent/plans/alpr-run-fixes-2026-10-01.md) preserve immutable historical artifacts. Result presentation is derived read-only: admitted statements retain Ledger-bound citations, research direction and evidence relationship have separate labels, final source dispositions are distinct from selection history, and current stopping/coverage disclosures may supplement historical rendered text without regenerating it. Future physical completions may retain optional input/output/cache splits; unknown historical splits remain unknown. Study-lineage warnings disclose shared DOI metadata or possible title matches; they do not merge source-family IDs, count independence, change scoring, or infer verified identity from titles alone.

## Evidence, storage, and application boundaries

- Approved R37–R52 repairs preserve query-lane provenance independently from
  evidence relationship, version fresh quotation context/offset handling and
  admission wording, and make dependent stage/admission commits atomic. Old
  ranking-only recovery explicitly discloses lost Scout decisions and uses the
  existing ranking fallback without a replacement call; physical charges and
  unknown reservations remain immutable. Optional unrepresentable author metadata
  is omitted from bounded identity projection without truncating or rewriting the
  original observation. Native evidence integrity failures remain per-record
  read-only diagnostics. Historical rendering, policies and exact resume gates
  remain authoritative; no research budget or prompt is changed.


- [Prompt 12 ownership](../verification/contract-ownership-2026-10-10.md) places stable
  search/neighborhood, retrieval, extraction and historical result shapes in neutral
  contracts, retaining old public objects through re-exports. Pure query validation
  and metadata identity do not load research execution. Historical inspection is a
  validated storage reader; provider execution remains explicit through `legacy_runner`.
  All six restricted import exceptions have migrated, so contract/storage rules now
  also reject research imports. Storage's provider URL and saved-response parsing
  helpers remain allowed and documented. No prompt, released text, policy or stored
  fingerprint is converted; source changes require new runs under the exact gate.

- Read-only provider inspection can reconstruct the two recognized historical
  Planner families whose web queries retained academic-study intent. Decoding
  requires the recorded schema, prompt, policy and valid provider fingerprint;
  all original query values and run relationships remain checked. Ordinary Planner
  reads and resume remain strict, and historical Planner objects cannot be admitted
  through Planner/query persistence. Report exports supplement full verified
  database backups; unreleased research still needs its historical readers.

- [Desktop shutdown](../verification/desktop-shutdown-2026-10-10.md) starts with
  pipe EOF and preserves Python's 90-second drain under a single 150-second outer
  deadline. The 30-second whole-startup timeout uses the same teardown path.
  POSIX launchers stay in the backend group until a fresh PID/request acknowledgement
  permits detachment. Failed handoffs terminate the launcher without running acquisition.
  POSIX owns dedicated groups; Windows uses the backend handle and an enclosing
  kill-on-close Job before bootstrap. Teardown excludes native modal dialogs and
  never writes completion, deletes SQLite sidecars or refunds unknown reservations.

- Research admission and idle-only service/credential/import changes share one lifecycle
  coordinator. A short mutex orders reservations and the in-memory worker ownership check;
  slow work runs outside it. An admitted/pending worker blocks ordinary stop with 409,
  including during cancellation/draining. A change in progress blocks new admission until
  completion or failure; callers retry explicitly. Concurrent database workers, native-vault
  rules, exact process ownership and conservative audit reservations remain intact. See
  [the lifecycle verification](../verification/service-lifecycle-2026-10-10.md).

The user-approved [discrimination-run fixes](../../.agent/plans/discrimination-run-fixes-2026-10-01.md) exclude unrelated findings from new claim admission under versioned policy. Ordinary attributed/scoped statements pass the existing qualification gate; a qualification repair stays within the bounded Analyst allowance. Extraction retains the complete source once in the rendered input and uses the original snapshot for exact quotations. Oversized sources remain subject to existing caps; source cap blocks may be skipped while run-wide exhaustion still stops work. No passage truncation or increased allowance is introduced. Optional cache-write telemetry distinguishes reported counts from conservative pricing assumptions; historical unknown values remain unknown. UI source counts and stopping disclosures are derived read-only, and conservative mirror warnings never merge immutable source families or imply independent replication.

- Exact quotations, source provenance, separate Evidence Quality and Claim Fit scores, immutable Ledger/output artifacts, and deterministic final validation remain required. Analyzer Admission checks structure and policy; it is not independent proof of entailment.
- The completed [database integrity plan](../../.agent/plans/database-integrity-fixes.md) added schema 14 for nullable cache-token accounting fields. The [database review](../../.agent/plans/database-review-2026-10-03.md) advances writable databases through schema 18: migration 15 preserves cache-write tokens/cost basis, and migration 16 protects same-run ownership and referenced keys. Migration 17 adds measured history/evidence indexes. The approved October 15 fixes add migration 18 for v2 round-four admissions, preserving historical declarations, rows, triggers and indexes; read-only inspection supports schemas 7–18. Shared preflight rejects damaged schemas without repair; recognized writable upgrades retain verified recovery copies. History and status inspection use validated read-only access. Public reads own one validated snapshot; polling does not overlap requests. Retain full request-time validation and rollback journaling by default: the measured WAL speedup does not establish a safe checkpoint/sidecar lifecycle. Both modes have coherent-reader coverage. A one-second SQLite wait produces retryable contention diagnostics without replaying provider calls or reservations. See [SQLite status polling](../../.agent/plans/sqlite-status-polling.md).
- Desktop credentials remain in native macOS Keychain or Windows Credential Manager. Secrets are not placed in browser storage, logs, SQLite, exports, or child arguments. OpenAlex and optional PubMed API keys are sent to their respective upstream services in HTTPS query strings. Runtime data remains outside the application bundle and checkout.
- Package metadata uses the Python distribution name `researchassistant`, version `0.1.0`; user-facing CLI and application copy use `ResearchAssistant`. Streamlit remains outside the base install and is installed only through `backend/requirements-legacy.txt`. The `dev` dependency set includes `httpx2` for Starlette tests; versions are constrained in `desktop/constraints.txt`.
- Backend implementation modules use canonical `researchassistant.*` imports grouped by contracts, research, evidence, storage, platform support, runtime, and common helpers. Installed `models.py`, `store.py`, and `orchestrator.py` facades in `backend/src/` preserve legacy imports; `backend/src/cli.py` preserves the script launcher after installation. The identity surface must cover the organized package sources and bundled PDF font bytes. If a source or executable change alters the exact run identity, new research must use a new run; saved history is never rewritten and remains available for inspection/export.

## Source dispositions — Prompt 15

The [approved October 15 repairs](../verification/full-review-fixes-2026-10-15.md)
bind public result reads to the saved run/claim and original release hash. Fresh
metadata ranking v4 retains normalized cues and IPv6 identity while explicit v2/v3
dispatch preserves old scores and identities. Acquisition provenance v5 and PDF policy v2 identify protected public
connections/browser requests and an owned PDF worker. These source changes require
fresh research; saved artifacts, research judgment policies and unknown reservations
are not relabeled. The already installed/locked httpcore 1.0.9, ipaddr.js 1.9.1 and
Playwright 1.60.0 dependencies are now explicit for these integration boundaries.

`source-leads-view-v1` is a derived read-only projection of persisted same-run
metadata, Scout/ranking, capture/Probe, selection, analysis and admission records.
Missing stages remain unknown; search direction never determines evidence
relationship. This does not change query compiler v3, discovery policy v3, Probe v4,
budgets, prompts or admission. The independently testable improvement is access
to saved sources/reasons without a final brief. Useful recall and human readability
remain unmeasured; query relaxation remains a measured proposal pending genuine
responses and labels. New backend source identity requires fresh runs; historical
records and the frozen Prompt 14 authorization are never relabeled.

## Source discovery foundations

Fresh acquisition uses [Probe v4](../verification/acquisition-usable-fallback-2026-10-09.md)
to continue after unusable captures within existing URL/method/time budgets. Usability
is independent of claim relevance and evidence direction. Per-attempt response/snapshot
records commit before further work; completed captures replay without transport, while
unknown outcomes require a new run. Historical Probe v1–v3 behavior remains unchanged.

Fresh seed expansion uses v3 after the [limit investigation](../verification/citation-expansion-limits-2026-10-09.md):
completed graph responses consume shared retention, and exact replay retains its original
physical parse limit while acceptance respects current capacity. Prior seed-policy dispatch,
immutable attempts/provenance, conservative reservations and the 3/10/30 and shared OpenAlex
10-request/$0.01 ceilings remain. Existing bindings cannot be relabeled; changed source
requires a fresh run under the compatibility gate.

All six phases of the [source-discovery plan](../../.agent/plans/source-discovery-v2-2026-10-05.md) are implemented in current source. Phase 1 introduced an opt-in policy and immutable typed handoffs while retaining the prior production policy; Phase 6 subsequently activated product policy v3 for ordinary fresh runs. The phase notes below record how the current rules were established. [STATUS](STATUS.md) owns delivery and acceptance state. Metadata depth is independent of `sources_per_stance_per_round`. Fair allocation uses stable enabled lanes and protects downstream model capacity. Native capability declarations do not authorize unsupported adapter transport or overstate effective depth. The three-request logical bound includes retries and metadata subrequests; PubMed therefore has at most one complete two-request metadata page under that bound. Existing provider ceilings remain unchanged.

New checkpoints and physical reservations reuse `v2_artifacts`; historical fingerprints, contracts and source meanings retain their original interpretation. Incompatible new settings require a new run. Unknown outcomes keep conservative exposure and stop further requests; any future recovery semantics require a separately versioned policy. Discovery items, edges, scores and previews cannot authorize factual evidence admission. Current acquisition, extraction, Analyst and deterministic admission remain the evidence boundary.

Phase 3 extends fresh discovery with durable bounded pagination (default depth 20, maximum requested depth 50, no more than three physical attempts per operation), deterministic ranking from common metadata signals, fair Scout allocation and ranked acquisition shortlisting. Effective depth always respects executable provider capabilities and tighter request/cost budgets. Raw retention is capped at 300 per round and 1,000 per run; Scout is capped at 60 per round, in batches of at most 20 and at most two attempts per batch; acquisition is capped at 25 per round. Search direction is provenance only; rank never interprets support/challenge, missing fields remain neutral, and conflicting metadata is recorded rather than silently resolved. Identity grouping uses conservative work anchors and does not assert study independence. Every enabled direction/provider lane receives a first pass before repeated strategies consume retention headroom. Completed pages and independent parser receipts checkpoint durably; cancellation/resume does not replay completed or terminal pages, and substituted page candidates fail provenance checks. Exa uses an effective result cap of 25 with $0.02 default-depth and $0.03 policy-depth request reservations, while retaining the established $0.18 total /18-request ceiling. Phase 4 activates deterministic exact snapshot previews in fresh Probe v3/selection-v2, with bounded windows and separate acquisition-usability/relevance diagnostics. Historical Probe v1/v2 and selection-v1 preserve serialization, prompt bytes and policy meaning. Full rendered selection input including adapter overhead is capped at 24,000 tokens through an audited whole-source shortlist; omissions remain in the complete pool/queue, downstream source capacity is protected, and lower configured ceilings remain authoritative. All ranks, Scout dispositions, shortlists and previews remain discovery/selection metadata and cannot satisfy the acquisition, snapshot, exact-extraction, Analyst or admission gates.

Phase 5 activates OpenAlex exact scholarly identity lookup and provider-reported one-hop
references/citing/related discovery inside existing Round 2–4 lane slots and Governor
permission. Three owned relevant seeds, ten unique neighbors per seed and thirty per run
are maximums; remaining shared budgets dominate. Each HTTP request reserves from the existing
10-request/$0.01 OpenAlex envelope. No title-only identity, hidden retry or new graph quota.
Author observations may be compatible subsets when exact identifiers, title and year agree;
conflicting author sets and bibliographic identifiers remain unresolved. Identity aliases
are checked before seed caps and persisted edges, including IDs learned by exact resolution.
Fresh capability/seed/prompt/schema identities require a fresh run. Exact bounded response
bytes commit with completion; pure re-parsing validates checkpoints and raw candidates on
resume, and unknown outcomes cannot repeat. Graph action provenance replaces query text
without inventing a query or evidence snapshot. All candidates retain the ordinary snapshot,
quotation, Analyst and deterministic admission gates. Historical optional fields serialize
as before, and released history remains unchanged.

Phase 6 activates fresh product policy v3 for ordinary API/desktop/CLI requests, with
metadata depth 50, paper expansion enabled and lexical scholarly search by default.
User depth choices 10/20/50 are independent of the per-direction acquisition target
(5/10/20/30, default 20). Current product runs allow up to 60 acquired clusters per round
(30 for each enabled direction) and 240 survivors across four rounds; provider and
run budgets still dominate. Historical discovery policy caps remain unchanged. Automatic selects lexical
deterministically. Semantic requires selected OpenAlex and never enables an unselected
provider. Disabled expansion is enforced at offering, execution and durable policy validation.
Direct-v2 omission and the explicit legacy runner preserve their prior dispatch; missing
historical fields serialize as before. Changed controls require a fresh run. Optional counts
and trails are read-only presentation, and released text/hashes remain immutable. Synthetic
evaluations report acquisition failures and independence abstentions separately from discovery
recall; model selection/admission and live research quality are not measured by that runner.
Displayed seed-derived candidates count accepted expansion edges rather than rejected raw hits.
The evaluation requires exact fixture provider identities and keeps same-title works and
their acquisition URLs separate; missing or unknown IDs fail explicitly without title fallback.

## Release boundary

macOS remains the first release target and Windows public release is deferred. The five-submission paid acceptance allowance is exhausted; further live research requires new explicit authorization. The unsigned Mac candidate has not cleared live-quality acceptance, clean-machine installation, minimum-OS, signing, or notarization gates. [Prompt 17](../verification/windows-ci-durability-2026-10-13.md) records actual current-source Windows Server 2025/NTFS CI/native evidence and exact remaining limits; it does not authorize publication or substitute process termination for physical power-loss evidence. See [desktop operations](../../desktop/README.md) and the current [status](STATUS.md).

The preceding authorized release work is [current Mac build and release-gate verification](../../.agent/plans/mac-current-build-release-verification-2026-09-28.md). It does not renew the paid-test allowance or change research policy, persisted historical data, or the release boundary.

The preceding testing fix is [adaptive budget route failure](../../.agent/plans/reviewer-route-testing-fix-2026-10-01.md). It preserves deterministic final review, historical routing, and conservative budget protection.

The completed [comprehensive code audit](../../.agent/plans/comprehensive-code-audit-2026-10-01.md)
preserves those boundaries and adds verified integrity, accounting, lifecycle, and
UI repairs. Physical prompt reservations include adapter-added instructions;
presented actual usage comes from independently complete physical-call audits;
desktop exports use same-origin API requests. The [report](../audits/2026-10-01/README.md)
records verified local artifacts and coverage limits. Installation, live quality,
and signed-release acceptance remain separate from offline audit completion.

## Backend and renderer ownership — Prompt 08

The Python distribution lives in `backend/`, with one canonical implementation under
`backend/src/researchassistant/`. API/services use `researchassistant.api`, providers use
`researchassistant.providers`, agents use `researchassistant.agents`, and shared renderer/
synthesizer code remains in `researchassistant.evidence`. Historical namespaces under
`backend/src/` alias canonical module objects. The Next.js renderer owns root `frontend/`.

`tests/pyproject.toml` owns workspace checks; backend metadata and the self-contained
source-distribution build hook own installation. `scripts/build_distribution.py` remains
a workspace facade. Installed/frozen source identity binds the new logical backend
paths, exact configuration bytes, all source/prompt/font bytes, and frozen executable
bytes where applicable. No stored fingerprint is converted and resume gates are unchanged.
The CLI facade is `backend/src/cli.py` and the Mac command file is under `desktop/`; the historical
`.agents/PLANS/` record retains its path. Native app replacement and publication are
separate delivery actions.

## Approved full-review admission/capacity/CLI repairs — R34–R36

Keep admission and its checkpoint atomic without a schema change; preserve and
validate original relational-only prefixes rather than reconstructing their dates.
Use explicit selection/shortlist v3 for the four-round 100-source bound; enforce the
older 75-source limit on prior policies and keep all research/input budgets intact.
CLI configuration errors report owned safe field labels instead of Pydantic input
or context. Historical artifacts, prompt/scoring policies and resume gates remain
unchanged. Exact verification and the incomplete manual review are in the current
review record and STATUS.

## Approved R53–R55 recovery and presentation decisions

Persist bounded-stage intent before provider dispatch and save typed outcomes before
aggregate completion. Reuse known outcomes under the exact saved request identity;
never infer an unsaved model decision from a completed cost audit or repeat an
unknown call. Keep original selection quotas/budget inputs, attempt counts and
reservations, while admitting future physical calls against current durable global
accounting. New checkpoints use the existing immutable artifact boundary.

Use explicit relationship-aware synthesis v2 and evidence validator v4 for new
Analyzer output. Search direction remains provenance. Preserve historical template
text, released hashes and omitted optional fields; retain existing qualification
warnings and prohibit Analyzer relationship labels on historical Reviewer records.
The full-review report owns remaining findings, and STATUS owns actual validation.

Approved R56–R59 retain exact Source Selection input/budget/shortlist and the initial
Planner request/outcome, reuse completed work and stop on unknown outcomes. Preserve
original plan dates and recover consistent partial plan publications. Selection
queue accounting subtracts its recorded attempts once from its original balance;
new calls remain subject to current durable limits. The checkout launcher uses a
45-second monotonic readiness deadline independent of Electron. Maintain current
guides against live schema/security/identity owners; archived records remain exact.

## Folders-only root — October 18

The user requested only folders and README at the repository root. Keep the ten
existing folder owners and README; instructions live in `.agent/AGENTS.md`, linked
from README. Workspace checks use `tests/pyproject.toml`: run `python -m pytest tests`
and pass `--config tests/pyproject.toml` to Ruff from the repository root. CI uses
those same explicit paths; coverage passes `--cov-config=tests/pyproject.toml`.

Each owner has its own ignore and LF rules, so a fresh clone retains generated-file
and nested private-input exclusions without a root Git configuration file. Existing
checkout-only root data remains protected by local Git exclusions and is untouched.
The Mac checkout launcher resolves its parent from `desktop/`; the duplicate root
CLI wrapper is removed in favor of the byte-identical installed/backend facade.
Backend metadata, runtime resources, source identity and the installed app are unchanged.

## Approved selection coverage, article identity and reporting — October 21

Keep full source provenance locally while sending a versioned compact source view
through both ordinary and native model renderers. Bound preview bytes with exact
snapshot offsets and disclose omissions. Preserve the 24,000-token input ceiling,
existing reservations and recommendation/analysis distinction; do not fill a quota.
Expose considered/omitted counts so a small recommendation list cannot imply full
comparative coverage.

Collapse confirmed retained mirrors before early/final assessment using consistent
DOI anchors plus matching full normalized titles. Preserve search directions and the
earliest round's canonical identity, every immutable snapshot and all original URLs.
Never relabel quotations from another snapshot or count mirror locations as independent
studies. Uncertain identities remain separate. New policy/code identities require a
fresh run rather than changing saved evidence judgments.

Derive blocked/unknown query counts from durable receipts and physical starts; keep
saved stop text/artifacts untouched and add truthful live diagnostics. Unknown request
outcomes retain their conservative accounting and stop further provider dispatch.
Offline replay verifies coverage and accounting mechanics, not research-quality gain.
