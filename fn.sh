#!/bin/bash
# fn.sh — Frontend code restart (TSX/TS/CSS edits, no new packages)
# Skips: uv sync, npm install, backend restart
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND="$ROOT/frontend"

LOG_FILE="$ROOT/logs/app.log"
mkdir -p "$ROOT/logs"
if [ -f "$LOG_FILE" ]; then
  tail -800 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

log_line() {
  printf "%-19s | %-7s | %-8s | %s\n" \
    "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$2" "$3" >> "$LOG_FILE"
}

# Poll a URL every 1s; succeed as soon as it responds (max 30s)
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

{ echo ""; echo "════════════════════════════════════════════"; log_line "BUILD" "APP" "=== Frontend restart (r2) ==="; echo "════════════════════════════════════════════"; } >> "$LOG_FILE"


# ── STEP 1: Stop frontend only ─────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 1] Stopping frontend...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
lsof -ti :3000 | xargs kill -9 2>/dev/null || true
sleep 1
echo "    ✓ Port 3000 cleared"


# ── STEP 2: Auto-bump localStorage version keys if defaults changed ────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 2] Checking localStorage version keys...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SUGGESTIONS_FILE="$FRONTEND/components/Chat/SuggestionsPane.tsx"
HASH_FILE="$ROOT/.defaults_hash"

CURRENT_HASH=$(grep -E '^\s+\{ id:' "$SUGGESTIONS_FILE" | shasum -a 256 | cut -d' ' -f1)
STORED_HASH=""
[ -f "$HASH_FILE" ] && STORED_HASH=$(cat "$HASH_FILE")

if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
  GMAIL_VER=$(grep -o 'quick_actions_gmail_v[0-9]*' "$SUGGESTIONS_FILE" | grep -o '[0-9]*$' | head -1)
  CAL_VER=$(grep -o 'quick_actions_calendar_v[0-9]*' "$SUGGESTIONS_FILE" | grep -o '[0-9]*$' | head -1)
  NEW_GMAIL_VER=$((GMAIL_VER + 1))
  NEW_CAL_VER=$((CAL_VER + 1))
  sed -i '' "s/quick_actions_gmail_v${GMAIL_VER}/quick_actions_gmail_v${NEW_GMAIL_VER}/g" "$SUGGESTIONS_FILE"
  sed -i '' "s/quick_actions_calendar_v${CAL_VER}/quick_actions_calendar_v${NEW_CAL_VER}/g" "$SUGGESTIONS_FILE"
  echo "$CURRENT_HASH" > "$HASH_FILE"
  echo "    ✓ Defaults changed — bumped keys:"
  echo "      gmail:    v${GMAIL_VER} → v${NEW_GMAIL_VER}"
  echo "      calendar: v${CAL_VER} → v${NEW_CAL_VER}"
else
  echo "    ✓ Defaults unchanged — no version bump needed"
fi


# ── STEP 3: Smart .next wipe — only if config files changed ──────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 3] Checking Next.js cache validity...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
CONFIG_HASH=$(cat "$FRONTEND/tsconfig.json" "$FRONTEND/tailwind.config.ts" "$FRONTEND/next.config.ts" "$FRONTEND/package.json" 2>/dev/null | shasum -a 256 | cut -d' ' -f1)
CONFIG_HASH_FILE="$ROOT/.config_hash"
STORED_CONFIG_HASH=""; [ -f "$CONFIG_HASH_FILE" ] && STORED_CONFIG_HASH=$(cat "$CONFIG_HASH_FILE")
if [ "$CONFIG_HASH" != "$STORED_CONFIG_HASH" ]; then
  rm -rf "$FRONTEND/.next"
  echo "$CONFIG_HASH" > "$CONFIG_HASH_FILE"
  echo "    ✓ Config changed — .next cleared for clean build"
else
  echo "    ✓ Config unchanged — using incremental cache"
fi


# ── STEP 4: Build frontend ─────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 4] Building frontend...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd "$FRONTEND" && npm run build 2>&1 | grep -E "✓|Route|error|Error|warn|Warn|compiled" || true
echo "    ✓ Frontend build complete"


# ── STEP 5: Start frontend ─────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 5] Starting frontend...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd "$FRONTEND" && npm start 2>&1 | while IFS= read -r line; do
  level="INFO"
  [[ "$line" =~ [Ee]rror|ERROR|Exception ]] && level="ERROR"
  [[ "$line" =~ [Ww]arning|WARN ]] && level="WARN"
  [[ "$line" =~ [Ss]tarted|[Rr]eady|[Ll]istening ]] && level="STARTUP"
  log_line "$level" "FRONTEND" "$line"
done &
echo "    ✓ Frontend process launched (port 3000)"


# ── STEP 6: Health check frontend ─────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 6] Waiting for frontend to be ready...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
wait_ready "http://localhost:3000" "Frontend :3000" || exit 1

echo ""
echo " ✅ Frontend ready at http://localhost:3000"
echo " 📄 Logs:    tail -f $LOG_FILE"
echo ""
