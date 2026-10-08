#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/3m-uv-cache}"
uv run ruff check backend
uv run pytest
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
