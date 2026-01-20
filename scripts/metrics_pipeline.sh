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

export TRACE_INDEX TRACE_TYPES EMIT_PP_COVERAGE INCLUDE_PP_SEQ PATH_COND_FORMAT
export MAX_PATHS MAX_PATH_DEPTH MAX_LOOP_ITERS MAX_INST

./scripts/gen_traces.sh

OUT="${1:-${ROOT}/metrics.csv}"
CFG_IN="${2:-${ROOT}/build/traces/toy.cfg.ndjson}"
python3 -m symex.metrics --cfg "${CFG_IN}" --out "${OUT}"
echo "Wrote ${OUT}"
