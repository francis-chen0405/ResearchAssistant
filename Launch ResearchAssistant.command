#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

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

export PATH="$SCRIPT_DIR/.venv/bin:$PATH"
exec "$SCRIPT_DIR/.venv/bin/streamlit" run "$SCRIPT_DIR/frontend/live_app.py" \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  --server.headless false
