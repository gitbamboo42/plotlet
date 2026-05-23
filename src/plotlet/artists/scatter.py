"""Scatter — single-series xy.

  c.scatter(xs, ys)                                       # wide-form
  c.scatter(data=df, x="col_x", y="col_y")                # long-form
  c.scatter(data=df, x="col_x", y="col_y", color="g")     # one color per level
  c.scatter(data=df, ..., color="g", group="subject")     # invisible finer split
  c.scatter(data=df, ..., alpha="cohort",                 # opacity per level
            alphas=(0.3, 1.0))
  c.scatter(data=df, ..., size="mass", sizes=(10, 200))   # per-point area
  c.scatter(data=df, ..., style="group")                  # per-level marker glyph

Column-driven splitting (any of `color`/`group`/`alpha`) is handled at
the Chart layer — the artist itself always sees one series per record.
`size`/`style` are computed per-point and stay inside a single record.

The per-point `c=` (numeric → colormap) is wide-form-only — it conflicts
with column-driven `color=`.
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list
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
    return {"type": "scatter",
            "xs": to_list(args[0]), "ys": to_list(args[1]),
            "opts": dict(kw)}


def _scatter_xdomain(a): return a["xs"]
def _scatter_ydomain(a): return a["ys"]


def _scatter_data_attrs(a):
    xs, ys = a["xs"], a["ys"]
    out = {"n": len(xs)}
    out.update(_xy_minmax(xs, ys))
    out["marker"] = a["opts"].get("marker", "o")
    return out


def _scatter_draw(a, ctx):
    return _artist_scatter(a, ctx.x_scale, ctx.y_scale, ctx.color,
                           a["xs"], a["ys"])


def _scatter_legend_entries(a):
    opts = a["opts"]
    label = opts.get("label")
    if not label:
        return []
    sw = _LEGSPEC["swatch_width"]
    def paint(_a, _ctx, x0, y_mid):
        raw_s = opts.get("s", _ctx.defaults["scatter_s"])
        raw_mk = opts.get("marker", "o")
        s_val = (sorted(raw_s)[len(raw_s) // 2]
                 if isinstance(raw_s, (list, tuple)) and raw_s
                 else (raw_s if not isinstance(raw_s, (list, tuple))
                       else _ctx.defaults["scatter_s"]))
        mk_val = (raw_mk[0]
                  if isinstance(raw_mk, (list, tuple)) and raw_mk
                  else (raw_mk if not isinstance(raw_mk, (list, tuple)) else "o"))
        s_size = math.sqrt(s_val) / 2
        return marker(mk_val, x0 + sw / 2, y_mid, s_size, _a["_color"],
                      opts.get("alpha", _ctx.defaults["scatter_alpha"]))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


add_artist(ArtistSpec(
    name="scatter",
    record=_scatter_record,
    xdomain=_scatter_xdomain,
    ydomain=_scatter_ydomain,
    draw=_scatter_draw,
    legend_entries=_scatter_legend_entries,
    data_attrs=_scatter_data_attrs,
))
