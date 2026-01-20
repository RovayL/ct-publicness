from __future__ import annotations

"""Stub analyzer that emits unknown publicness for each def on each path."""

import argparse
import json

from .pipeline import build_pipeline


def emit_path_publicness(trace_path: str, cfg_path: str, out_path: str) -> None:
    """Emit path_publicness records with public=None for all defs.

    Inputs:
    - trace_path: trace NDJSON file.
    - cfg_path: CFG/path NDJSON file.
    - out_path: output NDJSON file.
    """
    pipes = build_pipeline(trace_path, cfg_path)
    with open(out_path, "w", encoding="utf-8") as f:
        for fn, pipe in pipes.items():
            for bundle in pipe.paths:
                path_id = bundle.path.path_id
                if path_id is None:
                    continue
                for inst in bundle.insts:
                    if not inst.def_id:
                        continue
                    rec = {
                        "kind": "path_publicness",
                        "fn": fn,
                        "path_id": path_id,
                        "pp": inst.pp,
                        "value": inst.def_id,
                        "public": None,
                    }
                    f.write(json.dumps(rec) + "\n")


def main() -> int:
    """CLI entry point for stub path_publicness emission."""
    parser = argparse.ArgumentParser(
        description="Emit stub per-path publicness (unknown) for each def."
    )
    parser.add_argument("--trace", required=True, help="Path to trace NDJSON")
    parser.add_argument("--cfg", required=True, help="Path to CFG/path NDJSON")
    parser.add_argument("--out", required=True, help="Output NDJSON file")
    args = parser.parse_args()

    emit_path_publicness(args.trace, args.cfg, args.out)
    return 0


# TODO(person B): Replace this stub with real symbolic execution results.


if __name__ == "__main__":
    raise SystemExit(main())
