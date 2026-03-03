from __future__ import annotations

"""Aggregate per-path publicness into public-at-point results."""

import argparse
import json
from dataclasses import dataclass
from typing import Iterable, List

from .models import CfgPath, PpCoverage
from .parser import load_cfg, read_ndjson
from .publicness import PathPublicness, PublicAtPoint, aggregate_public_at_point


def load_path_results(path: str) -> List[PathPublicness]:
    """Load path_publicness records from NDJSON."""
    out: List[PathPublicness] = []
    for rec in read_ndjson(path):
        if rec.get("kind") != "path_publicness":
            continue
        out.append(
            PathPublicness(
                fn=rec["fn"],
                path_id=int(rec["path_id"]),
                pp=rec["pp"],
                value=rec["value"],
                public=rec.get("public"),
            )
        )
    return out


@dataclass(frozen=True)
class LoopPublicAtPoint:
    fn: str
    pp: str
    value: str
    public: bool | None
    reason: str | None
    loop_id: int | None
    support_paths: int | None
    first_iter_paths: int | None


def load_loop_public_at_point(path: str) -> List[LoopPublicAtPoint]:
    """Load loop_public_at_point records from analysis NDJSON."""
    out: List[LoopPublicAtPoint] = []
    for rec in read_ndjson(path):
        if rec.get("kind") != "loop_public_at_point":
            continue
        out.append(
            LoopPublicAtPoint(
                fn=rec["fn"],
                pp=rec["pp"],
                value=rec["value"],
                public=rec.get("public"),
                reason=rec.get("reason"),
                loop_id=rec.get("loop_id"),
                support_paths=rec.get("support_paths"),
                first_iter_paths=rec.get("first_iter_paths"),
            )
        )
    return out


def write_public_at_point(path: str, records: Iterable[PublicAtPoint]) -> None:
    """Write public_at_point records to NDJSON."""
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            rec = {
                "kind": "public_at_point",
                "fn": r.fn,
                "pp": r.pp,
                "value": r.value,
                "public": r.public,
                "total_paths": r.total_paths,
                "missing_paths": r.missing_paths,
                "truncated": r.truncated,
            }
            f.write(json.dumps(rec) + "\n")


def summarize(records: Iterable[PublicAtPoint]) -> None:
    """Print summary counts for public_at_point records."""
    total = 0
    pub = 0
    sec = 0
    unk = 0
    for r in records:
        total += 1
        if r.public is True:
            pub += 1
        elif r.public is False:
            sec += 1
        else:
            unk += 1
    print(f"public_at_point: total={total} public={pub} secret={sec} unknown={unk}")


def merge_enhanced_public_at_point(
    baseline: Iterable[PublicAtPoint],
    loop_records: Iterable[LoopPublicAtPoint],
) -> List[dict]:
    """Merge baseline aggregation with optional loop-invariant facts."""
    baseline_map = {(r.fn, r.pp, r.value): r for r in baseline}
    loop_map = {(r.fn, r.pp, r.value): r for r in loop_records}
    keys = sorted(set(baseline_map) | set(loop_map))
    out: List[dict] = []
    for key in keys:
        base = baseline_map.get(key)
        loop = loop_map.get(key)
        if loop is not None and loop.public is not None:
            public = loop.public
            if base is None:
                source = "loop_invariant_only"
            elif base.public == loop.public:
                source = "baseline_and_loop"
            else:
                source = "loop_invariant_override"
        elif base is not None:
            public = base.public
            source = "baseline"
        else:
            public = loop.public if loop is not None else None
            source = "loop_invariant_only"
        out.append(
            {
                "kind": "enhanced_public_at_point",
                "fn": key[0],
                "pp": key[1],
                "value": key[2],
                "public": public,
                "baseline_public": base.public if base is not None else None,
                "loop_public": loop.public if loop is not None else None,
                "source": source,
                "reason": loop.reason if loop is not None else None,
                "loop_id": loop.loop_id if loop is not None else None,
                "support_paths": loop.support_paths if loop is not None else None,
                "first_iter_paths": loop.first_iter_paths if loop is not None else None,
                "total_paths": base.total_paths if base is not None else None,
                "missing_paths": base.missing_paths if base is not None else None,
                "truncated": base.truncated if base is not None else None,
            }
        )
    return out


def write_enhanced_public_at_point(path: str, records: Iterable[dict]) -> None:
    """Write enhanced_public_at_point records to NDJSON."""
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def main() -> int:
    """CLI entry point for public_at_point aggregation."""
    parser = argparse.ArgumentParser(
        description="Aggregate per-path publicness into public_at_point."
    )
    parser.add_argument("--cfg", required=True, help="Path to CFG/path NDJSON")
    parser.add_argument("--path-results", required=True, help="Path to per-path results NDJSON")
    parser.add_argument("--out", help="Write public_at_point NDJSON to this path")
    parser.add_argument(
        "--enhanced-out",
        help="Write enhanced_public_at_point NDJSON using loop facts when present",
    )
    parser.add_argument(
        "--missing",
        choices=["unknown", "public", "secret"],
        default="unknown",
        help="Policy for missing path results",
    )
    args = parser.parse_args()

    blocks, edges, paths, summaries, pp_cov = load_cfg(args.cfg)
    _ = (blocks, edges, summaries)  # unused, but kept for clarity
    results = load_path_results(args.path_results)
    loop_results = load_loop_public_at_point(args.path_results)
    records = aggregate_public_at_point(
        paths=paths,
        pp_coverage=pp_cov,
        path_results=results,
        missing_policy=args.missing,
    )

    if args.out:
        write_public_at_point(args.out, records)
    else:
        summarize(records)
    if args.enhanced_out:
        enhanced = merge_enhanced_public_at_point(records, loop_results)
        write_enhanced_public_at_point(args.enhanced_out, enhanced)

    return 0


# TODO(person B): Extend output with per-function aggregate statistics.


if __name__ == "__main__":
    raise SystemExit(main())
