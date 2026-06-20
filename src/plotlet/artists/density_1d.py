"""1-D Gaussian KDE curve — the bin-free alternative to histogram.

Where `hist` answers "how many in each bin?", `density_1d` answers
"what's the smoothed distribution shape?" — bin-free, scaled so the
area integrates to 1 so you can overlay multiple groups fairly.

  c.density_1d(data=df, x="col")                      # long-form
  c.density_1d(data=df, x="col", color="group")       # one curve per group

Aesthetics:
  color=         line color (literal) or column name → grouped curves
  fill=False     True shades the area under each curve in the line color
  palette=       maps group levels → colors when `color=` is a column

Other styling kwargs:
  bw=None        bandwidth override; defaults to Silverman's rule
  n_grid=200     KDE evaluation grid resolution
  alpha=0.25     fill opacity (used only when fill=True)
  linewidth=1.6  curve stroke width
  label=None     legend label (single-series only)
"""
from ..registry import ArtistSpec, add_artist
from ..utils import (to_list, long_form_1d, resolve_aes, palette_color,
                     silverman_bw, kde_1d)
from ..draw import TAB10, resolve_color
from .._spec import _LEGSPEC
from ..draw import coord, path, polyline, segment


def _density_1d_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "density_1d requires long-form input: "
            "c.density_1d(data=df, x='col')."
        )
    data_df = kw.pop("data", None)
    x_col = kw.pop("x", None)
    if data_df is None or x_col is None:
        raise TypeError(
            "density_1d requires data=, x= (color= optional)."
        )
    color = kw.pop("color", None)
    color_kind, color_value = resolve_aes(data_df, color)
    group_col = color if color_kind == "column" else None
    groups, vals = long_form_1d(data_df, x_col, group_col)
    if color_kind == "literal" and color_value is not None:
        kw["_color_literal"] = color_value
    n_grid = kw.get("n_grid", 200)
    bw_kw = kw.get("bw")
    all_vals = [v for g in vals for v in g]
    if not all_vals:
        return {"type": "density_1d", "groups": groups,
                "_grids": [[] for _ in vals], "_ds": [[] for _ in vals],
                "opts": kw}
    lo, hi = min(all_vals), max(all_vals)
    pad = (hi - lo) * 0.1 or 1.0
    lo -= pad; hi += pad
    grid = [lo + (hi - lo) * i / (n_grid - 1) for i in range(n_grid)]
    grids = []
    ds = []
    for g in vals:
        if not g:
            grids.append([]); ds.append([])
            continue
        bw = bw_kw or silverman_bw(g)
        grids.append(grid)
        ds.append(kde_1d(g, grid, bw))
    return {"type": "density_1d", "groups": groups,
            "_grids": grids, "_ds": ds, "opts": kw}


def _density_1d_xdomain(a):
    return [v for g in a["_grids"] for v in g]


def _density_1d_ydomain(a):
    return [v for d in a["_ds"] for v in d] + [0]


def _group_color(groups, palette, j, fallback):
    if groups == [None]:
        return fallback
    return palette_color(palette, groups[j], j) or TAB10[j % 10]


def _density_1d_draw(a, ctx):
    palette = a["opts"].get("palette")
    lw = a["opts"].get("linewidth", 1.6)
    fill_flag = a["opts"].get("fill", False)
    alpha = a["opts"].get("alpha", 0.25)
    color_literal = resolve_color(a["opts"].get("_color_literal"))
    fallback = color_literal if color_literal is not None else ctx.color
    out = []
    for j, (grid, d) in enumerate(zip(a["_grids"], a["_ds"])):
        if not grid: continue
        col = _group_color(a["groups"], palette, j, fallback)
        pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(grid, d)]
        if fill_flag and pts:
            y0 = ctx.y_scale(0)
            d_path = ("M" + " L".join(f"{coord(x)},{coord(y)}" for x, y in pts)
                      + f" L{coord(pts[-1][0])},{coord(y0)} L{coord(pts[0][0])},{coord(y0)} Z")
            out.append(path(d_path, fill=col, alpha=alpha))
        out.append(polyline(pts, color=col, width=lw))
    return "".join(out)


def _density_1d_legend_entries(a):
    groups = a["groups"]
    opts = a["opts"]
    lw = opts.get("linewidth", 1.6)
    sw = _LEGSPEC["swatch_width"]
    if groups == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(_a, _ctx, x0, y_mid):
            col = _a.get("_color", _ctx.color)
            return segment(x0, y_mid, x0 + sw, y_mid, color=col, width=lw)
        return [{"label": label, "color": None, "paint": paint}]
    palette = opts.get("palette")
    entries = []
    for j, g in enumerate(groups):
        col = _group_color(groups, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return segment(x0, y_mid, x0 + sw, y_mid, color=_col, width=lw)
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="density_1d",
    record=_density_1d_record,
    xdomain=_density_1d_xdomain,
    ydomain=_density_1d_ydomain,
    draw=_density_1d_draw,
    legend_entries=_density_1d_legend_entries,
    force_zero_y=True,
))
