from __future__ import annotations

"""Emit a combined CSV of per-function metrics across many CFG files."""

import argparse
import csv
import glob
import os
from typing import Dict, List

from .parser import load_cfg, load_func_summary, read_ndjson


def _collect_rows(cfg_path: str) -> List[dict]:
    """Collect per-function rows for a single CFG file."""
    _blocks, _edges, _paths, summaries, _pp_cov = load_cfg(cfg_path)
    func_summaries = load_func_summary(cfg_path)
    source = os.path.basename(cfg_path)

    by_fn: Dict[str, dict] = {}
    for s in summaries:
        by_fn[s.fn] = {
            "source": source,
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
                "source": source,
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

    return [by_fn[k] for k in sorted(by_fn.keys())]


def _load_run_summary(path: str) -> Dict[str, dict]:
    """Load run_summary records from a summary NDJSON file."""
    by_source: Dict[str, dict] = {}
    if not os.path.exists(path):
        return by_source
    for rec in read_ndjson(path):
        if rec.get("kind") != "run_summary":
            continue
        by_source[rec["source"]] = {
            "elapsed_ms": rec.get("elapsed_ms"),
            "elapsed_ms_min": rec.get("elapsed_ms_min"),
            "elapsed_ms_max": rec.get("elapsed_ms_max"),
            "elapsed_ms_median": rec.get("elapsed_ms_median"),
            "elapsed_ms_mean": rec.get("elapsed_ms_mean"),
            "elapsed_runs": rec.get("elapsed_runs"),
            "max_paths": rec.get("max_paths"),
            "max_path_depth": rec.get("max_path_depth"),
            "max_loop_iters": rec.get("max_loop_iters"),
            "max_inst": rec.get("max_inst"),
        }
    return by_source


def main() -> int:
    """CLI entry point for benchmark CSV aggregation."""
    parser = argparse.ArgumentParser(
        description="Combine metrics across multiple CFG files into one CSV."
    )
    parser.add_argument(
        "--cfg",
        action="append",
        default=[],
        help="CFG NDJSON file (repeatable)",
    )
    parser.add_argument(
        "--cfg-glob",
        default="build/traces/*.cfg.ndjson",
        help="Glob for CFG NDJSON files (used if --cfg is not provided)",
    )
    parser.add_argument("--out", required=True, help="Output CSV file")
    args = parser.parse_args()

    if args.cfg:
        cfgs = sorted(args.cfg)
    else:
        cfgs = sorted(glob.glob(args.cfg_glob))
    if not cfgs:
        raise SystemExit(f"No files match: {args.cfg_glob}")

    fieldnames = [
        "source",
        "fn",
        "elapsed_ms",
        "elapsed_ms_min",
        "elapsed_ms_max",
        "elapsed_ms_median",
        "elapsed_ms_mean",
        "elapsed_runs",
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

    rows: List[dict] = []
    for cfg in cfgs:
        rows.extend(_collect_rows(cfg))

    # Merge optional run_summary files based on base name.
    run_summaries: Dict[str, dict] = {}
    for cfg in cfgs:
        base = os.path.basename(cfg).replace(".cfg.ndjson", "")
        summary_path = os.path.join(os.path.dirname(cfg), f"{base}.run_summary.ndjson")
        run_summaries[base] = _load_run_summary(summary_path).get(base, {})

    for row in rows:
        src = row.get("source", "")
        if not src:
            continue
        base = src.replace(".cfg.ndjson", "")
        rs = run_summaries.get(base, {})
        if rs:
            row["elapsed_ms"] = rs.get("elapsed_ms")
            row["elapsed_ms_min"] = rs.get("elapsed_ms_min")
            row["elapsed_ms_max"] = rs.get("elapsed_ms_max")
            row["elapsed_ms_median"] = rs.get("elapsed_ms_median")
            row["elapsed_ms_mean"] = rs.get("elapsed_ms_mean")
            row["elapsed_runs"] = rs.get("elapsed_runs")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return 0


# TODO(person B): Add solver runtime columns once available.


# TODO(person B): Add runtime columns once solver timing is available.


if __name__ == "__main__":
    raise SystemExit(main())
