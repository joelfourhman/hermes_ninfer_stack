#!/usr/bin/env bash
set -Eeuo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
model_dir="$root_dir/models"
model_name='qwen3_8_27b_nvfp4.ninfer'
if [[ -f "$root_dir/.env" ]]; then
  configured_name="$(grep -E '^NINFER_MODEL_FILE=' "$root_dir/.env" | tail -n 1 | tr -d '\r' | cut -d= -f2-)"
  [[ -z "$configured_name" || "$configured_name" == "$model_name" ]] \
    || { echo "This helper downloads only the tested $model_name artifact; .env selects $configured_name." >&2; exit 1; }
fi
model_file="$model_dir/$model_name"
repo='neroued/Qwen3.8-27B-nvfp4-NInfer'
revision='204e3d92c30d9d05f3300d2f52e443ad1edf6ddf'
sha256='bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32'

verify_checksum() {
  local actual
  if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$model_file" | awk '{print $1}')"
  elif command -v shasum >/dev/null 2>&1; then
    actual="$(shasum -a 256 "$model_file" | awk '{print $1}')"
  else
    echo "Need sha256sum or shasum to verify the model." >&2
    exit 1
  fi
  if [[ "$actual" != "$sha256" ]]; then
    echo "Model checksum mismatch." >&2
    echo "Expected: $sha256" >&2
    echo "Actual:   $actual" >&2
    exit 1
  fi
  echo "Model checksum verified: $sha256"
}

mkdir -p "$model_dir"

if [[ -s "$model_file" ]]; then
  echo "Model already exists; verifying it instead of downloading again."
  verify_checksum
  exit 0
fi

if (( $# > 1 )) || { (( $# == 1 )) && [[ "$1" != "--yes" ]]; }; then
  echo "Usage: ./scripts/download-model.sh [--yes]" >&2
  exit 2
fi

if ! command -v hf >/dev/null 2>&1 || ! hf download --help >/dev/null 2>&1; then
  echo "The Hugging Face CLI is required." >&2
  echo "Create a venv and install it with: python3 -m venv .venv-hf && . .venv-hf/bin/activate && python -m pip install --upgrade huggingface_hub" >&2
  exit 1
fi

echo "Artifact: $repo/qwen3_8_27b_nvfp4.ninfer"
echo "Size:     21,492,695,040 bytes (20.02 GiB)"
echo "Target:   $model_file"
df -h "$model_dir" 2>/dev/null || true

available_kib="$(df -Pk "$model_dir" | awk 'NR == 2 {print $4}')"
required_bytes=$((24 * 1024 * 1024 * 1024))
if [[ ! "$available_kib" =~ ^[0-9]+$ ]] || (( available_kib * 1024 < required_bytes )); then
  echo "At least 24 GiB of free space is required for the artifact and download staging." >&2
  exit 1
fi

if [[ "${1:-}" != "--yes" ]]; then
  read -r -p "Type DOWNLOAD to fetch this ~20 GiB model: " answer
  if [[ "$answer" != "DOWNLOAD" ]]; then
    echo "Download cancelled."
    exit 0
  fi
fi

hf download "$repo" \
  qwen3_8_27b_nvfp4.ninfer \
  --revision "$revision" \
  --local-dir "$model_dir"

verify_checksum
