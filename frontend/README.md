# Local Frontends

ResearchAssistant keeps its offline fixture demonstration clearly separate from the live
website.

## Live research website

On macOS, double-click `Launch ResearchAssistant.command` in the repository root. Native
hidden-input dialogs request required `MIMO_API_KEY` and `EXA_API_KEY` values when absent,
plus an optional `FIRECRAWL_API_KEY`. Values last only for that launch. The launcher
starts the local Streamlit server and opens the browser; its Terminal window/server
process must remain running while the website is open.

The page uses Exa Search `auto` for discovery, can start and health-check pinned Wigolo
`0.2.1` for primary acquisition, and optionally falls back to Firecrawl for approved
Wigolo-local extraction failures. It can run or compatibly resume direct
`mimo-v2.5-pro` research, inspect persisted history, show live progress, cooperatively
cancel, and copy or download a released validated brief.

History and reopening use the store's validated SQLite read-only session. They never
initialize or migrate a database and never create a missing file. An older database is
left untouched and produces a migration-required message; migrate it intentionally by
starting or resuming a writable CLI or website run. Invalid, newer, corrupt, or
inaccessible databases also fail safely without writable fallback.

Before any local source request, ResearchAssistant validates the initial URL and every
redirect target under its public HTTP(S) and resolver policy. Wigolo receives only the
validated final preflight URL. Firecrawl-returned source and canonical URLs are untrusted
provider metadata and do not enter provenance unless they independently pass the same
policy. This closes known-target redirect SSRF exposure but does not pin validated DNS
answers to transport sockets, so complete DNS-rebinding prevention is not claimed.

First-time setup still requires Python 3.11 or 3.12, the declared requirements, Node.js
20+, and enough local space for Wigolo. The Start stack control runs the pinned
`npx -y wigolo@0.2.1 serve` command on loopback.
Only application-owned children can be stopped from the page. An unrelated listener on
port 8000 is never killed.

The website reads provider keys only from its explicitly supplied process environment.
It never renders, logs, persists, downloads, or passes them in command arguments. It
does not load `.env` or shell profiles. Claims must be public and non-sensitive. Every
released brief requires human review.

The displayed USD ceiling and estimated cost cover MiMo model calls. Exa search charges
and optional Firecrawl credits remain visible in their respective provider dashboards.

Manual launch for development is:

```bash
MIMO_API_KEY="..." EXA_API_KEY="..." FIRECRAWL_API_KEY="..." \
  .venv/bin/streamlit run frontend/live_app.py
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
