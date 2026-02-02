Person B Python Section

Objective
Implement symbolic execution and SMT reasoning over per-path traces emitted by
the LLVM pass (Person A). The goal is to compute publicness per path and then
aggregate to public_at_point (public at a program point if public on all paths
through that point).

Inputs from Person A
- Trace NDJSON: build/traces/*.ndjson
  - See ../TRACE_SCHEMA.md for the format.
  - Optional type strings (def_ty/use_tys) with -public-data-trace-types.
- CFG/path NDJSON: build/traces/*.cfg.ndjson
  - See ../CFG_SCHEMA.md for the format.
  - Includes path IDs, decisions, path constraints, and pp coverage.
  - Path conditions can be strings or JSON (path_cond/path_cond_json).
- Optional trace index NDJSON: build/traces/*.trace_index.ndjson
  - Maps program points to trace line numbers.

Expected outputs (Person B)
- Per-path results NDJSON (path_publicness):
  {"kind":"path_publicness","fn":"foo","path_id":0,"pp":"foo:bb0:i3","value":"v7","public":true}
- Aggregated results NDJSON (public_at_point) via symex.aggregate:
  {"kind":"public_at_point","fn":"foo","pp":"foo:bb0:i3","value":"v7","public":true,...}

Workflow diagram
```
Person A outputs
  trace.ndjson  ----\
  cfg.ndjson     ----+--> parser.py ---> pipeline.py ---> analyze.py ---+
  trace_index     ---/                                      |           |
                                                         stub        symexec
                                                          |            |
                                                          v            v
                                                   path_publicness   symexec.py
                                                    (public=None)       |
                                                                         v
                                                                    solver.py (Z3)
                                                                         |
                                                                         v
                                                                  path_publicness
                                                                         |
                                                                         v
cfg.ndjson --------------------------------------------------------> aggregate.py
                                                                    publicness.py
                                                                         |
                                                                         v
                                                                  public_at_point

trace_index.ndjson ---> join_trace_index.py ---> path_public.with_line.ndjson
cfg.ndjson ---------> main.py (summaries / check_paths -> constraints.py -> solver.py)
cfg.ndjson ---------> metrics.py -> metrics.csv -> benchmarks.py (+ run_summary) -> benchmarks.csv
```

Workflow (in words)
1) Person A runs the LLVM pass to emit `trace.ndjson` and `cfg.ndjson` (and
   optionally `trace_index.ndjson`).
2) `parser.py` loads those NDJSON files into typed records via
   `load_trace()`, `load_cfg()`, and `load_trace_index()`.
3) `pipeline.py` calls those loaders and builds path bundles with
   `build_pipeline()` (CFG path + instruction list, using `pp_seq` if present).
4) `analyze.py` produces per-path publicness:
   - `--mode stub` emits placeholder `public=None`.
   - `--mode symexec` calls `SymExecEngine.analyze_path()` in `symexec.py`,
     which executes each path twice and queries Z3 via `solver.py`.
5) `aggregate.py` combines `path_publicness` + `cfg.ndjson` to compute
   `public_at_point` (public on all paths through a program point).
6) Optional utilities add detail:
   - `join_trace_index.py` annotates results with trace line numbers.
   - `main.py --check-paths` uses `constraints.py` to sanity-check path
     conditions.
   - `metrics.py` and `benchmarks.py` summarize path enumeration stats.

Where things stand
- Parsing: all input artifacts are parsed in parser.py.
- Constraints: constraints.py can accept path conditions (string or JSON).
- Solver: dummy solver + minimal Z3 backend in solver.py.
- Symexec: minimal Z3-backed dual execution in symexec.py, with PHI resolution
  based on predecessor basic blocks when available.
- Aggregation: public_at_point computation in publicness.py + aggregate.py.
- Analyzer: analyze.py supports stub and minimal symexec modes.

Quick start
1) Generate traces:
   ./scripts/gen_traces.sh
2) Summarize a trace + CFG:
   python3 -m symex.main --trace build/traces/toy.ndjson --cfg build/traces/toy.cfg.ndjson
3) Stub analysis + aggregation:
   python3 -m symex.analyze --trace build/traces/toy.ndjson --cfg build/traces/toy.cfg.ndjson --out path_public.ndjson
   python3 -m symex.aggregate --cfg build/traces/toy.cfg.ndjson --path-results path_public.ndjson
4) Minimal symexec (Z3 required):
   python3 -m symex.analyze --mode symexec --trace build/traces/toy.ndjson --cfg build/traces/toy.cfg.ndjson --out path_public.ndjson

Code map
- models.py: dataclasses for trace, CFG, and result records.
- parser.py: NDJSON loaders for trace, CFG, summaries, and index.
- pipeline.py: ties CFG paths to instruction streams.
- constraints.py: builds per-path constraints for the solver.
- solver.py: dummy solver + minimal Z3 backend.
- analyze.py: stub per-path results (public=None).
- symexec.py: minimal Z3-backed symbolic executor (MVP).
- aggregate.py: public_at_point aggregation.
- publicness.py: core aggregation logic.
- join_trace_index.py: adds line numbers to per-path results.
- metrics.py: emits per-function CSV from summaries.
- main.py: CLI summarizer.

TODO (Person B)
- Symbolic execution:
  - Expand opcode coverage beyond the current MVP in symexec.py.
  - Use trace types (def_ty/use_tys) to choose solver sorts.
- Constraint solving:
  - Encode rA != rB queries to decide publicness along a path.
  - Cache path constraints and per-path solver contexts.
- Output:
  - Emit path_publicness for each (path_id, pp, value).
  - Feed into aggregate.py to produce public_at_point.

Helpful utilities
- Trace index:
  python3 -m symex.main --trace build/traces/toy.ndjson --trace-index build/traces/toy.trace_index.ndjson
- Join trace index into per-path results:
  python3 -m symex.join_trace_index --path-results path_public.ndjson --trace-index build/traces/toy.trace_index.ndjson --out path_public.with_line.ndjson
- Metrics:
  python3 -m symex.metrics --cfg build/traces/toy.cfg.ndjson --out metrics.csv
- Benchmark runner (combined CSV across all CFGs):
  ./scripts/run_benchmarks.sh benchmarks.csv
  RUN_REPEAT=5 ./scripts/run_benchmarks.sh benchmarks.csv

Z3 solver setup
- Install:
  python3 -m pip install -r symex/requirements.txt
- Then run:
  python3 -m symex.main --cfg build/traces/toy.cfg.ndjson --check-paths --z3
