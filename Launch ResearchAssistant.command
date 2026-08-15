#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

WEB_URL="http://127.0.0.1:3000/"
API_URL="http://127.0.0.1:8765/api/health"

if [[ ! -x ".venv/bin/python" ]]; then
  osascript -e 'display alert "ResearchAssistant is not installed" message "Create .venv and install requirements.txt, then try again." as critical'
  exit 1
fi

if [[ ! -x "web/node_modules/.bin/next" || ! -f "web/.next/BUILD_ID" ]]; then
  osascript -e 'display alert "The website is not built" message "In the web folder, run pnpm install and pnpm run build once, then try again." as critical'
  exit 1
fi

API_PID=""
WEB_PID=""

cleanup() {
  if [[ -n "$WEB_PID" ]] && kill -0 "$WEB_PID" 2>/dev/null; then
    kill -TERM "$WEB_PID" 2>/dev/null || true
  fi
  if [[ -n "$API_PID" ]] && kill -0 "$API_PID" 2>/dev/null; then
    kill -TERM "$API_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

export PATH="$SCRIPT_DIR/.venv/bin:$PATH"
export NEXT_TELEMETRY_DISABLED=1

if ! /usr/sbin/lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  "$SCRIPT_DIR/.venv/bin/python" -m frontend.api &
  API_PID=$!
fi

if ! /usr/sbin/lsof -nP -iTCP:3000 -sTCP:LISTEN >/dev/null 2>&1; then
  (
    cd "$SCRIPT_DIR/web"
    "$SCRIPT_DIR/web/node_modules/.bin/next" start --hostname 127.0.0.1 --port 3000
  ) &
  WEB_PID=$!
fi

for _ in {1..45}; do
  if /usr/bin/curl --fail --silent "$API_URL" >/dev/null 2>&1 && \
     /usr/bin/curl --fail --silent "$WEB_URL" >/dev/null 2>&1; then
    open "$WEB_URL"
    break
  fi
  sleep 1
done

if ! /usr/bin/curl --fail --silent "$API_URL" >/dev/null 2>&1 || \
   ! /usr/bin/curl --fail --silent "$WEB_URL" >/dev/null 2>&1; then
  osascript -e 'display alert "ResearchAssistant could not start" message "The local website or research service did not become ready. Check this Terminal window for details." as critical'
  exit 1
fi

if [[ -n "$WEB_PID" ]]; then
  wait "$WEB_PID"
elif [[ -n "$API_PID" ]]; then
  wait "$API_PID"
fi
