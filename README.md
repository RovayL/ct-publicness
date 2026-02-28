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
  - Minimal symexec (Z3) with dual execution, transmitter equality, and
    PHI resolution based on predecessor block (when PHI operands include block labels).

Project status log (latest)
What is done
- Toolchain and build are stable on Ubuntu (LLVM 18).
- Person A LLVM pass:
  - Emits NDJSON trace with stable IDs, optional type strings, and icmp/fcmp preds.
  - Emits CFG/path records with path IDs, decisions, path conditions (string/json),
    per-path pp_seq (optional), pp coverage (optional), and path summaries.
  - Loop-bounded path enumeration with caps + pruning for constant branches/switch/indirect.
  - Optional trace index (pp -> line) and trace truncation (max inst).
- Scripts:
  - gen_traces.sh supports budgets, repeat runs, run_summary stats, and BENCH_LIST.
  - run_benchmarks.sh and metrics_pipeline.sh produce combined CSV summaries.
  - benchmarks.md + benchmarks.txt document the suite and usage.
- Person B Python:
  - Parsers for trace/cfg/index and a pipeline to join paths with instruction streams.
  - Minimal Z3-backed symexec (dual execution + transmitter equality).
  - Path conditions consumed from structured `path_cond_json` (with string fallback).
  - Per-path/function solver metrics: query counts, solver time, cache hits/misses.
  - Aggregation to public_at_point.
  - Utilities: join_trace_index, metrics, benchmarks, main CLI summaries.
  - Z3 setup documented in symex/README.md.

What is left
- Improve memory model (array theory or SSA-style memory) to reduce false positives.
- Expand opcode coverage and casts in symexec (e.g., div/rem, more conversions).
- Validation: expand benchmark suite and summarize precision/runtime in report tables.
- Add explicit handling/reporting for solver unknown/timeout budgets.

Handoff (for a new session)
Reproduce current artifacts
```bash
# Build LLVM pass
cd build && ninja
cd ..

# Emit traces + CFG (with pp coverage + trace index)
TRACE_INDEX=1 EMIT_PP_COVERAGE=1 PATH_COND_FORMAT=both ./scripts/gen_traces.sh
```

Run Person B minimal symexec + aggregation
```bash
source venv-ct-publicness/bin/activate
python -m symex.analyze --mode symexec \
  --trace build/traces/toy.ndjson \
  --cfg build/traces/toy.cfg.ndjson \
  --out path_public.ndjson
python -m symex.aggregate \
  --cfg build/traces/toy.cfg.ndjson \
  --path-results path_public.ndjson \
  --out public_at_point.ndjson
```

Run benchmarks + metrics
```bash
source venv-ct-publicness/bin/activate
RUN_REPEAT=3 ./scripts/run_benchmarks.sh benchmarks.csv
```

Notes to remember
- PHI resolution in symexec uses predecessor block labels; ensure traces include PHI
  block operands (compile with optimization or run mem2reg).
- PATH_COND_FORMAT can be string/json/both; symexec consumes `path_cond_json`
  when present and falls back to string constraints otherwise.
- `run_benchmarks.sh` now also emits:
  - `build/traces/*.path_public.ndjson` (includes solver summaries),
  - `build/traces/*.public_at_point.ndjson`,
  - benchmark CSV columns for `query_count`, `solver_time_ms`, and cache stats.
- If Z3 import fails, run: `python -m pip install -r symex/requirements.txt`.

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
3) Run benchmarks:
   ./scripts/run_benchmarks.sh benchmarks.csv
4) Benchmark documentation:
   see benchmarks.md

Command cheat sheet
Install system dependencies (Ubuntu)
```bash
sudo apt update
sudo apt install -y build-essential git cmake ninja-build python3 python3-venv \
  llvm llvm-dev clang lld libedit-dev libzstd-dev
```

Create and activate venv, install Python deps
```bash
python3 -m venv venv-ct-publicness
source venv-ct-publicness/bin/activate
python -m pip install --upgrade pip
python -m pip install -r symex/requirements.txt
```

Sequence of commands (end-to-end)
```bash
# 1) Build the LLVM pass
cd build && ninja
cd ..

# 2) Person A: emit trace + CFG artifacts
TRACE_INDEX=1 EMIT_PP_COVERAGE=1 PATH_COND_FORMAT=both ./scripts/gen_traces.sh

# 3) Person B: run minimal symexec and aggregate
source venv-ct-publicness/bin/activate
python -m symex.analyze --mode symexec \
  --trace build/traces/toy.ndjson \
  --cfg build/traces/toy.cfg.ndjson \
  --out path_public.ndjson
python -m symex.aggregate \
  --cfg build/traces/toy.cfg.ndjson \
  --path-results path_public.ndjson \
  --out public_at_point.ndjson
```

Run Person A only (generate artifacts)
```bash
cd build && ninja
cd ..
TRACE_INDEX=1 EMIT_PP_COVERAGE=1 PATH_COND_FORMAT=both ./scripts/gen_traces.sh
```

Run Person B only (minimal symexec + aggregation)
```bash
source venv-ct-publicness/bin/activate
python -m symex.analyze --mode symexec \
  --trace build/traces/toy.ndjson \
  --cfg build/traces/toy.cfg.ndjson \
  --out path_public.ndjson
python -m symex.aggregate \
  --cfg build/traces/toy.cfg.ndjson \
  --path-results path_public.ndjson
```

Run full pipeline (benchmarks + metrics)
```bash
source venv-ct-publicness/bin/activate
RUN_REPEAT=3 ./scripts/run_benchmarks.sh benchmarks.csv
```

Quick start (Person B)
1) Summarize trace + CFG:
   python3 -m symex.main --trace build/traces/toy.ndjson --cfg build/traces/toy.cfg.ndjson
2) Stub analysis + aggregation:
   python3 -m symex.analyze --trace build/traces/toy.ndjson --cfg build/traces/toy.cfg.ndjson --out path_public.ndjson
   python3 -m symex.aggregate --cfg build/traces/toy.cfg.ndjson --path-results path_public.ndjson
