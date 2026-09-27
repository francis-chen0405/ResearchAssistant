# Research, evidence, and storage invariants

These are current operational constraints for changes to the research pipeline and persisted results. Read them with [the architecture](../ARCHITECTURE.md) and [model settings](model-settings.md). This reference retains detailed current rules that do not fit the concise architecture overview.

## Frozen run identity and accounting

- Exact claim, enabled directions and providers, model routes and prices, policy/prompt/schema identities, budgets, and executable identity govern resume. A mismatch requires a new run. Compatible completed work may be reused; historical rows are never relabeled as v2.
- The seven active stages have independent model choices. Selected route, effort/thinking mode, credential provider, completion allowance, and conservative price cap are frozen. Historical Standard and low-level no-selection compatibility routes retain their documented behavior.
- Reserve calls, tokens, and exact decimal cost before every physical model attempt. Failed calls and retries count. Unknown outcomes retain conservative exposure; absent or invalid usage is never zero or a refund. The fresh-run ceilings are 160 calls and 500,000 tokens, with lower configured limits supported. Provider search and acquisition limits remain separate. Do not add synthetic per-call subscription prices.
- Completed usage uses verified endpoint/model-specific pricing, including applicable cache reads, writes, and long-context multipliers. Apply discounts only when model identity and usage metadata are verified. Unknown metadata/outcomes stay conservative. Historical costs are never recalculated.
- Deep analysis has a 60,000-token source allowance and a three-call envelope: at most two extraction attempts and one Analyst call. Preserve actual failed, rejected, and budget-prevented states; downstream capacity stays protected.

## Concurrency and cancellation

- Fresh deep analysis runs fixed priority-ordered waves of at most four sources. Dispatch only the largest prefix whose complete conservative envelopes fit the current call, token, cost, per-source, and downstream limits. Completion timing must not reorder semantic results.
- Each worker receives immutable typed inputs and returns a typed outcome. Workers do not mutate aggregate collections or share database connections, cursors, transactions, or mutable handoffs. Extraction, Analyst work, and deterministic admission remain sequential within each source.
- On cancellation, do not dispatch another wave. Cancel work that has not started, drain in-flight calls, retain their audit exposure, and do not write the aggregate completion artifact for a cancelled stage. Cancellation remains distinct from provider failure through invocation wrappers.
- Physical-call reconciliation uses the bounded typed bulk reader, validates the run-wide sequence and payload identity before filtering by source, preserves current/legacy key precedence, and retains missing usage conservatively.

## Source snapshots and quotations

- Source snapshots, Ledger records, and final artifacts are immutable. Preserve original, final, and canonical URLs and independently verified media provenance. Missing historical provenance remains unknown. Public URL/redirect validation is required; transport DNS is not socket-pinned. Digital PDFs require usable embedded text; OCR is not performed.
- Normalize supported source text deterministically and retain the 3,000-word snapshot cap. Search snippets, abstracts, recommendations, and Probe passages are not factual evidence.
- A quote must be an exact ordered passage from stored normalized text. Recheck its hash, offsets, immediate context, and explicit boundary/truncation markers. Do not fuzzy-repair, pad, replace a source, or paraphrase.
- The current word policy is 20 words for statistical claims and 30 for other claims. Frozen legacy fixture policy remains 50/100. Statistical classification requires both a digit and a whole-token marker. Keyword counts remain audit metadata even when zero.

## Admission, gaps, and final output

- Evidence Quality and Claim Fit are independent 1–5 scores. Both must be at least 2. Claim Fit 2 is qualified-only; Claim Fit 3 is ordinarily eligible. Do not let a derived Ledger score compensate for a failed axis. Preserve placement, entailment, and qualification unchanged; validate exact statement and provenance before assigning admission IDs.
- Fresh selection input explicitly requests conservative gap reporting and includes latest strategy coverage. Relevance of admitted evidence alone does not prove that a gap is resolved. Historical handoffs keep their legacy reporting semantics.
- Gap identity across rounds includes direction, claim dimension, and unsupported component. Round 4 coverage requires the original Gap ID, targeted Round-4 query provenance, Analyzer admission, and an explicit Analyst addressed-gap declaration.
- Round 4 requires a completed, non-degraded Round 3, material gaps in enabled directions, a typed Governor authorization, and full conservative reservation. It is limited to two provider lanes and two queries per lane per enabled direction (four queries per direction). There is no Round 5 or post-Round-4 Gap Analysis. Pre-authorization opportunities remain distinct from observed novelty/productivity.
- Rendering uses fixed application framing, approved connectives, and exact admitted statements. Unknown IDs, direction/placement/provenance drift, altered text, and invalid results block release and produce no release hash. Export revalidates released output. Fresh deterministic synthesis does not make a Reviewer call; results retain the not-independently-reviewed disclosure.

## SQLite, compatibility, and read-only access

- The current writable database remains schema 13 with its existing SQL, migration ordering, transaction/rollback behavior, descriptions, and immutability triggers. `ReadOnlyStore` supports compatible schema 7–13 databases using encoded URI `mode=ro`, foreign keys, and `query_only`, then validates integrity/schema.
- Read-only history/status/export never initializes or migrates, creates a missing file, or falls back to writable access. Do not use `immutable=1` where WAL writers may exist. Intentional writable run/resume is the existing migration boundary.
- Each v2 status request owns one validated read-only session and passes its connection through all status, progress, diagnostic, budget, provider, and terminal reconstruction readers. The session and validation result do not survive the request. Imported terminal results use the database path the user opened. Later polls see new commits.
- The browser starts its next poll 1.5 seconds after the preceding request completes, stops after terminal state, and cancels pending work on run replacement or unmount. Journal mode and busy-timeout defaults are unchanged.
- Historical provider, Reviewer-backed, portfolio/Governor, fixture, inspection, and export contracts remain supported. Legacy SQLite `REAL` cost values retain compatibility; their historical precision cannot be recovered. Do not recalculate historical reports or silently change their interpretation.

## Security and packaged identity

- Credentials use native macOS Keychain or Windows Credential Manager. They do not enter logs, SQLite, exports, browser storage, or child-process arguments. The existing OpenAlex integration has a narrow upstream HTTPS query-string API-key exception. No automatic `.env` or shell-profile loading is permitted.
- The database-scoped `.mvp5.lock` covers an entire fresh run. The controller transfers ownership explicitly. Application workers use owned process groups/jobs; cancellation is cooperative at existing boundaries and an in-flight provider request may run to its deadline.
- Packaged identity covers root Python modules, recursive `agents`, `providers`, and `frontend` sources, and `prompts`. Frozen builds also hash executable bytes. Source/executable identity changes require new runs under the exact resume check; historical inspection/export remains available.
