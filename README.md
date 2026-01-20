# Constant-Time Publicness (CT-Publicness)

Purpose
This project implements a static analysis for "public vs secret" values in
constant-time programs. The core idea is to symbolically execute each
control-flow path twice and check whether "transmitter operands" (e.g.,
branch conditions and memory addresses) are equal across both executions.
Values that can differ between the two executions are public along that path.
A value is public at a program point if it is public along all paths that pass
through that point.

High-level architecture
- Person A (LLVM pass):
  - Traverses LLVM IR, identifies transmitter operands.
  - Emits machine-readable traces (NDJSON) of instructions and operands.
  - Emits CFG/path info (edges, path decisions, path constraints).
  - Supports loop-bounded path enumeration and pruning.
  - Produces optional index/metrics artifacts to help downstream tooling.
- Person B (Python symex):
  - Parses the NDJSON artifacts.
  - Builds per-path constraints and a two-execution symbolic model.
  - Checks publicness per path and aggregates to public-at-point.

Key outputs (Person A)
- Trace NDJSON: instruction stream with operand IDs.
- CFG/path NDJSON: blocks/edges, path decisions, constraints.
- Optional trace index: maps program points to trace line numbers.
- Metrics: per-function summaries and path enumeration statistics.

Weekly milestones (8-week plan, abbreviated)
Week 1:
- Toolchain setup (LLVM/Clang), build pass plugin.
- Print program points and detect transmitters.

Week 2:
- Stable program-point IDs and value IDs.
- Emit NDJSON trace (straight-line blocks).
- Provide trace schema to Person B.

Week 3:
- Emit CFG info, edges, and acyclic paths.
- Emit path conditions (string and optional JSON).
- Add loop-bounded path enumeration.

Week 4:
- Add per-path IDs and optional per-path pp sequences.
- Emit program-point coverage (pp -> paths).
- Add path summary metrics.

Week 5:
- Add pruning heuristics (constant branch/switch/indirect).
- Add trace index and budgets (max paths, max depth, max inst).
- Add metrics pipelines for evaluation.

Current status
- Person A:
  - LLVM pass produces trace, CFG/path records, path conditions, loop bounds.
  - Optional path coverage, pp sequences, trace index, type strings.
  - Path pruning for constant conditions.
  - Metrics and summaries for evaluation (DFS stats, counts).
- Person B:
  - Python scaffolding to parse all NDJSON artifacts.
  - Constraint builder + dummy solver + minimal Z3 backend.
  - Path aggregation to public-at-point.
  - Stub path analysis to emit placeholder path_publicness.

Where to look
- LLVM pass: llvm-pass/PublicDataPass.cpp
- Trace schema: TRACE_SCHEMA.md
- CFG schema: CFG_SCHEMA.md
- Person B Python: symex/ (see symex/README.md)

Quick start (Person A)
1) Build pass:
   cd build && ninja
2) Generate traces:
   TRACE_INDEX=1 EMIT_PP_COVERAGE=1 ./scripts/gen_traces.sh

Quick start (Person B)
1) Summarize trace + CFG:
   python3 -m symex.main --trace build/traces/toy.ndjson --cfg build/traces/toy.cfg.ndjson
2) Stub analysis + aggregation:
   python3 -m symex.analyze --trace build/traces/toy.ndjson --cfg build/traces/toy.cfg.ndjson --out path_public.ndjson
   python3 -m symex.aggregate --cfg build/traces/toy.cfg.ndjson --path-results path_public.ndjson
