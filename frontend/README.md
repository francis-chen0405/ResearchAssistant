# Phase 7A Local Frontend

This is a minimal local Streamlit wrapper around the Phase 6 fixture-only pipeline.

Launch from the repository root:

```bash
streamlit run frontend/streamlit_app.py
```

The UI discovers fixture directories under `tests/fixtures/`, runs the existing offline
pipeline, and displays released or blocked status, final brief text when released,
validation errors, hashes, output paths, artifact counts, and audit metadata.
