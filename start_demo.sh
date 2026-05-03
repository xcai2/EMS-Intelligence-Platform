#!/usr/bin/env bash
# One-command demo sharing via Cloudflare Tunnel
# Usage: bash start_demo.sh
# Ctrl+C to stop everything

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv/bin/activate"
FRONTEND="$ROOT/frontend"
LOG_DIR="$ROOT/.demo_logs"
mkdir -p "$LOG_DIR"

cleanup() {
  echo ""
  echo "Stopping all processes…"
  kill $BACKEND_PID $CF_BACKEND_PID $FRONTEND_PID $CF_FRONTEND_PID 2>/dev/null
  wait 2>/dev/null
  echo "Done."
}
trap cleanup EXIT INT TERM

# Start a cloudflared tunnel with up to 3 retries, returns URL in CF_URL variable
start_tunnel() {
  local port="$1"
  local logfile="$2"
  local pidvar="$3"
  local found=""
  for attempt in 1 2 3; do
    [ "$attempt" -gt 1 ] && echo "  (retry $attempt/3…)" && sleep 5
    rm -f "$logfile"
    cloudflared tunnel --url "http://localhost:${port}" > "$logfile" 2>&1 &
    eval "${pidvar}=$!"
    for i in $(seq 1 35); do
      sleep 1
      found=$(grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' "$logfile" 2>/dev/null | head -1 || true)
      [ -n "$found" ] && break
      # If cloudflared already exited with an error, stop waiting
      if grep -q "failed to unmarshal\|error code:" "$logfile" 2>/dev/null; then
        kill "${!pidvar}" 2>/dev/null || true
        break
      fi
    done
    [ -n "$found" ] && break
  done
  CF_URL="$found"
}

# ── 1. Backend ────────────────────────────────────────────────────────────────
echo "▶ Starting backend (port 8001)..."
if [ -f "$VENV" ]; then
  source "$VENV"
else
  echo "  ⚠ venv not found at $VENV — using system Python"
fi

cd "$ROOT"
uvicorn backend.main:app --host 0.0.0.0 --port 8001 \
  > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

for i in $(seq 1 30); do
  sleep 1
  CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001 2>/dev/null || true)
  case "$CODE" in 200|404|422|307) break ;; esac
  [ "$i" -eq 30 ] && echo "  ⚠ Backend didn't start in time — continuing anyway"
done
echo "  ✓ Backend running (PID $BACKEND_PID)"

# ── 2. Cloudflare tunnel for backend ─────────────────────────────────────────
echo "▶ Creating Cloudflare tunnel for backend..."
start_tunnel 8001 "$LOG_DIR/cf_backend.log" CF_BACKEND_PID
BACKEND_URL="$CF_URL"

if [ -z "$BACKEND_URL" ]; then
  echo "  ⚠ Could not get backend tunnel URL after 3 attempts."
  echo "    Check $LOG_DIR/cf_backend.log"
  echo "    Using localhost:8001 instead (local use only)"
  BACKEND_URL="http://localhost:8001"
else
  echo "  ✓ Backend tunnel: $BACKEND_URL"
fi

# Wait 3s before opening second tunnel (avoids rate limiting)
sleep 3

# ── 3. Frontend ───────────────────────────────────────────────────────────────
echo "▶ Starting frontend (port 3000)..."
cd "$FRONTEND"
NEXT_PUBLIC_API_URL="$BACKEND_URL" npm run dev \
  > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

for i in $(seq 1 60); do
  sleep 1
  CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null || true)
  case "$CODE" in 200|304|307) break ;; esac
  [ "$i" -eq 60 ] && echo "  ⚠ Frontend didn't start in time — continuing anyway"
done
echo "  ✓ Frontend running (PID $FRONTEND_PID)"

# ── 4. Cloudflare tunnel for frontend ────────────────────────────────────────
echo "▶ Creating Cloudflare tunnel for frontend..."
start_tunnel 3000 "$LOG_DIR/cf_frontend.log" CF_FRONTEND_PID
FRONTEND_URL="$CF_URL"

# ── 5. Print share link ───────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
if [ -n "$FRONTEND_URL" ]; then
  echo "║  SUCCESS  Share this link:                                   ║"
  printf  "║  %-60s  ║\n" "$FRONTEND_URL"
else
  echo "║  WARNING  Could not get frontend tunnel URL                  ║"
  echo "║  Check .demo_logs/cf_frontend.log                           ║"
fi
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Press Ctrl+C to stop everything."

wait $BACKEND_PID
