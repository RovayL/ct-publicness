from __future__ import annotations

"""Aggregation logic for publicness results."""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .models import CfgPath, PpCoverage


@dataclass(frozen=True)
class PathPublicness:
    """Per-path publicness for a specific SSA value at a program point."""
    fn: str
    path_id: int
    pp: str
    value: str
    public: Optional[bool]


@dataclass(frozen=True)
class PublicAtPoint:
    """Aggregated publicness at a program point across all paths."""
    fn: str
    pp: str
    value: str
    public: Optional[bool]
    total_paths: int
    missing_paths: int
    truncated: bool


def _build_pp_paths(
    paths: List[CfgPath],
    pp_coverage: List[PpCoverage],
) -> Dict[Tuple[str, str], Tuple[List[int], bool]]:
    """Return mapping (fn, pp) -> (path_ids, truncated)."""
    pp_paths: Dict[Tuple[str, str], Tuple[List[int], bool]] = {}
    if pp_coverage:
        for rec in pp_coverage:
            pp_paths[(rec.fn, rec.pp)] = (list(rec.path_ids), rec.truncated)
        return pp_paths

    # Fallback: derive from path.pp_seq if available.
    for p in paths:
        if p.path_id is None:
            continue
        if not p.pp_seq:
            continue
        seen = set()
        for pp in p.pp_seq:
            key = (p.fn, pp)
            if key in seen:
                continue
            seen.add(key)
            ids, truncated = pp_paths.get(key, ([], False))
            ids.append(p.path_id)
            pp_paths[key] = (ids, truncated)
    return pp_paths


def aggregate_public_at_point(
    paths: List[CfgPath],
    pp_coverage: List[PpCoverage],
    path_results: Iterable[PathPublicness],
    missing_policy: str = "unknown",
) -> List[PublicAtPoint]:
    """Aggregate per-path publicness into per-program-point publicness.

    Rule: public_at_point(pp, value) is True iff public_along_path is True
    for all paths through pp. If any path is False -> False. If any path is
    missing/unknown -> None (unless missing_policy overrides).
    """
    pp_paths = _build_pp_paths(paths, pp_coverage)

    results: Dict[Tuple[str, str, str], Dict[int, Optional[bool]]] = {}
    for r in path_results:
        key = (r.fn, r.pp, r.value)
        results.setdefault(key, {})[r.path_id] = r.public

    out: List[PublicAtPoint] = []
    for (fn, pp), (path_ids, truncated) in pp_paths.items():
        # Collect values observed at this pp across any path results.
        values = [
            value for (r_fn, r_pp, value) in results.keys()
            if r_fn == fn and r_pp == pp
        ]
        if not values:
            continue
        for value in sorted(set(values)):
            key = (fn, pp, value)
            per_path = results.get(key, {})
            missing = 0
            any_false = False
            any_unknown = False
            for pid in path_ids:
                if pid not in per_path:
                    missing += 1
                    any_unknown = True
                    continue
                val = per_path[pid]
                if val is False:
                    any_false = True
                elif val is None:
                    any_unknown = True
            if any_false:
                public = False
            elif any_unknown or truncated:
                if missing_policy == "public":
                    public = True
                elif missing_policy == "secret":
                    public = False
                else:
                    public = None
            else:
                public = True
            out.append(
                PublicAtPoint(
                    fn=fn,
                    pp=pp,
                    value=value,
                    public=public,
                    total_paths=len(path_ids),
                    missing_paths=missing,
                    truncated=truncated,
                )
            )
    return out


# TODO(person B): Extend aggregation to include per-function summaries.
