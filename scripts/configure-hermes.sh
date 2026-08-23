#!/usr/bin/env bash
set -Eeuo pipefail

# Compatibility entry point. The implementation is cross-platform Python.
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$root_dir/stack.py" configure-hermes "$@"
