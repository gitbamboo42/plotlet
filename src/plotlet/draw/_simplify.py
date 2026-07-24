"""Deterministic vertex decimation for dense lines.

A dense line has the opposite problem from a dense point cloud: the
whole series is already ONE `<path>` node, so resvg's node limit never
triggers -- what balloons is the d-string itself (tens of MB for a
million vertices) and the time resvg spends stroking that many
segments. Rasterizing (`draw/_raster.py`) is the wrong tool here: a
stroked path paints its color once no matter how often it crosses
itself, while the splatter's per-mark alpha stacking would darken every
self-overlap. So dense lines stay vector and instead drop the vertices
a stroke cannot show at pixel resolution.

Two reducers, picked per gap-free run. Both are plain functions of the
pixel coordinates (no float FFT, no randomness), so byte-identical
output holds:

  - x-monotonic runs (the time-series shape): per-pixel-column min-max
    (the "M4" reduction) -- keep the first, lowest, highest and last
    vertex of each 1-px column. The stroke still covers each column to
    the same vertical extent, so the drawn pixels match the full path.
  - anything else (parametric curves): collapse consecutive vertices
    that land in the same `dense_tolerance`-px grid cell. Error is
    bounded by the tolerance; vertex order is preserved.

Dashes are the one style decimation can visibly change: dash phase
follows arc length, and collapsing a zigzag shortens the path. Auto
mode therefore skips dashed lines; an explicit `simplify=True` still
forces it.
"""
import numpy as np

from .._spec import _D


def should_simplify(n, simplify_opt, dashed):
    """Verbatim vs decimated for an `n`-vertex line. Explicit `simplify=`
    wins; otherwise auto above `dense_threshold` — the same spec number
    the point-cloud raster path uses — except for dashed lines (see
    module docstring)."""
    if simplify_opt is not None:
        return bool(simplify_opt)
    if dashed:
        return False
    return n >= _D.get("dense_threshold", 20000)


def _m4(px, py):
    """Kept-vertex indices for an x-monotonic run: first / min-y / max-y /
    last per 1-px column. Equal-x columns are contiguous because the run
    is monotonic."""
    cols = np.floor(px).astype(np.int64)
    starts = np.flatnonzero(np.r_[True, cols[1:] != cols[:-1]])
    ends = np.r_[starts[1:], len(cols)]
    keep = []
    for s, e in zip(starts, ends):
        seg = py[s:e]
        keep.extend(sorted({s, s + int(np.argmin(seg)),
                            s + int(np.argmax(seg)), e - 1}))
    return keep


def _grid_dedup(px, py, tol):
    """Kept-vertex indices for a non-monotonic run: drop each vertex that
    rounds to the same tol-px grid cell as its predecessor."""
    gx = np.round(px / tol)
    gy = np.round(py / tol)
    keep = np.r_[True, (gx[1:] != gx[:-1]) | (gy[1:] != gy[:-1])]
    keep[-1] = True  # the run must still end at the real last vertex
    return np.flatnonzero(keep)


def _simplify_run(pts):
    """One gap-free run of (px, py) pixel pairs -> a reduced subset of the
    same pairs, order kept."""
    if len(pts) <= 4:
        return pts
    px = np.asarray([p[0] for p in pts], dtype=float)
    py = np.asarray([p[1] for p in pts], dtype=float)
    dx = np.diff(px)
    if np.all(dx >= 0) or np.all(dx <= 0):
        keep = _m4(px, py)
    else:
        keep = _grid_dedup(px, py, float(_D.get("dense_tolerance", 0.5)))
    return [pts[i] for i in keep]


def simplify_path_pts(path_pts):
    """Decimate a path-point list: (px, py) pairs with None gap markers.
    Each gap-delimited run reduces independently, so breaks stay breaks."""
    out = []
    run = []
    for p in path_pts:
        if p is None:
            out.extend(_simplify_run(run))
            run = []
            out.append(None)
        else:
            run.append(p)
    out.extend(_simplify_run(run))
    return out
