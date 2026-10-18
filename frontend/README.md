# Renderer development

This folder owns the Next.js renderer. Python API/services are installed from
`backend/` under `researchassistant.api`; the historical Python `frontend` imports
remain backend-owned facades. See [architecture](../docs/project/ARCHITECTURE.md).

From the repository root, install the backend development environment as described
in [README](../README.md#install-and-develop), then run:

```sh
pnpm --dir frontend install --frozen-lockfile
.venv/bin/python -m researchassistant.api.api
# In another terminal:
pnpm --dir frontend dev
```

Use [API notes](../backend/src/researchassistant/api/README.md) for browser origins
and configuration. [The test map](../tests/README.md#desktop-and-renderer-checks)
lists lint, type, static export and offline browser checks; [desktop operations](../desktop/README.md)
owns bundled builds. [STATUS](../docs/project/STATUS.md) owns verification and delivery facts.

The page composes feature owners under `features/`: `research` owns start/poll/cancel,
`history` owns database-bound lists and run selection, `preferences` owns saved
settings/configuration and service controls, and `results` owns brief/evidence/trail
reads. Shared presentation and shell views remain under `shared` and `shell`.
`components/dialog.tsx` remains the native modal/focus/keyboard owner.

Fast checks run independently of desktop packaging:

```sh
python frontend/scripts/generate_api_contracts.py --check
python -m pytest tests/test_frontend_api_contracts.py
pnpm --dir frontend lint
pnpm --dir frontend exec tsc --noEmit
RESEARCHASSISTANT_DESKTOP=1 NEXT_PUBLIC_RESEARCH_API_URL= NEXT_TELEMETRY_DISABLED=1 pnpm --dir frontend exec next build --webpack
npm ci --prefix desktop/acquisition --ignore-scripts --no-audit --no-fund
node desktop/acquisition/node_modules/playwright/cli.js install chromium
pnpm --dir frontend smoke:offline
```

Linux CI installs Chromium's system dependencies with `install --with-deps chromium`.
The shared runner reuses all six `desktop/*smoke.cjs` offline fixtures and their
existing locked Playwright runtime; it needs neither frozen Python nor Electron.
Use `PLAYWRIGHT_BROWSERS_PATH` when exercising an existing desktop browser bundle.
No paid providers or research databases are used by these checks. With dependencies
already installed offline, add `--config.verify-deps-before-run=false` to pnpm.

Generated response types live under `lib/generated/`. Regenerate intentionally with
`python frontend/scripts/generate_api_contracts.py`, review, then run `--check` and
contract tests. Freeform catalog/serializer schemas are supplemented from their
existing backend models. TypeScript checks fields/enums/nullability; backend
validators own numerical bounds and successful JSON is not runtime-validated by the
client. Native packaging/install/signing checks remain in [desktop operations](../desktop/README.md).
