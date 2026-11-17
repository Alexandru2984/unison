#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
unison_port="${UNISON_PORT:-8097}"
if ! [[ "$unison_port" =~ ^[0-9]+$ ]] || (( unison_port < 1024 || unison_port > 65535 )); then
  echo 'UNISON_PORT must be between 1024 and 65535' >&2
  exit 1
fi
cd "$project_dir/backend"
exec "$project_dir/backend/.venv/bin/uvicorn" main:app --host 127.0.0.1 --port "$unison_port" \
  --workers 1 --ws websockets --ws-max-size 1024 --timeout-keep-alive 5 \
  --timeout-graceful-shutdown 8 --limit-concurrency 96 --backlog 64 --no-access-log
