from __future__ import annotations

"""Join trace index data into path_publicness records."""

import argparse
import json

from .parser import read_ndjson
from .trace_index_lookup import build_trace_index_lookup


def main() -> int:
    """CLI entry point to enrich path_publicness with trace metadata."""
    parser = argparse.ArgumentParser(
        description="Enrich path_publicness records with trace line numbers."
    )
    parser.add_argument("--path-results", required=True, help="Input NDJSON")
    parser.add_argument("--trace-index", required=True, help="Trace index NDJSON")
    parser.add_argument("--out", required=True, help="Output NDJSON")
    args = parser.parse_args()

    idx = build_trace_index_lookup(args.trace_index)

    with open(args.out, "w", encoding="utf-8") as f:
        for rec in read_ndjson(args.path_results):
            if rec.get("kind") != "path_publicness":
                f.write(json.dumps(rec) + "\n")
                continue
            pp = rec.get("pp")
            if isinstance(pp, str):
                entry = idx.get_by_pp(pp)
                if entry is not None:
                    rec["trace_line"] = entry.line
                    rec["trace_op"] = entry.op
                    rec["trace_def"] = entry.def_id
            f.write(json.dumps(rec) + "\n")

    return 0


# TODO(person B): Optionally join additional trace fields (types, uses).


if __name__ == "__main__":
    raise SystemExit(main())
