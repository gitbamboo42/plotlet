"""1-D Gaussian KDE curve — the bin-free alternative to histogram.

Where `hist` answers "how many in each bin?", `density_1d` answers
"what's the smoothed distribution shape?" — bin-free, scaled so the
area integrates to 1 so you can overlay multiple groups fairly.

  c.density_1d(values)                                # wide-form
  c.density_1d(data=df, x="col")                      # long-form
  c.density_1d(data=df, x="col", hue="group")         # one curve per hue

Styling kwargs:
  bw=None        bandwidth override; defaults to Silverman's rule
  n_grid=200     KDE evaluation grid resolution
  fill=False     True shades the area under each curve
  alpha=0.25     fill opacity (used only when fill=True)
  linewidth=1.6  curve stroke width
  label=None     legend label (single-series only)
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list, long_form_1d, silverman_bw, kde_1d, hue_color
from .._spec import _LEGSPEC
from ..draw import path, polyline, segment


def _density_1d_record(args, kw):
    kw = dict(kw)
    if "data" in kw or "x" in kw or "y" in kw:
        data_df = kw.pop("data", None)
        x_col = kw.pop("x", None)
        hue_col = kw.pop("hue", None)
        if data_df is None or x_col is None:
            raise TypeError(
                "density_1d long-form requires data=, x= (hue= optional)."
            )
        hues, groups = long_form_1d(data_df, x_col, hue_col)
    else:
        hues = [None]
        groups = [to_list(args[0])]
    n_grid = kw.get("n_grid", 200)
    bw_kw = kw.get("bw")
    all_vals = [v for g in groups for v in g]
    if not all_vals:
        return {"type": "density_1d", "hues": hues,
                "_grids": [[] for _ in groups], "_ds": [[] for _ in groups],
                "opts": kw}
    lo, hi = min(all_vals), max(all_vals)
    pad = (hi - lo) * 0.1 or 1.0
    lo -= pad; hi += pad
    grid = [lo + (hi - lo) * i / (n_grid - 1) for i in range(n_grid)]
    grids = []
    ds = []
    for g in groups:
        if not g:
            grids.append([]); ds.append([])
            continue
        bw = bw_kw or silverman_bw(g)
        grids.append(grid)
        ds.append(kde_1d(g, grid, bw))
    return {"type": "density_1d", "hues": hues,
            "_grids": grids, "_ds": ds, "opts": kw}


def _density_1d_xdomain(a):
    return [v for g in a["_grids"] for v in g]


def _density_1d_ydomain(a):
    return [v for d in a["_ds"] for v in d] + [0]


def _density_1d_draw(a, ctx):
    palette = a["opts"].get("palette")
    lw = a["opts"].get("linewidth", 1.6)
    fill = a["opts"].get("fill", False)
    alpha = a["opts"].get("alpha", 0.25)
    out = []
    for j, (grid, d) in enumerate(zip(a["_grids"], a["_ds"])):
        if not grid: continue
        col = hue_color(a["hues"], palette, j, ctx.color)
        pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(grid, d)]
        if fill and pts:
            y0 = ctx.y_scale(0)
            d_path = ("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
                      + f" L{pts[-1][0]:.2f},{y0:.2f} L{pts[0][0]:.2f},{y0:.2f} Z")
            out.append(path(d_path, fill=col, alpha=alpha))
        out.append(polyline(pts, color=col, width=lw))
    return "".join(out)


def _density_1d_legend_entries(a):
    hues = a["hues"]
    opts = a["opts"]
    lw = opts.get("linewidth", 1.6)
    sw = _LEGSPEC["swatch_width"]
    if hues == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(_a, _ctx, x0, y_mid):
            col = _a.get("_color", _ctx.color)
            return segment(x0, y_mid, x0 + sw, y_mid, color=col, width=lw)
        return [{"label": label, "color": None, "paint": paint}]
    palette = opts.get("palette")
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return segment(x0, y_mid, x0 + sw, y_mid, color=_col, width=lw)
        entries.append({"label": str(h), "color": col, "paint": paint})
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
