from __future__ import annotations

"""Aggregate per-path publicness into public-at-point results."""

import argparse
import json
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


def main() -> int:
    """CLI entry point for public_at_point aggregation."""
    parser = argparse.ArgumentParser(
        description="Aggregate per-path publicness into public_at_point."
    )
    parser.add_argument("--cfg", required=True, help="Path to CFG/path NDJSON")
    parser.add_argument("--path-results", required=True, help="Path to per-path results NDJSON")
    parser.add_argument("--out", help="Write public_at_point NDJSON to this path")
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

    return 0


# TODO(person B): Extend output with per-function aggregate statistics.


if __name__ == "__main__":
    raise SystemExit(main())
