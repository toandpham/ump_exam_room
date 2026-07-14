#!/usr/bin/env bash
# First-run setup: create .env with strong secrets, set the mDNS hostname,
# build & start the stack.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(openssl rand -hex 32)
  PGPASS=$(openssl rand -hex 16)
  # macOS/BSD sed in-place
  sed -i '' "s|^JWT_SECRET=.*|JWT_SECRET=${SECRET}|" .env
  sed -i '' "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PGPASS}|" .env
  sed -i '' "s|change_me_postgres|${PGPASS}|g" .env
  echo "Created .env with random JWT secret + DB password."
else
  echo ".env already exists — leaving it untouched."
fi

# mDNS hostname so the server is reachable at https://exam-server.local
if [[ "$(uname)" == "Darwin" ]]; then
  current=$(scutil --get LocalHostName 2>/dev/null || echo "")
  if [ "$current" != "exam-server" ]; then
    echo "Tip: set the mDNS hostname so clients reach https://exam-server.local :"
    echo "    sudo scutil --set HostName exam-server && sudo scutil --set LocalHostName exam-server"
  fi
fi

echo "Building and starting the stack…"
docker compose up -d --build
echo "Done. Waiting for services to become healthy:  docker compose ps"
