from __future__ import annotations

"""Solver interfaces and minimal Z3 backend.

This module currently supports only basic equality/inequality constraints
over the path_cond format emitted by the LLVM pass.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Tuple

import re


@dataclass
class SolverResult:
    """Result of a solver check."""
    sat: bool
    model: dict[str, str] | None = None


class SolverBase(Protocol):
    """Protocol for solver backends."""
    def add_constraint_str(self, constraint: str) -> None: ...
    def check(self) -> SolverResult: ...


class DummySolver:
    """A no-op solver that treats all constraint sets as satisfiable."""
    def __init__(self) -> None:
        self.constraints: List[str] = []

    def add_constraint_str(self, constraint: str) -> None:
        """Store constraint strings for debugging."""
        self.constraints.append(constraint)

    def check(self) -> SolverResult:
        """Always returns sat; replace with a real solver if needed."""
        return SolverResult(sat=True, model=None)


def _normalize_name(name: str, existing: Dict[str, str]) -> str:
    """Convert arbitrary IDs into Z3-safe names."""
    if name in existing:
        return existing[name]
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not safe or safe[0].isdigit():
        safe = "_" + safe
    if safe in existing.values():
        safe = f"{safe}_{abs(hash(name)) % 10000}"
    existing[name] = safe
    return safe


def _parse_value(val: str) -> Tuple[str, Optional[int], str]:
    """Parse a token into (kind, width, literal).

    kind is one of {"int","real","str","var"}.
    """
    if val.startswith("const:i"):
        rest = val[len("const:i") :]
        width_str, num_str = rest.split(":", 1)
        return "int", int(width_str), num_str
    if val.startswith("const:fp:"):
        return "real", None, val[len("const:fp:") :]
    if val.startswith("label:"):
        return "str", None, val[len("label:") :]
    if val in ("const:null", "const:undef", "const:poison"):
        return "str", None, val
    if val.startswith("const:"):
        return "str", None, val[len("const:") :]
    return "var", None, val


def _split_constraint(constraint: str) -> List[str]:
    """Split compound constraints on ' && ' (used by switch default)."""
    parts = [p.strip() for p in constraint.split(" && ") if p.strip()]
    return parts if parts else [constraint]


class Z3Solver:
    """Minimal Z3 backend for equality/inequality constraints."""
    def __init__(self) -> None:
        try:
            import z3  # type: ignore
        except Exception as exc:  # pragma: no cover - import-time error
            raise RuntimeError(
                "z3-solver is not installed. "
                "Install it via symex/requirements.txt"
            ) from exc

        self._z3 = z3
        self._solver = z3.Solver()
        self._vars: Dict[str, object] = {}
        self._types: Dict[str, str] = {}
        self._widths: Dict[str, int] = {}
        self._name_map: Dict[str, str] = {}

    def _get_var(self, name: str, kind: str, width: Optional[int] = None) -> object:
        """Create or retrieve a Z3 variable for a token."""
        safe = _normalize_name(name, self._name_map)
        if name in self._vars:
            existing_kind = self._types[name]
            if existing_kind != kind:
                raise ValueError(f"type mismatch for {name}: {existing_kind} vs {kind}")
            if kind == "bv" and width is not None and self._widths.get(name) != width:
                raise ValueError(f"width mismatch for {name}: {self._widths.get(name)} vs {width}")
            return self._vars[name]

        if kind == "str":
            var = self._z3.String(safe)
        elif kind == "real":
            var = self._z3.Real(safe)
        elif kind == "bv":
            if width is None:
                width = 64
            var = self._z3.BitVec(safe, width)
            self._widths[name] = width
        else:
            var = self._z3.Int(safe)
        self._vars[name] = var
        self._types[name] = kind
        return var

    def _to_expr(self, token: str, prefer_kind: Optional[str] = None,
                 prefer_width: Optional[int] = None) -> object:
        """Convert a token into a Z3 expression."""
        kind, width, lit = _parse_value(token)
        if kind == "var":
            if prefer_kind == "bv":
                return self._get_var(lit, "bv", prefer_width)
            if prefer_kind == "real":
                return self._get_var(lit, "real")
            if prefer_kind == "str":
                return self._get_var(lit, "str")
            return self._get_var(lit, "int")
        if kind == "int":
            if width is None:
                return self._z3.IntVal(int(lit))
            return self._z3.BitVecVal(int(lit), width)
        if kind == "real":
            return self._z3.RealVal(lit)
        if kind == "str":
            return self._z3.StringVal(lit)
        raise ValueError(f"unknown token: {token}")

    def add_constraint_str(self, constraint: str) -> None:
        """Translate a string constraint into a Z3 assertion."""
        for part in _split_constraint(constraint):
            if "==" in part:
                left, right = [p.strip() for p in part.split("==", 1)]
                l_kind, l_width, _ = _parse_value(left)
                r_kind, r_width, _ = _parse_value(right)
                prefer_left = None
                prefer_right = None
                left_width = None
                right_width = None
                if l_kind == "var" and r_kind == "int":
                    prefer_left = "bv"
                    left_width = r_width
                if r_kind == "var" and l_kind == "int":
                    prefer_right = "bv"
                    right_width = l_width
                if l_kind == "var" and r_kind == "str":
                    prefer_left = "str"
                if r_kind == "var" and l_kind == "str":
                    prefer_right = "str"
                if l_kind == "var" and r_kind == "real":
                    prefer_left = "real"
                if r_kind == "var" and l_kind == "real":
                    prefer_right = "real"
                expr = self._to_expr(left, prefer_left, left_width) == self._to_expr(
                    right, prefer_right, right_width
                )
            elif "!=" in part:
                left, right = [p.strip() for p in part.split("!=", 1)]
                l_kind, l_width, _ = _parse_value(left)
                r_kind, r_width, _ = _parse_value(right)
                prefer_left = None
                prefer_right = None
                left_width = None
                right_width = None
                if l_kind == "var" and r_kind == "int":
                    prefer_left = "bv"
                    left_width = r_width
                if r_kind == "var" and l_kind == "int":
                    prefer_right = "bv"
                    right_width = l_width
                if l_kind == "var" and r_kind == "str":
                    prefer_left = "str"
                if r_kind == "var" and l_kind == "str":
                    prefer_right = "str"
                if l_kind == "var" and r_kind == "real":
                    prefer_left = "real"
                if r_kind == "var" and l_kind == "real":
                    prefer_right = "real"
                expr = self._to_expr(left, prefer_left, left_width) != self._to_expr(
                    right, prefer_right, right_width
                )
            else:
                raise ValueError(f"unsupported constraint: {part}")
            self._solver.add(expr)

    def check(self) -> SolverResult:
        """Return sat/unsat and an optional model."""
        res = self._solver.check()
        if res == self._z3.sat:
            model = self._solver.model()
            assignments: Dict[str, str] = {}
            for name, var in self._vars.items():
                val = model.eval(var, model_completion=True)
                assignments[name] = str(val)
            return SolverResult(sat=True, model=assignments)
        return SolverResult(sat=False, model=None)

    def add_expr(self, expr: object) -> None:
        """Add a raw Z3 expression to the solver."""
        self._solver.add(expr)

    def solver(self):
        """Return the underlying Z3 solver (for push/pop)."""
        return self._solver

    def z3(self):
        """Return the z3 module used by this solver."""
        return self._z3


# TODO(person B): Replace Int/Real/String with LLVM-like bitvector sorts.
# TODO(person B): Add support for boolean connectives beyond 'and'.
