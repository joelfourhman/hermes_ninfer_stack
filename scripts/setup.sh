#!/usr/bin/env bash
set -Eeuo pipefail

# Compatibility entry point. The implementation is cross-platform Python.
# Pinned NInfer revision: feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$root_dir/stack.py" setup "$@"
