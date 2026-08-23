#!/usr/bin/env bash
set -Eeuo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="$root_dir/.env"
example_file="$root_dir/.env.example"
expected_ninfer_commit='feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a'
legacy_hermes_image='nousresearch/hermes-agent:v2026.8.19'
pinned_hermes_image='nousresearch/hermes-agent:v2026.8.19@sha256:f3cba6abf5ed80d47a271498d663ace5dda87f45000552afb8be8370a35df1b5'

die() {
  echo "setup: $*" >&2
  exit 1
}

for command_name in git grep mktemp; do
  command -v "$command_name" >/dev/null 2>&1 || die "missing required command: $command_name"
done

[[ -f "$example_file" ]] || die "missing .env.example"

if [[ ! -e "$root_dir/ninfer/.git" ]]; then
  echo "Initializing the pinned NInfer submodule..."
  git -C "$root_dir" submodule update --init --recursive --depth 1
fi

actual_ninfer_commit="$(git -C "$root_dir/ninfer" rev-parse HEAD 2>/dev/null)" \
  || die "NInfer is unavailable; run 'git submodule update --init --recursive'"
[[ "$actual_ninfer_commit" == "$expected_ninfer_commit" ]] \
  || die "NInfer is at $actual_ninfer_commit; expected $expected_ninfer_commit. Run 'git submodule update --init --recursive --checkout'."

if [[ -n "$(git -C "$root_dir/ninfer" status --porcelain --untracked-files=all)" ]]; then
  die "the NInfer submodule has local or untracked changes; preserve or remove them before setup"
fi
echo "NInfer submodule is pinned at ${expected_ninfer_commit:0:12}."

generate_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  else
    echo "Need openssl or python3 to generate local API secrets." >&2
    exit 1
  fi
}

env_value() {
  local file="$1"
  local key="$2"
  local line
  line="$(grep -E "^${key}=" "$file" | tail -n 1 | tr -d '\r')" || return 1
  [[ "$line" == "${key}="* ]] || return 1
  printf '%s' "${line#*=}"
}

validate_env_file() {
  local file="$1"
  local ninfer_key hermes_key uid gid port gpu model_file model_id context concurrency image
  image="$(env_value "$file" HERMES_IMAGE)" || return 1
  ninfer_key="$(env_value "$file" NINFER_API_KEY)" || return 1
  hermes_key="$(env_value "$file" HERMES_API_SERVER_KEY)" || return 1
  uid="$(env_value "$file" HERMES_UID)" || return 1
  gid="$(env_value "$file" HERMES_GID)" || return 1
  port="$(env_value "$file" NINFER_HOST_PORT)" || return 1
  gpu="$(env_value "$file" NINFER_GPU_DEVICE)" || return 1
  model_file="$(env_value "$file" NINFER_MODEL_FILE)" || return 1
  model_id="$(env_value "$file" NINFER_MODEL_ID)" || return 1
  context="$(env_value "$file" NINFER_CONTEXT_LENGTH)" || return 1
  concurrency="$(env_value "$file" NINFER_MAX_CONCURRENCY)" || return 1

  [[ -n "$image" ]] || return 1
  [[ "$ninfer_key" =~ ^[[:xdigit:]]{64}$ ]] || return 1
  [[ "$hermes_key" =~ ^[[:xdigit:]]{64}$ ]] || return 1
  [[ "$ninfer_key" != "$hermes_key" ]] || return 1
  [[ "$uid" =~ ^[0-9]+$ ]] || return 1
  (( uid >= 1000 && uid <= 60000 )) || return 1
  [[ "$gid" =~ ^[0-9]+$ ]] || return 1
  (( gid >= 1000 && gid <= 60000 )) || return 1
  [[ "$port" =~ ^[0-9]+$ ]] || return 1
  (( port >= 1 && port <= 65535 )) || return 1
  [[ "$gpu" =~ ^[0-9]+$ ]] || return 1
  [[ "$model_file" =~ ^[A-Za-z0-9._-]+\.ninfer$ ]] || return 1
  [[ "$model_id" =~ ^[A-Za-z0-9._-]+$ ]] || return 1
  [[ "$context" =~ ^[0-9]+$ ]] || return 1
  (( context >= 1024 && context <= 262144 )) || return 1
  [[ "$concurrency" =~ ^[0-9]+$ ]] || return 1
  (( concurrency >= 1 && concurrency <= 8 )) || return 1
}

merge_env_defaults() {
  local changed=false line key temp_env
  umask 077
  temp_env="$(mktemp "$root_dir/.env.merge.XXXXXX")"
  cp "$env_file" "$temp_env"
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^([A-Z][A-Z0-9_]*)= ]] || continue
    key="${BASH_REMATCH[1]}"
    if ! grep -q -E "^${key}=" "$env_file"; then
      printf '%s\n' "$line" >> "$temp_env"
      changed=true
    fi
  done < "$example_file"

  if [[ "$changed" == true ]]; then
    chmod 0600 "$temp_env" 2>/dev/null || true
    mv -f "$temp_env" "$env_file"
    echo "Added newly documented defaults to the existing .env."
  else
    rm -f "$temp_env"
  fi
}

migrate_legacy_defaults() {
  local temp_env line changed=false
  grep -q -F -x "HERMES_IMAGE=$legacy_hermes_image" "$env_file" || return 0

  umask 077
  temp_env="$(mktemp "$root_dir/.env.migrate.XXXXXX")"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "HERMES_IMAGE=$legacy_hermes_image" ]]; then
      printf 'HERMES_IMAGE=%s\n' "$pinned_hermes_image"
      changed=true
    else
      printf '%s\n' "$line"
    fi
  done < "$env_file" > "$temp_env"

  if [[ "$changed" == true ]]; then
    chmod 0600 "$temp_env" 2>/dev/null || true
    mv -f "$temp_env" "$env_file"
    echo "Migrated the former Hermes tag-only default to its reviewed image digest."
  else
    rm -f "$temp_env"
  fi
}

fill_empty_secrets() {
  local ninfer_key hermes_key temp_env changed=false
  ninfer_key="$(env_value "$env_file" NINFER_API_KEY)" || return 0
  hermes_key="$(env_value "$env_file" HERMES_API_SERVER_KEY)" || return 0
  [[ -z "$ninfer_key" ]] && { ninfer_key="$(generate_secret)"; changed=true; }
  [[ -z "$hermes_key" ]] && { hermes_key="$(generate_secret)"; changed=true; }
  [[ "$changed" == true ]] || return 0

  umask 077
  temp_env="$(mktemp "$root_dir/.env.secrets.XXXXXX")"
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      NINFER_API_KEY=*) printf 'NINFER_API_KEY=%s\n' "$ninfer_key" ;;
      HERMES_API_SERVER_KEY=*) printf 'HERMES_API_SERVER_KEY=%s\n' "$hermes_key" ;;
      *) printf '%s\n' "$line" ;;
    esac
  done < "$env_file" > "$temp_env"
  chmod 0600 "$temp_env" 2>/dev/null || true
  mv -f "$temp_env" "$env_file"
  echo "Replaced empty API-key placeholders with random local secrets."
}

mkdir -p "$root_dir/hermes-data" "$root_dir/workspace" "$root_dir/models"

if [[ ! -f "$root_dir/hermes-data/config.yaml" ]]; then
  cp "$root_dir/hermes/config.example.yaml" "$root_dir/hermes-data/config.yaml"
  echo "Created the local Hermes config from hermes/config.example.yaml."
fi

if [[ ! -e "$env_file" ]]; then
  uid="$(id -u 2>/dev/null || printf '1000')"
  gid="$(id -g 2>/dev/null || printf '1000')"
  # MSYS/Git Bash reports Windows SID-derived IDs that Linux useradd/usermod
  # should not use. Docker Desktop bind mounts are happiest with the normal
  # container fallback in that case; native Linux/WSL keeps the real IDs.
  case "$(uname -s 2>/dev/null || true)" in
    MINGW*|MSYS*|CYGWIN*) uid=1000; gid=1000 ;;
  esac
  if (( uid < 1000 || uid > 60000 || gid < 1000 || gid > 60000 )); then
    echo "Run ./scripts/setup.sh as a normal Linux/WSL user with UID/GID from 1000 through 60000." >&2
    exit 1
  fi
  ninfer_key="$(generate_secret)"
  hermes_key="$(generate_secret)"
  umask 077
  temp_env="$(mktemp "$root_dir/.env.tmp.XXXXXX")"
  trap 'rm -f "$temp_env"' EXIT

  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      HERMES_UID=*) printf 'HERMES_UID=%s\n' "$uid" ;;
      HERMES_GID=*) printf 'HERMES_GID=%s\n' "$gid" ;;
      NINFER_API_KEY=*) printf 'NINFER_API_KEY=%s\n' "$ninfer_key" ;;
      HERMES_API_SERVER_KEY=*) printf 'HERMES_API_SERVER_KEY=%s\n' "$hermes_key" ;;
      *) printf '%s\n' "$line" ;;
    esac
  done < "$example_file" > "$temp_env"
  chmod 0600 "$temp_env" 2>/dev/null || true
  mv -f "$temp_env" "$env_file"
  trap - EXIT
  echo "Created .env with random local API keys."
else
  migrate_legacy_defaults
  merge_env_defaults
  fill_empty_secrets
  if ! validate_env_file "$env_file"; then
    echo ".env is invalid. Compare it with .env.example and use distinct 64-character hexadecimal secrets." >&2
    echo "Preserve any values you need, then correct it or remove it and rerun ./scripts/setup.sh." >&2
    exit 1
  fi
  echo "Existing .env is valid; existing values and secrets were preserved."
fi

if [[ ! -e "$root_dir/hermes-data/.env" ]]; then
  umask 077
  : > "$root_dir/hermes-data/.env"
  chmod 0600 "$root_dir/hermes-data/.env" 2>/dev/null || true
fi

if command -v docker >/dev/null 2>&1; then
  docker compose --project-directory "$root_dir" --env-file "$env_file" \
    -f "$root_dir/docker-compose.yml" config --quiet
  echo "Docker Compose configuration is valid."
else
  echo "Docker is not on PATH; files were initialized but Compose was not validated." >&2
fi

echo
echo "No model was downloaded. Next: ./scripts/download-model.sh"
