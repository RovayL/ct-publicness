from __future__ import annotations

"""Minimal symbolic execution engine for trace paths.

This is an MVP that supports a small subset of LLVM opcodes and an
approximate memory model (per-pointer map). It is intended as a starting
point for Person B to extend.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .models import TraceInst, TxInfo
from .publicness import PathPublicness
from .solver import Z3Solver


@dataclass
class SymState:
    env: Dict[str, object]
    mem: Dict[str, object]
    fresh_id: int


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

    def __init__(self, ptr_width: int = 64) -> None:
        self.ptr_width = ptr_width

    def _fresh(self, z3, state: SymState, name: str, width: int) -> object:
        sym = z3.BitVec(f"{name}_{state.fresh_id}", width)
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
        path_conditions: List[str],
    ) -> List[PathPublicness]:
        """Run dual execution for a single path and emit publicness results."""
        solver = Z3Solver()
        z3 = solver.z3()
        for cond in path_conditions:
            solver.add_constraint_str(cond)

        state_a = SymState(env={}, mem={}, fresh_id=0)
        state_b = SymState(env={}, mem={}, fresh_id=0)

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
                a_expr = state_a.env.get(op_id)
                b_expr = state_b.env.get(op_id)
                if a_expr is not None and b_expr is not None:
                    solver.add_expr(a_expr == b_expr)

        results: List[PathPublicness] = []
        for inst in insts:
            if not inst.def_id:
                continue
            a_expr = state_a.env.get(inst.def_id)
            b_expr = state_b.env.get(inst.def_id)
            if a_expr is None or b_expr is None:
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
            solver.solver().push()
            solver.add_expr(a_expr != b_expr)
            sat = solver.solver().check() == z3.sat
            solver.solver().pop()
            results.append(
                PathPublicness(
                    fn=inst.fn,
                    path_id=path_id,
                    pp=inst.pp,
                    value=inst.def_id,
                    public=bool(sat),
                )
            )
        return results


# TODO(person B): Replace the memory model with array theory or SSA memory.
# TODO(person B): Use path_cond_json directly for structured constraints.
