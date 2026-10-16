#!/usr/bin/env bash
set -euo pipefail

cp -n .env.example .env || true
pnpm install
uv python install 3.12
uv sync --directory apps/backend

printf '\nDependencies are ready. Configure .env, then run pnpm db:migrate and pnpm dev.\n'
