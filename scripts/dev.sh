#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/3m-uv-cache}"

if [[ ! -f .env ]]; then
  echo "Fichier .env manquant. Copiez .env.example vers .env et remplacez le jeton local."
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

cleanup() {
  kill "$BACKEND_PID" "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
npm --prefix apps/web run dev &
WEB_PID=$!
wait "$BACKEND_PID" "$WEB_PID"
