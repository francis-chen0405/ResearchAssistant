# Database and reliability audit — November 24, 2026

The audit used read-only SQLite connections. No saved runs, evidence, provider settings,
or credentials were modified, and no model generations were requested.

## Coverage

- All 42 runs: 31 completed, 10 failed, and one cancelled.
- All 15,626 V2 artifacts: valid JSON, matching SHA-256 checksums, and matching run ownership.
- SQLite quick check passed; foreign-key check returned no violations; 18 schema migrations recorded.
- All 42 history, research-trail, terminal-state, and physical-call audit reads passed.
- All 31 released result/evidence reads passed, including 558 surviving-source records and 333 evidence display items.
- The database contains V2 history. Empty native legacy tables provide no evidence about pre-V2 compatibility.

## Accounting and discovery findings

There are 1,497 physical-call starts and 1,497 completions, with no pending or orphaned calls.
Of these, 1,403 calls succeeded and 94 failed. Thirty-nine failed calls have unknown usage;
their reservations remain conservative exposure, not confirmed spend.

The audit found no run or source quota breach. There were 1,140 source-attributed calls
across 542 run/source pairs; the highest observed source exposure was three calls and
59,234 tokens against a 60,000-token cap. Analyst route records cover all 556 Analyst
physical calls. Logical output-validation failures are separate from transport failures.

All 397 search outcomes had consistent provider and round identities. Sixty-seven search
failures were recorded with failure codes. Scout recorded nine fallback batches among
166 batch audits; smaller batches are a mitigation, not proof that truncation cannot recur.

## Implemented fixes

1. Connection-pool waits must spend only the remaining absolute request deadline.
   Offline regressions reproduced an overlong pool wait and dispatch after deadline expiry.
2. Budget-stop reading aids must show the saved stopping explanation rather than say
   the specific limit was unidentified. Signed released report text remains unchanged.
3. Exact complete captured-document mirrors no longer trigger redundant analysis in the same
   research direction. Confirmed examples include the Natick/Verona Centennial report
   in run `6850f986-3e8b-4b14-84eb-f2b631dec3cc` and two mirrored ALPR papers in run
   `2d234a95`. Similar titles, quotations, or hosts alone are insufficient to merge sources.
   Both progressive early analysis and backfill use a frozen policy and mirror plan;
   repeated callbacks and interrupted execution preserve the first retained owner.
4. New Scout plans use eight-source batches while old checkpointed plans retain their original 15- or 20-source layout.
5. Live Scout source projection uses the saved batch size rather than assuming 20.

## Limits

No audit can prove the absence of all bugs. External authentication failures, malformed
provider responses, protocol disruptions, and provider outages remain possible. The
historical transport records do not identify the responsible upstream component.
Unknown usage must not be released from budget exposure without evidence.

The user's excluded source-context verification, capture-classification changes, and
normalized cost-comparison work were not introduced. No semantic or fuzzy document
deduplication is proposed here.

## Verification

The long Python suite was interrupted after 2,941 outcomes. The remaining modules
were executed separately, followed by a combined 189-test rerun of all corrected
modules. Matching test IDs against the 3,465-item collection confirms complete coverage:
**3,456 passed, nine skipped, zero uncovered cases, zero remaining failures**.
Seven skips are native Windows checks unavailable on this Mac; two are opt-in live
model tests, which were not enabled. This is aggregate coverage across runs, not a
claim that a single uninterrupted suite or remote GitHub Actions run completed.

Full-suite testing also corrected stale tests for the approved Analyst/Extractor
prompt identities, the smaller Scout reservation envelope, provider-isolated recovery,
and synthetic distinct-publication fixture bodies. Historical fingerprint guards,
exact source-body assertions, and retry/no-repeat invariants remain tested.

- Frontend: 66 hook regressions passed; ESLint, TypeScript, and production webpack build passed.
- Desktop: 23 shutdown tests passed.
- API contracts, repository boundaries, Ruff, formatting, and whitespace checks passed.
- Rechecked all 31 released runs and 333 evidence display items with the changed code:
  every saved release remained valid and readable.

The changed implementation remains local for review and rebuilding. No real database
migrations, rewrites, external model generations, commits, or pushes were performed.
