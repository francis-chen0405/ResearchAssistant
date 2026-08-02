# Local Frontends

ResearchAssistant keeps its offline fixture demonstration clearly separate from the live
website.

## Live research website

On macOS, double-click `Launch ResearchAssistant.command` in the repository root. If
`MIMO_API_KEY` is not already present in the launcher environment, a native hidden-input
dialog requests it for that launch only. The launcher starts the local Streamlit server
and opens the browser; its Terminal window/server process must remain running while the
website is open.

The page can start and health-check pinned Wigolo `0.2.1` with native SearXNG, run or
compatibly resume direct `mimo-v2.5-pro` research, inspect persisted history, show live
checkpoints/usage/cost/supporting/opposing progress, cooperatively cancel, and copy or
download a released validated brief.

First-time setup still requires Python 3.11 or 3.12, the declared requirements, Node.js
20+, and enough local space for Wigolo/SearXNG resources. The Start stack control runs
the pinned `npx -y wigolo@0.2.1 serve` command on loopback with native SearXNG settings.
Only application-owned children can be stopped from the page. An unrelated listener on
port 8000 is never killed.

The website reads `MIMO_API_KEY` only from its explicitly supplied process environment.
It never renders, logs, persists, downloads, or passes the key in command arguments. It
does not load `.env` or shell profiles. Claims must be public and non-sensitive. Every
released brief requires human review.

Manual launch for development is:

```bash
MIMO_API_KEY="..." .venv/bin/streamlit run frontend/live_app.py
```

## Fixture-only website

This is a minimal local Streamlit wrapper around the Phase 6 fixture-only pipeline. It
never uses MiMo, Wigolo, live search, or provider credentials.

Launch from the repository root:

```bash
streamlit run frontend/streamlit_app.py
```

The fixture UI discovers directories under `tests/fixtures/`, runs the existing offline
pipeline, and displays released or blocked status, final brief text when released,
validation errors, hashes, output paths, artifact counts, and audit metadata.
