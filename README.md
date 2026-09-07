# ResearchAssistant

ResearchAssistant is a local desktop application for source-backed research on a claim.
Choose Support, Challenge, or both. The existing v2 pipeline searches, acquires sources,
preserves exact evidence and provenance, investigates gaps within budget, and releases
only deterministically validated results. Historical runs remain readable and exportable.
Provider calls run in the local Python backend; there is no hosted application backend.

## Install and run

macOS test artifacts contain ResearchAssistant.app in a DMG/ZIP. Windows uses a per-user
NSIS installer. End users need no Python, Node or Docker. See
[desktop instructions](desktop/README.md) for installation, native credential storage,
data locations, importing history, recovery, supported targets and release limitations.
Unsigned builds are test artifacts; Windows installation and public-release gates must
be verified on their native targets.

## Develop and verify

Use Python 3.12, Node 24.18.0 and the committed dependency locks. From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -c desktop/constraints.txt -r requirements.txt -r desktop/requirements-build.txt pytest ruff
pnpm --dir web install --frozen-lockfile
npm ci --prefix desktop
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
git diff --check
pnpm --dir web lint
pnpm --dir web exec tsc --noEmit
```

On Windows use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.
The [desktop build guide](desktop/README.md#build-and-verification-developersci-only)
covers the static web export, frozen backend, native runtime/window smokes and installers.
Build and smoke on both macOS and Windows; a macOS success cannot validate Windows.
Tests do not require paid provider calls; existing opt-in integration checks remain opt-in.

For browser development run `.venv/bin/python -m frontend.api` and, in another terminal,
`pnpm --dir web dev`. See [frontend developer notes](frontend/README.md).
Use `.venv/bin/python cli.py --help` for the preserved fixture, inspection, export and
live CLI entry points. Provider secrets are entered through the existing setup flow;
never add them to source files, database exports or shell-profile loading.

## Read next

- [Architecture](ARCHITECTURE.md): module ownership, research flow and invariants.
- [Conventions](CONVENTIONS.md) and [decisions](DECISIONS.md): contracts and rationale.
- [Status](STATUS.md), [handoff](HANDOFF.md), [active plan](.agent/PLANS.md): current work and verification.
- [Historical archive](docs/archive/README.md): exact replaced documents and completed plans.

Phase 2 cleanup is complete. The Phase 3 frontend redesign has not started. The former
README is preserved in [the archive](docs/archive/pre-phase-2/README.md); current operating
instructions above and the desktop guide replace its older launcher-first descriptions.
