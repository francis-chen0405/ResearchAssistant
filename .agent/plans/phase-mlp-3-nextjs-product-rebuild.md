# MLP-3 — Next.js Product Rebuild

Status: Complete and verified on 2026-08-14. The user approved the dependency set,
full live-product migration, and retirement of the superseded live Streamlit surface.

## Authority and intent

The user explicitly authorized building the redesign in this task on 2026-08-14. MLP-3
replaces the live Streamlit product experience with a clean-slate Next.js application.
The visual language is named **Quiet Momentum**: warm, contemporary, restrained, and
slightly playful, with purposeful motion that makes research progress feel alive without
overstating what the product does.

The recently completed MLP-2 Streamlit interface is behavior reference material only.
Its layout, component shapes, spacing, colors, typography, CSS, and page composition must
not be copied or used as the starting point for the new design.

## Product direction

- Use an off-white canvas, near-black type, muted neutral structure, and one restrained
  signal accent. Favor editorial typography, generous space, fine rules, and modest
  corner radii over dashboard chrome.
- Build five coherent product states: new research, active research, released brief,
  history, and local provider setup. Keep operational details in a secondary Advanced
  surface.
- Use Motion for React for view transitions, navigation state, claim-input focus,
  button feedback, staged progress, restrained number changes, result reveal, history
  continuity, citation emphasis, and reduced-motion behavior.
- Keep animation subordinate to state and meaning. Do not add WebGL, decorative floating
  cards, a custom cursor, scroll choreography, sound, particles, or an elaborate launch
  sequence.
- Write honest copy: the product researches a claim, shows both sides, preserves sources,
  and releases a deterministic brief after validation. It is not marketed as an oracle,
  autonomous truth engine, or human-research replacement.

## Architecture boundary

- Add a Next.js App Router application under `web/`; it owns presentation, interaction,
  responsive behavior, and browser-side polling only.
- Add a small typed Python HTTP adapter under `frontend/` that binds only to loopback and
  delegates to the existing `LiveResearchController`, `WigoloServiceManager`, and
  Keychain credential functions.
- Keep SQLite and the existing Python controller authoritative for run state, progress,
  history, cancellation, final brief contents, hashes, budgets, and resume behavior.
- Serialize strict Pydantic request and response models only at the HTTP boundary. Do not
  pass raw dictionaries between internal Python services.
- Never return provider secrets. Credential input is transient, is sent only to the
  loopback API, is saved through the existing macOS Keychain boundary, and is not stored
  in URLs, browser persistence, logs, SQLite, repository files, or child-process argv.
- Restrict accepted browser origins and hosts to the configured local Next.js and Python
  loopback addresses. Fail closed for other hosts or origins.
- Keep Streamlit only for fixture replay and the read-only Evidence Browser. The user's
  full live-product migration direction authorizes retiring the superseded live page
  after Next.js parity verification passes.

## Proposed dependencies requiring explicit approval

Python runtime:

- `fastapi>=0.115,<1.0`
- `uvicorn>=0.30,<1.0`

JavaScript runtime:

- `next>=16,<17`
- `react>=19.2,<20`
- `react-dom>=19.2,<20`
- `motion>=12,<13`

JavaScript development tooling:

- `typescript>=5.9,<6`
- `eslint>=9,<10`
- `eslint-config-next>=16,<17`
- compatible `@types/node`, `@types/react`, and `@types/react-dom` packages

The phase uses the existing package manager available in the workspace. Tailwind, GSAP,
Three.js, component kits, icon packs, browser-test frameworks, ORMs, and new Python HTTP
clients are not part of the proposed dependency set.

The user approved this complete dependency set on 2026-08-14. Record the resolved
versions in the lockfile and the final dependency ranges in repository documentation.

## Implementation sequence

1. Add regression tests for strict API models, loopback host/origin enforcement, secret
   non-disclosure, controller delegation, history, cancellation, service management,
   and credential setup.
2. Implement the typed loopback adapter without changing the research pipeline.
3. Establish the clean-slate Next.js design system, semantic layout, responsive shell,
   motion tokens, and reduced-motion behavior.
4. Implement new research, progress, released brief, history, provider setup, and
   Advanced experiences against the loopback API.
5. Update the local launcher so one user action starts the required local processes and
   opens the Next.js product. Preserve clear failure messages and owned-process cleanup.
6. Update the README, setup instructions, architecture/current-state documentation, and
   tests so the Next.js product is the default live experience. Keep Streamlit wording
   only where it accurately describes the fixture replay tool or migration history.
7. Verify desktop and narrow layouts in a real browser, including keyboard navigation,
   focus visibility, motion reduction, empty/error/cancelled/blocked/released states,
   and no accidental horizontal overflow.

## Explicitly out of scope

- Research-pipeline, evidence-policy, validator, provider-routing, budget, fingerprint,
  persistence, or SQLite schema changes
- Accounts, identity, cloud sync, hosting, deployment, telemetry, or analytics
- New providers, background daemons beyond the existing owned Wigolo process, or public
  network binding
- Visual reuse of the MLP-2 Streamlit implementation
- Removing the fixture-only Streamlit tool or its dependency

## Completion record

- The strict local API, all five product states, provider setup, Advanced controls,
  launcher, documentation, and migrated live-product tests are complete.
- The live Streamlit page was retired after parity verification; fixture replay and the
  Evidence Browser remain intact.
- Focused regression: 29 passed. Full offline suite: 612 passed, 2 expected opt-in skips.
- Ruff lint/format, frontend lint and production build, launcher syntax,
  `git diff --check`, and desktop/390px browser QA passed.
- No database migration, provider call/spending, research pipeline, release policy,
  hosting, account, cloud, telemetry, or analytics change occurred.
- No later phase is authorized.

## Acceptance and verification

- Existing databases and released runs remain readable and unchanged.
- Website-created runs use `DEFAULT_RESEARCH_CONTROLS` and the existing controller's
  exact budget, locking, fingerprint, cancellation, and release behavior.
- No secret appears in an API response, URL, browser storage, log, SQLite record,
  repository file, or acquisition child-process environment/arguments.
- The full Python suite, Ruff checks, frontend lint, TypeScript/build checks, launcher
  syntax checks, and `git diff --check` pass.
- Desktop and mobile browser QA demonstrates a visually independent design, complete
  core flows, meaningful motion, reduced-motion support, keyboard operation, and clear
  terminal/error states.
- `STATUS.md` and `HANDOFF.md` record changes, verification, unresolved items, dependency
  additions, and the next authorized boundary before MLP-3 is called complete.
