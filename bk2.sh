#!/bin/bash
# r3.sh — Backend dependency update (pyproject.toml changed, or backend + new packages)
# Adds uv sync before restarting backend. Frontend untouched.
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"

LOG_FILE="$ROOT/logs/app.log"
mkdir -p "$ROOT/logs"
if [ -f "$LOG_FILE" ]; then
  tail -800 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

log_line() {
  printf "%-19s | %-7s | %-8s | %s\n" \
    "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$2" "$3" >> "$LOG_FILE"
}

wait_ready() {
  local url=$1 name=$2
  for i in $(seq 1 30); do
    if curl -sf -o /dev/null "$url" 2>/dev/null; then
      echo "    ✓ $name ready in ${i}s"; return 0
    fi
    sleep 1
  done
  echo "    ❌ $name not ready after 30s"; return 1
}

{ echo ""; echo "════════════════════════════════════════════"; log_line "BUILD" "APP" "=== Backend + deps restart (r3) ==="; echo "════════════════════════════════════════════"; } >> "$LOG_FILE"


# ── STEP 1: Stop backend only ──────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 1] Stopping backend...  [BACKEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
sleep 1
echo "    ✓ Port 8000 cleared"


# ── STEP 2: Sync backend Python dependencies ──────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 2] Syncing backend Python dependencies...  [BACKEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd "$BACKEND" && uv sync 2>&1 | tail -3
echo "    ✓ Backend Python packages up to date"


# ── STEP 3: Start backend ──────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 3] Starting backend...  [BACKEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd "$BACKEND" && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 | while IFS= read -r line; do
  level="INFO"
  [[ "$line" =~ [Ee]rror|ERROR|Exception|Traceback ]] && level="ERROR"
  [[ "$line" =~ [Ww]arning|WARN ]] && level="WARN"
  [[ "$line" =~ [Ss]tarted|[Ss]tarting|[Rr]unning|[Ll]istening ]] && level="STARTUP"
  log_line "$level" "BACKEND" "$line"
done &
echo "    ✓ Backend process launched (port 8000)"


# ── STEP 4: Health check backend ──────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 4] Waiting for backend to be ready...  [BACKEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
wait_ready "http://localhost:8000/health" "Backend :8000" || exit 1

echo ""
echo " ✅ Backend ready at http://localhost:8000"
echo " 📄 Logs:    tail -f $LOG_FILE"
echo ""
