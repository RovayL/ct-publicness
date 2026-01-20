from __future__ import annotations

"""CLI utilities for inspecting trace and CFG outputs."""

import argparse
import json
from collections import Counter
from typing import List

from .parser import load_cfg, load_trace, load_trace_index
from .constraints import ConstraintBuilder
from .solver import DummySolver, Z3Solver


def summarize_trace(trace_path: str, index_path: str | None) -> None:
    """Print summary stats for a trace NDJSON file."""
    insts = load_trace(trace_path)
    fns = sorted({i.fn for i in insts})
    op_counts = Counter(i.op for i in insts)
    tx_count = sum(1 for i in insts if i.tx is not None)

    print(f"trace: {trace_path}")
    print(f"  instructions: {len(insts)}")
    print(f"  functions: {', '.join(fns)}")
    print(f"  transmitters: {tx_count}")
    print("  op counts:")
    for op, count in op_counts.most_common():
        print(f"    {op}: {count}")
    if index_path:
        index = load_trace_index(index_path)
        by_fn = Counter(ti.fn for ti in index)
        print(f"  trace index entries: {len(index)}")
        for fn, count in by_fn.most_common():
            print(f"    {fn}: {count}")


def summarize_cfg(cfg_path: str, show_paths: bool) -> None:
    """Print summary stats for a CFG NDJSON file."""
    blocks, edges, paths, summaries, pp_cov = load_cfg(cfg_path)
    fns = sorted({b.fn for b in blocks} | {e.fn for e in edges})

    print(f"cfg: {cfg_path}")
    print(f"  functions: {', '.join(fns)}")
    print(f"  blocks: {len(blocks)}")
    print(f"  edges: {len(edges)}")
    print(f"  paths: {len(paths)}")
    print(f"  pp coverage: {len(pp_cov)}")

    if summaries:
        print("  path summaries:")
        for s in summaries:
            print(
                f"    {s.fn}: emitted={s.paths_emitted} "
                f"truncated={s.truncated} "
                f"cutoff_depth={s.cutoff_depth} "
                f"cutoff_loop={s.cutoff_loop} "
                f"dfs_calls={s.dfs_calls} "
                f"dfs_leaves={s.dfs_leaves}"
            )

    if show_paths:
        for p in paths:
            print(f"  path {p.fn}: {' -> '.join(p.bbs)}")
            if p.path_cond:
                print(f"    cond: {' && '.join(p.path_cond)}")
            elif p.path_cond_json:
                print(f"    cond_json: {json.dumps(p.path_cond_json)}")


def check_paths(cfg_path: str, use_z3: bool) -> None:
    """Run a quick satisfiability check on each path condition."""
    _blocks, _edges, paths, _summaries, _pp_cov = load_cfg(cfg_path)
    for p in paths:
        solver = Z3Solver() if use_z3 else DummySolver()
        builder = ConstraintBuilder(solver=solver)
        builder.add_path_conditions(p)
        res = solver.check()
        print(f"{p.fn}: {' -> '.join(p.bbs)} sat={res.sat}")


def main(argv: List[str] | None = None) -> int:
    """Entry point for the symex CLI."""
    parser = argparse.ArgumentParser(
        description="Parse and summarize PublicDataPass NDJSON outputs."
    )
    parser.add_argument("--trace", help="Path to trace NDJSON")
    parser.add_argument("--trace-index", help="Path to trace index NDJSON")
    parser.add_argument("--cfg", help="Path to CFG/path NDJSON")
    parser.add_argument("--show-paths", action="store_true", help="Print paths")
    parser.add_argument("--check-paths", action="store_true", help="Solve path constraints")
    parser.add_argument("--z3", action="store_true", help="Use Z3 backend")
    args = parser.parse_args(argv)

    if not args.trace and not args.cfg:
        parser.error("At least one of --trace or --cfg is required.")

    if args.trace:
        summarize_trace(args.trace, args.trace_index)
    if args.cfg:
        summarize_cfg(args.cfg, args.show_paths)
        if args.check_paths:
            check_paths(args.cfg, args.z3)

    return 0


# TODO(person B): Add a mode that checks rA != rB for publicness queries.


if __name__ == "__main__":
    raise SystemExit(main())
