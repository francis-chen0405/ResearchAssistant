# Run 1 initial-planner rejection — October 21, 2026

Read-only review of run `7a38a9c4-e164-4b77-976c-296910da0252`, claim
“Biodiversity loss increases the risk of species extinction”. It failed after
31.50 seconds at `claim_planner`, before any provider search or source acquisition.
All nine saved artifact payload SHA-256 values verify. No application source,
installed bundle, saved research or charges were changed by this review. No paid
research or retry was run.

## Observed failure

The sole `gpt-6-luna-xhigh` model attempt returned a response that failed the semantic
schema at `queries.[6].required_concepts.[3]:value_error`: seventh query, fourth
required-concept group. The live `V2QueryConceptGroup.unique_aliases` validator rejects
blank concepts/aliases or duplicates after trimming and case folding. Each of those
three categories reproduces the exact saved diagnostic offline. The raw invalid
response is not persisted, so the specific offending string/category cannot be
recovered from these artifacts. Do not claim a specific duplicate term was observed.

The physical completion records 2,792 input tokens, 3,223 output tokens (6,015 total)
and $0.001960425 known cost. Remaining budget: 493,985 tokens, 159 physical calls and
$0.498039575. This was a known schema rejection, not budget exhaustion, a timeout,
source cap or an unknown request outcome. Eight previous-run leads were offered to
planning, but none was searched or assessed.

Both the stage and production failure checkpoints retain the rejection. Initial
planning dispatches only attempt 1 and immediately propagates a failed outcome;
there is no bounded schema-repair attempt. Reopening the failed run cannot manufacture
a valid plan or reissue the completed call automatically.

## Consequence and proposed next repair

Search queries, retrieval attempts, snapshots, candidates and ledger records are all
zero. The source-loss, compact selection, paper-identity and source-analysis changes
were never reached. This run supplies no evidence about their live quality or the
broad-versus-specific wording comparison.

Before another user-paid run, address planner resilience: remove only semantically
redundant alias duplicates/empty aliases with an explicit recorded normalization;
keep blank primary concepts and unsafe syntax invalid. Add precise owned error codes
without logging untrusted response contents. Consider one journaled repair attempt
only for a known completed invalid response, within existing stage/run reserves.
Never retry unknown dispatches, expand budgets, skip missing required concepts or
rewrite this failed run. Verify replay, invalid-plan refusal, repair bounds and exact
query semantics offline before packaging another app. This is a proposed repair,
not implemented by this review.
