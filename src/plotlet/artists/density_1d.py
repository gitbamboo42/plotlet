"""1-D Gaussian KDE curve — the bin-free alternative to histogram. Seaborn's kdeplot.

Where `hist` answers "how many in each bin?", `density_1d` answers "what's the
smoothed distribution shape?" — bin-free, scaled so the area integrates to 1
so you can overlay multiple groups fairly.

API: c.density_1d(values)

Styling kwargs:
  bw=None        bandwidth override; defaults to Silverman's rule
  n_grid=200     KDE evaluation grid resolution
  fill=False     True shades the area under the curve
  alpha=0.25     fill opacity (used only when fill=True)
  linewidth=1.6  curve stroke width
  label=None     legend label (no legend entry when absent)
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list, silverman_bw, kde_1d
from ..draw import path, polyline, segment


def _density_1d_record(args, kw):
    vals = to_list(args[0])
    n_grid = kw.get("n_grid", 200)
    bw = kw.get("bw") or silverman_bw(vals)
    if not vals:
        return {"type": "density_1d", "_grid": [], "_d": [], "opts": kw}
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.1 or 1.0
    lo -= pad; hi += pad
    grid = [lo + (hi - lo) * i / (n_grid - 1) for i in range(n_grid)]
    d = kde_1d(vals, grid, bw)
    return {"type": "density_1d", "_grid": grid, "_d": d, "opts": kw}


def _density_1d_xdomain(a): return a["_grid"]
def _density_1d_ydomain(a): return list(a["_d"]) + [0]


def _density_1d_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.6)
    fill = a["opts"].get("fill", False)
    alpha = a["opts"].get("alpha", 0.25)
    out = []
    pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(a["_grid"], a["_d"])]
    if fill and pts:
        y0 = ctx.y_scale(0)
        d = ("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
             + f" L{pts[-1][0]:.2f},{y0:.2f} L{pts[0][0]:.2f},{y0:.2f} Z")
        out.append(path(d, fill=col, alpha=alpha))
    out.append(polyline(pts, color=col, width=lw))
    return "".join(out)


def _density_1d_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(_a, _ctx, _x0, _y_mid):
        col = _a.get("_color", _ctx.color)
        return segment(_x0, _y_mid, _x0 + 22, _y_mid, color=col, width=1.6)
    return [{"label": label, "color": None, "paint": paint}]


add_artist(ArtistSpec(
    name="density_1d",
    record=_density_1d_record,
    xdomain=_density_1d_xdomain,
    ydomain=_density_1d_ydomain,
    draw=_density_1d_draw,
    legend_entries=_density_1d_legend_entries,
    force_zero_y=True,
))
