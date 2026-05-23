"""Scatter — single-series xy or long-form with optional hue split.

  c.scatter(xs, ys)                                       # wide-form
  c.scatter(data=df, x="col_x", y="col_y")                # long-form
  c.scatter(data=df, x="col_x", y="col_y", hue="group")   # one colour per hue

The per-point `c=`, `s=`, `marker=` mappings are wide-form-only — they
conflict with hue-based colouring.
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list, hue_color
from ..draw import marker
from ..draw.colormaps import colormap_lut, _ContinuousNorm
from .._spec import _D, _LEGSPEC
from ._shared import _xy_minmax


def _artist_scatter(a, xs_, ys_, col, xs, ys):
    opts = a["opts"]
    raw_s = opts.get("s", _D["scatter_s"])
    raw_mk = opts.get("marker", "o")
    alpha = opts.get("alpha", _D["scatter_alpha"])
    edgecolor = opts.get("edgecolor")
    linewidth = opts.get("linewidth")
    c_vals = opts.get("c")
    n = len(xs)
    sizes   = list(raw_s)  if isinstance(raw_s,  (list, tuple)) else [raw_s]  * n
    markers = list(raw_mk) if isinstance(raw_mk, (list, tuple)) else [raw_mk] * n

    if c_vals is not None:
        cmap_name = opts.get("cmap", _D["default_cmap"])
        lut = colormap_lut(cmap_name)
        numeric = [v for v in c_vals if isinstance(v, (int, float)) and v == v]
        vmin = opts.get("vmin")
        vmax = opts.get("vmax")
        if vmin is None: vmin = min(numeric) if numeric else 0.0
        if vmax is None: vmax = max(numeric) if numeric else 1.0
        normalizer = _ContinuousNorm(vmin, vmax, kind=opts.get("norm", "linear"))
        point_colors = []
        for v in c_vals:
            if not (isinstance(v, (int, float)) and v == v):
                point_colors.append("rgb(0,0,0)")
            else:
                idx = int(normalizer.to_unit(v) * 255 + 0.5) * 3
                point_colors.append(f"rgb({lut[idx]},{lut[idx+1]},{lut[idx+2]})")
    else:
        point_colors = [col] * n

    out = []
    for i, (x, y) in enumerate(zip(xs, ys)):
        px, py = xs_(x), ys_(y)
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        sz = math.sqrt(sizes[i]) / 2
        out.append(marker(markers[i], px, py, sz, point_colors[i], alpha,
                          edgecolor=edgecolor, edgewidth=linewidth))
    return "".join(out)


def _scatter_record(args, kw):
    # Long-form is handled at the Chart layer (`Chart.scatter` resolves
    # data/x/y/hue → per-hue records); the artist only sees wide-form.
    return {"type": "scatter", "hues": [None],
            "groups": [(to_list(args[0]), to_list(args[1]))], "opts": dict(kw)}


def _scatter_xdomain(a):
    return [x for xs, _ in a["groups"] for x in xs]


def _scatter_ydomain(a):
    return [y for _, ys in a["groups"] for y in ys]


def _scatter_data_attrs(a):
    xs = [x for xs, _ in a["groups"] for x in xs]
    ys = [y for _, ys in a["groups"] for y in ys]
    out = {"n": len(xs)}
    out.update(_xy_minmax(xs, ys))
    out["marker"] = a["opts"].get("marker", "o")
    return out


def _scatter_draw(a, ctx):
    palette = a["opts"].get("palette")
    out = []
    for j, (xs, ys) in enumerate(a["groups"]):
        col = hue_color(a["hues"], palette, j, ctx.color)
        out.append(_artist_scatter(a, ctx.x_scale, ctx.y_scale, col, xs, ys))
    return "".join(out)


def _scatter_legend_entries(a):
    hues = a["hues"]
    opts = a["opts"]
    sw = _LEGSPEC["swatch_width"]
    if hues == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(a, ctx, x0, y_mid):
            raw_s = opts.get("s", ctx.defaults["scatter_s"])
            raw_mk = opts.get("marker", "o")
            s_val = (sorted(raw_s)[len(raw_s) // 2]
                     if isinstance(raw_s, (list, tuple)) and raw_s
                     else (raw_s if not isinstance(raw_s, (list, tuple))
                           else ctx.defaults["scatter_s"]))
            mk_val = (raw_mk[0]
                      if isinstance(raw_mk, (list, tuple)) and raw_mk
                      else (raw_mk if not isinstance(raw_mk, (list, tuple)) else "o"))
            s_size = math.sqrt(s_val) / 2
            return marker(mk_val, x0 + sw / 2, y_mid, s_size, a["_color"],
                          opts.get("alpha", ctx.defaults["scatter_alpha"]))
        return [{"label": label, "color": a.get("_color"), "paint": paint}]
    palette = opts.get("palette")
    alpha = opts.get("alpha", _D["scatter_alpha"])
    s_val = opts.get("s", _D["scatter_s"])
    mk_val = opts.get("marker", "o")
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return marker(mk_val, x0 + sw / 2, y_mid,
                          math.sqrt(s_val) / 2, _col, alpha)
        entries.append({"label": str(h), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="scatter",
    record=_scatter_record,
    xdomain=_scatter_xdomain,
    ydomain=_scatter_ydomain,
    draw=_scatter_draw,
    legend_entries=_scatter_legend_entries,
    data_attrs=_scatter_data_attrs,
))
