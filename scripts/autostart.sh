#!/usr/bin/env bash
# Bring the exam stack up at login. Waits for the Docker engine (OrbStack) to be
# ready, then `docker compose up -d`. Invoked by the LaunchAgent.
export PATH="$HOME/.orbstack/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

echo "[$(date)] autostart: waiting for Docker engine…"
for _ in $(seq 1 120); do
  if docker info >/dev/null 2>&1; then
    echo "[$(date)] Docker ready — starting stack"
    docker compose up -d
    echo "[$(date)] done"
    exit 0
  fi
  sleep 3
done
echo "[$(date)] autostart: Docker never became ready (timeout)"
exit 1
