#!/usr/bin/env bash
set -Eeuo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

total_steps=11
step=0
current_label='startup'

begin() {
  step=$((step + 1))
  current_label="$1"
  printf '[%02d/%02d] %-34s' "$step" "$total_steps" "$current_label"
}

pass() {
  printf ' PASS\n'
  [[ $# -eq 0 ]] || printf '         %s\n' "$*"
}

fail() {
  local reason="$1"
  local diagnostic="${2:-}"
  printf ' FAIL\n' >&2
  printf '         %s\n' "$reason" >&2
  if [[ -n "$diagnostic" ]]; then
    printf '         Next: %s\n' "$diagnostic" >&2
  fi
  exit 1
}

dotenv_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" .env | tail -n 1 | tr -d '\r')" || return 1
  [[ "$line" == "${key}="* ]] || return 1
  printf '%s' "${line#*=}"
}

hash_file() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" | awk '{print $1}'
  else
    return 1
  fi
}

begin 'Prerequisites and configuration'
for command_name in docker curl grep jq mktemp git awk; do
  command -v "$command_name" >/dev/null 2>&1 \
    || fail "Missing required command: $command_name" 'install the prerequisites in docs/installation.md'
done
[[ -f .env ]] || fail 'Missing .env' './scripts/setup.sh'

NINFER_API_KEY="$(dotenv_value NINFER_API_KEY)" || fail 'NINFER_API_KEY is missing from .env' './scripts/setup.sh'
host_port="$(dotenv_value NINFER_HOST_PORT)" || fail 'NINFER_HOST_PORT is missing from .env' 'compare .env with .env.example'
gpu_device="$(dotenv_value NINFER_GPU_DEVICE)" || fail 'NINFER_GPU_DEVICE is missing from .env' 'compare .env with .env.example'
model_name="$(dotenv_value NINFER_MODEL_FILE)" || fail 'NINFER_MODEL_FILE is missing from .env' 'compare .env with .env.example'
model_id="$(dotenv_value NINFER_MODEL_ID)" || fail 'NINFER_MODEL_ID is missing from .env' 'compare .env with .env.example'
context_length="$(dotenv_value NINFER_CONTEXT_LENGTH)" || fail 'NINFER_CONTEXT_LENGTH is missing from .env' 'compare .env with .env.example'
[[ "$NINFER_API_KEY" =~ ^[[:xdigit:]]{64}$ ]] || fail 'NINFER_API_KEY must be a 64-character hexadecimal secret' './scripts/setup.sh'
[[ "$host_port" =~ ^[0-9]+$ ]] \
  || fail 'NINFER_HOST_PORT must be numeric' 'edit .env'
(( host_port >= 1 && host_port <= 65535 )) \
  || fail 'NINFER_HOST_PORT must be from 1 through 65535' 'edit .env'
[[ "$gpu_device" =~ ^[0-9]+$ ]] || fail 'NINFER_GPU_DEVICE must be a non-negative integer' 'edit .env'
[[ "$model_name" =~ ^[A-Za-z0-9._-]+\.ninfer$ ]] || fail 'NINFER_MODEL_FILE must be a safe .ninfer basename' 'edit .env'
[[ "$model_id" =~ ^[A-Za-z0-9._-]+$ ]] || fail 'NINFER_MODEL_ID contains unsupported characters' 'edit .env'
[[ "$context_length" =~ ^[0-9]+$ ]] || fail 'NINFER_CONTEXT_LENGTH must be numeric' 'edit .env'
pass "model=$model_id context=$context_length GPU device=$gpu_device"

compose=(docker compose --project-directory "$root_dir" --env-file "$root_dir/.env" -f "$root_dir/docker-compose.yml")
tmp_dir="$(mktemp -d)"
sentinel=''

cleanup() {
  local status=$?
  [[ -z "$sentinel" ]] || rm -f -- "$sentinel"
  if (( status == 0 )); then
    rm -rf -- "$tmp_dir"
  else
    echo "Verification responses were preserved at: $tmp_dir" >&2
  fi
}
trap cleanup EXIT

begin 'Compose and source pin'
"${compose[@]}" config --quiet 2>"$tmp_dir/compose-config.log" \
  || fail 'Docker Compose configuration is invalid' 'docker compose --env-file .env config'
actual_commit="$(git -C ninfer rev-parse HEAD 2>/dev/null)" \
  || fail 'The NInfer submodule is not initialized' 'git submodule update --init --recursive'
expected_commit='feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a'
[[ "$actual_commit" == "$expected_commit" ]] \
  || fail "NInfer is at $actual_commit, expected $expected_commit" 'git submodule update --init --recursive --checkout'
pass "NInfer ${actual_commit:0:12}; Compose resolves"

begin 'Docker daemon'
docker info >/dev/null 2>"$tmp_dir/docker-info.log" \
  || fail 'Docker is not running or is not reachable' 'docker info'
docker_version="$(docker version --format '{{.Server.Version}}' 2>/dev/null)"
pass "Docker Engine $docker_version"

begin 'NVIDIA container runtime'
runtime_json="$(docker info --format '{{json .Runtimes}}' 2>/dev/null)" \
  || fail 'Docker runtime information is unavailable' 'docker info'
grep -q 'nvidia' <<<"$runtime_json" \
  || fail 'Docker does not advertise the NVIDIA runtime' 'configure NVIDIA Container Toolkit, restart Docker, then run docker info'
pass 'NVIDIA runtime is registered with Docker'

begin 'RTX 5090 GPU passthrough'
gpu_output="$("${compose[@]}" run --rm --no-deps -T --entrypoint nvidia-smi ninfer \
  --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>&1)" \
  || fail 'A NInfer container could not access the selected GPU' 'docker compose run --rm --no-deps --entrypoint nvidia-smi ninfer'
grep -qi 'RTX 5090' <<<"$gpu_output" \
  || fail "The selected container GPU is not an RTX 5090: $gpu_output" 'set NINFER_GPU_DEVICE in .env to the RTX 5090 index'
pass "$gpu_output"

begin 'Pinned model artifact'
model_file="$root_dir/models/$model_name"
expected_model='qwen3_8_27b_nvfp4.ninfer'
expected_sha='bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32'
[[ "$model_name" == "$expected_model" ]] \
  || fail "No checksum is registered for $model_name" 'document and register the replacement artifact before verification'
[[ -s "$model_file" ]] || fail "Missing models/$model_name" './scripts/download-model.sh'
actual_sha="$(hash_file "$model_file")" \
  || fail 'Neither sha256sum nor shasum is available' 'install coreutils or use a shell with shasum'
[[ "$actual_sha" == "$expected_sha" ]] \
  || fail "Model checksum mismatch (expected $expected_sha, got $actual_sha)" './scripts/download-model.sh'
pass 'Qwen3.8-27B NVFP4 checksum matches'

begin 'NInfer container health'
ninfer_id="$("${compose[@]}" ps -q ninfer)"
[[ -n "$ninfer_id" ]] || fail 'NInfer is not running' 'docker compose up -d --wait --wait-timeout 900 ninfer'
ninfer_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$ninfer_id")" \
  || fail "Could not inspect NInfer container $ninfer_id" 'docker compose ps && docker compose logs --tail=100 ninfer'
if [[ "$ninfer_health" != healthy ]]; then
  "${compose[@]}" logs --tail=80 ninfer >&2 || true
  fail "NInfer health is '$ninfer_health'" 'docker compose logs --tail=200 ninfer'
fi
pass 'NInfer /health reports ready'

begin 'NInfer authenticated API'
curl --fail --silent --show-error --max-time 30 \
  -H "Authorization: Bearer $NINFER_API_KEY" \
  "http://127.0.0.1:${host_port}/v1/models" \
  -o "$tmp_dir/models.json" \
  || fail "GET /v1/models failed on 127.0.0.1:$host_port" 'docker compose logs --tail=100 ninfer'
jq -e --arg model "$model_id" 'any(.data[]?; .id == $model)' "$tmp_dir/models.json" >/dev/null \
  || fail "NInfer does not advertise model ID $model_id" 'compare NINFER_MODEL_ID in .env with NInfer startup logs'
pass "GET /v1/models advertises $model_id"

begin 'Direct NInfer generation'
direct_payload="$(jq -cn --arg model "$model_id" '{model:$model,messages:[{role:"user",content:"Reply with exactly NINFER_DIRECT_OK and nothing else."}],max_tokens:64,temperature:0,enable_thinking:false}')"
curl --fail --silent --show-error --max-time 600 \
  -H "Authorization: Bearer $NINFER_API_KEY" \
  -H 'Content-Type: application/json' \
  --data "$direct_payload" \
  "http://127.0.0.1:${host_port}/v1/chat/completions" \
  -o "$tmp_dir/ninfer-chat.json" \
  || fail 'Direct /v1/chat/completions request failed' 'docker compose logs --tail=200 ninfer'
jq -e '((.choices[0].message.content // "") | gsub("^\\s+|\\s+$"; "")) == "NINFER_DIRECT_OK"' \
  "$tmp_dir/ninfer-chat.json" >/dev/null \
  || fail 'NInfer returned a response, but not the deterministic verification marker' "cat $tmp_dir/ninfer-chat.json"
pass 'OpenAI-compatible chat completion succeeded'

begin 'Hermes health and routing'
hermes_id="$("${compose[@]}" ps -q hermes)"
[[ -n "$hermes_id" ]] || fail 'Hermes is not running' 'docker compose up -d --wait --wait-timeout 900 hermes'
hermes_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$hermes_id")" \
  || fail "Could not inspect Hermes container $hermes_id" 'docker compose ps && docker compose logs --tail=100 hermes'
if [[ "$hermes_health" != healthy ]]; then
  "${compose[@]}" logs --tail=80 hermes >&2 || true
  fail "Hermes health is '$hermes_health'" 'docker compose logs --tail=200 hermes'
fi
# The positional parameters and container environment expand inside Hermes.
# shellcheck disable=SC2016
"${compose[@]}" exec -T hermes sh -lc '
  hermes config check >/dev/null
  test "$(hermes config get model.provider)" = custom:ninfer
  test "$(hermes config get model.default)" = "$1"
  test "$(hermes config get model.context_length)" = "$2"
  test "$(hermes config get providers.ninfer.api)" = http://ninfer:8080/v1
  getent hosts ninfer >/dev/null
  curl -fsS -H "Authorization: Bearer $NINFER_API_KEY" http://ninfer:8080/v1/models | grep -q "$1"
' sh "$model_id" "$context_length" \
  || fail 'Hermes config does not match .env, or Hermes cannot reach NInfer' './scripts/configure-hermes.sh; docker compose exec hermes getent hosts ninfer'
pass "Hermes uses custom:ninfer / $model_id / context $context_length and resolves NInfer"

begin 'Hermes to NInfer generation'
hermes_payload='{"model":"hermes-agent","messages":[{"role":"user","content":"Reply with exactly HERMES_NINFER_OK and nothing else. Do not use tools."}],"stream":false}'
# The container environment expands inside Hermes.
# shellcheck disable=SC2016
"${compose[@]}" exec -T hermes sh -lc '
  curl --fail --silent --show-error --max-time 900 \
    -H "Authorization: Bearer $API_SERVER_KEY" \
    -H "Content-Type: application/json" \
    --data "$1" \
    http://127.0.0.1:8642/v1/chat/completions
' sh "$hermes_payload" > "$tmp_dir/hermes-chat.json" \
  || fail 'Hermes could not complete a prompt through NInfer' 'docker compose logs --tail=200 hermes; docker compose logs --tail=200 ninfer'
jq -e '((.choices[0].message.content // "") | gsub("^\\s+|\\s+$"; "")) == "HERMES_NINFER_OK"' \
  "$tmp_dir/hermes-chat.json" >/dev/null \
  || fail 'Hermes returned a response, but not the deterministic verification marker' "cat $tmp_dir/hermes-chat.json"
pass 'Hermes completed a request through NInfer'

begin 'Agent tool execution in sandbox'
sentinel="$(mktemp "$root_dir/workspace/.hermes-sandbox-verify.XXXXXX")" \
  || fail 'Could not create a workspace sentinel' 'check write permissions on workspace/'
sentinel_name="${sentinel##*/}"
tool_payload="$(jq -cn --arg sentinel "$sentinel_name" '{
  model:"hermes-agent",
  messages:[{
    role:"user",
    content:("You must use the terminal tool, not prior knowledge. Run this exact command on its own line and do not alter it:\nuname -r > /workspace/" + $sentinel + "\nAfter the tool succeeds, reply exactly TOOL_EXECUTION_OK.")
  }],
  stream:false
}')"
# The container environment expands inside Hermes.
# shellcheck disable=SC2016
"${compose[@]}" exec -T hermes sh -lc '
  curl --fail --silent --show-error --max-time 900 \
    -H "Authorization: Bearer $API_SERVER_KEY" \
    -H "Content-Type: application/json" \
    --data "$1" \
    http://127.0.0.1:8642/v1/chat/completions
' sh "$tool_payload" > "$tmp_dir/hermes-tool.json" \
  || fail 'Hermes tool-call request failed' 'docker compose logs --tail=200 hermes; docker compose logs --tail=100 sandbox'
[[ -s "$sentinel" ]] \
  || fail 'The model did not produce a successful terminal side effect in workspace/' 'docker compose logs --tail=200 hermes; docker compose logs --tail=100 sandbox'
jq -e '((.choices[0].message.content // "") | gsub("^\\s+|\\s+$"; "")) == "TOOL_EXECUTION_OK"' \
  "$tmp_dir/hermes-tool.json" >/dev/null \
  || fail 'The sandbox command ran, but Hermes did not return the expected marker' "cat $tmp_dir/hermes-tool.json"
kernel_version="$(tr -d '\r\n' < "$sentinel")"
pass "Hermes executed uname in the SSH sandbox (kernel $kernel_version)"

echo
echo "All $total_steps verification layers passed."
