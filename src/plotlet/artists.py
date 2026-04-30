"""Per-artist SVG-emit helpers, marker primitive, histogram binning.

Each `_artist_<type>` takes the recorded artist dict, the x and y scales,
and the resolved color, and returns an SVG fragment. They're called from
`core._render`.
"""
import base64
import math

from ._spec import _D, _DASH
from ._png import encode_rgb
from .colormaps import colormap_lut


def _to_pylist(obj):
    """Convert numpy / pandas / arbitrary iterables to plain Python lists."""
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, (list, tuple)):
        return list(obj)
    return list(obj)


def _to_2d_pylist(obj):
    """Convert a 2-D input (list-of-lists, numpy 2-D, DataFrame) to nested lists."""
    if hasattr(obj, "values") and not hasattr(obj, "tolist"):
        obj = obj.values
    if hasattr(obj, "tolist"):
        out = obj.tolist()
    else:
        out = [list(row) for row in obj]
    if not out:
        return out
    if not isinstance(out[0], list):
        raise ValueError("imshow data must be 2-D")
    return out


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


def _artist_axhline(a, xs_, ys_, iw, ih, col):
    opts = a["opts"]
    y = ys_(a["y"])
    if not math.isfinite(y) or y < 0 or y > ih:
        return ""
    x0 = iw * opts.get("xmin", 0.0)
    x1 = iw * opts.get("xmax", 1.0)
    lw = opts.get("linewidth", _D["refline_width"])
    ls = opts.get("linestyle")
    da = f' stroke-dasharray="{_DASH[ls]}"' if ls and _DASH.get(ls) else ""
    alpha = opts.get("alpha", 1)
    return (f'<line x1="{x0:.2f}" x2="{x1:.2f}" y1="{y:.2f}" y2="{y:.2f}" '
            f'stroke="{col}" stroke-width="{lw}" opacity="{alpha}"{da}/>')


def _artist_axvline(a, xs_, ys_, iw, ih, col):
    opts = a["opts"]
    x = xs_(a["x"])
    if not math.isfinite(x) or x < 0 or x > iw:
        return ""
    y0 = ih * (1 - opts.get("ymax", 1.0))
    y1 = ih * (1 - opts.get("ymin", 0.0))
    lw = opts.get("linewidth", _D["refline_width"])
    ls = opts.get("linestyle")
    da = f' stroke-dasharray="{_DASH[ls]}"' if ls and _DASH.get(ls) else ""
    alpha = opts.get("alpha", 1)
    return (f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y0:.2f}" y2="{y1:.2f}" '
            f'stroke="{col}" stroke-width="{lw}" opacity="{alpha}"{da}/>')


def _artist_axhspan(a, xs_, ys_, iw, ih, col):
    opts = a["opts"]
    y_a = ys_(a["ymin"]); y_b = ys_(a["ymax"])
    y0 = max(0.0, min(ih, min(y_a, y_b)))
    y1 = max(0.0, min(ih, max(y_a, y_b)))
    if y1 - y0 <= 0:
        return ""
    x0 = iw * opts.get("xmin", 0.0)
    x1 = iw * opts.get("xmax", 1.0)
    alpha = opts.get("alpha", _D["refspan_alpha"])
    return (f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" '
            f'height="{y1 - y0:.2f}" fill="{col}" opacity="{alpha}"/>')


def _artist_axvspan(a, xs_, ys_, iw, ih, col):
    opts = a["opts"]
    x_a = xs_(a["xmin"]); x_b = xs_(a["xmax"])
    x0 = max(0.0, min(iw, min(x_a, x_b)))
    x1 = max(0.0, min(iw, max(x_a, x_b)))
    if x1 - x0 <= 0:
        return ""
    y0 = ih * (1 - opts.get("ymax", 1.0))
    y1 = ih * (1 - opts.get("ymin", 0.0))
    alpha = opts.get("alpha", _D["refspan_alpha"])
    return (f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" '
            f'height="{y1 - y0:.2f}" fill="{col}" opacity="{alpha}"/>')


def _artist_fill_between(a, xs_, ys_, col):
    upper = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["y1"])]
    lower = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["y2"])]
    pts = upper + list(reversed(lower))
    if not pts:
        return ""
    d = "M" + "L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts) + "Z"
    alpha = a["opts"].get("alpha", _D["fill_alpha"])
    return f'<path d="{d}" fill="{col}" opacity="{alpha}"/>'


def _artist_imshow(a, xs_, ys_, col):
    """2-D array → colored grid. Branches between many <rect>s and one PNG.

    The threshold (`imshow_max_rects` in spec.json) trades vector cleanliness
    for SVG file size. Below the threshold, each cell is its own <rect> — sharp
    at any zoom. Above, the whole image is encoded as base64 PNG.

    Row 0 is rendered at the TOP of the data rectangle. With plotlet's standard
    Cartesian y-axis (small y at bottom), this means image row 0 lands at the
    LARGEST y value of `extent`. Users coming from matplotlib's `origin='upper'`
    convention should know: the image looks correct (matrix as printed), but
    the y-axis tick labels read in Cartesian order.
    """
    nrows = a["_nrows"]; ncols = a["_ncols"]
    if nrows == 0 or ncols == 0:
        return ""
    data = a["_data"]
    vmin = a["_vmin"]; vmax = a["_vmax"]
    span = (vmax - vmin) or 1.0
    lut = colormap_lut(a["opts"].get("cmap", _D["default_cmap"]))

    extent = a["opts"].get("extent")
    if extent is None:
        x_left, x_right, y_bot, y_top = 0.0, float(ncols), 0.0, float(nrows)
    else:
        x_left, x_right, y_bot, y_top = extent

    sx_l = xs_(min(x_left, x_right)); sx_r = xs_(max(x_left, x_right))
    sy_t = ys_(max(y_bot, y_top));    sy_b = ys_(min(y_bot, y_top))
    pw = sx_r - sx_l; ph = sy_b - sy_t
    if pw <= 0 or ph <= 0:
        return ""

    use_rects = nrows * ncols <= _D["imshow_max_rects"]

    if use_rects:
        out = []
        cw = pw / ncols; ch = ph / nrows
        for r in range(nrows):
            row = data[r]
            y = sy_t + r * ch
            for c in range(ncols):
                v = row[c]
                if v != v:
                    fill = "rgb(0,0,0)"
                else:
                    t = (v - vmin) / span
                    if t < 0: t = 0
                    elif t > 1: t = 1
                    i = int(t * 255 + 0.5) * 3
                    fill = f"rgb({lut[i]},{lut[i+1]},{lut[i+2]})"
                x = sx_l + c * cw
                out.append(
                    f'<rect x="{x:.3f}" y="{y:.3f}" width="{cw:.3f}" '
                    f'height="{ch:.3f}" fill="{fill}"/>')
        return "".join(out)

    buf = bytearray()
    for r in range(nrows):
        row = data[r]
        for c in range(ncols):
            v = row[c]
            if v != v:
                buf.append(0); buf.append(0); buf.append(0)
            else:
                t = (v - vmin) / span
                if t < 0: t = 0
                elif t > 1: t = 1
                i = int(t * 255 + 0.5) * 3
                buf.append(lut[i]); buf.append(lut[i+1]); buf.append(lut[i+2])
    png = encode_rgb(bytes(buf), ncols, nrows)
    b64 = base64.b64encode(png).decode("ascii")
    return (f'<image x="{sx_l:.3f}" y="{sy_t:.3f}" '
            f'width="{pw:.3f}" height="{ph:.3f}" '
            f'preserveAspectRatio="none" image-rendering="pixelated" '
            f'href="data:image/png;base64,{b64}"/>')


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
