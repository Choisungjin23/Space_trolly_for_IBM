#!/usr/bin/env bash

# macOS launcher for the complete Phase A + B + C application.
# It intentionally uses a separate virtual environment so a Windows .venv can
# remain beside it when the same checkout is shared between operating systems.

set -Eeuo pipefail

NO_BROWSER=0
SETUP_ONLY=0

usage() {
    cat <<'EOF'
Usage: ./run-app.sh [--no-browser] [--setup-only]

  --no-browser  Start the app without opening the default browser.
  --setup-only  Install/check dependencies, then exit without starting servers.
  -h, --help    Show this help.
EOF
}

for argument in "$@"; do
    case "$argument" in
        --no-browser) NO_BROWSER=1 ;;
        --setup-only) SETUP_ONLY=1 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n\n' "$argument" >&2; usage >&2; exit 2 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
BACKEND_DIR="$SCRIPT_DIR/Phase b/spacecraft-sim/backend"
FRONTEND_DIR="$SCRIPT_DIR/Phase b/spacecraft-sim/frontend"
PHASE_A_DIR="$SCRIPT_DIR/spacecraft-sim"
PHASE_C_DIR="$SCRIPT_DIR/phase-c"
VENV_DIR="$BACKEND_DIR/.venv-macos"
VENV_PYTHON="$VENV_DIR/bin/python"
ENV_FILE="$BACKEND_DIR/.env"
ENV_EXAMPLE="$BACKEND_DIR/.env.example"
LOG_DIR="$BACKEND_DIR/.run-logs"
BACKEND_PID=""
FRONTEND_PID=""

step() {
    printf '\n\033[36m==> %s\033[0m\n' "$1"
}

fail() {
    printf '\nError: %s\n' "$1" >&2
    exit 1
}

version_at_least() {
    "$1" - "$2" <<'PY'
import sys

required = tuple(map(int, sys.argv[1].split(".")))
raise SystemExit(0 if sys.version_info[:2] >= required else 1)
PY
}

find_python() {
    local candidate
    for candidate in python3.12 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            candidate="$(command -v "$candidate")"
            if version_at_least "$candidate" 3.11; then
                printf '%s\n' "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

port_owner() {
    lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null || true
}

assert_port_free() {
    local owner
    owner="$(port_owner "$1")"
    if [[ -n "$owner" ]]; then
        printf 'Port %s is already in use:\n%s\n' "$1" "$owner" >&2
        fail "Close that process and run this script again."
    fi
}

show_log_tail() {
    local path="$1"
    local label="$2"
    if [[ -f "$path" ]]; then
        printf '\n%s (last 30 lines):\n' "$label" >&2
        tail -n 30 "$path" >&2
    fi
}

stop_servers() {
    trap - INT TERM EXIT
    local pid
    for pid in "$FRONTEND_PID" "$BACKEND_PID"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    for pid in "$FRONTEND_PID" "$BACKEND_PID"; do
        if [[ -n "$pid" ]]; then
            wait "$pid" 2>/dev/null || true
        fi
    done
}

wait_for_url() {
    local url="$1"
    local pid="$2"
    local attempts=0
    while (( attempts < 60 )); do
        if ! kill -0 "$pid" 2>/dev/null; then
            return 1
        fi
        if curl --fail --silent --show-error --max-time 2 "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        attempts=$((attempts + 1))
    done
    return 1
}

for required_dir in "$BACKEND_DIR" "$FRONTEND_DIR" "$PHASE_A_DIR" "$PHASE_C_DIR"; do
    [[ -d "$required_dir" ]] || fail "Required project directory is missing: $required_dir"
done

command -v curl >/dev/null 2>&1 || fail "curl is required (it is included with macOS)."
command -v lsof >/dev/null 2>&1 || fail "lsof is required (it is included with macOS)."

if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    printf 'Warning: Created backend/.env from .env.example. Fill in IBM credentials to enable Advisor.\n' >&2
elif grep -Eq 'YOUR_IBM_API_KEY|YOUR_WATSONX_PROJECT_ID|YOUR_REGION|PUT_YOUR_' "$ENV_FILE"; then
    printf 'Warning: backend/.env contains placeholders. The simulator works, but Advisor remains disabled.\n' >&2
fi

SYSTEM_PYTHON="$(find_python)" || fail "Python 3.11 or newer was not found. Install Python 3.12 (for example: brew install python@3.12)."

if [[ ! -x "$VENV_PYTHON" ]]; then
    step "Creating the macOS Python virtual environment"
    "$SYSTEM_PYTHON" -m venv "$VENV_DIR"
else
    step "Reusing the macOS Python virtual environment"
fi

if ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
    "$VENV_PYTHON" -m ensurepip --upgrade
fi

if ! "$VENV_PYTHON" -c 'import dotenv, fastapi, uvicorn, spacecraft_sim, phase_c, ibm_watsonx_ai' >/dev/null 2>&1; then
    step "Installing backend, simulator, and Granite dependencies (first launch)"
    "$VENV_PYTHON" -m pip install --disable-pip-version-check -r "$BACKEND_DIR/requirements.txt"
    "$VENV_PYTHON" -m pip install --disable-pip-version-check -e "$PHASE_A_DIR" -e "$PHASE_C_DIR[granite]"
else
    step "Python dependencies are already installed"
fi

command -v node >/dev/null 2>&1 || fail "Node.js was not found. Install Node.js 18 or newer (for example: brew install node)."
command -v npm >/dev/null 2>&1 || fail "npm was not found. Install Node.js 18 or newer (for example: brew install node)."

NODE_BIN="$(command -v node)"
NODE_MAJOR="$($NODE_BIN -p 'Number(process.versions.node.split(".")[0])')"
(( NODE_MAJOR >= 18 )) || fail "Node.js 18 or newer is required; found $($NODE_BIN --version)."

PLATFORM_STAMP="$FRONTEND_DIR/node_modules/.installed-for-macos-$(uname -m)"
if [[ ! -f "$PLATFORM_STAMP" ]]; then
    step "Installing macOS frontend dependencies (first launch)"
    (
        cd "$FRONTEND_DIR"
        npm ci
        touch "$PLATFORM_STAMP"
    )
else
    step "Frontend dependencies are already installed for this Mac"
fi

if (( SETUP_ONLY == 1 )); then
    printf '\n\033[32mSetup is complete. Run ./run-app.sh to start the app.\033[0m\n'
    exit 0
fi

assert_port_free 8000
assert_port_free 5173

mkdir -p "$LOG_DIR"
BACKEND_OUT="$LOG_DIR/backend.stdout.log"
BACKEND_ERR="$LOG_DIR/backend.stderr.log"
FRONTEND_OUT="$LOG_DIR/frontend.stdout.log"
FRONTEND_ERR="$LOG_DIR/frontend.stderr.log"
VITE_ENTRY="$FRONTEND_DIR/node_modules/vite/bin/vite.js"

trap stop_servers INT TERM EXIT

step "Starting FastAPI and Vite"
(
    cd "$BACKEND_DIR"
    exec "$VENV_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
) >"$BACKEND_OUT" 2>"$BACKEND_ERR" &
BACKEND_PID=$!

(
    cd "$FRONTEND_DIR"
    exec "$NODE_BIN" "$VITE_ENTRY" --host 127.0.0.1
) >"$FRONTEND_OUT" 2>"$FRONTEND_ERR" &
FRONTEND_PID=$!

if ! wait_for_url "http://127.0.0.1:8000/" "$BACKEND_PID"; then
    show_log_tail "$BACKEND_ERR" "Backend error log"
    fail "Backend did not become ready at http://127.0.0.1:8000/."
fi
if ! wait_for_url "http://127.0.0.1:5173/" "$FRONTEND_PID"; then
    show_log_tail "$FRONTEND_ERR" "Frontend error log"
    fail "Frontend did not become ready at http://127.0.0.1:5173/."
fi

printf '\n\033[32mApp is ready: http://localhost:5173\033[0m\n'
printf '\033[32mBackend:     http://localhost:8000\033[0m\n'
printf 'Press Ctrl+C in this Terminal window to stop both servers.\n'

if (( NO_BROWSER == 0 )); then
    open "http://localhost:5173"
fi

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
    sleep 1
done

show_log_tail "$BACKEND_ERR" "Backend error log"
show_log_tail "$FRONTEND_ERR" "Frontend error log"
fail "A server stopped unexpectedly."
