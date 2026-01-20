from __future__ import annotations

"""Helpers to join trace instructions with CFG paths."""

from dataclasses import dataclass
from typing import Dict, List

from .models import CfgBlock, CfgEdge, CfgPath, PathSummary, PpCoverage, TraceInst, TraceIndex
from .parser import load_inputs, load_trace_index


@dataclass(frozen=True)
class PathBundle:
    """A CFG path plus the instruction list for that path."""
    path: CfgPath
    insts: List[TraceInst]


@dataclass(frozen=True)
class FunctionPipeline:
    """All per-function data needed by the symbolic executor."""
    fn: str
    insts: List[TraceInst]
    bb_insts: Dict[str, List[TraceInst]]
    blocks: List[CfgBlock]
    edges: List[CfgEdge]
    paths: List[PathBundle]
    summaries: List[PathSummary]
    pp_coverage: List[PpCoverage]
    trace_index: List[TraceIndex]


def build_pipeline(
    trace_path: str,
    cfg_path: str,
    trace_index_path: str | None = None,
) -> Dict[str, FunctionPipeline]:
    """Join trace and CFG data into per-function bundles.

    Inputs:
    - trace_path: trace NDJSON.
    - cfg_path: CFG/path NDJSON.
    - trace_index_path: optional trace index NDJSON.
    Output:
    - Dict[fn -> FunctionPipeline]
    """
    inputs = load_inputs(trace_path, cfg_path)
    trace_index: List[TraceIndex] = []
    if trace_index_path:
        trace_index = load_trace_index(trace_index_path)

    by_fn: Dict[str, List[TraceInst]] = {}
    for inst in inputs.trace:
        by_fn.setdefault(inst.fn, []).append(inst)

    blocks_by_fn: Dict[str, List[CfgBlock]] = {}
    for b in inputs.blocks:
        blocks_by_fn.setdefault(b.fn, []).append(b)

    edges_by_fn: Dict[str, List[CfgEdge]] = {}
    for e in inputs.edges:
        edges_by_fn.setdefault(e.fn, []).append(e)

    paths_by_fn: Dict[str, List[CfgPath]] = {}
    for p in inputs.paths:
        paths_by_fn.setdefault(p.fn, []).append(p)

    summaries_by_fn: Dict[str, List[PathSummary]] = {}
    for s in inputs.summaries:
        summaries_by_fn.setdefault(s.fn, []).append(s)

    pp_cov_by_fn: Dict[str, List[PpCoverage]] = {}
    for p in inputs.pp_coverage:
        pp_cov_by_fn.setdefault(p.fn, []).append(p)

    out: Dict[str, FunctionPipeline] = {}
    fns = set(by_fn) | set(blocks_by_fn) | set(paths_by_fn)
    for fn in fns:
        insts = by_fn.get(fn, [])
        bb_insts: Dict[str, List[TraceInst]] = {}
        for inst in insts:
            bb_insts.setdefault(inst.bb, []).append(inst)
        inst_by_pp = {inst.pp: inst for inst in insts}

        path_bundles: List[PathBundle] = []
        for p in paths_by_fn.get(fn, []):
            p_insts: List[TraceInst] = []
            if p.pp_seq:
                for pp in p.pp_seq:
                    inst = inst_by_pp.get(pp)
                    if inst is not None:
                        p_insts.append(inst)
            else:
                for bb in p.bbs:
                    p_insts.extend(bb_insts.get(bb, []))
            path_bundles.append(PathBundle(path=p, insts=p_insts))

        fn_index = [ti for ti in trace_index if ti.fn == fn]
        out[fn] = FunctionPipeline(
            fn=fn,
            insts=insts,
            bb_insts=bb_insts,
            blocks=blocks_by_fn.get(fn, []),
            edges=edges_by_fn.get(fn, []),
            paths=path_bundles,
            summaries=summaries_by_fn.get(fn, []),
            pp_coverage=pp_cov_by_fn.get(fn, []),
            trace_index=fn_index,
        )

    return out


# TODO(person B): Preserve instruction ordering across blocks when pp_seq missing.
