from __future__ import annotations

"""Analyzer entry point (stub or minimal symexec)."""

import argparse
import json

from .pipeline import build_pipeline
from .symexec import SymExecEngine


def emit_path_publicness_stub(trace_path: str, cfg_path: str, out_path: str) -> None:
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


def emit_path_publicness_symexec(trace_path: str, cfg_path: str, out_path: str) -> None:
    """Run minimal symexec per path and emit path_publicness records."""
    pipes = build_pipeline(trace_path, cfg_path)
    engine = SymExecEngine()
    with open(out_path, "w", encoding="utf-8") as f:
        for fn, pipe in pipes.items():
            for bundle in pipe.paths:
                path_id = bundle.path.path_id
                if path_id is None:
                    continue
                results = engine.analyze_path(
                    path_id=path_id,
                    insts=bundle.insts,
                    path_conditions=bundle.path.path_cond,
                )
                for r in results:
                    rec = {
                        "kind": "path_publicness",
                        "fn": r.fn,
                        "path_id": r.path_id,
                        "pp": r.pp,
                        "value": r.value,
                        "public": r.public,
                    }
                    f.write(json.dumps(rec) + "\n")


def main() -> int:
    """CLI entry point for stub or minimal symexec analysis."""
    parser = argparse.ArgumentParser(
        description="Emit per-path publicness (stub or minimal symexec)."
    )
    parser.add_argument("--trace", required=True, help="Path to trace NDJSON")
    parser.add_argument("--cfg", required=True, help="Path to CFG/path NDJSON")
    parser.add_argument("--out", required=True, help="Output NDJSON file")
    parser.add_argument(
        "--mode",
        choices=["stub", "symexec"],
        default="stub",
        help="Analysis mode (symexec is minimal MVP)",
    )
    args = parser.parse_args()

    if args.mode == "symexec":
        emit_path_publicness_symexec(args.trace, args.cfg, args.out)
    else:
        emit_path_publicness_stub(args.trace, args.cfg, args.out)
    return 0


# TODO(person B): Extend symexec with proper memory handling.


if __name__ == "__main__":
    raise SystemExit(main())
