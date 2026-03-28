#!/bin/bash
# r4.sh — Frontend dependency update (package.json changed, or new Node packages added)
# Adds npm install before rebuilding frontend. Backend untouched.
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

{ echo ""; echo "════════════════════════════════════════════"; log_line "BUILD" "APP" "=== Frontend + deps restart (r4) ==="; echo "════════════════════════════════════════════"; } >> "$LOG_FILE"


# ── STEP 1: Stop frontend only ─────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 1] Stopping frontend...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
lsof -ti :3000 | xargs kill -9 2>/dev/null || true
sleep 1
echo "    ✓ Port 3000 cleared"


# ── STEP 2: Install / update frontend Node packages ───────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 2] Installing frontend Node packages...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd "$FRONTEND" && npm install --silent 2>&1 | tail -3
echo "    ✓ Frontend Node packages up to date"


# ── STEP 3: Auto-bump localStorage version keys if defaults changed ────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 3] Checking localStorage version keys...  [FRONTEND]"
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


# ── STEP 4: Wipe Next.js build cache ──────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 4] Clearing Next.js build cache...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
rm -rf "$FRONTEND/.next"
echo "    ✓ .next directory removed"


# ── STEP 5: Build frontend ─────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 5] Building frontend...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd "$FRONTEND" && npm run build 2>&1 | grep -E "✓|Route|error|Error|warn|Warn|compiled" || true
echo "    ✓ Frontend build complete"


# ── STEP 6: Start frontend ─────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 6] Starting frontend...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd "$FRONTEND" && npm start 2>&1 | while IFS= read -r line; do
  level="INFO"
  [[ "$line" =~ [Ee]rror|ERROR|Exception ]] && level="ERROR"
  [[ "$line" =~ [Ww]arning|WARN ]] && level="WARN"
  [[ "$line" =~ [Ss]tarted|[Rr]eady|[Ll]istening ]] && level="STARTUP"
  log_line "$level" "FRONTEND" "$line"
done &
echo "    ✓ Frontend process launched (port 3000)"


# ── STEP 7: Health check frontend ─────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " [STEP 7] Waiting for frontend to be ready...  [FRONTEND]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sleep 10

FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000)

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "  Frontend :3000  →  HTTP $FRONTEND_STATUS"
echo "╚═══════════════════════════════════════════╝"

if [ "$FRONTEND_STATUS" = "200" ]; then
  echo ""
  echo " ✅ Frontend ready at http://localhost:3000"
  echo " 📄 Logs:    tail -f $LOG_FILE"
  echo ""
else
  echo ""
  echo " ❌ Frontend failed to start."
  echo " 📄 Log file: $LOG_FILE"
  echo ""
  exit 1
fi
