"""Findings to output. Sorts, filters, formats; never runs a command."""

import json
from dataclasses import asdict
from typing import TextIO

from idle_hunter_lib.models import Finding


def render(findings: list[Finding], min_confidence: int = 0, show_commands: bool = False) -> str:
    rows = [f for f in findings if f.confidence >= max(min_confidence, 1)]
    rows.sort(key=lambda f: (-f.confidence, -f.monthly_usd))
    total = sum(f.monthly_usd for f in rows)
    lines = [f"# idle-hunter report — {len(rows)} finding(s), ~${total:,.0f}/mo reclaimable\n"]
    for f in rows:
        lines.append(f"[{f.confidence:3d}%] {f.kind}  {f.id}  ({f.region})  ~${f.monthly_usd}/mo")
        lines.append(f"       {f.note}")
        if show_commands and f.command:
            lines.append(f"       $ {f.command}")
    return "\n".join(lines)


def render_json(findings: list[Finding], min_confidence: int, stream: TextIO) -> None:
    """The same findings as JSON, for dashboards and examples/basic/review.sh."""
    # --min-confidence applies here too: a script generated from this output
    # must not contain deletes the caller asked to be filtered out.
    json.dump(
        [asdict(f) for f in findings if f.confidence >= min_confidence],
        stream,
        indent=2,
        default=str,
    )
