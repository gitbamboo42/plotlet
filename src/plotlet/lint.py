"""Figure-quality lint — minimal. Two checks, one tiny whitelist for
structural geometry.

  edge_clip   any region with a vertex past the figure boundary
  overlap     any two regions whose bboxes overlap, except name-pairs
              in `ALLOWED_OVERLAP_PAIRS` (panel↔spine, spine↔spine —
              unavoidable rendering geometry)

Hits are *warnings*, not errors. A flagged figure may still be
intentional or acceptable; the lint surfaces candidates and the human
reviewer judges. No name-based categorization, no ownership heuristics
— the warning carries the name-pair (e.g., "tick-x ↔ tick-y") so the
reviewer can tell at a glance whether it matters.

Usage:

    from plotlet.lint import lint
    warnings = lint(chart)
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from .draw import coord



EDGE_TOL = 0.0

# Overlapping name-pairs we accept as structural noise rather than
# layout bugs. Each entry is a frozenset of two region names — the
# order doesn't matter when looking up.
#
#   panel ↔ spine: spines render with stroke ±0.5 px around the panel
#     boundary, so the stroke's outer half lives in the panel (data)
#     rect. Unavoidable at the SVG-rendering level.
#   spine ↔ spine: adjacent spines touch at panel corners by one stroke
#     width. Geometric necessity.
ALLOWED_OVERLAP_PAIRS: frozenset[frozenset[str]] = frozenset({
    frozenset({"panel", "spine"}),
    frozenset({"spine"}),  # spine ↔ spine — single-element set covers same-name
})


@dataclass
class Warning:
    """A single lint hit. Severity: warning — the figure renders fine,
    but a human should glance at it before shipping."""
    check: str
    region: str
    bbox: tuple
    message: str

    def __str__(self):
        x, y, w, h = self.bbox
        return (f"{self.check}: {self.region} at "
                f"({coord(x)},{coord(y)},{coord(w)},{coord(h)}) — {self.message}")


def _materialize(chart):
    """FacetGrid doesn't have `.regions()` — it builds a Layout on demand."""
    return chart._materialize() if hasattr(chart, "_materialize") else chart


def _collect(chart) -> tuple[list[dict], float, float]:
    """Regions plus figure (W, H) for one chart. Two seam calls, two
    renders — rendering is deterministic, so the regions and the parsed
    size describe the same figure."""
    chart = _materialize(chart)
    from .figure_ir import to_ir
    from .render import regions, render_svg
    ir = to_ir(chart)
    regs = regions(ir)
    svg = render_svg(ir)
    m = re.search(r'<svg[^>]*\bwidth="([0-9.]+)"\s+height="([0-9.]+)"', svg)
    return regs, float(m.group(1)), float(m.group(2))


def _vertices(r: dict) -> list[tuple[float, float]]:
    """Outer-SVG corners. For rotated text the regions sink records the
    precise 4-vertex polygon — use it so a 45°-rotated label projects
    to its actual extent, not the swollen AABB."""
    poly = r.get("meta", {}).get("polygon")
    if poly:
        return [(float(x), float(y)) for x, y in poly]
    x, y, w, h = r["bbox"]
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def edge_clip(regs, W, H) -> list[Warning]:
    out = []
    for r in regs:
        for vx, vy in _vertices(r):
            if (vx < -EDGE_TOL or vy < -EDGE_TOL
                    or vx > W + EDGE_TOL or vy > H + EDGE_TOL):
                out.append(Warning(
                    "edge_clip", r["name"], r["bbox"],
                    f"vertex ({coord(vx)},{coord(vy)}) outside figure "
                    f"({W:.0f}x{H:.0f})"
                ))
                break
    return out


def overlap(regs, W, H) -> list[Warning]:
    """Brute-force: every pair of regions whose bboxes overlap, except
    name-pairs in `ALLOWED_OVERLAP_PAIRS` (structural noise)."""
    out = []
    for i, a in enumerate(regs):
        ax, ay, aw, ah = a["bbox"]
        for b in regs[i + 1:]:
            if frozenset({a["name"], b["name"]}) in ALLOWED_OVERLAP_PAIRS:
                continue
            bx, by, bw, bh = b["bbox"]
            ox = min(ax + aw, bx + bw) - max(ax, bx)
            oy = min(ay + ah, by + bh) - max(ay, by)
            if ox > 0 and oy > 0:
                out.append(Warning(
                    "overlap", f'{a["name"]} ↔ {b["name"]}',
                    b["bbox"], f"overlap {coord(ox)}x{coord(oy)}px"
                ))
    return out


def lint(chart) -> list[Warning]:
    try:
        regs, W, H = _collect(chart)
    except Exception as e:
        return [Warning("lint_error", "chart", (0, 0, 0, 0),
                           f"render failed: {type(e).__name__}: {e}")]
    return edge_clip(regs, W, H) + overlap(regs, W, H)
