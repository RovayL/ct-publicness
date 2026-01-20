from __future__ import annotations

"""Emit per-function metrics CSV from CFG/path summaries."""

import argparse
import csv
from typing import Dict

from .parser import load_cfg, load_func_summary


def main() -> int:
    """CLI entry point for metrics export."""
    parser = argparse.ArgumentParser(
        description="Emit per-function metrics from CFG/path NDJSON."
    )
    parser.add_argument("--cfg", required=True, help="Path to CFG/path NDJSON")
    parser.add_argument("--out", required=True, help="Output CSV file")
    args = parser.parse_args()

    _blocks, _edges, _paths, summaries, _pp_cov = load_cfg(args.cfg)
    func_summaries = load_func_summary(args.cfg)

    by_fn: Dict[str, dict] = {}
    for s in summaries:
        by_fn[s.fn] = {
            "fn": s.fn,
            "inst_count": None,
            "bb_count": None,
            "tx_count": None,
            "trace_emitted": None,
            "trace_truncated": None,
            "trace_max_inst": None,
            "paths_emitted": s.paths_emitted,
            "truncated": s.truncated,
            "max_paths": s.max_paths,
            "max_depth": s.max_depth,
            "max_loop_iters": s.max_loop_iters,
            "cutoff_depth": s.cutoff_depth,
            "cutoff_loop": s.cutoff_loop,
            "const_pruned_br": s.const_pruned_br,
            "const_pruned_switch": s.const_pruned_switch,
            "const_pruned_indirect": s.const_pruned_indirect,
            "dfs_calls": s.dfs_calls,
            "dfs_leaves": s.dfs_leaves,
            "dfs_prune_max_paths": s.dfs_prune_max_paths,
            "dfs_prune_max_depth": s.dfs_prune_max_depth,
            "dfs_prune_loop": s.dfs_prune_loop,
        }

    for f in func_summaries:
        by_fn.setdefault(
            f.fn,
            {
                "fn": f.fn,
                "paths_emitted": None,
                "truncated": None,
                "max_paths": None,
                "max_depth": None,
                "max_loop_iters": None,
                "cutoff_depth": None,
                "cutoff_loop": None,
                "const_pruned_br": None,
                "const_pruned_switch": None,
                "const_pruned_indirect": None,
                "dfs_calls": None,
                "dfs_leaves": None,
                "dfs_prune_max_paths": None,
                "dfs_prune_max_depth": None,
                "dfs_prune_loop": None,
            },
        )
        by_fn[f.fn].update(
            {
                "inst_count": f.inst_count,
                "bb_count": f.bb_count,
                "tx_count": f.tx_count,
                "trace_emitted": f.trace_emitted,
                "trace_truncated": f.trace_truncated,
                "trace_max_inst": f.trace_max_inst,
            }
        )

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "fn",
            "inst_count",
            "bb_count",
            "tx_count",
            "trace_emitted",
            "trace_truncated",
            "trace_max_inst",
            "paths_emitted",
            "truncated",
            "max_paths",
            "max_depth",
            "max_loop_iters",
            "cutoff_depth",
            "cutoff_loop",
            "const_pruned_br",
            "const_pruned_switch",
            "const_pruned_indirect",
            "dfs_calls",
            "dfs_leaves",
            "dfs_prune_max_paths",
            "dfs_prune_max_depth",
            "dfs_prune_loop",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for fn in sorted(by_fn.keys()):
            writer.writerow(by_fn[fn])

    return 0


# TODO(person B): Add metrics from solver runtime once available.


if __name__ == "__main__":
    raise SystemExit(main())
