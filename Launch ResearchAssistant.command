#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if /usr/sbin/lsof -nP -iTCP:8501 -sTCP:LISTEN >/dev/null 2>&1; then
  open "http://127.0.0.1:8501/"
  exit 0
fi

if [[ ! -x ".venv/bin/streamlit" ]]; then
  osascript -e 'display alert "ResearchAssistant is not installed" message "Create .venv and install requirements.txt once, then double-click this launcher again." as critical'
  exit 1
fi

if [[ -z "${MIMO_API_KEY:-}" ]]; then
  MIMO_API_KEY="$(osascript -e 'display dialog "Enter MIMO_API_KEY for this launch. It will stay only in the local server process and will not be saved." default answer "" with hidden answer buttons {"Cancel", "Launch"} default button "Launch"' -e 'text returned of result')"
  if [[ -z "$MIMO_API_KEY" ]]; then
    osascript -e 'display alert "MIMO_API_KEY is required" as warning'
    exit 1
  fi
  export MIMO_API_KEY
fi

if [[ -z "${EXA_API_KEY:-}" ]]; then
  EXA_API_KEY="$(osascript -e 'display dialog "Enter EXA_API_KEY for search. It will stay only in the local server process and will not be saved." default answer "" with hidden answer buttons {"Cancel", "Continue"} default button "Continue"' -e 'text returned of result')"
  if [[ -z "$EXA_API_KEY" ]]; then
    osascript -e 'display alert "EXA_API_KEY is required" as warning'
    exit 1
  fi
  export EXA_API_KEY
fi

if [[ -z "${FIRECRAWL_API_KEY:-}" ]]; then
  FIRECRAWL_API_KEY="$(osascript -e 'display dialog "Optional: enter FIRECRAWL_API_KEY to enable automatic fallback when Wigolo cannot extract a public page. Leave blank to use Wigolo only." default answer "" with hidden answer buttons {"Cancel", "Continue"} default button "Continue"' -e 'text returned of result')"
  if [[ -n "$FIRECRAWL_API_KEY" ]]; then
    export FIRECRAWL_API_KEY
  fi
fi

export PATH="$SCRIPT_DIR/.venv/bin:$PATH"
"$SCRIPT_DIR/.venv/bin/streamlit" run "$SCRIPT_DIR/frontend/live_app.py" \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  --server.headless true &
STREAMLIT_PID=$!

for _ in {1..30}; do
  if /usr/sbin/lsof -nP -iTCP:8501 -sTCP:LISTEN >/dev/null 2>&1; then
    open "http://127.0.0.1:8501/"
    break
  fi
  sleep 1
done

wait "$STREAMLIT_PID"
