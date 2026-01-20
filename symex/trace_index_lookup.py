from __future__ import annotations

"""Trace index lookup helpers."""

from dataclasses import dataclass
from typing import Dict, Optional

from .models import TraceIndex
from .parser import load_trace_index


@dataclass(frozen=True)
class TraceIndexLookup:
    """Index for fast pp/line lookups."""
    by_pp: Dict[str, TraceIndex]
    by_line: Dict[int, TraceIndex]

    def get_by_pp(self, pp: str) -> Optional[TraceIndex]:
        """Return the trace index entry for a program point."""
        return self.by_pp.get(pp)

    def get_by_line(self, line: int) -> Optional[TraceIndex]:
        """Return the trace index entry for a line number."""
        return self.by_line.get(line)


def build_trace_index_lookup(path: str) -> TraceIndexLookup:
    """Build a lookup object from a trace index NDJSON file."""
    entries = load_trace_index(path)
    by_pp = {e.pp: e for e in entries}
    by_line = {e.line: e for e in entries}
    return TraceIndexLookup(by_pp=by_pp, by_line=by_line)
