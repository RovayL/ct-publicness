from __future__ import annotations

"""Minimal symbolic execution engine for trace paths.

This is an MVP that supports a small subset of LLVM opcodes and an
approximate memory model (per-pointer map). It is intended as a starting
point for Person B to extend.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .models import TraceInst
from .publicness import PathPublicness
from .solver import Z3Solver


@dataclass
class SymState:
    tag: str
    env: Dict[str, object]
    mem: Dict[str, object]
    fresh_id: int


@dataclass(frozen=True)
class PathAnalysisSummary:
    """Per-path solver/query stats for benchmarking and reporting."""
    fn: str
    path_id: int
    inst_count: int
    def_count: int
    query_count: int
    sat_count: int
    unsat_count: int
    unknown_count: int
    solver_time_ms: float
    cache_hits: int
    cache_misses: int


def _parse_ty_width(ty: Optional[str], ptr_width: int) -> int:
    if not ty:
        return ptr_width
    if ty.startswith("i") and ty[1:].isdigit():
        return int(ty[1:])
    if "ptr" in ty or ty.endswith("*"):
        return ptr_width
    return ptr_width


def _const_to_bv(z3, const_id: str, width: int) -> object:
    # const:iW:V
    rest = const_id[len("const:i") :]
    w_str, v_str = rest.split(":", 1)
    w = int(w_str)
    v = int(v_str)
    return z3.BitVecVal(v, w if w else width)


def _label_to_bv(z3, label_id: str, width: int) -> object:
    """Encode label tokens (e.g., label:bb1) as stable BV literals."""
    digest = hashlib.sha256(label_id.encode("utf-8")).hexdigest()
    val = int(digest[:16], 16)
    return z3.BitVecVal(val, width)


def _parse_const(z3, const_id: str, width: int, ptr_width: int) -> object:
    if const_id.startswith("const:i"):
        return _const_to_bv(z3, const_id, width)
    if const_id.startswith("const:fp:"):
        return z3.RealVal(const_id[len("const:fp:") :])
    if const_id in ("const:null", "const:undef", "const:poison"):
        return z3.BitVecVal(0, ptr_width)
    if const_id.startswith("const:"):
        # Fallback to string literal representation.
        return z3.StringVal(const_id[len("const:") :])
    raise ValueError(f"unknown constant: {const_id}")


def _as_bv(z3, expr: object, width: int) -> object:
    if z3.is_bv(expr):
        if expr.size() == width:
            return expr
        if expr.size() < width:
            return z3.ZeroExt(width - expr.size(), expr)
        return z3.Extract(width - 1, 0, expr)
    if z3.is_bool(expr):
        return z3.If(expr, z3.BitVecVal(1, width), z3.BitVecVal(0, width))
    if z3.is_int(expr):
        return z3.Int2BV(expr, width)
    return expr


def _icmp_pred(z3, pred: str, a: object, b: object, signed: bool) -> object:
    if pred in ("eq", "oeq", "ueq"):
        return a == b
    if pred in ("ne", "one", "une"):
        return a != b
    if signed:
        if pred in ("slt",):
            return a < b
        if pred in ("sle",):
            return a <= b
        if pred in ("sgt",):
            return a > b
        if pred in ("sge",):
            return a >= b
    else:
        if pred in ("ult",):
            return z3.ULT(a, b)
        if pred in ("ule",):
            return z3.ULE(a, b)
        if pred in ("ugt",):
            return z3.UGT(a, b)
        if pred in ("uge",):
            return z3.UGE(a, b)
    # Unknown predicate: return unconstrained bool.
    return z3.BoolVal(True)


class SymExecEngine:
    """Execute a path trace twice and query publicness via Z3."""

    def __init__(self, ptr_width: int = 64, enable_query_cache: bool = True) -> None:
        self.ptr_width = ptr_width
        self.enable_query_cache = enable_query_cache
        self._query_cache: Dict[str, Optional[bool]] = {}

    def _fresh(self, z3, state: SymState, name: str, width: int) -> object:
        sym = z3.BitVec(f"{state.tag}_{name}_{state.fresh_id}", width)
        state.fresh_id += 1
        return sym

    def _eval_operand(
        self,
        z3,
        state: SymState,
        operand_id: str,
        width: int,
    ) -> object:
        if operand_id.startswith("const:"):
            return _parse_const(z3, operand_id, width, self.ptr_width)
        if operand_id in state.env:
            return state.env[operand_id]
        # Uninitialized values default to fresh symbols.
        sym = self._fresh(z3, state, f"u_{operand_id}", width)
        state.env[operand_id] = sym
        return sym

    def _token_hint(self, token: str) -> Tuple[str, Optional[int]]:
        if token.startswith("const:i"):
            rest = token[len("const:i") :]
            width_str, _ = rest.split(":", 1)
            return "bv", int(width_str)
        if token.startswith("const:fp:"):
            return "real", None
        if token in ("const:null", "const:undef", "const:poison"):
            return "bv", self.ptr_width
        if token.startswith("label:"):
            return "bv", self.ptr_width
        if token.startswith("const:"):
            return "str", None
        return "var", None

    def _fresh_typed(
        self,
        z3,
        state: SymState,
        name: str,
        prefer_kind: str,
        prefer_width: Optional[int],
    ) -> object:
        if prefer_kind == "real":
            sym = z3.Real(f"{state.tag}_{name}_{state.fresh_id}")
            state.fresh_id += 1
            return sym
        if prefer_kind == "str":
            sym = z3.String(f"{state.tag}_{name}_{state.fresh_id}")
            state.fresh_id += 1
            return sym
        width = prefer_width if prefer_width is not None else self.ptr_width
        return self._fresh(z3, state, name, width)

    def _eval_condition_token(
        self,
        z3,
        state: SymState,
        token: str,
        prefer_kind: str = "bv",
        prefer_width: Optional[int] = None,
    ) -> object:
        if token.startswith("const:"):
            return _parse_const(z3, token, prefer_width or self.ptr_width, self.ptr_width)
        if token.startswith("label:"):
            width = prefer_width if prefer_width is not None else self.ptr_width
            return _label_to_bv(z3, token, width)
        if token in state.env:
            expr = state.env[token]
            if prefer_kind == "bv":
                width = prefer_width if prefer_width is not None else self.ptr_width
                return _as_bv(z3, expr, width)
            return expr
        sym = self._fresh_typed(
            z3, state, f"pc_{token}", prefer_kind, prefer_width
        )
        state.env[token] = sym
        return sym

    def _build_cmp_expr(
        self,
        z3,
        state: SymState,
        lhs: str,
        rhs: str,
        cmp_op: str,
    ) -> object:
        l_kind, l_width = self._token_hint(lhs)
        r_kind, r_width = self._token_hint(rhs)

        lhs_kind = r_kind if l_kind == "var" and r_kind != "var" else l_kind
        rhs_kind = l_kind if r_kind == "var" and l_kind != "var" else r_kind
        lhs_width = r_width if lhs_kind == "bv" and l_width is None else l_width
        rhs_width = l_width if rhs_kind == "bv" and r_width is None else r_width

        if lhs_kind == "var":
            lhs_kind = "bv"
        if rhs_kind == "var":
            rhs_kind = "bv"

        l_expr = self._eval_condition_token(
            z3, state, lhs, prefer_kind=lhs_kind, prefer_width=lhs_width
        )
        r_expr = self._eval_condition_token(
            z3, state, rhs, prefer_kind=rhs_kind, prefer_width=rhs_width
        )

        if z3.is_bv(l_expr) and z3.is_bv(r_expr) and l_expr.size() != r_expr.size():
            width = max(l_expr.size(), r_expr.size())
            l_expr = _as_bv(z3, l_expr, width)
            r_expr = _as_bv(z3, r_expr, width)

        if cmp_op == "==":
            return l_expr == r_expr
        if cmp_op == "!=":
            return l_expr != r_expr
        raise ValueError(f"unsupported compare op: {cmp_op}")

    def _add_path_condition_json(self, solver: Z3Solver, z3, state: SymState, expr: dict) -> None:
        op = expr.get("op")
        if op == "and":
            for term in expr.get("terms", []):
                self._add_path_condition_json(solver, z3, state, term)
            return
        if op in ("==", "!="):
            lhs = expr.get("lhs")
            rhs = expr.get("rhs")
            if not isinstance(lhs, str) or not isinstance(rhs, str):
                raise ValueError(f"malformed path condition JSON: {expr}")
            solver.add_expr(self._build_cmp_expr(z3, state, lhs, rhs, op))
            return
        raise ValueError(f"unsupported path condition JSON op: {op}")

    def _add_path_conditions(
        self,
        solver: Z3Solver,
        z3,
        state: SymState,
        path_conditions: Sequence[str],
        path_conditions_json: Sequence[dict],
    ) -> None:
        if path_conditions_json:
            for cond in path_conditions_json:
                self._add_path_condition_json(solver, z3, state, cond)
            return
        for cond in path_conditions:
            parts = [p.strip() for p in cond.split(" && ") if p.strip()]
            for part in parts:
                if "==" in part:
                    lhs, rhs = [x.strip() for x in part.split("==", 1)]
                    solver.add_expr(self._build_cmp_expr(z3, state, lhs, rhs, "=="))
                elif "!=" in part:
                    lhs, rhs = [x.strip() for x in part.split("!=", 1)]
                    solver.add_expr(self._build_cmp_expr(z3, state, lhs, rhs, "!="))
                else:
                    raise ValueError(f"unsupported path condition string: {part}")

    def _eval_inst(
        self,
        z3,
        inst: TraceInst,
        state: SymState,
        exec_tag: str,
        prev_bb: Optional[str],
    ) -> Optional[object]:
        op = inst.op
        def_id = inst.def_id
        def_width = _parse_ty_width(inst.def_ty, self.ptr_width)

        # Helper to fetch operands.
        def get_op(idx: int) -> object:
            if idx >= len(inst.uses):
                return self._fresh(z3, state, f"missing_{exec_tag}", def_width)
            width = def_width
            if inst.use_tys and idx < len(inst.use_tys):
                width = _parse_ty_width(inst.use_tys[idx], self.ptr_width)
            return self._eval_operand(z3, state, inst.uses[idx], width)

        if op == "alloca":
            if def_id:
                state.env[def_id] = self._fresh(z3, state, f"alloca_{exec_tag}", self.ptr_width)
            return None
        if op == "load":
            ptr_id = inst.uses[0] if inst.uses else "unknown_ptr"
            if ptr_id in state.mem:
                val = state.mem[ptr_id]
            else:
                val = self._fresh(z3, state, f"load_{exec_tag}_{ptr_id}", def_width)
                state.mem[ptr_id] = val
            if def_id:
                state.env[def_id] = val
            return val
        if op == "store":
            if len(inst.uses) >= 2:
                val = get_op(0)
                ptr_id = inst.uses[1]
                state.mem[ptr_id] = val
            return None
        if op in ("add", "sub", "mul", "and", "or", "xor", "shl", "lshr", "ashr"):
            a = _as_bv(z3, get_op(0), def_width)
            b = _as_bv(z3, get_op(1), def_width)
            if op == "add":
                expr = a + b
            elif op == "sub":
                expr = a - b
            elif op == "mul":
                expr = a * b
            elif op == "and":
                expr = a & b
            elif op == "or":
                expr = a | b
            elif op == "xor":
                expr = a ^ b
            elif op == "shl":
                expr = a << b
            elif op == "lshr":
                expr = z3.LShR(a, b)
            else:
                expr = a >> b
            if def_id:
                state.env[def_id] = expr
            return expr
        if op == "icmp":
            pred = inst.icmp_pred or "eq"
            a = _as_bv(z3, get_op(0), def_width)
            b = _as_bv(z3, get_op(1), def_width)
            signed = pred.startswith("s")
            cond = _icmp_pred(z3, pred, a, b, signed)
            expr = z3.If(cond, z3.BitVecVal(1, 1), z3.BitVecVal(0, 1))
            if def_id:
                state.env[def_id] = expr
            return expr
        if op in ("zext", "sext"):
            a = get_op(0)
            from_width = a.size() if z3.is_bv(a) else 1
            to_width = def_width
            if op == "zext":
                expr = z3.ZeroExt(to_width - from_width, _as_bv(z3, a, from_width))
            else:
                expr = z3.SignExt(to_width - from_width, _as_bv(z3, a, from_width))
            if def_id:
                state.env[def_id] = expr
            return expr
        if op == "trunc":
            a = get_op(0)
            expr = _as_bv(z3, a, def_width)
            if def_id:
                state.env[def_id] = expr
            return expr
        if op == "select":
            cond = get_op(0)
            tval = get_op(1)
            fval = get_op(2)
            cond_b = _as_bv(z3, cond, 1)
            expr = z3.If(cond_b == z3.BitVecVal(1, 1), tval, fval)
            if def_id:
                state.env[def_id] = expr
            return expr
        if op == "getelementptr":
            # Approximate: treat GEP as base + last index.
            base = get_op(0)
            idx = get_op(len(inst.uses) - 1) if inst.uses else self._fresh(z3, state, "idx", self.ptr_width)
            expr = _as_bv(z3, base, self.ptr_width) + _as_bv(z3, idx, self.ptr_width)
            if def_id:
                state.env[def_id] = expr
            return expr
        if op == "phi":
            # PHI operands are emitted as value/block pairs in the trace.
            chosen_id: Optional[str] = None
            chosen_idx = None
            if inst.uses:
                if prev_bb:
                    for i in range(0, len(inst.uses) - 1, 2):
                        val_id = inst.uses[i]
                        bb_id = inst.uses[i + 1]
                        if bb_id == prev_bb:
                            chosen_id = val_id
                            chosen_idx = i
                            break
                if chosen_id is None and len(inst.uses) >= 2:
                    # Fallback: pick the first incoming value.
                    chosen_id = inst.uses[0]
                    chosen_idx = 0
            if chosen_id is not None:
                width = def_width
                if inst.use_tys and chosen_idx is not None and chosen_idx < len(inst.use_tys):
                    width = _parse_ty_width(inst.use_tys[chosen_idx], self.ptr_width)
                expr = self._eval_operand(z3, state, chosen_id, width)
            else:
                expr = self._fresh(z3, state, f"phi_{exec_tag}", def_width)
            if def_id:
                state.env[def_id] = expr
            return expr
        if op == "call":
            if def_id:
                state.env[def_id] = self._fresh(z3, state, f"call_{exec_tag}", def_width)
            return None

        # Default: unsupported opcode -> fresh symbol if it defines a value.
        if def_id:
            expr = self._fresh(z3, state, f"u_{exec_tag}", def_width)
            state.env[def_id] = expr
            return expr
        return None

    def analyze_path(
        self,
        path_id: int,
        insts: List[TraceInst],
        path_conditions: Sequence[str],
        path_conditions_json: Sequence[dict] = (),
    ) -> Tuple[List[PathPublicness], PathAnalysisSummary]:
        """Run dual execution for a single path and emit publicness results."""
        solver = Z3Solver()
        z3 = solver.z3()

        state_a = SymState(tag="A", env={}, mem={}, fresh_id=0)
        state_b = SymState(tag="B", env={}, mem={}, fresh_id=0)
        tx_equalities: List[object] = []

        # Execute instructions and collect transmitter equality constraints.
        prev_bb = None
        current_bb = None
        for inst in insts:
            if inst.bb != current_bb:
                prev_bb = current_bb
                current_bb = inst.bb
            self._eval_inst(z3, inst, state_a, "A", prev_bb)
            self._eval_inst(z3, inst, state_b, "B", prev_bb)
            if inst.tx and inst.tx.which < len(inst.uses):
                op_id = inst.uses[inst.tx.which]
                op_width = self.ptr_width
                if inst.use_tys and inst.tx.which < len(inst.use_tys):
                    op_width = _parse_ty_width(inst.use_tys[inst.tx.which], self.ptr_width)
                a_expr = self._eval_operand(z3, state_a, op_id, op_width)
                b_expr = self._eval_operand(z3, state_b, op_id, op_width)
                tx_equalities.append(a_expr == b_expr)

        # Path constraints must hold for each execution separately.
        self._add_path_conditions(
            solver=solver,
            z3=z3,
            state=state_a,
            path_conditions=path_conditions,
            path_conditions_json=path_conditions_json,
        )
        self._add_path_conditions(
            solver=solver,
            z3=z3,
            state=state_b,
            path_conditions=path_conditions,
            path_conditions_json=path_conditions_json,
        )
        for eq in tx_equalities:
            solver.add_expr(eq)

        results: List[PathPublicness] = []
        query_count = 0
        sat_count = 0
        unsat_count = 0
        unknown_count = 0
        cache_hits = 0
        cache_misses = 0
        solver_time_ms = 0.0
        base_key = hashlib.sha256(solver.solver().sexpr().encode("utf-8")).hexdigest()

        for inst in insts:
            if not inst.def_id:
                continue
            query_count += 1
            a_expr = state_a.env.get(inst.def_id)
            b_expr = state_b.env.get(inst.def_id)
            if a_expr is None or b_expr is None:
                unknown_count += 1
                results.append(
                    PathPublicness(
                        fn=inst.fn,
                        path_id=path_id,
                        pp=inst.pp,
                        value=inst.def_id,
                        public=None,
                    )
                )
                continue

            diff_expr = a_expr != b_expr
            query_key = hashlib.sha256(
                f"{base_key}|{diff_expr.sexpr()}".encode("utf-8")
            ).hexdigest()
            sat: Optional[bool]
            cached = self.enable_query_cache and query_key in self._query_cache
            if cached:
                cache_hits += 1
                sat = self._query_cache[query_key]
            else:
                cache_misses += 1
                solver.solver().push()
                solver.add_expr(diff_expr)
                t0 = time.perf_counter()
                check_res = solver.solver().check()
                solver_time_ms += (time.perf_counter() - t0) * 1000.0
                solver.solver().pop()
                if check_res == z3.sat:
                    sat = True
                elif check_res == z3.unsat:
                    sat = False
                else:
                    sat = None
                if self.enable_query_cache:
                    self._query_cache[query_key] = sat

            if sat is True:
                sat_count += 1
            elif sat is False:
                unsat_count += 1
            else:
                unknown_count += 1
            results.append(
                PathPublicness(
                    fn=inst.fn,
                    path_id=path_id,
                    pp=inst.pp,
                    value=inst.def_id,
                    public=sat,
                )
            )
        summary = PathAnalysisSummary(
            fn=insts[0].fn if insts else "",
            path_id=path_id,
            inst_count=len(insts),
            def_count=sum(1 for inst in insts if inst.def_id),
            query_count=query_count,
            sat_count=sat_count,
            unsat_count=unsat_count,
            unknown_count=unknown_count,
            solver_time_ms=solver_time_ms,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
        )
        return results, summary


# TODO(person B): Replace the memory model with array theory or SSA memory.
