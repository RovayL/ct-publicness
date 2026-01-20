from __future__ import annotations

"""Constraint builder for per-path analysis.

This module translates path conditions into solver constraints. It currently
supports the simple string and JSON formats emitted by the LLVM pass.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .models import CfgPath
from .solver import DummySolver, SolverBase


@dataclass
class ConstraintBuilder:
    """Builds and stores constraints, and forwards them to a solver.

    constraints: list of string constraints for debugging or replay.
    solver: optional solver implementation (Dummy or Z3-backed).
    """
    constraints: List[str] = field(default_factory=list)
    solver: Optional[SolverBase] = None

    def __post_init__(self) -> None:
        """Ensure a solver is always available."""
        if self.solver is None:
            self.solver = DummySolver()

    def add_path_conditions(self, path: CfgPath) -> None:
        """Add all path conditions from a CfgPath into the solver."""
        if path.path_cond_json:
            for expr in path.path_cond_json:
                self._add_expr(expr)
            return
        for cond in path.path_cond:
            self.add_constraint(cond)

    def add_constraint(self, cond: str) -> None:
        """Record a single constraint and push it into the solver."""
        self.constraints.append(cond)
        if self.solver is not None:
            self.solver.add_constraint_str(cond)

    def _add_expr(self, expr: dict) -> None:
        """Translate a JSON condition expression into string constraints."""
        op = expr.get("op")
        if op == "and":
            for term in expr.get("terms", []):
                self._add_expr(term)
            return
        if op in ("==", "!="):
            lhs = expr.get("lhs", "")
            rhs = expr.get("rhs", "")
            if lhs and rhs:
                self.add_constraint(f"{lhs}{op}{rhs}")
            return
        raise ValueError(f"unsupported expr op: {op}")


# TODO(person B): Replace string constraints with solver-native expressions.
# TODO(person B): Add cache for path conditions to avoid rebuilding per path.
