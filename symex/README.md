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

Where things stand
- Parsing: all input artifacts are parsed in parser.py.
- Constraints: constraints.py can accept path conditions (string or JSON).
- Solver: dummy solver + minimal Z3 backend in solver.py.
- Aggregation: public_at_point computation in publicness.py + aggregate.py.
- Stub analyzer: analyze.py can emit placeholder path_publicness.

Quick start
1) Generate traces:
   ./scripts/gen_traces.sh
2) Summarize a trace + CFG:
   python3 -m symex.main --trace build/traces/toy.ndjson --cfg build/traces/toy.cfg.ndjson
3) Stub analysis + aggregation:
   python3 -m symex.analyze --trace build/traces/toy.ndjson --cfg build/traces/toy.cfg.ndjson --out path_public.ndjson
   python3 -m symex.aggregate --cfg build/traces/toy.cfg.ndjson --path-results path_public.ndjson

Code map
- models.py: dataclasses for trace, CFG, and result records.
- parser.py: NDJSON loaders for trace, CFG, summaries, and index.
- pipeline.py: ties CFG paths to instruction streams.
- constraints.py: builds per-path constraints for the solver.
- solver.py: dummy solver + minimal Z3 backend.
- analyze.py: stub per-path results (public=None).
- aggregate.py: public_at_point aggregation.
- publicness.py: core aggregation logic.
- join_trace_index.py: adds line numbers to per-path results.
- metrics.py: emits per-function CSV from summaries.
- main.py: CLI summarizer.

TODO (Person B)
- Symbolic execution:
  - Implement SSA value evaluation for opcodes in TraceInst.
  - Track two executions (A/B) and relate transmitter operands.
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
