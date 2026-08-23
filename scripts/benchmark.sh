#!/usr/bin/env bash
set -Eeuo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

die() {
  echo "benchmark: $*" >&2
  exit 1
}

for command_name in docker curl jq awk grep git date mktemp sed head tr; do
  command -v "$command_name" >/dev/null 2>&1 || die "missing required command: $command_name"
done
[[ -f .env ]] || die 'missing .env; run ./scripts/setup.sh'

dotenv_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" .env | tail -n 1 | tr -d '\r')" || return 1
  [[ "$line" == "${key}="* ]] || return 1
  printf '%s' "${line#*=}"
}

api_key="$(dotenv_value NINFER_API_KEY)" || die 'NINFER_API_KEY is missing from .env'
host_port="$(dotenv_value NINFER_HOST_PORT)" || die 'NINFER_HOST_PORT is missing from .env'
model_id="$(dotenv_value NINFER_MODEL_ID)" || die 'NINFER_MODEL_ID is missing from .env'
model_file="$(dotenv_value NINFER_MODEL_FILE)" || die 'NINFER_MODEL_FILE is missing from .env'
context_length="$(dotenv_value NINFER_CONTEXT_LENGTH)" || die 'NINFER_CONTEXT_LENGTH is missing from .env'
max_concurrency="$(dotenv_value NINFER_MAX_CONCURRENCY)" || die 'NINFER_MAX_CONCURRENCY is missing from .env'
hermes_image="$(dotenv_value HERMES_IMAGE)" || die 'HERMES_IMAGE is missing from .env'
runs="${BENCHMARK_RUNS:-3}"
max_tokens="${BENCHMARK_MAX_TOKENS:-512}"

[[ "$api_key" =~ ^[[:xdigit:]]{64}$ ]] || die 'NINFER_API_KEY must be a 64-character hexadecimal secret'
[[ "$host_port" =~ ^[0-9]+$ ]] || die 'NINFER_HOST_PORT must be numeric'
[[ "$model_id" =~ ^[A-Za-z0-9._-]+$ ]] || die 'NINFER_MODEL_ID contains unsupported characters'
[[ "$model_file" =~ ^[A-Za-z0-9._-]+\.ninfer$ ]] || die 'NINFER_MODEL_FILE must be a safe .ninfer basename'
[[ "$context_length" =~ ^[0-9]+$ ]] || die 'NINFER_CONTEXT_LENGTH must be numeric'
[[ "$max_concurrency" =~ ^[0-9]+$ ]] || die 'NINFER_MAX_CONCURRENCY must be numeric'
[[ "$runs" =~ ^[0-9]+$ ]] || die 'BENCHMARK_RUNS must be numeric'
(( runs >= 1 && runs <= 20 )) || die 'BENCHMARK_RUNS must be from 1 through 20'
[[ "$max_tokens" =~ ^[0-9]+$ ]] || die 'BENCHMARK_MAX_TOKENS must be numeric'
(( max_tokens >= 32 && max_tokens <= 4096 )) || die 'BENCHMARK_MAX_TOKENS must be from 32 through 4096'

compose=(docker compose --project-directory "$root_dir" --env-file "$root_dir/.env" -f "$root_dir/docker-compose.yml")
ninfer_id="$("${compose[@]}" ps -q ninfer)"
[[ -n "$ninfer_id" ]] || die 'NInfer is not running; use docker compose up -d'
health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$ninfer_id")"
[[ "$health" == healthy ]] || die "NInfer health is '$health'; inspect docker compose logs ninfer"

curl --fail --silent --show-error --max-time 30 \
  -H "Authorization: Bearer $api_key" \
  "http://127.0.0.1:${host_port}/v1/models" >/dev/null \
  || die 'the NInfer API is not reachable'

timestamp="$(date -u +'%Y%m%dT%H%M%SZ')"
started_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
result_dir="$root_dir/benchmarks/$timestamp"
mkdir -p "$result_dir"
sampler_pid=''

cleanup() {
  local status=$?
  if [[ -n "$sampler_pid" ]] && kill -0 "$sampler_pid" 2>/dev/null; then
    kill "$sampler_pid" 2>/dev/null || true
    wait "$sampler_pid" 2>/dev/null || true
  fi
  if (( status != 0 )); then
    echo "Partial benchmark evidence was preserved at: $result_dir" >&2
  fi
}
trap cleanup EXIT

prompt_template='Explain how prefill and decode differ in an autoregressive transformer. Use eight numbered points, include one concrete latency example, and finish with a two-sentence summary.'
printf '%s\n' '<unique first word>. '"$prompt_template" > "$result_dir/prompt-template.txt"
nonce_words=(Amber Birch Cobalt Delta Ember Fjord Granite Harbor Indigo Juniper Kestrel Linden Maple Nimbus Onyx Poppy Quartz Rowan Sable Topaz)

gpu_line="$("${compose[@]}" exec -T ninfer nvidia-smi \
  --query-gpu=name,driver_version,memory.total \
  --format=csv,noheader,nounits | tr -d '\r' | head -n 1)" \
  || die 'could not query GPU metadata from the NInfer container'
gpu_name="$(awk -F, '{gsub(/^[ \t]+|[ \t]+$/, "", $1); print $1}' <<<"$gpu_line")"
driver_version="$(awk -F, '{gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2}' <<<"$gpu_line")"
vram_total_mib="$(awk -F, '{gsub(/^[ \t]+|[ \t]+$/, "", $3); print $3}' <<<"$gpu_line")"
ninfer_commit="$(git -C ninfer rev-parse HEAD)"
docker_version="$(docker version --format '{{.Server.Version}}')"
compose_version="$(docker compose version --short)"
cuda_base="$(grep -m1 -E '^FROM nvidia/cuda:' ninfer/Dockerfile | sed -E 's/^FROM nvidia\/cuda:([^ ]+).*/\1/')"
image_id="$(docker inspect --format '{{.Image}}' "$ninfer_id")"
model_path="$root_dir/models/$model_file"
[[ -s "$model_path" ]] || die "model file is missing: models/$model_file"
if command -v sha256sum >/dev/null 2>&1; then
  model_sha256="$(sha256sum "$model_path" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  model_sha256="$(shasum -a 256 "$model_path" | awk '{print $1}')"
else
  die 'sha256sum or shasum is required to record the model checksum'
fi
expected_model_sha256='bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32'
[[ "$model_sha256" == "$expected_model_sha256" ]] || die 'model checksum does not match the registered benchmark artifact'

jq -n \
  --arg collected_at "$timestamp" \
  --arg gpu "$gpu_name" \
  --arg driver "$driver_version" \
  --arg vram_total_mib "$vram_total_mib" \
  --arg docker "$docker_version" \
  --arg compose "$compose_version" \
  --arg cuda_base "$cuda_base" \
  --arg ninfer_commit "$ninfer_commit" \
  --arg image_id "$image_id" \
  --arg model_id "$model_id" \
  --arg model_file "$model_file" \
  --arg model_sha256 "$model_sha256" \
  --arg context_length "$context_length" \
  --arg max_concurrency "$max_concurrency" \
  --arg hermes_image "$hermes_image" \
  --arg quantization 'NVFP4' \
  --arg runs "$runs" \
  --arg max_tokens "$max_tokens" \
  '{
    collected_at_utc:$collected_at,
    gpu:$gpu,
    driver_version:$driver,
    vram_total_mib:($vram_total_mib|tonumber),
    docker_engine:$docker,
    docker_compose:$compose,
    cuda_image:$cuda_base,
    ninfer_commit:$ninfer_commit,
    ninfer_image_id:$image_id,
    model_id:$model_id,
    model_file:$model_file,
    model_sha256:$model_sha256,
    quantization:$quantization,
    context_length:($context_length|tonumber),
    kv_cache:{dtype:"int8",capacity:"auto"},
    max_concurrency:($max_concurrency|tonumber),
    prefill_chunk:1024,
    speculative_decoding:{mode:"mtp",draft_tokens:3,lm_head_draft:true},
    prefix_reuse:{enabled:true,workload_control:"unique first user word per measured request; shared chat-template prefixes may remain reusable"},
    vision_enabled:false,
    hermes_image:$hermes_image,
    measurement_scope:"direct NInfer HTTP API",
    benchmark_runs:($runs|tonumber),
    max_completion_tokens:($max_tokens|tonumber),
    timing:"client-observed SSE wall clock",
    server_state:"warm persistent server; kernels warmed with a separate prompt"
  }' > "$result_dir/environment.json"

echo "Warming the persistent NInfer server..."
warmup_payload="$(jq -cn --arg model "$model_id" '{model:$model,messages:[{role:"user",content:"Reply with exactly WARMUP_OK."}],max_tokens:32,temperature:0,enable_thinking:false,stream:false}')"
curl --fail --silent --show-error --max-time 600 \
  -H "Authorization: Bearer $api_key" \
  -H 'Content-Type: application/json' \
  --data "$warmup_payload" \
  "http://127.0.0.1:${host_port}/v1/chat/completions" \
  > "$result_dir/warmup.json" \
  || die 'warm-up request failed'

printf 'run,prompt_tokens,completion_tokens,ttft_ms,total_seconds,generation_tokens_per_second,gpu_samples,gpu_utilization_mean_pct,gpu_utilization_max_pct,vram_max_mib\n' \
  > "$result_dir/runs.csv"

for ((run = 1; run <= runs; run++)); do
  run_id="$(printf '%02d' "$run")"
  echo "Running measurement $run/$runs..."
  prompt="${nonce_words[$((run - 1))]}. $prompt_template"
  printf '%s\n' "$prompt" > "$result_dir/run-$run_id.prompt.txt"
  payload="$(jq -cn \
    --arg model "$model_id" \
    --arg prompt "$prompt" \
    --argjson max_tokens "$max_tokens" \
    --argjson seed "$run" \
    '{model:$model,messages:[{role:"user",content:$prompt}],max_completion_tokens:$max_tokens,temperature:0,seed:$seed,enable_thinking:false,stream:true,stream_options:{include_usage:true}}')"

  timed_sse="$result_dir/run-$run_id.sse.tsv"
  gpu_samples="$result_dir/run-$run_id.gpu.csv"
  response_file="$result_dir/run-$run_id.response.txt"
  : > "$response_file"

  "${compose[@]}" exec -T ninfer nvidia-smi \
    --query-gpu=utilization.gpu,memory.used \
    --format=csv,noheader,nounits \
    --loop-ms=250 > "$gpu_samples" 2>"$result_dir/run-$run_id.gpu.log" &
  sampler_pid=$!

  start_ns="$(date +%s%N)"
  if ! curl --fail --silent --show-error --no-buffer --max-time 1800 \
    -H "Authorization: Bearer $api_key" \
    -H 'Content-Type: application/json' \
    --data "$payload" \
    "http://127.0.0.1:${host_port}/v1/chat/completions" \
    | while IFS= read -r line; do
        printf '%s\t%s\n' "$(date +%s%N)" "$line"
      done > "$timed_sse"; then
    die "streaming request $run failed"
  fi
  end_ns="$(date +%s%N)"
  if ! kill -0 "$sampler_pid" 2>/dev/null; then
    sampler_status=0
    wait "$sampler_pid" 2>/dev/null || sampler_status=$?
    sampler_pid=''
    die "GPU sampler stopped before request $run completed (exit $sampler_status)"
  fi
  kill "$sampler_pid" 2>/dev/null || true
  wait "$sampler_pid" 2>/dev/null || true
  sampler_pid=''

  first_token_ns=''
  prompt_tokens=''
  completion_tokens=''
  while IFS=$'\t' read -r event_ns line; do
    [[ "$line" == data:* ]] || continue
    data="${line#data: }"
    [[ "$data" != '[DONE]' ]] || continue
    if [[ -z "$first_token_ns" ]] \
      && jq -e '((.choices[0].delta.content // .choices[0].delta.reasoning_content // "") | length) > 0' \
        >/dev/null 2>&1 <<<"$data"; then
      first_token_ns="$event_ns"
    fi
    jq -r '.choices[0].delta.content // .choices[0].delta.reasoning_content // empty' \
      <<<"$data" >> "$response_file" 2>/dev/null || true
    usage_prompt="$(jq -r '.usage.prompt_tokens // empty' <<<"$data" 2>/dev/null || true)"
    usage_completion="$(jq -r '.usage.completion_tokens // empty' <<<"$data" 2>/dev/null || true)"
    [[ -z "$usage_prompt" ]] || prompt_tokens="$usage_prompt"
    [[ -z "$usage_completion" ]] || completion_tokens="$usage_completion"
  done < "$timed_sse"

  [[ "$first_token_ns" =~ ^[0-9]+$ ]] || die "request $run emitted no token-bearing SSE event"
  [[ "$prompt_tokens" =~ ^[0-9]+$ ]] || die "request $run emitted no prompt-token usage"
  [[ "$completion_tokens" =~ ^[0-9]+$ ]] || die "request $run emitted no completion-token usage"

  read -r ttft_ms total_seconds generation_tps < <(
    awk -v start="$start_ns" -v first="$first_token_ns" -v end="$end_ns" -v tokens="$completion_tokens" \
      'BEGIN {
        ttft=(first-start)/1000000;
        total=(end-start)/1000000000;
        decode=(end-first)/1000000000;
        rate=(decode>0 && tokens>1) ? (tokens-1)/decode : 0;
        printf "%.2f %.3f %.2f\n", ttft, total, rate;
      }'
  )

  gpu_metrics="$(awk -F, '
      {
        gsub(/^[ \t]+|[ \t]+$/, "", $1);
        gsub(/^[ \t]+|[ \t]+$/, "", $2);
        if ($1 ~ /^[0-9.]+$/ && $2 ~ /^[0-9.]+$/) {
          count++; sum += $1;
          if ($1 > max_gpu) max_gpu=$1;
          if ($2 > max_vram) max_vram=$2;
        }
      }
      END {
        if (count == 0) exit 1;
        printf "%d %.2f %.2f %.0f\n", count, sum/count, max_gpu, max_vram;
      }' "$gpu_samples"
  )" || die "request $run produced no valid GPU samples; inspect run-$run_id.gpu.log"
  read -r gpu_sample_count gpu_mean gpu_max vram_max <<<"$gpu_metrics"

  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$run" "$prompt_tokens" "$completion_tokens" "$ttft_ms" "$total_seconds" \
    "$generation_tps" "$gpu_sample_count" "$gpu_mean" "$gpu_max" "$vram_max" \
    >> "$result_dir/runs.csv"
done

"${compose[@]}" logs --no-color --since "$started_at" ninfer > "$result_dir/ninfer.log" 2>&1 \
  || echo 'Warning: could not capture NInfer logs for this benchmark.' >&2

read -r mean_ttft mean_tps peak_vram < <(
  awk -F, 'NR>1 {n++; ttft+=$4; tps+=$6; if ($10>vram) vram=$10} END {printf "%.2f %.2f %.0f\n", ttft/n, tps/n, vram}' \
    "$result_dir/runs.csv"
)

{
  echo '# Local NInfer benchmark'
  echo
  echo "Collected: $timestamp"
  echo
  echo "- GPU: $gpu_name ($vram_total_mib MiB), driver $driver_version"
  echo "- CUDA image: $cuda_base"
  echo "- Docker: Engine $docker_version, Compose $compose_version"
  echo "- NInfer: \`$ninfer_commit\`"
  echo "- Model: $model_id / $model_file (NVFP4)"
  echo "- Model SHA-256: \`$model_sha256\`"
  echo "- Context ceiling: $context_length tokens"
  echo "- Runtime profile: INT8 automatic KV, concurrency $max_concurrency, prefill 1024, MTP3, prefix reuse enabled"
  echo "- Timing: client-observed SSE wall clock on a warm persistent server"
  echo "- Cache control: each measured request begins with a different user word; shared chat-template prefixes may remain reusable"
  echo
  echo '| Runs | Mean TTFT | Mean generation | Peak VRAM |'
  echo '|---:|---:|---:|---:|'
  echo "| $runs | $mean_ttft ms | $mean_tps tok/s | $peak_vram MiB |"
  echo
  echo "Per-run measurements are in \`runs.csv\`; raw SSE timing and GPU samples are retained for audit."
} > "$result_dir/summary.md"

echo
echo "Benchmark complete: $result_dir"
echo "Mean TTFT:       $mean_ttft ms"
echo "Mean generation: $mean_tps tokens/s"
echo "Peak VRAM:       $peak_vram MiB"
echo 'Review the generated responses before publishing any result.'
