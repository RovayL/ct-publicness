from __future__ import annotations

"""Dataclasses for trace, CFG, and analysis results.

These models define the input/output contracts between the LLVM pass (Person A)
and the Python analysis pipeline (Person B).
"""

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class TxInfo:
    """Transmitter metadata for an instruction."""
    kind: str
    which: int


@dataclass(frozen=True)
class TraceInst:
    """Instruction record from the trace NDJSON."""
    fn: str
    bb: str
    pp: str
    op: str
    def_id: Optional[str]
    uses: Sequence[str]
    tx: Optional[TxInfo]
    def_ty: Optional[str]
    use_tys: Optional[Sequence[str]]


@dataclass(frozen=True)
class TraceIndex:
    """Trace index record mapping program points to trace line numbers."""
    fn: str
    bb: str
    pp: str
    op: str
    def_id: Optional[str]
    line: int


@dataclass(frozen=True)
class FuncSummary:
    """Per-function trace summary emitted by the LLVM pass."""
    fn: str
    inst_count: int
    bb_count: int
    tx_count: int
    trace_emitted: int
    trace_truncated: bool
    trace_max_inst: int


@dataclass(frozen=True)
class CfgBlock:
    """Basic block record from CFG NDJSON."""
    fn: str
    bb: str
    succs: Sequence[str]
    term_pp: Optional[str]
    term_op: Optional[str]
    cond: Optional[str]
    target: Optional[str]


@dataclass(frozen=True)
class CfgEdge:
    """Edge record from CFG NDJSON."""
    fn: str
    from_bb: str
    to_bb: str
    term_pp: Optional[str]
    branch: Optional[str]
    cond: Optional[str]
    sense: Optional[str]
    case: Optional[str]
    is_default: bool
    target: Optional[str]


@dataclass(frozen=True)
class PathDecision:
    """Branch decision taken along a path."""
    pp: str
    kind: str
    succ: str
    cond: Optional[str]
    sense: Optional[str]
    case: Optional[str]
    is_default: bool
    target: Optional[str]


@dataclass(frozen=True)
class CfgPath:
    """Path record from CFG NDJSON."""
    fn: str
    path_id: Optional[int]
    bbs: Sequence[str]
    decisions: Sequence[PathDecision]
    path_cond: Sequence[str]
    path_cond_json: Sequence[dict]
    pp_seq: Sequence[str]


@dataclass(frozen=True)
class PpCoverage:
    """Program point coverage record (pp -> path IDs)."""
    fn: str
    pp: str
    path_count: int
    path_ids: Sequence[int]
    truncated: bool


@dataclass(frozen=True)
class PathSummary:
    """Per-function path enumeration summary and pruning stats."""
    fn: str
    paths_emitted: int
    truncated: Optional[bool]
    max_paths: Optional[int]
    max_depth: Optional[int]
    max_loop_iters: Optional[int]
    cutoff_depth: Optional[bool]
    cutoff_loop: Optional[bool]
    disabled: Optional[bool]
    const_pruned_br: Optional[int]
    const_pruned_switch: Optional[int]
    const_pruned_indirect: Optional[int]
    dfs_calls: Optional[int]
    dfs_leaves: Optional[int]
    dfs_prune_max_paths: Optional[int]
    dfs_prune_max_depth: Optional[int]
    dfs_prune_loop: Optional[int]
