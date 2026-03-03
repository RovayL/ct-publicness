from __future__ import annotations

"""Loop invariant helpers built on top of first-iteration loop prefixes.

This is a conservative extension for the current bounded-path pipeline:

- identify natural loop-like SCCs in the CFG,
- look for emitted paths that revisit a loop block,
- slice each such path just before the repeated loop-header visit,
- run the existing dual-execution symexec on that first-iteration slice,
- if a value is public on all observed first-iteration slices for a loop
  program point, emit a loop-invariant publicness fact saying we assume the
  same static program point remains public in later iterations.

This follows the project feedback heuristic: prove publicness on the first
iteration and propagate that fact to later iterations.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .pipeline import FunctionPipeline, PathBundle
from .symexec import SymExecEngine


@dataclass(frozen=True)
class LoopInfo:
    fn: str
    loop_id: int
    blocks: frozenset[str]


@dataclass(frozen=True)
class LoopInvariantRecord:
    fn: str
    loop_id: int
    pp: str
    value: str
    public: Optional[bool]
    support_paths: int
    evidence_path_ids: Tuple[int, ...]
    first_iter_paths: int


@dataclass(frozen=True)
class LoopSlice:
    loop: LoopInfo
    path_id: int
    prefix_bbs: Tuple[str, ...]
    insts: List[object]
    path_cond: Sequence[str]
    path_cond_json: Sequence[dict]


def _self_loop_blocks(pipe: FunctionPipeline) -> Set[str]:
    out: Set[str] = set()
    for edge in pipe.edges:
        if edge.from_bb == edge.to_bb:
            out.add(edge.from_bb)
    return out


def _compute_sccs(pipe: FunctionPipeline) -> List[LoopInfo]:
    """Compute SCCs and retain those that correspond to loops."""
    blocks = sorted({b.bb for b in pipe.blocks})
    graph: Dict[str, List[str]] = {bb: [] for bb in blocks}
    for e in pipe.edges:
        graph.setdefault(e.from_bb, []).append(e.to_bb)
        graph.setdefault(e.to_bb, [])

    index = 0
    index_of: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    stack: List[str] = []
    on_stack: Set[str] = set()
    sccs: List[List[str]] = []

    def strongconnect(v: str) -> None:
        nonlocal index
        index_of[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        for w in graph.get(v, []):
            if w not in index_of:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index_of[w])

        if lowlink[v] == index_of[v]:
            comp: List[str] = []
            while stack:
                w = stack.pop()
                on_stack.remove(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for bb in blocks:
        if bb not in index_of:
            strongconnect(bb)

    self_loops = _self_loop_blocks(pipe)
    loops: List[LoopInfo] = []
    next_loop_id = 0
    for comp in sccs:
        comp_set = frozenset(comp)
        if len(comp_set) > 1 or any(bb in self_loops for bb in comp_set):
            loops.append(LoopInfo(fn=pipe.fn, loop_id=next_loop_id, blocks=comp_set))
            next_loop_id += 1
    loops.sort(key=lambda lp: (sorted(lp.blocks), lp.loop_id))
    return loops


def _block_from_pp(pp: str) -> str:
    """Extract the basic-block label from a pp of the form fn:bb:iN."""
    _fn, bb, _idx = pp.rsplit(":", 2)
    return bb


def _is_decision_block(term_op: Optional[str], has_cond: bool, has_target: bool) -> bool:
    if term_op == "br":
        return has_cond
    if term_op == "switch":
        return True
    if term_op == "indirectbr":
        return has_target
    return False


def _find_first_loop_repeat(path_bbs: Sequence[str], loop: LoopInfo) -> Optional[int]:
    seen: Set[str] = set()
    for idx, bb in enumerate(path_bbs):
        if bb in loop.blocks and bb in seen:
            return idx
        if bb in loop.blocks:
            seen.add(bb)
    return None


def _build_slice(pipe: FunctionPipeline, bundle: PathBundle, loop: LoopInfo) -> Optional[LoopSlice]:
    repeat_idx = _find_first_loop_repeat(bundle.path.bbs, loop)
    if repeat_idx is None or bundle.path.path_id is None:
        return None

    prefix_bbs = tuple(bundle.path.bbs[:repeat_idx])
    if not prefix_bbs:
        return None

    insts = []
    for bb in prefix_bbs:
        insts.extend(pipe.bb_insts.get(bb, []))

    blocks_by_bb = {b.bb: b for b in pipe.blocks}
    decision_count = 0
    for bb in prefix_bbs[:-1]:
        block = blocks_by_bb.get(bb)
        if block is None:
            continue
        if _is_decision_block(
            term_op=block.term_op,
            has_cond=block.cond is not None,
            has_target=block.target is not None,
        ):
            decision_count += 1

    return LoopSlice(
        loop=loop,
        path_id=bundle.path.path_id,
        prefix_bbs=prefix_bbs,
        insts=insts,
        path_cond=bundle.path.path_cond[:decision_count],
        path_cond_json=bundle.path.path_cond_json[:decision_count],
    )


def extract_loop_slices(pipe: FunctionPipeline) -> List[LoopSlice]:
    """Return first-iteration loop prefixes for all loop-containing paths."""
    loops = _compute_sccs(pipe)
    out: List[LoopSlice] = []
    for bundle in pipe.paths:
        for loop in loops:
            sl = _build_slice(pipe, bundle, loop)
            if sl is not None:
                out.append(sl)
    return out


def analyze_loop_invariants(
    pipe: FunctionPipeline,
    engine: Optional[SymExecEngine] = None,
) -> List[LoopInvariantRecord]:
    """Infer loop-invariant publicness from first-iteration loop slices."""
    if engine is None:
        engine = SymExecEngine()

    slices = extract_loop_slices(pipe)
    if not slices:
        return []

    facts: Dict[Tuple[int, str, str], List[Optional[bool]]] = {}
    support: Dict[Tuple[int, str, str], Set[int]] = {}
    slice_counts: Dict[Tuple[int, str, str], int] = {}

    for sl in slices:
        results, _summary = engine.analyze_path(
            path_id=sl.path_id,
            insts=sl.insts,
            path_conditions=sl.path_cond,
            path_conditions_json=sl.path_cond_json,
        )
        for r in results:
            bb = _block_from_pp(r.pp)
            if bb not in sl.loop.blocks:
                continue
            key = (sl.loop.loop_id, r.pp, r.value)
            facts.setdefault(key, []).append(r.public)
            support.setdefault(key, set()).add(sl.path_id)
            slice_counts[key] = slice_counts.get(key, 0) + 1

    out: List[LoopInvariantRecord] = []
    for (loop_id, pp, value), vals in sorted(facts.items()):
        any_false = any(v is False for v in vals)
        any_unknown = any(v is None for v in vals)
        if any_false:
            public: Optional[bool] = False
        elif any_unknown:
            public = None
        else:
            public = True
        evidence = tuple(sorted(support.get((loop_id, pp, value), set())))
        out.append(
            LoopInvariantRecord(
                fn=pipe.fn,
                loop_id=loop_id,
                pp=pp,
                value=value,
                public=public,
                support_paths=len(evidence),
                evidence_path_ids=evidence,
                first_iter_paths=slice_counts.get((loop_id, pp, value), 0),
            )
        )
    return out
