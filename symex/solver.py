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
        self._name_map: Dict[str, str] = {}

    def _get_var(self, name: str, kind: str) -> object:
        """Create or retrieve a Z3 variable for a token."""
        safe = _normalize_name(name, self._name_map)
        if name in self._vars:
            existing_kind = self._types[name]
            if existing_kind != kind:
                raise ValueError(f"type mismatch for {name}: {existing_kind} vs {kind}")
            return self._vars[name]

        if kind == "str":
            var = self._z3.String(safe)
        elif kind == "real":
            var = self._z3.Real(safe)
        else:
            var = self._z3.Int(safe)
        self._vars[name] = var
        self._types[name] = kind
        return var

    def _to_expr(self, token: str) -> object:
        """Convert a token into a Z3 expression."""
        kind, _width, lit = _parse_value(token)
        if kind == "var":
            return self._get_var(lit, "int")
        if kind == "int":
            return self._z3.IntVal(int(lit))
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
                l_kind, _, _ = _parse_value(left)
                r_kind, _, _ = _parse_value(right)
                if l_kind == "var" and r_kind == "str":
                    self._get_var(left, "str")
                if r_kind == "var" and l_kind == "str":
                    self._get_var(right, "str")
                expr = self._to_expr(left) == self._to_expr(right)
            elif "!=" in part:
                left, right = [p.strip() for p in part.split("!=", 1)]
                l_kind, _, _ = _parse_value(left)
                r_kind, _, _ = _parse_value(right)
                if l_kind == "var" and r_kind == "str":
                    self._get_var(left, "str")
                if r_kind == "var" and l_kind == "str":
                    self._get_var(right, "str")
                expr = self._to_expr(left) != self._to_expr(right)
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


# TODO(person B): Replace Int/Real/String with LLVM-like bitvector sorts.
# TODO(person B): Add support for boolean connectives beyond 'and'.
