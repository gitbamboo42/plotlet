"""Per-artist SVG-emit helpers, marker primitive, histogram binning.

Each `_artist_<type>` takes the recorded artist dict, the x and y scales,
and the resolved color, and returns an SVG fragment. They're called from
`core._render`.
"""
import base64
import math

from ._spec import _D, _DASH
from ._png import encode_rgb
from .colormaps import colormap_lut, _ContinuousNorm
from .colors import _resolve_color


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


def _op(alpha):
    """SVG opacity attribute, omitted when fully opaque to keep output lean."""
    return "" if alpha == 1 else f' opacity="{alpha}"'


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
    alpha = opts.get("alpha", 1)
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
                   f'stroke-width="{opts.get("linewidth", _D["linewidth"])}"'
                   f'{_op(alpha)}{da}/>')
    if opts.get("marker"):
        sz = opts.get("markersize", _D["markersize"])
        for p in pts:
            if p is None:
                continue
            out.append(_marker_at(opts["marker"], p[0], p[1], sz, col, alpha))
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
    # padding=0 produces contiguous bands (heatmap track look). Adjacent
    # rects in SVG anti-alias their shared edge into a hairline gap;
    # shape-rendering="crispEdges" pixel-aligns the borders so the cells
    # really butt up. Skip it for normal bars where the visible inner
    # padding makes anti-aliased edges look smoother.
    crisp = ' shape-rendering="crispEdges"' if getattr(xs_, "padding", 0.2) == 0 else ''
    for c, v in zip(a["cats"], a["vals"]):
        x = xs_(c) - bw / 2
        y = ys_(v)
        out.append(f'<rect x="{x:.2f}" y="{min(y0, y):.2f}" width="{bw:.2f}" '
                   f'height="{abs(y - y0):.2f}" fill="{col}"{_op(alpha)}{crisp}/>')
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
                   f'fill="{col}"{_op(alpha)}/>')
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
            f'stroke="{col}" stroke-width="{lw}"{_op(alpha)}{da}/>')


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
            f'stroke="{col}" stroke-width="{lw}"{_op(alpha)}{da}/>')


def _broadcast(*vals):
    """Each input is scalar or list-like; broadcast to a common length.
    Length-1 lists broadcast like scalars; mismatched longer lengths raise."""
    arrs = []
    for v in vals:
        if hasattr(v, "__iter__") and not isinstance(v, str):
            arrs.append(_to_pylist(v))
        else:
            arrs.append([v])
    n = max(len(a) for a in arrs)
    out = []
    for a in arrs:
        if len(a) == 1:
            out.append(list(a) * n)
        elif len(a) == n:
            out.append(list(a))
        else:
            raise ValueError(f"cannot broadcast length {len(a)} to {n}")
    return out


def _artist_hlines(a, xs_, ys_, col):
    opts = a["opts"]
    lw = opts.get("linewidth", _D["refline_width"])
    ls = opts.get("linestyle")
    da = f' stroke-dasharray="{_DASH[ls]}"' if ls and _DASH.get(ls) else ""
    alpha = opts.get("alpha", 1)
    out = []
    for y, x0, x1 in zip(a["ys"], a["xmins"], a["xmaxs"]):
        py = ys_(y); px0 = xs_(x0); px1 = xs_(x1)
        if not (math.isfinite(py) and math.isfinite(px0) and math.isfinite(px1)):
            continue
        out.append(f'<line x1="{px0:.2f}" x2="{px1:.2f}" '
                   f'y1="{py:.2f}" y2="{py:.2f}" '
                   f'stroke="{col}" stroke-width="{lw}"{_op(alpha)}{da}/>')
    return "".join(out)


def _artist_vlines(a, xs_, ys_, col):
    opts = a["opts"]
    lw = opts.get("linewidth", _D["refline_width"])
    ls = opts.get("linestyle")
    da = f' stroke-dasharray="{_DASH[ls]}"' if ls and _DASH.get(ls) else ""
    alpha = opts.get("alpha", 1)
    out = []
    for x, y0, y1 in zip(a["xs"], a["ymins"], a["ymaxs"]):
        px = xs_(x); py0 = ys_(y0); py1 = ys_(y1)
        if not (math.isfinite(px) and math.isfinite(py0) and math.isfinite(py1)):
            continue
        out.append(f'<line x1="{px:.2f}" x2="{px:.2f}" '
                   f'y1="{py0:.2f}" y2="{py1:.2f}" '
                   f'stroke="{col}" stroke-width="{lw}"{_op(alpha)}{da}/>')
    return "".join(out)


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
            f'height="{y1 - y0:.2f}" fill="{col}"{_op(alpha)}/>')


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
            f'height="{y1 - y0:.2f}" fill="{col}"{_op(alpha)}/>')


def _artist_fill_between(a, xs_, ys_, col):
    upper = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["y1"])]
    lower = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["y2"])]
    pts = upper + list(reversed(lower))
    if not pts:
        return ""
    d = "M" + "L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts) + "Z"
    alpha = a["opts"].get("alpha", _D["fill_alpha"])
    return f'<path d="{d}" fill="{col}"{_op(alpha)}/>'


def _stroke_attrs(a, ctx_color):
    """Shared edge/fill resolution for rect and polygon. Returns
    `(fill_attr, stroke_attr)` — strings ready to splice into the SVG tag.
    `fill=False` switches the fill off entirely; `edgecolor=` overrides the
    artist color for the outline; `linewidth=` controls outline width
    (default spec linewidth)."""
    opts = a["opts"]
    fill = opts.get("fill", True)
    edge = opts.get("edgecolor")
    lw = opts.get("linewidth", _D["linewidth"])
    alpha = opts.get("alpha", _D["bar_alpha"])
    if fill:
        fill_attr = f'fill="{ctx_color}"{_op(alpha)}'
    else:
        fill_attr = 'fill="none"'
    if edge is not None:
        ec = _resolve_color(edge)
        stroke_attr = f' stroke="{ec}" stroke-width="{lw}"'
    elif not fill:
        # No fill and no explicit edge: draw the outline in the artist color
        # so the shape is visible at all (matplotlib's `fill=False` idiom).
        stroke_attr = f' stroke="{ctx_color}" stroke-width="{lw}"'
    else:
        stroke_attr = ''
    return fill_attr, stroke_attr


def _artist_rect(a, xs_, ys_, col):
    """Scale-aware axis-aligned rectangles. `xs`, `ys`, `ws`, `hs` are
    pre-broadcast to a common length in `record`. Each rect spans
    `(x, y) -> (x + w, y + h)` in data coords; pixel-space sign is fixed
    up so flipped y-axes (imshow origin='upper') still render correctly."""
    fill_attr, stroke_attr = _stroke_attrs(a, col)
    out = []
    for x, y, w, h in zip(a["xs"], a["ys"], a["ws"], a["hs"]):
        px0 = xs_(x); px1 = xs_(x + w)
        py0 = ys_(y); py1 = ys_(y + h)
        if not all(math.isfinite(v) for v in (px0, px1, py0, py1)):
            continue
        x_l = min(px0, px1); y_t = min(py0, py1)
        pw = abs(px1 - px0); ph = abs(py1 - py0)
        if pw <= 0 or ph <= 0:
            continue
        out.append(f'<rect x="{x_l:.2f}" y="{y_t:.2f}" width="{pw:.2f}" '
                   f'height="{ph:.2f}" {fill_attr}{stroke_attr}/>')
    return "".join(out)


def _artist_polygon(a, xs_, ys_, col):
    """Closed polygon from `(xs, ys)` vertices. Always emits a closed path
    (trailing `Z`) — matches matplotlib's `plt.fill()` which auto-closes."""
    pts = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["ys"])]
    pts = [(px, py) for px, py in pts if math.isfinite(px) and math.isfinite(py)]
    if len(pts) < 3:
        return ""
    fill_attr, stroke_attr = _stroke_attrs(a, col)
    d = "M" + "L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts) + "Z"
    return f'<path d="{d}" {fill_attr}{stroke_attr}/>'


def _artist_imshow(a, xs_, ys_, col):
    """2-D array → colored grid. Branches between many <rect>s and one PNG.

    The threshold (`imshow_max_rects` in spec.json) trades vector cleanliness
    for SVG file size. Below the threshold, each cell is its own <rect> — sharp
    at any zoom. Above, the whole image is encoded as base64 PNG.

    `origin` controls vertical orientation. Default `"lower"` puts row 0 at
    the BOTTOM of the data rectangle (Cartesian). Opt in to `"upper"` for
    matrix-style display (row 0 at top, what you see when you print the
    array); the panel auto-inverts the y-axis in that case so tick "0"
    lands next to row 0, matching matplotlib.

    Color mapping goes through `_ContinuousNorm`, which supports `norm="log"`
    and `center=` on top of the default linear range.
    """
    nrows = a["_nrows"]; ncols = a["_ncols"]
    if nrows == 0 or ncols == 0:
        return ""
    data = a["_data"]
    opts = a["opts"]
    norm = _ContinuousNorm(a["_vmin"], a["_vmax"],
                           kind=opts.get("norm", "linear"),
                           center=opts.get("center"))
    lut = colormap_lut(opts.get("cmap", _D["default_cmap"]))
    origin = opts.get("origin", "lower")

    extent = opts.get("extent")
    if extent is None:
        x_left, x_right, y_bot, y_top = 0.0, float(ncols), 0.0, float(nrows)
    else:
        x_left, x_right, y_bot, y_top = extent

    sxa = xs_(x_left); sxb = xs_(x_right)
    sya = ys_(y_bot);  syb = ys_(y_top)
    sx_l = min(sxa, sxb); sx_r = max(sxa, sxb)
    sy_t = min(sya, syb); sy_b = max(sya, syb)
    pw = sx_r - sx_l; ph = sy_b - sy_t
    if pw <= 0 or ph <= 0:
        return ""

    # Render order = order in which we walk pixel rows from top to bottom.
    # Default origin="lower": row 0 belongs at the bottom, so iterate
    # data in reverse to put the highest-index row at top first.
    # origin="upper": row 0 belongs at the top — natural data order.
    row_index = range(nrows) if origin == "upper" \
                else ((nrows - 1 - r) for r in range(nrows))
    rows_in_render_order = [data[i] for i in row_index]

    use_rects = nrows * ncols <= _D["imshow_max_rects"]

    if use_rects:
        out = []
        cw = pw / ncols; ch = ph / nrows
        for r, row in enumerate(rows_in_render_order):
            y = sy_t + r * ch
            for c in range(ncols):
                v = row[c]
                if v != v:
                    fill = "rgb(0,0,0)"
                else:
                    i = int(norm.to_unit(v) * 255 + 0.5) * 3
                    fill = f"rgb({lut[i]},{lut[i+1]},{lut[i+2]})"
                x = sx_l + c * cw
                out.append(
                    f'<rect x="{x:.3f}" y="{y:.3f}" width="{cw:.3f}" '
                    f'height="{ch:.3f}" fill="{fill}"/>')
        return "".join(out)

    buf = bytearray()
    for row in rows_in_render_order:
        for c in range(ncols):
            v = row[c]
            if v != v:
                buf.append(0); buf.append(0); buf.append(0)
            else:
                i = int(norm.to_unit(v) * 255 + 0.5) * 3
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
    op = _op(alpha)
    if marker == "o":
        return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size}" fill="{col}"{op}/>'
    if marker == "s":
        return (f'<rect x="{x - size:.2f}" y="{y - size:.2f}" width="{2 * size}" '
                f'height="{2 * size}" fill="{col}"{op}/>')
    if marker == "^":
        return (f'<path d="M{x:.2f},{y - size:.2f}L{x + size:.2f},{y + size:.2f}'
                f'L{x - size:.2f},{y + size:.2f}Z" fill="{col}"{op}/>')
    if marker == "v":
        return (f'<path d="M{x:.2f},{y + size:.2f}L{x + size:.2f},{y - size:.2f}'
                f'L{x - size:.2f},{y - size:.2f}Z" fill="{col}"{op}/>')
    if marker == "x":
        return (f'<path d="M{x - size:.2f},{y - size:.2f}L{x + size:.2f},{y + size:.2f}'
                f'M{x - size:.2f},{y + size:.2f}L{x + size:.2f},{y - size:.2f}" '
                f'stroke="{col}" stroke-width="{msw}"{op}/>')
    if marker == "+":
        return (f'<path d="M{x - size:.2f},{y:.2f}L{x + size:.2f},{y:.2f}'
                f'M{x:.2f},{y - size:.2f}L{x:.2f},{y + size:.2f}" '
                f'stroke="{col}" stroke-width="{msw}"{op}/>')
    return ""
