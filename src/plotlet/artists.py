"""Per-artist SVG-emit helpers, marker primitive, histogram binning.

Each `_artist_<type>` takes the recorded artist dict, the x and y scales,
and the resolved color, and returns an SVG fragment. They're called from
`core._render`.
"""
import math

from ._spec import _D, _DASH


def _to_pylist(obj):
    """Convert numpy / pandas / arbitrary iterables to plain Python lists."""
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, (list, tuple)):
        return list(obj)
    return list(obj)


def _histogram(data, bins):
    """Equal-width binning. Returns list of {'x0', 'x1', 'count'} dicts."""
    data = [v for v in _to_pylist(data)
            if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not data:
        return []
    lo, hi = min(data), max(data)
    if lo == hi:
        hi = lo + 1
    n = bins if isinstance(bins, int) else 10
    width = (hi - lo) / n
    counts = [0] * n
    for v in data:
        if v == hi:
            counts[-1] += 1
        else:
            i = int((v - lo) / width)
            if 0 <= i < n:
                counts[i] += 1
    return [{"x0": lo + i * width, "x1": lo + (i + 1) * width, "count": counts[i]}
            for i in range(n)]


# ---------------------------------------------------------------------------
# Artist helpers
# ---------------------------------------------------------------------------

def _artist_plot(a, xs_, ys_, col):
    out = []
    opts = a["opts"]
    pts = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["ys"])]
    pts = [(px, py) if (math.isfinite(px) and math.isfinite(py)) else None
           for px, py in pts]
    d_segs, started = [], False
    for p in pts:
        if p is None:
            started = False
            continue
        d_segs.append(f'{"M" if not started else "L"}{p[0]:.2f},{p[1]:.2f}')
        started = True
    ls = opts.get("linestyle")
    if ls not in ("", "none"):
        da = f' stroke-dasharray="{_DASH[ls]}"' if ls and _DASH.get(ls) else ""
        out.append(f'<path d="{"".join(d_segs)}" fill="none" stroke="{col}" '
                   f'stroke-width="{opts.get("linewidth", _D["linewidth"])}"{da}/>')
    if opts.get("marker"):
        sz = opts.get("markersize", _D["markersize"])
        for p in pts:
            if p is None:
                continue
            out.append(_marker_at(opts["marker"], p[0], p[1], sz, col, 1))
    return "".join(out)


def _artist_scatter(a, xs_, ys_, col):
    opts = a["opts"]
    sz = math.sqrt(opts.get("s", _D["scatter_s"])) / 2
    alpha = opts.get("alpha", _D["scatter_alpha"])
    marker = opts.get("marker", "o")
    out = []
    for x, y in zip(a["xs"], a["ys"]):
        px, py = xs_(x), ys_(y)
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        out.append(_marker_at(marker, px, py, sz, col, alpha))
    return "".join(out)


def _artist_bar(a, xs_, ys_, col):
    out = []
    opts = a["opts"]
    bw = xs_.bandwidth
    y0 = ys_(0)
    alpha = opts.get("alpha", _D["bar_alpha"])
    for c, v in zip(a["cats"], a["vals"]):
        x = xs_(c)
        y = ys_(v)
        out.append(f'<rect x="{x:.2f}" y="{min(y0, y):.2f}" width="{bw:.2f}" '
                   f'height="{abs(y - y0):.2f}" fill="{col}" opacity="{alpha}"/>')
    return "".join(out)


def _artist_hist(a, xs_, ys_, ih, col):
    out = []
    alpha = a["opts"].get("alpha", _D["hist_alpha"])
    half_gap = _D["hist_gap"] / 2
    for b in a["_bins"]:
        x0 = xs_(b["x0"]) + half_gap
        x1 = xs_(b["x1"]) - half_gap
        w = max(0, x1 - x0)
        y = ys_(b["count"])
        h = ih - y
        out.append(f'<rect x="{x0:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
                   f'fill="{col}" opacity="{alpha}"/>')
    return "".join(out)


def _artist_fill_between(a, xs_, ys_, col):
    upper = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["y1"])]
    lower = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["y2"])]
    pts = upper + list(reversed(lower))
    if not pts:
        return ""
    d = "M" + "L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts) + "Z"
    alpha = a["opts"].get("alpha", _D["fill_alpha"])
    return f'<path d="{d}" fill="{col}" opacity="{alpha}"/>'


# ---------------------------------------------------------------------------
# Marker primitive — used by plot/scatter and the legend
# ---------------------------------------------------------------------------

def _marker_at(marker, x, y, size, col, alpha):
    msw = _D["marker_stroke_width"]
    if marker == "o":
        return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size}" fill="{col}" opacity="{alpha}"/>'
    if marker == "s":
        return (f'<rect x="{x - size:.2f}" y="{y - size:.2f}" width="{2 * size}" '
                f'height="{2 * size}" fill="{col}" opacity="{alpha}"/>')
    if marker == "^":
        return (f'<path d="M{x:.2f},{y - size:.2f}L{x + size:.2f},{y + size:.2f}'
                f'L{x - size:.2f},{y + size:.2f}Z" fill="{col}" opacity="{alpha}"/>')
    if marker == "v":
        return (f'<path d="M{x:.2f},{y + size:.2f}L{x + size:.2f},{y - size:.2f}'
                f'L{x - size:.2f},{y - size:.2f}Z" fill="{col}" opacity="{alpha}"/>')
    if marker == "x":
        return (f'<path d="M{x - size:.2f},{y - size:.2f}L{x + size:.2f},{y + size:.2f}'
                f'M{x - size:.2f},{y + size:.2f}L{x + size:.2f},{y - size:.2f}" '
                f'stroke="{col}" stroke-width="{msw}" opacity="{alpha}"/>')
    if marker == "+":
        return (f'<path d="M{x - size:.2f},{y:.2f}L{x + size:.2f},{y:.2f}'
                f'M{x:.2f},{y - size:.2f}L{x:.2f},{y + size:.2f}" '
                f'stroke="{col}" stroke-width="{msw}" opacity="{alpha}"/>')
    return ""
