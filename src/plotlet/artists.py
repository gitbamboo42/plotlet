"""Per-artist SVG-emit helpers, marker primitive, histogram binning.

Each `_artist_<type>` takes the recorded artist dict, the x and y scales,
and the resolved color, and returns an SVG fragment. They're called from
`core._render`.
"""
import base64
import math

from ._spec import _D
from .draw._png import encode_rgb
from .draw.colormaps import colormap_lut, _ContinuousNorm
from .draw.colors import _resolve_color
from .draw import (text_path, marker, op,
                    segment, rect as draw_rect, path as draw_path,
                    polygon as draw_polygon, errorbar_v, errorbar_h)
from .utils import to_list, to_list_2d, histogram


# ---------------------------------------------------------------------------
# Artist helpers
# ---------------------------------------------------------------------------

_CURVE_VALUES = ("linear", "step-before", "step-after", "step-mid")


def _step_coords(xs, ys, mode):
    """Interleave (xs, ys) into step-shaped coordinates.

    `mode` is one of 'before' | 'after' | 'mid'. NaN values pass through
    unchanged — the path-building stage breaks the stroke at them, so
    gaps don't get bridged by a phantom step."""
    n = len(xs)
    if n < 2:
        return list(xs), list(ys)
    out_x = [xs[0]]
    out_y = [ys[0]]
    for i in range(1, n):
        x0, x1 = xs[i - 1], xs[i]
        y0, y1 = ys[i - 1], ys[i]
        if mode == "before":
            out_x.append(x0); out_y.append(y1)
        elif mode == "after":
            out_x.append(x1); out_y.append(y0)
        else:  # mid
            mid = (x0 + x1) / 2
            out_x.append(mid); out_y.append(y0)
            out_x.append(mid); out_y.append(y1)
        out_x.append(x1); out_y.append(y1)
    return out_x, out_y


def _artist_line(a, xs_, ys_, col):
    out = []
    opts = a["opts"]
    alpha = opts.get("alpha", 1)
    curve = opts.get("curve", "linear")
    if curve not in _CURVE_VALUES:
        raise ValueError(
            f"unknown curve={curve!r}; expected one of {_CURVE_VALUES}"
        )
    # Path coordinates depend on the curve mode; markers always sit at
    # the original data points, so we keep two coordinate lists.
    if curve == "linear":
        path_xs, path_ys = a["xs"], a["ys"]
    else:
        path_xs, path_ys = _step_coords(a["xs"], a["ys"], curve[5:])
    path_pts = [(xs_(x), ys_(y)) for x, y in zip(path_xs, path_ys)]
    path_pts = [(px, py) if (math.isfinite(px) and math.isfinite(py)) else None
                for px, py in path_pts]
    d_segs, started = [], False
    for p in path_pts:
        if p is None:
            started = False
            continue
        d_segs.append(f'{"M" if not started else "L"}{p[0]:.2f},{p[1]:.2f}')
        started = True
    ls = opts.get("linestyle")
    if ls not in ("", "none"):
        out.append(draw_path("".join(d_segs), stroke=col,
                             stroke_width=opts.get("linewidth", _D["linewidth"]),
                             dash=ls, alpha=alpha))
    if opts.get("marker"):
        sz = opts.get("markersize", _D["markersize"])
        for x, y in zip(a["xs"], a["ys"]):
            px, py = xs_(x), ys_(y)
            if not (math.isfinite(px) and math.isfinite(py)):
                continue
            out.append(marker(opts["marker"], px, py, sz, col, alpha))
    return "".join(out)


def _artist_scatter(a, xs_, ys_, col):
    opts = a["opts"]
    raw_s = opts.get("s", _D["scatter_s"])
    raw_mk = opts.get("marker", "o")
    alpha = opts.get("alpha", _D["scatter_alpha"])
    n = len(a["xs"])
    # `s` and `marker` accept either a scalar (one value for every point)
    # or a per-point sequence (size=/style= mappings produce the list form).
    sizes   = list(raw_s)  if isinstance(raw_s,  (list, tuple)) else [raw_s]  * n
    markers = list(raw_mk) if isinstance(raw_mk, (list, tuple)) else [raw_mk] * n
    out = []
    for i, (x, y) in enumerate(zip(a["xs"], a["ys"])):
        px, py = xs_(x), ys_(y)
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        sz = math.sqrt(sizes[i]) / 2
        out.append(marker(markers[i], px, py, sz, col, alpha))
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
                   f'height="{abs(y - y0):.2f}" fill="{col}"{op(alpha)}{crisp}/>')
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
        out.append(draw_rect(x0, y, w, h, fill=col, alpha=alpha))
    return "".join(out)


def _artist_axhline(a, xs_, ys_, iw, ih, col):
    opts = a["opts"]
    y = ys_(a["y"])
    if not math.isfinite(y) or y < 0 or y > ih:
        return ""
    x0 = iw * opts.get("xmin", 0.0)
    x1 = iw * opts.get("xmax", 1.0)
    return segment(x0, y, x1, y,
                   color=col,
                   width=opts.get("linewidth", _D["refline_width"]),
                   dash=opts.get("linestyle"),
                   alpha=opts.get("alpha", 1))


def _artist_axvline(a, xs_, ys_, iw, ih, col):
    opts = a["opts"]
    x = xs_(a["x"])
    if not math.isfinite(x) or x < 0 or x > iw:
        return ""
    y0 = ih * (1 - opts.get("ymax", 1.0))
    y1 = ih * (1 - opts.get("ymin", 0.0))
    return segment(x, y0, x, y1,
                   color=col,
                   width=opts.get("linewidth", _D["refline_width"]),
                   dash=opts.get("linestyle"),
                   alpha=opts.get("alpha", 1))


def _artist_hlines(a, xs_, ys_, col):
    opts = a["opts"]
    lw = opts.get("linewidth", _D["refline_width"])
    ls = opts.get("linestyle")
    alpha = opts.get("alpha", 1)
    out = []
    for y, x0, x1 in zip(a["ys"], a["xmins"], a["xmaxs"]):
        py = ys_(y); px0 = xs_(x0); px1 = xs_(x1)
        if not (math.isfinite(py) and math.isfinite(px0) and math.isfinite(px1)):
            continue
        out.append(segment(px0, py, px1, py, color=col, width=lw,
                           dash=ls, alpha=alpha))
    return "".join(out)


def _artist_vlines(a, xs_, ys_, col):
    opts = a["opts"]
    lw = opts.get("linewidth", _D["refline_width"])
    ls = opts.get("linestyle")
    alpha = opts.get("alpha", 1)
    out = []
    for x, y0, y1 in zip(a["xs"], a["ymins"], a["ymaxs"]):
        px = xs_(x); py0 = ys_(y0); py1 = ys_(y1)
        if not (math.isfinite(px) and math.isfinite(py0) and math.isfinite(py1)):
            continue
        out.append(segment(px, py0, px, py1, color=col, width=lw,
                           dash=ls, alpha=alpha))
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
    return draw_rect(x0, y0, x1 - x0, y1 - y0, fill=col,
                     alpha=opts.get("alpha", _D["refspan_alpha"]))


def _artist_axvspan(a, xs_, ys_, iw, ih, col):
    opts = a["opts"]
    x_a = xs_(a["xmin"]); x_b = xs_(a["xmax"])
    x0 = max(0.0, min(iw, min(x_a, x_b)))
    x1 = max(0.0, min(iw, max(x_a, x_b)))
    if x1 - x0 <= 0:
        return ""
    y0 = ih * (1 - opts.get("ymax", 1.0))
    y1 = ih * (1 - opts.get("ymin", 0.0))
    return draw_rect(x0, y0, x1 - x0, y1 - y0, fill=col,
                     alpha=opts.get("alpha", _D["refspan_alpha"]))


def _artist_fill_between(a, xs_, ys_, col):
    opts = a["opts"]
    curve = opts.get("curve", "linear")
    if curve not in _CURVE_VALUES:
        raise ValueError(
            f"unknown curve={curve!r}; expected one of {_CURVE_VALUES}"
        )
    # Apply step interleaving to both edges so the polygon zips correctly
    # — for constant baselines (area) this still interleaves x-coords,
    # which the upper edge needs to pair with.
    if curve == "linear":
        upper_xs, upper_ys = a["xs"], a["y1"]
        lower_xs, lower_ys = a["xs"], a["y2"]
    else:
        mode = curve[5:]
        upper_xs, upper_ys = _step_coords(a["xs"], a["y1"], mode)
        lower_xs, lower_ys = _step_coords(a["xs"], a["y2"], mode)
    upper = [(xs_(x), ys_(y)) for x, y in zip(upper_xs, upper_ys)]
    lower = [(xs_(x), ys_(y)) for x, y in zip(lower_xs, lower_ys)]
    pts = upper + list(reversed(lower))
    return draw_polygon(pts, fill=col,
                        alpha=opts.get("alpha", _D["fill_alpha"]))


def _fill_stroke_params(a, ctx_color):
    """Shared edge/fill resolution for rect and polygon. Returns a kwargs
    dict ready to splat into `draw.rect` / `draw.polygon`.
    `fill=False` switches the fill off entirely; `edgecolor=` overrides the
    artist color for the outline; `linewidth=` controls outline width
    (default spec linewidth)."""
    opts = a["opts"]
    do_fill = opts.get("fill", True)
    edge = opts.get("edgecolor")
    lw = opts.get("linewidth", _D["linewidth"])
    alpha = opts.get("alpha", _D["bar_alpha"])
    if edge is not None:
        stroke = _resolve_color(edge)
    elif not do_fill:
        # No fill and no explicit edge: draw the outline in the artist color
        # so the shape is visible at all (matplotlib's `fill=False` idiom).
        stroke = ctx_color
    else:
        stroke = None
    return {"fill": ctx_color if do_fill else None,
            "stroke": stroke,
            "stroke_width": lw,
            # `fill=False` means a transparent shape with an opaque outline —
            # never apply the fill-alpha to the stroke.
            "alpha": alpha if do_fill else 1}


def _artist_rect(a, xs_, ys_, col):
    """Scale-aware axis-aligned rectangles. `xs`, `ys`, `ws`, `hs` are
    pre-broadcast to a common length in `record`. Each rect spans
    `(x, y) -> (x + w, y + h)` in data coords; pixel-space sign is fixed
    up so flipped y-axes (imshow origin='upper') still render correctly."""
    params = _fill_stroke_params(a, col)
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
        out.append(draw_rect(x_l, y_t, pw, ph, **params))
    return "".join(out)


def _artist_polygon(a, xs_, ys_, col):
    """Closed polygon from `(xs, ys)` vertices. Always emits a closed path
    (trailing `Z`) — matches matplotlib's `plt.fill()` which auto-closes."""
    pts = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["ys"])]
    pts = [(px, py) for px, py in pts if math.isfinite(px) and math.isfinite(py)]
    return draw_polygon(pts, **_fill_stroke_params(a, col))


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


# Marker primitive lives in `plotlet.draw.marker` (imported above).


# ---------------------------------------------------------------------------
# text — data-anchored labels via bundled DejaVu Sans (font-independent)
# ---------------------------------------------------------------------------

_HA_TO_ANCHOR = {"left": "start", "center": "middle", "right": "end"}


def _artist_annotate(a, xs_, ys_, col):
    """Text label at `xytext`, optionally connected to `xy` by an arrow.

    Pixel placement and arrow geometry both run through the panel's
    scales — the user gives data coordinates, we draw in pixels. The
    arrowhead is a small filled triangle; the line stops at the head's
    base so the seam doesn't show through anti-aliasing.
    """
    opts = a["opts"]
    fontsize = opts.get("fontsize", _D["text_size"])
    ha = opts.get("ha", "left")
    va = opts.get("va", "baseline")
    color = opts.get("color") or col or _D["text_color"]
    anchor = _HA_TO_ANCHOR.get(ha, "start")
    if va == "top":      va_offset = fontsize * 0.78
    elif va == "center": va_offset = fontsize * 0.34
    elif va == "bottom": va_offset = 0.0
    else:                va_offset = 0.0

    x_xy, y_xy = a["xy"]
    x_tx, y_tx = a["xytext"]
    px_xy, py_xy = xs_(x_xy), ys_(y_xy)
    px_tx, py_tx = xs_(x_tx), ys_(y_tx)
    if not all(math.isfinite(v) for v in (px_xy, py_xy, px_tx, py_tx)):
        return ""

    out = []
    if opts.get("arrow", True):
        head_len = opts.get("arrow_head", 7.0)
        line_w = opts.get("arrow_width", 0.9)
        dx, dy = px_xy - px_tx, py_xy - py_tx
        dist = math.hypot(dx, dy)
        if dist > head_len:
            ux, uy = dx / dist, dy / dist
            # Line stops at the back of the arrowhead.
            line_end_x = px_xy - ux * head_len
            line_end_y = py_xy - uy * head_len
            out.append(segment(px_tx, py_tx, line_end_x, line_end_y,
                                color=color, width=line_w))
            # Triangular head: tip at xy, base perpendicular to the line.
            half = head_len * 0.45
            base_cx = line_end_x
            base_cy = line_end_y
            perp_x, perp_y = -uy, ux
            x1 = base_cx + perp_x * half
            y1 = base_cy + perp_y * half
            x2 = base_cx - perp_x * half
            y2 = base_cy - perp_y * half
            out.append(f'<path d="M{px_xy:.2f},{py_xy:.2f}L{x1:.2f},{y1:.2f}'
                       f'L{x2:.2f},{y2:.2f}Z" fill="{color}"/>')
    out.append(text_path(a["text"], px_tx, py_tx + va_offset,
                          fontsize, anchor=anchor, color=color))
    return "".join(out)


def _artist_text(a, xs_, ys_, col):
    """Render text labels at data coordinates. Accepts parallel
    `xs` / `ys` / `labels` lists. Empty labels are skipped."""
    opts = a["opts"]
    fontsize = opts.get("fontsize", _D["text_size"])
    ha = opts.get("ha", "left")
    va = opts.get("va", "baseline")
    color = opts.get("color") or col or _D["text_color"]
    dx = opts.get("dx", 0)
    dy = opts.get("dy", 0)
    anchor = _HA_TO_ANCHOR.get(ha, "start")
    # va offset on top of the SVG baseline. Cap-height of DejaVu ≈ 0.7 * size;
    # x-height ≈ 0.5. These constants give visually-centered placement for
    # the three common va values without measuring per-glyph metrics.
    if va == "top":
        va_offset = fontsize * 0.78
    elif va == "center":
        va_offset = fontsize * 0.34
    elif va == "bottom":
        va_offset = 0.0
    else:  # baseline
        va_offset = 0.0
    out = []
    for x, y, s in zip(a["xs"], a["ys"], a["labels"]):
        if s is None or s == "":
            continue
        px = xs_(x) + dx
        py = ys_(y) + dy + va_offset
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        out.append(text_path(str(s), px, py, fontsize, anchor=anchor, color=color))
    return "".join(out)


# ---------------------------------------------------------------------------
# errorbar — points with vertical/horizontal error bars and optional caps
# ---------------------------------------------------------------------------

def _expand_err(err, n):
    """Normalize an error-spec into (lower, upper) lists of length n.
    Accepts scalar, list/array, or a 2-tuple (lower, upper) for asymmetric."""
    if err is None:
        return [0.0] * n, [0.0] * n
    if isinstance(err, tuple) and len(err) == 2:
        lo = to_list(err[0]); hi = to_list(err[1])
        if len(lo) == 1: lo = lo * n
        if len(hi) == 1: hi = hi * n
        return lo, hi
    if hasattr(err, "__iter__") and not isinstance(err, str):
        v = to_list(err)
        return list(v), list(v)
    return [float(err)] * n, [float(err)] * n


def _artist_errorbar(a, xs_, ys_, col):
    xs, ys, opts = a["xs"], a["ys"], a["opts"]
    n = len(xs)
    xlo, xhi = _expand_err(opts.get("xerr"), n)
    ylo, yhi = _expand_err(opts.get("yerr"), n)
    capsize = opts.get("capsize", _D["errorbar_capsize"])
    lw = opts.get("linewidth", _D["errorbar_linewidth"])
    mk = opts.get("marker", "o")
    msize = opts.get("markersize", _D["markersize"])
    alpha = opts.get("alpha", 1)
    out = []
    for x, y, dxl, dxh, dyl, dyh in zip(xs, ys, xlo, xhi, ylo, yhi):
        px = xs_(x); py = ys_(y)
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        if dyl or dyh:
            out.append(errorbar_v(px, ys_(y - dyl), ys_(y + dyh),
                                  capsize=capsize, color=col, width=lw, alpha=alpha))
        if dxl or dxh:
            out.append(errorbar_h(py, xs_(x - dxl), xs_(x + dxh),
                                  capsize=capsize, color=col, width=lw, alpha=alpha))
        if mk:
            out.append(marker(mk, px, py, msize, col, alpha))
    return "".join(out)
