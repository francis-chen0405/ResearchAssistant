#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h:h}"
cd "$SCRIPT_DIR"

WEB_URL="http://127.0.0.1:3000/"
API_URL="http://127.0.0.1:8765/api/health"
EXPECTED_API_VERSION="mlp-5-v2-phase13-analyzer-admission"

if [[ ! -x ".venv/bin/python" ]]; then
  osascript -e 'display alert "ResearchAssistant is not installed" message "Create .venv and install -e ./backend, then try again." as critical'
  exit 1
fi

if [[ ! -x "frontend/node_modules/.bin/next" || ! -f "frontend/.next/BUILD_ID" ]]; then
  osascript -e 'display alert "The website is not built" message "In the frontend folder, run pnpm install and pnpm run build once, then try again." as critical'
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

STARTUP_DEADLINE=$("$SCRIPT_DIR/.venv/bin/python" -c 'import time; print(time.monotonic() + 45)')

request_timeout() {
  "$SCRIPT_DIR/.venv/bin/python" -c '
import sys, time
remaining = float(sys.argv[1]) - time.monotonic()
if remaining <= 0:
    sys.exit(1)
print(min(2.0, remaining))
' "$STARTUP_DEADLINE"
}

startup_failed() {
  osascript -e 'display alert "ResearchAssistant could not start" message "The local website or research service did not become ready. Check this Terminal window for details." as critical'
  exit 1
}

api_is_ready() {
  local timeout
  timeout=$(request_timeout) || return 1
  /usr/bin/curl --fail --silent --connect-timeout "$timeout" --max-time "$timeout" "$API_URL" |
    /usr/bin/grep -Fq "\"api_version\":\"$EXPECTED_API_VERSION\""
}

web_is_ready() {
  local timeout
  timeout=$(request_timeout) || return 1
  /usr/bin/curl --fail --silent --connect-timeout "$timeout" --max-time "$timeout" "$WEB_URL" >/dev/null 2>&1
}

if ! api_is_ready; then
  request_timeout >/dev/null || startup_failed
  for pid in ${(f)"$(/usr/sbin/lsof -nP -tiTCP:8765 -sTCP:LISTEN 2>/dev/null || true)"}; do
    process_command=$(/bin/ps -p "$pid" -o command= 2>/dev/null || true)
    if [[ "$process_command" == *"$SCRIPT_DIR/.venv/bin/python -m researchassistant.api.api"* ]]; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  for _ in {1..20}; do
    request_timeout >/dev/null || startup_failed
    if ! /usr/sbin/lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done
fi

if ! api_is_ready; then
  request_timeout >/dev/null || startup_failed
  if /usr/sbin/lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
    osascript -e 'display alert "ResearchAssistant API conflict" message "Port 8765 is occupied by a different service. Stop it, then launch ResearchAssistant again." as critical'
    exit 1
  fi
  "$SCRIPT_DIR/.venv/bin/python" -m researchassistant.api.api &
  API_PID=$!
fi

request_timeout >/dev/null || startup_failed
if ! /usr/sbin/lsof -nP -iTCP:3000 -sTCP:LISTEN >/dev/null 2>&1; then
  (
    cd "$SCRIPT_DIR/frontend"
    exec "$SCRIPT_DIR/frontend/node_modules/.bin/next" start --hostname 127.0.0.1 --port 3000
  ) &
  WEB_PID=$!
fi

READY=0
while request_timeout >/dev/null; do
  if api_is_ready && web_is_ready; then
    READY=1
    break
  fi
  "$SCRIPT_DIR/.venv/bin/python" -c '
import sys, time
time.sleep(min(1.0, max(0.0, float(sys.argv[1]) - time.monotonic())))
' "$STARTUP_DEADLINE"
done

if (( ! READY )); then
  startup_failed
fi
open "$WEB_URL"

if [[ -n "$WEB_PID" ]]; then
  wait "$WEB_PID"
elif [[ -n "$API_PID" ]]; then
  wait "$API_PID"
fi
