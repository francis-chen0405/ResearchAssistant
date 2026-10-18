# Prompt 11 — renderer feature split and independent checks

## Scope

Root `frontend/` already owns Next.js after Prompt 08. This task preserves the
visible workflow, research settings/directions, cost and provenance disclosures,
native dialog keyboard/focus behavior and reduced motion. Research policy, backend
routes, prompt bytes, dependency versions/locks and native packaging remain unchanged.
Earlier staged/unstaged work is preserved.

The baseline root page had 784 physical lines, 78,539 bytes and 23 state hooks.
The composed page has 182 lines, 6,412 bytes and five shell state hooks; feature
state lives in the five focused hooks below. The API client shrank from 544 to
295 lines, with its generated wire definitions owned under `frontend/lib/generated/`.

## Feature ownership

| Owner | State/behavior | Views |
| --- | --- | --- |
| `frontend/app/page.tsx` | Navigation, modal visibility, notices and app connectivity; feature composition | Root shell |
| `features/preferences/` | Preference load/debounced ordered saves; model defaults; configuration request IDs/abort; service controls | Settings panel and service card |
| `features/research/` | Claim/acknowledgment; admission/start; sequential status polling; cancellation and terminal reset | Composer, starting view, progress and stance cards |
| `features/history/` | Database-bound list requests and selected-run request IDs; synchronous database/navigation invalidation | Saved history |
| `features/results/` | Released result/evidence and lazy research trail, guarded by disposal/abort | Brief, admitted evidence, source leads, coverage and trail |
| `features/shared/`, `features/shell/` | Display labels, model usage/cost disclosure and navigation | Welcome/header/notice |

Feature views keep their preceding text/classes/IDs/ARIA and event behavior.
Discovery candidates and preview passages remain separately labeled source leads;
only the existing Ledger-bound items appear as admitted evidence. Result views
remain keyed by database, run and classification.

## API contracts

`frontend/scripts/generate_api_contracts.py` produces
`frontend/lib/generated/api-contracts.ts` from the assembled backend OpenAPI.
`--check` fails on generated-byte drift. The client derives its wire types and
inline route response types from those schemas; a few UI projections select
catalog fields or require fields emitted by current FastAPI default serialization.
Nested historical optional fields retain their generated optional/null meanings.

OpenAPI's model-options response is freeform, so the generator uses its existing
`ModelOptionsPayload`. Wrap serializers advertise unstructured dictionaries for
some historical contracts; their existing validation models supply the field schemas.
These supplements are local to generation and do not modify the backend or OpenAPI.
The JSON decoder still trusts successful local API responses; TypeScript schema
checking is not runtime validation or an evidence admission gate.

`tests/test_frontend_api_contracts.py` checks live-schema byte parity and compiles
real offline HTTP payloads against renderer types, including released results,
evidence and trails. Negative type examples reject an invented lifecycle state and
an unadmitted preview used as evidence. The existing Prompt 10 fixture remains
immutable and checks all 21 route registrations, OpenAPI and 24 offline responses.

| Contract group | Before and after operations | HTTP change |
| --- | --- | --- |
| Health/catalog | GET health, model-profiles, model-options | None |
| Configuration/credentials | GET configuration; POST configuration/check, credentials, credentials/{name}/check, credentials/{name}/remove | None |
| Preferences | GET and POST preferences | None |
| Acquisition service | GET service; POST service/start, service/stop | None |
| History | GET history; POST history/import | None |
| Research lifecycle | POST research/start; GET research/{run_id}; POST research/{run_id}/cancel | None |
| Released inspection | GET research/{run_id}/trail, v2-result, v2-evidence | None |

All paths have the `/api/` prefix. Methods, paths, names, 200 response schemas,
request fields and session/host/origin checks match the unchanged pre-split fixture.
This task replaces hand-maintained renderer declarations; it does not establish
or claim a pre-existing HTTP mismatch.

## Fast versus native checks

`frontend/scripts/smoke.cjs` runs all five existing shared offline smokes sequentially.
The frontend CI job independently installs locked frontend dependencies and the
existing locked acquisition Playwright runtime with lifecycle scripts disabled,
then exports the UI, installs Chromium and exercises mocked local API responses.
It needs no frozen Python build, acquisition service, Electron or installer.
Backend schema generation/contract fixtures use the installed development package
with isolated fake providers. No dependency versions or lockfiles changed.

Desktop CI uses the same smoke runner after its bundled build and retains frozen
backend, native window/shutdown and unsigned installer jobs. Static export and
browser checks do not verify an installed app, a signed installer or notarization.

## Verification

Local macOS 26.6.2 arm64 / Python 3.12.14 results:

| Check | Result | Feedback path |
| --- | --- | --- |
| Generated contract byte check and representative payload compilation | 3 tests pass | Independent frontend CI |
| Frontend lint and TypeScript | Pass | Independent frontend CI |
| Static desktop export | Pass, `/` and `/_not-found` | Independent frontend CI |
| Five offline browser/API smokes | All pass | Shared runner in frontend and desktop CI |
| Affected API/credential/read/poll/evidence regressions | 90 pass | Python checks |
| Offline CLI/API subprocess regressions | 36 pass, 1 existing skip | Python checks |
| Full Python collection | 2,390 pass, 5 existing skips (2,395 collected), 210.25 s | Required repository check |
| Ruff lint/format, repository boundaries, staged/unstaged whitespace | Pass; 405 Python files formatted | Required repository checks |
| Desktop shutdown handlers | 20 pass | Native path retained |
| Local native process shutdown smoke | All 9 modes pass | Native path retained |

The final documentation audit checks 1,745 local links across 310 Markdown files:
zero active or completed-record failures; nine immutable archive references retain
their prior meaning. All three frontend/acquisition/desktop lock hashes match the
baseline. Required lint/format/boundary and staged/unstaged whitespace checks pass
after the documentation update.

Race results: configuration ignores both late success and late failure after a
selection changes. History ignores old-database lists, overlapping opens and
navigation during a pending open; changing the database clears old terminal
selection. Polling observes seven deterministic snapshots with a maximum of one
same-run request in flight, stops at terminal state and cleans up on replacement
or unmount. The extended history smoke observes two aborted requests for a pending
released result and research trail; their late payload/error cannot reappear after
returning home. Preference saves remain ordered and recover after a failed save.
Service readiness remains bounded. Keyboard dialog focus/Tab/Escape, transient
password fields, copy/export, cost/provenance, responsive sizing and static reduced
motion pass the existing broad smoke.

The first full run exposed two source assertions still aimed at the old page and
three subprocess deadline failures while a static build was competing for resources.
Assertions now target their actual feature owners without dropping expectations;
the subprocess subset and fresh full collection pass with loopback/process permissions. The native shutdown
retry also passes with process permissions after build contention ended.

No backend source, research policy, prompt bytes, dependency versions or lockfiles
changed in this task. The original staged binary diff remains byte-identical;
local `master` HEAD is still `94a241b`. No staging, commit or publication occurred.
The graph was refreshed and verified against live source. The prior installed app
and frozen/wheel verification belong to their preceding records. No current
installer, Electron window, Windows execution, signing or notarization was verified
here. Logs and the exact page/API baseline are under
`/private/tmp/researchassistant-prompt11/`.
