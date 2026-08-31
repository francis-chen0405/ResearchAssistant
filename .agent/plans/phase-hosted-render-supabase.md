# Hosted Render + Supabase Product Phase

Status: Authorized by the user on 2026-08-30; free staging profile and canonical worker
adapter verified locally, staging verification pending.

## Objective

Move the staging product boundary from local SQLite/Keychain operation to a no-payment
Render + Supabase deployment while preserving the existing typed research pipeline,
immutable evidence/release artifacts, and historical local compatibility readers. Add
the viewport-first research workspace redesign required for the hosted product.

## Boundaries

- Render hosts two Free web services: the public Next.js web service and a public-but-
  JWT-protected FastAPI API service. The API embeds the leased worker in its single
  instance. Private services and standalone workers are deferred because they require
  payment. Render Cron, Postgres, Key Value, and Workflows are not part of v1.
- Supabase Auth supplies personal-account magic links; verified JWT identity is the
  only account identity. Supabase Postgres is the hosted source of truth, RLS is
  enabled on every account-owned table, and Vault-backed RPCs own provider secrets.
- Hosted browser calls are same-origin Next.js server-proxy calls to a configured public
  API URL. The service-role key, database credentials, and provider secrets never reach
  browser state, URLs, logs, artifacts, or build output. The API routes remain protected
  by verified Supabase JWTs even though the Free API service is publicly reachable.
- Hosted jobs have server-generated opaque IDs, durable queued/running/terminal
  state, leases, checkpoints, retries, cancellation, duplicate reconnect, and
  account ownership. Incomplete local runs migrate as history-only records.
- SQLite remains the persistence source of truth only for the legacy local product and
  migration reader. The hosted adapter may use a run-scoped ephemeral SQLite scratch
  database solely because the canonical v2 coordinator still exposes that internal
  persistence interface; hosted durable state and released artifacts remain in Supabase.
  Hosted execution never uses loopback services, macOS Keychain, or local service controls.

## Planned deliverables

- `hosted.py` typed auth, Supabase REST/RPC/Storage boundary, hosted run/job/artifact
  contracts, ownership checks, encrypted-credential metadata, and migration models.
- `frontend/hosted_api.py`, `render_api.py`, `hosted_worker.py`, and `hosted_canonical.py`
  for the authenticated API and embedded worker boundary.
  `CanonicalHostedPipelineExecutor` invokes the concrete
  `hosted_canonical:run_canonical_hosted_pipeline` adapter around the canonical v2
  coordinator; it never falls back to a local SQLite source of truth.
- `migrate_local_history.py` for read-only, fingerprinted, idempotent local history
  transfer over authenticated HTTPS without modifying the source database.
- `supabase/migrations/001_hosted_foundation.sql` with RLS, immutable artifacts,
  queue/lease RPCs, migration mapping, and Vault credential routines.
- `render.yaml` and `.env.hosted.example` for staging-only service wiring and secret
  separation.
- Focused Next.js components, same-origin auth/session routes, hosted API types,
  immediate workspace rendering, progress reconnect, account/provider settings,
  history/results, and migration UI with reduced-motion/accessibility support.
- Regression tests for auth/ownership/isolation, credentials, jobs, migration,
  immutable artifacts, hosted control mapping, and frontend source contracts.

## Verification and limitations

Python syntax, repository-wide explicit annotation checks, and local static contract checks
are complete. The complete Python and frontend checks plus hosted-boundary tests pass in a
dependency-complete checkout. Staging deployment, magic-link delivery, Supabase RLS
execution, Free web-service lifecycle, and real worker/provider smoke tests require configured
external accounts; they must pass before any production cutover. Free services may restart or
spin down after inactivity, so the embedded worker relies on durable Supabase leases and
checkpoints but is not a production substitute for a persistent worker. The worker loads its
`hosted_canonical:run_canonical_hosted_pipeline` adapter and never falls back to a local SQLite
source of truth. No production deployment or real-data migration was run.
