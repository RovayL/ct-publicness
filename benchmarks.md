Benchmark Suite

Purpose
This file documents how to run and extend the benchmark suite used for
evaluation (path counts, pruning stats, and runtime).

Current suite
The default suite is listed in benchmarks.txt:
- examples/toy.c
- examples/linear.c
- examples/loop.c
- examples/loop_invariant.c
- examples/diversity.c
- examples/algos.c
- examples/bitwise.c
- examples/classic_benchmarks.c
- examples/crypto_kernels.c
- examples/const_pruned.ll
- examples/transmitters.ll

Loop-invariant benchmark
- `loop_public_value`: loop-local arithmetic that does not feed any
  transmitter; this is the positive demo for invariant lifting.
- `loop_nonpublic_addr`: loop-local address construction that flows into a
  load-address transmitter; this is the negative demo.

Extended transmitter benchmark
- `tx_div`: division operands are treated as transmitters.
- `tx_rem`: remainder operands are treated as transmitters.
- `tx_indirect_call_target`: indirect call targets are treated as transmitters.
- `tx_direct_call_const`: direct-call summary returns a fixed constant.
- `tx_direct_call_identity`: direct-call summary returns a value derived from
  the caller argument.
- `tx_atomicrmw_addr`: atomic read-modify-write addresses are treated as
  transmitters.
- `tx_cmpxchg_extract`: cmpxchg plus extractvalue modeling.
- `tx_cmpxchg_insert_extract`: cmpxchg aggregate flow through insertvalue then
  extractvalue; the forced success bit should become non-public.
- `tx_atomicrmw_alias_eq`: atomic update plus load through an equivalent
  address expression; the final equality should be non-public only if alias
  canonicalization is working.

Classical algorithm kernels
- `bubble_sort`: nested loops with branchy swaps over array accesses.
- `quicksort_partition_kernel`: partition step for quicksort, with pivot loads,
  conditional swaps, and multiple stores.
- `tsp_choose_next_city`: nearest-neighbor TSP step over a dense distance
  matrix with a visited-mask branch.
- `convex_hull_next_point`: Jarvis-march style step over point arrays.
- `recursive_binary_search`: recursion plus data-dependent branch and indexed
  load.

Crypto-style kernels
- `bitwise_eq`: branchless equality mask.
- `bitwise_secret_index`: secret-dependent lookup.
- `bitwise_secret_store`: secret-dependent store address.
- `rsa_square_multiply`: classical branchy modular exponentiation kernel.
- `rsa_ladder_mix`: branchless ladder-style modular exponentiation step.
- `sha256_round_kernel`: SHA-256 round-style kernel with dynamic message/round
  loads.
- `paillier_encrypt_lookup`: direct Paillier-style table lookup plus modular
  multiply/remainder.
- `paillier_encrypt_ct_lookup`: constant-time style full-table scan for the
  same Paillier-style lookup.
- `ct_memcmp_u8`: constant-time bytewise comparison loop.

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
  - build/traces/*.enhanced_public_at_point.ndjson (baseline aggregate plus loop facts)
  - build/traces/*.run_summary.ndjson (timings, if EMIT_RUN_SUMMARY=1)
  - benchmarks.csv (combined metrics, including query_count + solver_time_ms)

Environment knobs (selected)
- RUN_REPEAT: number of opt runs per source (timing stats).
- MAX_PATHS, MAX_PATH_DEPTH, MAX_LOOP_ITERS, MAX_INST: path/trace budgets.
- TRACE_INDEX, TRACE_TYPES, EMIT_PP_COVERAGE, INCLUDE_PP_SEQ: trace options.
- RUN_SYMEX, ANALYZE_MODE, ANALYZE_NO_CACHE, AGGREGATE_RESULTS: Person B analysis controls in `run_benchmarks.sh`.
- ANALYZE_LOOP_INVARIANTS: emit first-iteration loop-invariant results when set to `1`.
- AGGREGATE_ENHANCED: emit `*.enhanced_public_at_point.ndjson` when set to `1`.

Loop-invariant demo run
```bash
source venv-ct-publicness/bin/activate
MAX_LOOP_ITERS=1 ANALYZE_LOOP_INVARIANTS=1 ./scripts/run_benchmarks.sh benchmarks.loopinv.csv
```

Useful outputs for the demo
- `build/traces/loop_invariant.path_public.ndjson`
  - includes `loop_invariant_publicness` and `loop_public_at_point` records.
- `benchmarks.loopinv.csv`
  - includes `loop_inv_total`, `loop_inv_public_true`, `loop_inv_public_false`,
    and `loop_inv_public_unknown` per function.
