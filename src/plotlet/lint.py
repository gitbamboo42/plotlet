"""Figure-quality lint — minimal. Two checks, a small filter for
structural geometry, and per-pair clustering so one crowded axis
reads as one warning.

  edge_clip   any region with a vertex past the figure boundary
  overlap     any two regions whose bboxes overlap, clustered by
              name-pair: N labels piling up on one axis produce one
              warning carrying the pair count and the worst pair's
              labels, not O(N²) restatements. Rotated text is tested
              against its precise rotated corners, not the swollen
              AABB — 45°-rotated tick labels sitting cleanly side by
              side don't flag.

Overlaps that are rendering geometry rather than layout bugs are
skipped:

  * name-pairs in `ALLOWED_OVERLAP_PAIRS` (panel↔spine, spine↔spine —
    stroke geometry);
  * regions marked `structural` by the renderer (coordinate-owned
    chrome like a circular chart's angular tick labels, an
    inside-positioned legend) and sector walls/labels (`STRUCTURAL_NAMES`)
    — all live inside the panel rect *by design*. Exception: two text
    regions always report, because overlapping labels are unreadable
    no matter whose design put them there;
  * a panel fully inside another panel (insets, a circular chart's
    inner panel).

Hits are *warnings*, not errors. A flagged figure may still be
intentional or acceptable; the lint surfaces candidates and the human
reviewer judges. The warning carries the name-pair (e.g.,
"tick-x ↔ tick-y") and the colliding label texts when the regions are
text, so the reviewer can tell at a glance whether it matters.

Scope note: regions capture *chrome only* — the lint cannot see an
inside-positioned legend covering data marks, because data marks
produce no regions.

Usage:

    warnings = pt.lint(chart)      # also: from plotlet.lint import lint
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

# Chrome that spans the panel by design wherever it appears: sector
# walls cross the data area, sector labels sit against it. Same
# footing as regions the renderer marks `structural=True` in meta.
STRUCTURAL_NAMES = frozenset({"sector-divider", "sector-label"})


def _is_structural(r: dict) -> bool:
    return (r["name"] in STRUCTURAL_NAMES
            or bool(r.get("meta", {}).get("structural")))


def _contains(outer: dict, inner: dict) -> bool:
    ox, oy, ow, oh = outer["bbox"]
    ix, iy, iw, ih = inner["bbox"]
    return (ix >= ox and iy >= oy
            and ix + iw <= ox + ow and iy + ih <= oy + oh)


def _label(r: dict) -> str | None:
    """The region's text, when it has one — for naming the colliding
    labels in the warning message."""
    t = r.get("meta", {}).get("text")
    return str(t) if t not in (None, "") else None


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
    from .record.figure_ir import to_ir
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


def _polys_overlap(pa: list, pb: list) -> bool:
    """Separating-axis test for two convex polygons — True when they
    intersect with positive area (merely touching edges don't count).
    Needed because rotated tick labels' AABBs overlap hugely while the
    actual rotated rectangles sit cleanly side by side — the standard
    45°-rotation-to-avoid-crowding pattern must not be flagged."""
    for poly in (pa, pb):
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            nx, ny = y1 - y2, x2 - x1   # edge normal
            a_proj = [nx * x + ny * y for x, y in pa]
            b_proj = [nx * x + ny * y for x, y in pb]
            if max(a_proj) <= min(b_proj) or max(b_proj) <= min(a_proj):
                return False
    return True


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
    """Brute-force pairwise scan, then cluster the hits by name-pair —
    one warning per pair kind, carrying the pair count and the worst
    pair's geometry and labels. Structural chrome (see module
    docstring) is skipped, except text-vs-text which always reports."""
    hits: dict[frozenset, list] = {}
    for i, a in enumerate(regs):
        ax, ay, aw, ah = a["bbox"]
        for b in regs[i + 1:]:
            if frozenset({a["name"], b["name"]}) in ALLOWED_OVERLAP_PAIRS:
                continue
            both_text = a["kind"] == "text" and b["kind"] == "text"
            if (_is_structural(a) or _is_structural(b)) and not both_text:
                continue
            if (a["name"] == b["name"] == "panel"
                    and (_contains(a, b) or _contains(b, a))):
                continue  # insets, a circular chart's inner panel
            bx, by, bw, bh = b["bbox"]
            ox = min(ax + aw, bx + bw) - max(ax, bx)
            oy = min(ay + ah, by + bh) - max(ay, by)
            if ox > 0 and oy > 0:
                # AABB overlap is only a necessary condition when a
                # region is rotated (carries a `polygon`) — confirm
                # with the precise corners before flagging. The
                # reported ox×oy stays the AABB overlap: an upper
                # bound, but enough to rank severity.
                if (("polygon" in a.get("meta", {})
                     or "polygon" in b.get("meta", {}))
                        and not _polys_overlap(_vertices(a), _vertices(b))):
                    continue
                key = frozenset({a["name"], b["name"]})
                hits.setdefault(key, []).append((a, b, ox, oy))
    out = []
    for members in hits.values():  # insertion order — deterministic
        a, b, ox, oy = max(members, key=lambda h: h[2] * h[3])
        pair = f'{a["name"]} ↔ {b["name"]}'
        labels = [l for l in (_label(a), _label(b)) if l is not None]
        named = f" ({' ↔ '.join(repr(l) for l in labels)})" if labels else ""
        if len(members) == 1:
            msg = f"overlap {coord(ox)}x{coord(oy)}px{named}"
        else:
            n_regions = len({id(r) for m in members for r in m[:2]})
            msg = (f"{len(members)} overlapping pairs among {n_regions} "
                   f"regions; worst {coord(ox)}x{coord(oy)}px{named}")
        out.append(Warning("overlap", pair, b["bbox"], msg))
    return out


def lint(chart) -> list[Warning]:
    try:
        regs, W, H = _collect(chart)
    except Exception as e:
        return [Warning("lint_error", "chart", (0, 0, 0, 0),
                           f"render failed: {type(e).__name__}: {e}")]
    return edge_clip(regs, W, H) + overlap(regs, W, H)
