from __future__ import annotations

"""NDJSON parsers for trace and CFG artifacts."""

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .models import (
    CfgBlock,
    CfgEdge,
    CfgPath,
    PathDecision,
    PathSummary,
    PpCoverage,
    TraceIndex,
    FuncSummary,
    TraceInst,
    TxInfo,
)


def read_ndjson(path: str) -> Iterable[dict]:
    """Yield JSON objects from an NDJSON file.

    Inputs:
    - path: filesystem path to NDJSON.
    Output:
    - Iterator of dicts, one per non-empty line.
    """
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def load_trace(path: str) -> List[TraceInst]:
    """Load TraceInst records from a trace NDJSON file."""
    insts: List[TraceInst] = []
    for rec in read_ndjson(path):
        tx = None
        if "tx" in rec and rec["tx"] is not None:
            tx = TxInfo(kind=rec["tx"]["kind"], which=int(rec["tx"]["which"]))
        insts.append(
            TraceInst(
                fn=rec["fn"],
                bb=rec["bb"],
                pp=rec["pp"],
                op=rec["op"],
                def_id=rec.get("def"),
                uses=list(rec.get("uses", [])),
                tx=tx,
                def_ty=rec.get("def_ty"),
                use_tys=rec.get("use_tys"),
            )
        )
    return insts


def load_trace_index(path: str) -> List[TraceIndex]:
    """Load TraceIndex records from a trace index NDJSON file."""
    out: List[TraceIndex] = []
    for rec in read_ndjson(path):
        if rec.get("kind") != "trace_index":
            continue
        out.append(
            TraceIndex(
                fn=rec["fn"],
                bb=rec["bb"],
                pp=rec["pp"],
                op=rec["op"],
                def_id=rec.get("def"),
                line=int(rec["line"]),
            )
        )
    return out


def load_func_summary(path: str) -> List[FuncSummary]:
    """Load FuncSummary records from a CFG NDJSON file."""
    out: List[FuncSummary] = []
    for rec in read_ndjson(path):
        if rec.get("kind") != "func_summary":
            continue
        out.append(
            FuncSummary(
                fn=rec["fn"],
                inst_count=int(rec.get("inst_count", 0)),
                bb_count=int(rec.get("bb_count", 0)),
                tx_count=int(rec.get("tx_count", 0)),
                trace_emitted=int(rec.get("trace_emitted", 0)),
                trace_truncated=bool(rec.get("trace_truncated", False)),
                trace_max_inst=int(rec.get("trace_max_inst", 0)),
            )
        )
    return out


def load_cfg(
    path: str,
) -> Tuple[List[CfgBlock], List[CfgEdge], List[CfgPath], List[PathSummary], List[PpCoverage]]:
    """Load CFG/path records from a CFG NDJSON file."""
    blocks: List[CfgBlock] = []
    edges: List[CfgEdge] = []
    paths: List[CfgPath] = []
    summaries: List[PathSummary] = []
    pp_cov: List[PpCoverage] = []

    for rec in read_ndjson(path):
        kind = rec.get("kind")
        if kind == "block":
            blocks.append(
                CfgBlock(
                    fn=rec["fn"],
                    bb=rec["bb"],
                    succs=list(rec.get("succs", [])),
                    term_pp=rec.get("term_pp"),
                    term_op=rec.get("term_op"),
                    cond=rec.get("cond"),
                    target=rec.get("target"),
                )
            )
        elif kind == "edge":
            edges.append(
                CfgEdge(
                    fn=rec["fn"],
                    from_bb=rec["from"],
                    to_bb=rec["to"],
                    term_pp=rec.get("term_pp"),
                    branch=rec.get("branch"),
                    cond=rec.get("cond"),
                    sense=rec.get("sense"),
                    case=rec.get("case"),
                    is_default=bool(rec.get("default", False)),
                    target=rec.get("target"),
                )
            )
        elif kind == "path":
            decs = []
            for d in rec.get("decisions", []):
                decs.append(
                    PathDecision(
                        pp=d["pp"],
                        kind=d["kind"],
                        succ=d["succ"],
                        cond=d.get("cond"),
                        sense=d.get("sense"),
                        case=d.get("case"),
                        is_default=bool(d.get("default", False)),
                        target=d.get("target"),
                    )
                )
            paths.append(
                CfgPath(
                    fn=rec["fn"],
                    path_id=rec.get("path_id"),
                    bbs=list(rec.get("bbs", [])),
                    decisions=decs,
                    path_cond=list(rec.get("path_cond", [])),
                    path_cond_json=list(rec.get("path_cond_json", [])),
                    pp_seq=list(rec.get("pp_seq", [])),
                )
            )
        elif kind == "path_summary":
            summaries.append(
                PathSummary(
                    fn=rec["fn"],
                    paths_emitted=int(rec.get("paths_emitted", 0)),
                    truncated=rec.get("truncated"),
                    max_paths=rec.get("max_paths"),
                    max_depth=rec.get("max_depth"),
                    max_loop_iters=rec.get("max_loop_iters"),
                    cutoff_depth=rec.get("cutoff_depth"),
                    cutoff_loop=rec.get("cutoff_loop"),
                    disabled=rec.get("disabled"),
                    const_pruned_br=rec.get("const_pruned_br"),
                    const_pruned_switch=rec.get("const_pruned_switch"),
                    const_pruned_indirect=rec.get("const_pruned_indirect"),
                    dfs_calls=rec.get("dfs_calls"),
                    dfs_leaves=rec.get("dfs_leaves"),
                    dfs_prune_max_paths=rec.get("dfs_prune_max_paths"),
                    dfs_prune_max_depth=rec.get("dfs_prune_max_depth"),
                    dfs_prune_loop=rec.get("dfs_prune_loop"),
                )
            )
        elif kind == "pp_coverage":
            pp_cov.append(
                PpCoverage(
                    fn=rec["fn"],
                    pp=rec["pp"],
                    path_count=int(rec.get("path_count", 0)),
                    path_ids=list(rec.get("path_ids", [])),
                    truncated=bool(rec.get("truncated", False)),
                )
            )
    return blocks, edges, paths, summaries, pp_cov


@dataclass(frozen=True)
class Inputs:
    """Bundle of parsed inputs for convenience."""
    trace: List[TraceInst]
    blocks: List[CfgBlock]
    edges: List[CfgEdge]
    paths: List[CfgPath]
    summaries: List[PathSummary]
    pp_coverage: List[PpCoverage]


def load_inputs(trace_path: str, cfg_path: str) -> Inputs:
    """Load trace + CFG inputs in one call."""
    trace = load_trace(trace_path)
    blocks, edges, paths, summaries, pp_cov = load_cfg(cfg_path)
    return Inputs(
        trace=trace,
        blocks=blocks,
        edges=edges,
        paths=paths,
        summaries=summaries,
        pp_coverage=pp_cov,
    )


def trace_by_fn(trace: List[TraceInst]) -> Dict[str, List[TraceInst]]:
    """Group trace instructions by function name."""
    out: Dict[str, List[TraceInst]] = {}
    for inst in trace:
        out.setdefault(inst.fn, []).append(inst)
    return out
