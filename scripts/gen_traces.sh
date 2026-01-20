#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT}/build"
PLUGIN="${BUILD_DIR}/PublicDataPass.so"
OUT_DIR="${BUILD_DIR}/traces"

if [[ ! -f "${PLUGIN}" ]]; then
  echo "Missing ${PLUGIN}. Build the plugin first." >&2
  echo "Hint: (cd \"${BUILD_DIR}\" && ninja)" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

shopt -s nullglob
sources=("${ROOT}"/examples/*.c)
if (( ${#sources[@]} == 0 )); then
  echo "No example .c files found in ${ROOT}/examples" >&2
  exit 1
fi

for src in "${sources[@]}"; do
  base="$(basename "${src}" .c)"
  ll="${OUT_DIR}/${base}.ll"
  trace="${OUT_DIR}/${base}.ndjson"
  cfg="${OUT_DIR}/${base}.cfg.ndjson"
  index="${OUT_DIR}/${base}.trace_index.ndjson"

  clang -O0 -Xclang -disable-O0-optnone -S -emit-llvm "${src}" -o "${ll}"
  trace_index_arg=()
  if [[ "${TRACE_INDEX:-0}" == "1" ]]; then
    trace_index_arg=(-public-data-trace-index="${index}")
  fi

  opt -load-pass-plugin "${PLUGIN}" \
    -passes="function(public-data)" \
    -public-data-quiet \
    -public-data-trace="${trace}" \
    -public-data-trace-types="${TRACE_TYPES:-0}" \
    -public-data-max-inst="${MAX_INST:-0}" \
    -public-data-cfg="${cfg}" \
    -public-data-max-loop-iters="${MAX_LOOP_ITERS:-0}" \
    -public-data-max-paths="${MAX_PATHS:-200}" \
    -public-data-max-path-depth="${MAX_PATH_DEPTH:-256}" \
    -public-data-path-cond-format="${PATH_COND_FORMAT:-string}" \
    -public-data-path-include-pp-seq="${INCLUDE_PP_SEQ:-0}" \
    -public-data-pp-coverage="${EMIT_PP_COVERAGE:-0}" \
    "${trace_index_arg[@]}" \
    -disable-output "${ll}"

  echo "Wrote ${trace}"
  echo "Wrote ${cfg}"
  if [[ "${TRACE_INDEX:-0}" == "1" ]]; then
    echo "Wrote ${index}"
  fi
done
