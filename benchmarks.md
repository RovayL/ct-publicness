Benchmark Suite

Purpose
This file documents how to run and extend the benchmark suite used for
evaluation (path counts, pruning stats, and runtime).

Current suite
The default suite is listed in benchmarks.txt:
- examples/toy.c
- examples/linear.c
- examples/loop.c
- examples/diversity.c
- examples/const_pruned.ll

Add a new benchmark
1) Add a new C or LLVM IR (`.ll`) file under examples/ (or elsewhere).
2) Add its relative path to benchmarks.txt.
3) Regenerate traces:
   BENCH_LIST=benchmarks.txt ./scripts/gen_traces.sh

Run benchmarks
1) One-shot CSV (all CFGs):
   ./scripts/run_benchmarks.sh benchmarks.csv

2) Repeat runs for timing stability:
   RUN_REPEAT=5 ./scripts/run_benchmarks.sh benchmarks.csv

Inputs and outputs
- Input sources: paths in benchmarks.txt (relative to repo root).
- Outputs:
  - build/traces/*.ndjson        (trace)
  - build/traces/*.cfg.ndjson    (CFG/path)
  - build/traces/*.path_public.ndjson (symexec results + solver summaries)
  - build/traces/*.public_at_point.ndjson (aggregated results)
  - build/traces/*.run_summary.ndjson (timings, if EMIT_RUN_SUMMARY=1)
  - benchmarks.csv (combined metrics, including query_count + solver_time_ms)

Environment knobs (selected)
- RUN_REPEAT: number of opt runs per source (timing stats).
- MAX_PATHS, MAX_PATH_DEPTH, MAX_LOOP_ITERS, MAX_INST: path/trace budgets.
- TRACE_INDEX, TRACE_TYPES, EMIT_PP_COVERAGE, INCLUDE_PP_SEQ: trace options.
- RUN_SYMEX, ANALYZE_MODE, ANALYZE_NO_CACHE, AGGREGATE_RESULTS: Person B analysis controls in `run_benchmarks.sh`.
