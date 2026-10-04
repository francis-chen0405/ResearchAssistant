# Historical read regressions

These synthetic, redacted fixtures preserve the verified contract drift in the
repository schema-13 history. They are regression inputs, not repaired user
records or evidence that the original database is corrupt. Current SQLite
integrity, foreign-key and recorded-schema checks remain authoritative.

| File | Recognized recorded formats |
| --- | --- |
| `native-ledger-august2.json` | Both August 2 Ledger cases: EQ/CF/score 4, secondary placement, original `Strong`, phase8 Analyst-v1/Reviewer-v2. Exact schema/prompt/policy identities are recorded with a canonical provider contract. |
| `legacy-researcher-trails.json` | The two schema/prompt identity pairs in `LEGACY_TRAIL_IDENTITIES`, with the exact policy catalog in `LEGACY_TRAIL_POLICIES`: historical web academic-study intent and the pre-relaxation discard floor 20. The later relaxed policy retains floor 5. |
| `v2-prior-policy-artifacts.json` | Queue caps 12/7; phase-12 extraction v1/v2; phase-9 Analyst v1/v2; phase-10 Reviewer v1/v2; phase-12 backfill-v1 containing historical queue/Reviewer/Analyst wrappers. A phase-13 backfill/admission case covers unchanged current nested decoding. |

Run, candidate, snapshot and source identifiers and URLs are replaced consistently
with synthetic UUIDs or `example.invalid` URLs. Claims, source text and explanatory
prose are redacted. Snapshot replacement text retains lengths so offsets remain
meaningful; fixture snapshot hashes and references are recalculated consistently.
Fixture envelope hashes authenticate the redacted JSON, and provider fingerprints
authenticate the redacted canonical contract. Those fixture hashes are explicitly
synthetic; no stored hash or row in the original database was changed. Recorded
policy names, enum values, caps, scores, prompt versions and exact accounting
amounts retain their historical meaning. No credential or provider access is
needed to run the tests.

The native old intent and ranking rules were verified against retained source
before `9f10e73`; the August release-v1 connective text was verified against
`1fc21a8:agents/renderer.py`. Native stage envelopes do not have an independent
payload-hash column: their existing provider fingerprint, embedded snapshot hashes
and original final-release hash are checked where available, without inventing an
envelope hash. V2 envelopes retain their existing SHA-256 validation.

`historical_decode.py` dispatches these read-only types explicitly. An absent
historical source cap or Analyst result policy stays unknown; the recorded input
policy supplies the old Analyst contract. Unknown policies, bad hashes, wrong
run ownership and malformed shapes produce typed per-record compatibility
results. Current admission, release validation and resume still use strict
current contracts. The tests exercise public browser, provider inspection, trail
and export reconstruction, alongside strict-current rejection of the old invalid
combinations and unchanged database bytes/mtime.
