import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from ..draw import marker
from ..draw.colormaps import colormap_lut, _ContinuousNorm
from .._spec import _D, _LEGSPEC
from ._shared import _xy_minmax


def _artist_scatter(a, xs_, ys_, col):
    opts = a["opts"]
    raw_s = opts.get("s", _D["scatter_s"])
    raw_mk = opts.get("marker", "o")
    alpha = opts.get("alpha", _D["scatter_alpha"])
    edgecolor = opts.get("edgecolor")
    linewidth = opts.get("linewidth")
    c_vals = opts.get("c")
    n = len(a["xs"])
    # `s` and `marker` accept either a scalar (one value for every point)
    # or a per-point sequence (size=/style= mappings produce the list form).
    sizes   = list(raw_s)  if isinstance(raw_s,  (list, tuple)) else [raw_s]  * n
    markers = list(raw_mk) if isinstance(raw_mk, (list, tuple)) else [raw_mk] * n

    # Per-point numeric color via colormap LUT. When `c=` is unset every
    # point uses the artist's single `col`; when set, each point's value
    # maps through `_ContinuousNorm` → LUT → rgb(...).
    if c_vals is not None:
        from ..draw.colormaps import colormap_lut, _ContinuousNorm
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
    for i, (x, y) in enumerate(zip(a["xs"], a["ys"])):
        px, py = xs_(x), ys_(y)
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        sz = math.sqrt(sizes[i]) / 2
        out.append(marker(markers[i], px, py, sz, point_colors[i], alpha,
                          edgecolor=edgecolor, edgewidth=linewidth))
    return "".join(out)


def _scatter_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["ys"]))
    out["marker"] = a["opts"].get("marker", "o")
    return out


def _scatter_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        # When `s` or `marker` is per-point (size=/style= mappings), the legend
        # swatch picks the median size and the first marker so the entry stays
        # a single recognizable glyph.
        raw_s = a["opts"].get("s", ctx.defaults["scatter_s"])
        raw_mk = a["opts"].get("marker", "o")
        s_val = sorted(raw_s)[len(raw_s) // 2] if isinstance(raw_s, (list, tuple)) and raw_s else (
            raw_s if not isinstance(raw_s, (list, tuple)) else ctx.defaults["scatter_s"])
        mk_val = raw_mk[0] if isinstance(raw_mk, (list, tuple)) and raw_mk else (
            raw_mk if not isinstance(raw_mk, (list, tuple)) else "o")
        s_size = math.sqrt(s_val) / 2
        return marker(mk_val, x0 + sw / 2, y_mid, s_size, a["_color"],
                      a["opts"].get("alpha", ctx.defaults["scatter_alpha"]))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


add_artist(ArtistSpec(
    name="scatter",
    record=lambda args, kw: {"type": "scatter", "xs": to_list(args[0]),
                              "ys": to_list(args[1]), "opts": kw},
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: a["ys"],
    draw=lambda a, ctx: _artist_scatter(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_scatter_legend_entries,
    data_attrs=_scatter_data_attrs,
))
