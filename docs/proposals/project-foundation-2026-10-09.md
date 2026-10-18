# Project review and foundation proposal

Reviewed October 9, 2026 against `94a241b` and the working tree. This is a completed analysis and proposed implementation sequence; the repairs and relocation below have not been implemented.

Four GPT-6.1 Sol reviewers covered architecture (xhigh), research quality (xhigh), runtime reliability (high), and frontend/delivery (medium). The primary reviewer checked their findings against source and independently reran the defect probes. The advisory graph was checked against the current checkout. The 17 pre-existing staged root-file deletions were preserved.

## Judgment

The project has substantial integrity engineering: immutable evidence, exact quotations, conservative cost accounting, historical reads, durable checkpoints, native credential storage, and isolated desktop rendering. Those foundations are worth preserving.

Its main weaknesses are fragmented ownership, checkout-dependent packaging, concentrated UI/application logic, several lifecycle and acquisition defects, and limited evidence of real research quality. A broad rewrite would discard useful safeguards. A coordinated repository migration followed by focused decomposition is the better investment.

[DebateAI](https://github.com/justinwen4/DebateAI) provides the useful visual reference: a small root with recognizable application folders. ResearchAssistant needs more areas because it includes a native app, historical storage and an evaluation suite. Copy the clarity of ownership; keep the folders justified by this product.

## Repairs to make before relocating their owners

### 1. Continue acquisition after a successful but unusable capture

**Confirmed source-loss defect.** [Acquisition](../../backend/src/researchassistant/agents/v2_acquisition.py) returns the first nonempty response at line 666, while the caller checks capture usability later at line 343. At line 297 it also marks alternate URLs as acquired before establishing usability.

An offline probe uses production clustering for two locations with the same DOI and production acquisition under the current preview policy. A preferred location containing only `OSF` produces one request and zero usable sources, despite an available substantive alternate. An empty preferred response instead produces two requests and one usable source.

**Repair:** introduce a successor acquisition policy that checks capture usability inside the bounded location/method loop. Preserve each snapshot and physical attempt; distinguish attempted, acquired and usable locations. Continue to an allowed alternate within existing request, cost, cancellation and time limits. Keep historical policy behavior and resume compatibility explicit.

**Acceptance:** shell→usable alternate succeeds; all-unusable, budget exhaustion and cancellation terminate correctly; known-PDF preference remains; prior snapshots and accounting remain inspectable. Do not equate low claim relevance with an unreadable capture or use retrying to seek a preferred conclusion.

### 2. Report rejected resume attempts without showing a nonexistent worker

**Confirmed status defect.** [Live controller](../../backend/src/researchassistant/api/live_service.py), lines 360–438, prioritizes persisted progress and discards cached worker outcomes. An interrupted run can remain `running` on disk. Resuming it with changed metadata depth correctly returns `invalid_input`, but subsequent polling returns `running`, deletes the rejection cache, and reports no active worker.

The independently repeated probe uses real production orchestration, persisted reservations and compatibility checks, with fake transports. The rejected resume makes zero model/search calls.

**Repair:** reconcile persisted research state with the latest execution-attempt outcome and actual worker ownership. Present the rejected resume clearly while retaining the original run as historical/interrupted state. Do not rewrite its evidence, frozen settings or previous result to represent the rejected attempt. A restart must not turn an orphaned `running` row into a claim of active execution.

**Acceptance:** interrupted run + changed settings shows rejection; interrupted run after app restart is distinguishable from a live worker; valid running and completed runs retain their existing behavior.

### 3. Make service lifecycle changes atomic with research startup

**Confirmed race at the endpoint boundary.** [Service stop](../../backend/src/researchassistant/api/api.py), lines 1410–1417, checks for active runs and stops acquisition in separate operations. A deterministic scheduled interleaving lets research become active between those operations; the endpoint returns 200 and stops the service.

This probe uses boundary doubles to force the interleaving; it is not evidence of a previously observed native incident.

**Repair:** give one application lifecycle coordinator authority over research admission and service-changing operations. Use a shared atomic gate rather than independent check-then-act calls. Review credential/configuration mutations for the same pattern without assuming each has a reproduced defect.

**Acceptance:** concurrent start/stop has one valid ordering: stop completes before admission, or stop is rejected while research owns the service. Exercise contention and cancellation without real provider calls.

### 4. Bound desktop shutdown when a child does not exit

**Confirmed missing recovery path.** [Desktop shell](../../desktop/main.cjs), lines 103–109, closes backend stdin and waits indefinitely for exit. Further quit requests are prevented. A probe of the actual handler with a non-exiting child confirms no shutdown timer or termination escalation is installed.

**Repair:** allow graceful cancellation/draining first, then use a bounded deadline and platform-appropriate termination of owned processes. The deadline must account for existing provider and controller shutdown allowances. Preserve unknown-attempt reservations and recoverable database state after forced interruption.

**Acceptance:** normal quit drains safely; stalled startup/shutdown can exit; repeat quit is well-defined; owned children do not remain orphaned. Verify native behavior separately from the handler test.

## Target repository layout

```text
backend/
  pyproject.toml              # installable Python distribution
  requirements*.txt
  src/researchassistant/
    api/                     # routes, HTTP schemas, authentication
    application/             # lifecycle, workers, history/progress views
    contracts/
    research/                # orchestration and stage implementations
    providers/
    evidence/                # admission, rendering, exports
    storage/
    platform_support/
    runtime/
    common/
    compatibility/           # historical execution support
    resources/               # prompts and other packaged resources
frontend/                    # current web/, Next.js only
desktop/                     # Electron and native packaging
tests/                       # grouped gradually by subsystem
evaluations/                 # quality and integrity benchmarks
docs/
  project/                   # current architecture/status/decisions/handoff
  proposals/
  verification/
  archive/
scripts/                     # launchers, development and benchmark tools
.github/
.agent/                      # one plan index; retained historical plans
README.md
AGENTS.md
pyproject.toml                # workspace test/lint configuration
```

Normal Git configuration files remain at root. Temporary compatibility launchers may remain during migration; they are an explicit transition exception, not implementation owners. Existing import facades can be installed under `backend/src/`, including old `agents`, `providers`, and Python `frontend` namespaces where needed. They re-export canonical objects rather than duplicate implementation. Retiring the filesystem command `python cli.py` requires a documented console-command replacement and intentional compatibility decision.

The current index has 18 root files after the staged deletions. The main visible improvement is consolidating Python code beneath `backend/`, renaming `web/` to `frontend/`, and placing project records under `docs/project/`. Keep the existing useful contracts/research/evidence/storage divisions.

### Migration constraints

- [README](../../README.md), line 30, explicitly says editable installation is unsupported. Introduce explicit build configuration, package discovery, console entry points and resource inclusion; test installation outside the checkout.
- [Executable identity](../../backend/src/researchassistant/runtime/application_runtime.py), lines 28–61, hashes both paths and bytes. Relocation intentionally changes identity. Preserve incompatible-resume rejection and historical inspection/export; do not disguise the move by weakening identity checks.
- [Desktop build](../../desktop/build.py), lines 87–126, hardcodes renderer paths and Python source staging. Update packaging, resource discovery, launchers, tests and CI together. Validate the complete identity/resource manifest in the frozen app.
- Prompt relocation must be explicitly included in the migration plan. Preserve prompt bytes, font bytes and policy meanings; replace checkout-ancestry lookups with package resource resolution.
- Preserve historical documents and archive snapshots. Update current links and instruction pointers, checking links before removing old locations. Root README should explain purpose, installation and the folder map, then link to detailed documents.

## Internal boundaries to improve

| Area | Verified problem | Proposed boundary |
| --- | --- | --- |
| Python API | `frontend/api.py`: 1,431 lines; HTTP handling mixed with result assembly | Routers by runs/history/evidence/settings; application services own projections and lifecycle |
| UI | `web/app/page.tsx`: 78,233 bytes, 783 lines, 23 state hooks; some JSX lines exceed 7,600 characters | Research, results, history and settings features; dedicated polling/preferences hooks; multiline formatting |
| Shared contracts | `contracts/query_retrieval.py:10` and `contracts/neighborhood.py:10–11` import provider-owned types | Neutral data contracts consumed by adapters, storage and research |
| Historical support | Exports import the 4,241-line historical orchestrator; shared renderer/synthesizer also serve v2 | Separate historical reading from historical execution; retain shared rendering in evidence |
| Active research | Adaptive search: 2,252 lines; Round 4: 1,775 lines | Separate planning, durable execution/checkpoints and summaries at existing typed handoffs |
| Persistence | Store: 3,218 lines; research contracts: 2,563 lines | Later split by coherent responsibility while preserving transactions, validators and public exports |

The architecture scan found no cycles among direct top-level imports in 136 Python runtime files. Including lazy/type imports exposed coupled groups. This is a layering concern, not evidence of a startup failure. Guardrails should ratchet down existing exceptions rather than declare every current dependency invalid.

Generate or mechanically check frontend API types against backend response schemas. The present TypeScript client asserts returned JSON as `T`; this review did not find a concrete response mismatch. Preserve the five existing offline browser smokes and add an independent fast frontend CI job so routine UI validation does not depend on native bundling. Keep native CI for integration and packaging.

## Research quality and the next improvements

Current tests strongly exercise integrity. They do not establish that real searches find the best sources or that current model interpretations are reliable. The 38-case historical evaluation uses frozen observations; the separate six-scenario discovery evaluation uses authored fixtures and does not run model selection, Analyst or admission. Some discovery scenarios use capacity above product defaults.

The next quality foundation should combine frozen real provider responses and source snapshots, human relevance/entailment labels, production-stage replay and held-out topics. Measure useful-source recall/precision, readable captures, source independence, supported findings, cost and elapsed time. Report unavailable measurements explicitly. Offline replay can establish regression behavior; new live collection needs its own bounded allowance.

Prioritize these improvements after the relevant foundations are ready:

1. **Explain source loss.** Track useful URLs through provider return, normalization, ranking, Scout, capture, selection and admission. Show the user discovered sources and exclusion/readability reasons even when no final evidence is admitted. Keep leads clearly separate from validated evidence.
2. **Measure broader search formulations.** Current SERP compilation quotes every concept and requests verbatim mode. That behavior is verified; its recall cost is unmeasured. Compare concise ordinary wording and selective phrase matching at equal budgets before changing defaults. The existing [web-discovery proposal](web-discovery-quality-2026-10-09.md) provides a detailed experiment design.
3. **Make integrations easier to extend.** Give provider adapters stable neutral request/response contracts and conformance fixtures. A new provider should not require edits throughout orchestration, persistence and UI.
4. **Improve result usefulness and onboarding.** Prioritize readable findings, qualifications and next steps; keep full audit detail accessible. Use representative claims and existing offline browser fixtures to test complete setup→research→result/history flows.
5. **Finish distribution acceptance.** The October 9 local Mac install is documented as successful. Signed/notarized distribution, clean-machine/minimum-OS testing, installed cache acceptance and Windows verification remain separate delivery work. Fresh GitHub Actions outcomes were not verified in this review.

General autonomous search controllers, OCR, additional providers and more expensive models should follow measured bottlenecks. Repository cleanliness alone does not establish product quality.

## Implementation order and completion gates

1. **Repair the four reproduced defects**, with focused regressions. Keep behavior changes separate from relocation.
2. **Prepare installable packaging and resource/identity handling**, then consolidate backend and rename the renderer. Update build/CI/launch paths in the same coherent migration.
3. **Clean current documentation and enforce the root layout.** README, ARCHITECTURE and the current plan index contain stale installed-app statements that contradict STATUS. Keep one owner for delivery facts and check links.
4. **Split API and frontend features**, then neutralize shared contracts and historical inspection dependencies. Address adaptive-search/storage internals in subsequent small changes.
5. **Build the quality benchmark and source-loss view**, then evaluate search and acquisition improvements against it.

Foundation completion means: the agreed root is enforced; a fresh backend installation and CLI/API work from an unrelated directory; compatibility imports resolve to canonical objects; packaged resources and identity are complete; prior fixtures remain inspectable/exportable; incompatible resumes fail clearly; lifecycle/fallback regressions pass; existing offline/browser/native checks pass on their applicable platforms. Mechanical relocation does not require a paid research run. A claim of improved live research quality does require quality evidence.

## Verification performed

- Full Python suite: **2,232 passed, 3 skipped**, 182.54 seconds.
- Ruff lint and formatting: passed, **295 Python files** after the staged deletions. Staged and unstaged whitespace checks passed.
- Frontend ESLint and TypeScript: passed using existing local validator binaries. The package-manager launcher first attempted an unavailable registry lookup; no dependency changes were made.
- Historical offline evaluation: **38 cases passed**; live comparison remained disabled.
- Research reviewer: 41 targeted acquisition/preview/ranking/evaluation tests passed. Runtime reviewer: 183 focused lifecycle/concurrency/security/compatibility/recovery tests passed. These overlap the full suite and are not additional unique-test totals.
- Primary reviewer independently repeated the acquisition, rejected-resume, service-stop interleaving and non-exiting-child probes. The latter two deliberately simulate adverse scheduling/process behavior.

No paid calls, user-data changes, installation, commit, push or publication occurred. Native installer/clean-machine checks, live source quality and the remote CI state were not revalidated. The only repository artifact added by this review is this proposal.

The subsequent [implementation prompt pack](project-foundation-implementation-prompts/README.md) turns the remaining work into standalone, scoped tasks. It was created after this review; its existence does not mark those tasks complete.
