#!/usr/bin/env bash
set -Eeuo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

if [[ ! -f .env ]]; then
  echo "Missing .env. Run ./scripts/setup.sh first." >&2
  exit 1
fi

compose=(docker compose --project-directory "$root_dir" --env-file "$root_dir/.env" -f "$root_dir/docker-compose.yml")

dotenv_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" .env | tail -n 1 | tr -d '\r')" || return 1
  [[ "$line" == "${key}="* ]] || return 1
  printf '%s' "${line#*=}"
}

model_id="$(dotenv_value NINFER_MODEL_ID)" || { echo "NINFER_MODEL_ID is missing from .env" >&2; exit 1; }
context_length="$(dotenv_value NINFER_CONTEXT_LENGTH)" || { echo "NINFER_CONTEXT_LENGTH is missing from .env" >&2; exit 1; }
[[ "$model_id" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "NINFER_MODEL_ID contains unsupported characters" >&2; exit 1; }
if ! [[ "$context_length" =~ ^[0-9]+$ ]] \
  || ! (( context_length >= 1024 && context_length <= 262144 )); then
  echo "NINFER_CONTEXT_LENGTH must be from 1024 through 262144" >&2
  exit 1
fi

if [[ -n "$("${compose[@]}" ps --status running -q hermes 2>/dev/null)" ]]; then
  echo "Hermes is running. Stop it with 'docker compose stop hermes' before changing its config." >&2
  exit 1
fi

config_file="$root_dir/hermes-data/config.yaml"
[[ -f "$config_file" ]] || { echo "Missing $config_file" >&2; exit 1; }
hermes_env_file="$root_dir/hermes-data/.env"
backup_dir="$(mktemp -d "$root_dir/hermes-data/.config-backup.XXXXXX")"
cp -p "$config_file" "$backup_dir/config.yaml"
env_existed=false
if [[ -f "$hermes_env_file" ]]; then
  cp -p "$hermes_env_file" "$backup_dir/hermes.env"
  env_existed=true
fi
configured=false

restore_on_failure() {
  local status=$?
  if [[ "$configured" != true ]]; then
    cp -p "$backup_dir/config.yaml" "$config_file"
    if [[ "$env_existed" == true ]]; then
      cp -p "$backup_dir/hermes.env" "$hermes_env_file"
    else
      rm -f "$hermes_env_file"
    fi
    echo "Hermes configuration failed; the previous config and environment file were restored." >&2
  fi
  rm -rf -- "$backup_dir"
  return "$status"
}
trap restore_on_failure EXIT

provider_json="$(printf '{\"api\":\"http://ninfer:8080/v1\",\"key_env\":\"NINFER_API_KEY\",\"transport\":\"chat_completions\",\"default_model\":\"%s\",\"models\":{\"%s\":{\"context_length\":%s,\"supports_vision\":false}}}' "$model_id" "$model_id" "$context_length")"

# The positional parameters are expanded by the container shell, not here.
# shellcheck disable=SC2016
"${compose[@]}" run --rm --no-deps hermes sh -euc '
  hermes config set providers.ninfer "$1"
  hermes config set model.provider custom:ninfer
  hermes config set model.default "$2"
  hermes config set model.context_length "$3"
  hermes config set model.supports_vision false
  hermes config set terminal.backend ssh
  hermes config set terminal.cwd /workspace
  hermes config set terminal.timeout 180
  hermes config set terminal.persistent_shell true
  hermes config set terminal.env_passthrough "[]"
  hermes config set TERMINAL_SSH_HOST sandbox
  hermes config set TERMINAL_SSH_USER agent
  hermes config set TERMINAL_SSH_PORT 2222
  hermes config set TERMINAL_SSH_KEY /ssh/id_ed25519
  hermes config set tool_loop_guardrails.hard_stop_enabled true
  hermes config set tool_loop_guardrails.hard_stop_after.exact_failure 5
  hermes config set tool_loop_guardrails.hard_stop_after.idempotent_no_progress 5
  hermes config check
' sh "$provider_json" "$model_id" "$context_length"

configured=true
echo "Hermes is configured for $model_id at http://ninfer:8080/v1 with the SSH sandbox backend."
