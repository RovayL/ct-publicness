#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TRACE_INDEX="${TRACE_INDEX:-1}"
TRACE_TYPES="${TRACE_TYPES:-0}"
EMIT_PP_COVERAGE="${EMIT_PP_COVERAGE:-1}"
INCLUDE_PP_SEQ="${INCLUDE_PP_SEQ:-0}"
PATH_COND_FORMAT="${PATH_COND_FORMAT:-both}"
MAX_PATHS="${MAX_PATHS:-200}"
MAX_PATH_DEPTH="${MAX_PATH_DEPTH:-256}"
MAX_LOOP_ITERS="${MAX_LOOP_ITERS:-0}"
MAX_INST="${MAX_INST:-0}"
BENCH_LIST="${BENCH_LIST:-${ROOT}/benchmarks.txt}"
EMIT_RUN_SUMMARY="${EMIT_RUN_SUMMARY:-1}"
RUN_REPEAT="${RUN_REPEAT:-1}"
RUN_SYMEX="${RUN_SYMEX:-1}"
ANALYZE_MODE="${ANALYZE_MODE:-symexec}"
ANALYZE_NO_CACHE="${ANALYZE_NO_CACHE:-0}"
ANALYZE_LOOP_INVARIANTS="${ANALYZE_LOOP_INVARIANTS:-0}"
AGGREGATE_RESULTS="${AGGREGATE_RESULTS:-1}"
AGGREGATE_ENHANCED="${AGGREGATE_ENHANCED:-1}"

export TRACE_INDEX TRACE_TYPES EMIT_PP_COVERAGE INCLUDE_PP_SEQ PATH_COND_FORMAT
export MAX_PATHS MAX_PATH_DEPTH MAX_LOOP_ITERS MAX_INST
export BENCH_LIST EMIT_RUN_SUMMARY RUN_REPEAT RUN_SYMEX ANALYZE_MODE ANALYZE_NO_CACHE ANALYZE_LOOP_INVARIANTS AGGREGATE_RESULTS AGGREGATE_ENHANCED
./scripts/gen_traces.sh

OUT="${1:-${ROOT}/benchmarks.csv}"
shift || true

cfg_args=()
cfg_files=()
if (( $# > 0 )); then
  if [[ $# -eq 1 && ( "$1" == *"*"* || "$1" == *"?"* || "$1" == *"["* ) ]]; then
    cfg_args=(--cfg-glob "$1")
    shopt -s nullglob
    for cfg in $1; do
      cfg_files+=("$cfg")
    done
    shopt -u nullglob
  else
    for cfg in "$@"; do
      cfg_args+=(--cfg "$cfg")
      cfg_files+=("$cfg")
    done
  fi
else
  cfg_args=(--cfg-glob "${ROOT}/build/traces/*.cfg.ndjson")
  shopt -s nullglob
  cfg_files=("${ROOT}"/build/traces/*.cfg.ndjson)
  shopt -u nullglob
fi

if (( ${#cfg_files[@]} == 0 )); then
  echo "No CFG files found for benchmark run." >&2
  exit 1
fi

if [[ "${RUN_SYMEX}" == "1" ]]; then
  no_cache_arg=()
  if [[ "${ANALYZE_NO_CACHE}" == "1" ]]; then
    no_cache_arg=(--no-cache)
  fi
  loop_inv_arg=()
  if [[ "${ANALYZE_LOOP_INVARIANTS}" == "1" ]]; then
    loop_inv_arg=(--loop-invariants)
  fi
  for cfg in "${cfg_files[@]}"; do
    base="$(basename "${cfg}" .cfg.ndjson)"
    dir="$(dirname "${cfg}")"
    trace="${dir}/${base}.ndjson"
    path_public="${dir}/${base}.path_public.ndjson"
    public_at_point="${dir}/${base}.public_at_point.ndjson"
    enhanced_public_at_point="${dir}/${base}.enhanced_public_at_point.ndjson"
    if [[ ! -f "${trace}" ]]; then
      echo "Skipping symexec: trace not found for ${cfg} (${trace})" >&2
      continue
    fi
    python3 -m symex.analyze \
      --mode "${ANALYZE_MODE}" \
      --trace "${trace}" \
      --cfg "${cfg}" \
      --out "${path_public}" \
      "${loop_inv_arg[@]}" \
      "${no_cache_arg[@]}"
    if [[ "${AGGREGATE_RESULTS}" == "1" ]]; then
      enhanced_arg=()
      if [[ "${AGGREGATE_ENHANCED}" == "1" ]]; then
        enhanced_arg=(--enhanced-out "${enhanced_public_at_point}")
      fi
      python3 -m symex.aggregate \
        --cfg "${cfg}" \
        --path-results "${path_public}" \
        --out "${public_at_point}" \
        "${enhanced_arg[@]}"
    fi
  done
fi

python3 -m symex.benchmarks "${cfg_args[@]}" --out "${OUT}"
echo "Wrote ${OUT}"
