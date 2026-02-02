#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TRACE_INDEX="${TRACE_INDEX:-1}"
TRACE_TYPES="${TRACE_TYPES:-0}"
EMIT_PP_COVERAGE="${EMIT_PP_COVERAGE:-1}"
INCLUDE_PP_SEQ="${INCLUDE_PP_SEQ:-0}"
PATH_COND_FORMAT="${PATH_COND_FORMAT:-string}"
MAX_PATHS="${MAX_PATHS:-200}"
MAX_PATH_DEPTH="${MAX_PATH_DEPTH:-256}"
MAX_LOOP_ITERS="${MAX_LOOP_ITERS:-0}"
MAX_INST="${MAX_INST:-0}"
BENCH_LIST="${BENCH_LIST:-${ROOT}/benchmarks.txt}"
EMIT_RUN_SUMMARY="${EMIT_RUN_SUMMARY:-1}"
RUN_REPEAT="${RUN_REPEAT:-1}"

export TRACE_INDEX TRACE_TYPES EMIT_PP_COVERAGE INCLUDE_PP_SEQ PATH_COND_FORMAT
export MAX_PATHS MAX_PATH_DEPTH MAX_LOOP_ITERS MAX_INST
export BENCH_LIST EMIT_RUN_SUMMARY RUN_REPEAT
./scripts/gen_traces.sh

OUT="${1:-${ROOT}/benchmarks.csv}"
shift || true

cfg_args=()
if (( $# > 0 )); then
  if [[ $# -eq 1 && ( "$1" == *"*"* || "$1" == *"?"* || "$1" == *"["* ) ]]; then
    cfg_args=(--cfg-glob "$1")
  else
    for cfg in "$@"; do
      cfg_args+=(--cfg "$cfg")
    done
  fi
else
  cfg_args=(--cfg-glob "${ROOT}/build/traces/*.cfg.ndjson")
fi

python3 -m symex.benchmarks "${cfg_args[@]}" --out "${OUT}"
echo "Wrote ${OUT}"
