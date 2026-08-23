#!/usr/bin/env bash
set -Eeuo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Compatibility wrapper: the downloader now runs through Docker Compose and uv." >&2
exec python3 "$root_dir/stack.py" download-model "$@"
