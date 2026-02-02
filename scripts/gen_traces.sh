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

sources=()
if [[ -n "${BENCH_LIST:-}" ]]; then
  if [[ ! -f "${BENCH_LIST}" ]]; then
    echo "Bench list not found: ${BENCH_LIST}" >&2
    exit 1
  fi
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    [[ "${line}" == \#* ]] && continue
    sources+=("${ROOT}/${line}")
  done < "${BENCH_LIST}"
else
  shopt -s nullglob
  sources=("${ROOT}"/examples/*.c)
fi
if (( ${#sources[@]} == 0 )); then
  echo "No benchmark sources found." >&2
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

  runs="${RUN_REPEAT:-1}"
  if (( runs < 1 )); then
    runs=1
  fi
  times=()
  for ((i = 0; i < runs; i++)); do
    start_ns="$(date +%s%N)"
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
    end_ns="$(date +%s%N)"
    elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))
    times+=("${elapsed_ms}")
  done
  min_ms="${times[0]}"
  max_ms="${times[0]}"
  sum_ms=0
  for t in "${times[@]}"; do
    (( sum_ms += t ))
    if (( t < min_ms )); then min_ms="${t}"; fi
    if (( t > max_ms )); then max_ms="${t}"; fi
  done
  avg_ms=$(( sum_ms / runs ))
  sorted=($(printf '%s\n' "${times[@]}" | sort -n))
  if (( runs % 2 == 1 )); then
    median_ms="${sorted[$((runs / 2))]}"
  else
    mid=$((runs / 2))
    median_ms=$(( (sorted[mid - 1] + sorted[mid]) / 2 ))
  fi

  echo "Wrote ${trace}"
  echo "Wrote ${cfg}"
  if [[ "${TRACE_INDEX:-0}" == "1" ]]; then
    echo "Wrote ${index}"
  fi
  if [[ "${EMIT_RUN_SUMMARY:-0}" == "1" ]]; then
    summary="${OUT_DIR}/${base}.run_summary.ndjson"
    printf '{"kind":"run_summary","source":"%s","elapsed_ms":%s,"elapsed_ms_min":%s,"elapsed_ms_max":%s,"elapsed_ms_median":%s,"elapsed_ms_mean":%s,"elapsed_runs":%s,"max_paths":%s,"max_path_depth":%s,"max_loop_iters":%s,"max_inst":%s}\n' \
      "${base}" \
      "${avg_ms}" \
      "${min_ms}" \
      "${max_ms}" \
      "${median_ms}" \
      "${avg_ms}" \
      "${runs}" \
      "${MAX_PATHS:-200}" \
      "${MAX_PATH_DEPTH:-256}" \
      "${MAX_LOOP_ITERS:-0}" \
      "${MAX_INST:-0}" \
      > "${summary}"
    echo "Wrote ${summary}"
  fi
done
