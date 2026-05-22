"""2-D Gaussian KDE iso-density contours from a scatter sample.

Estimates a smooth 2-D density from (xs, ys) using a separable Gaussian kernel
on a regular grid, then draws iso-density contours via marching squares. The
visual cousin of hexbin for smaller, smoother samples.

Differs from the cookbook contour recipe, which expects a pre-computed 2-D
scalar grid. Here the grid is estimated from data.

API: c.kde_2d(xs, ys)

Styling kwargs:
  n_grid=60          KDE evaluation grid resolution (n × n)
  bw=None            bandwidth override; defaults to Silverman's rule per axis
  levels=None        list of iso-density levels; defaults to 5 quantile levels
  cmap=None          colormap name for coloring contours by level
  color='#1f77b4'    fallback contour color when cmap is not set
  linewidth=1.2      contour stroke width
"""
import math

from ..registry import ArtistSpec, add_artist
from ..draw import segment
from ..draw.colormaps import colormap, _ContinuousNorm
from ..utils import to_list, silverman_bw


_MS_CASES = {
    0: [], 15: [],
    1: [(0, 3)], 14: [(0, 3)],
    2: [(0, 1)], 13: [(0, 1)],
    3: [(1, 3)], 12: [(1, 3)],
    4: [(1, 2)], 11: [(1, 2)],
    5: [(0, 3), (1, 2)], 10: [(0, 1), (2, 3)],
    6: [(0, 2)], 9: [(0, 2)],
    7: [(2, 3)], 8: [(2, 3)],
}


def _kde2d_grid(xs, ys, n_grid, bw_x, bw_y, x_lo, x_hi, y_lo, y_hi):
    grid = [[0.0] * n_grid for _ in range(n_grid)]
    inv = 1.0 / (2 * math.pi * bw_x * bw_y * max(len(xs), 1))
    dx = (x_hi - x_lo) / (n_grid - 1) if n_grid > 1 else 1.0
    dy = (y_hi - y_lo) / (n_grid - 1) if n_grid > 1 else 1.0
    for x, y in zip(xs, ys):
        for i in range(n_grid):
            gy = y_lo + i * dy
            ey = (gy - y) / bw_y
            ey2 = -0.5 * ey * ey
            for j in range(n_grid):
                gx = x_lo + j * dx
                ex = (gx - x) / bw_x
                grid[i][j] += math.exp(ey2 - 0.5 * ex * ex)
    return [[v * inv for v in row] for row in grid]


def _edge_pt(edge, r, c, vtl, vtr, vbr, vbl, lvl):
    if edge == 0:
        t = (lvl - vtl) / (vtr - vtl) if vtr != vtl else 0.5
        return (c + t, r)
    if edge == 1:
        t = (lvl - vtr) / (vbr - vtr) if vbr != vtr else 0.5
        return (c + 1, r + t)
    if edge == 2:
        t = (lvl - vbl) / (vbr - vbl) if vbr != vbl else 0.5
        return (c + t, r + 1)
    t = (lvl - vtl) / (vbl - vtl) if vbl != vtl else 0.5
    return (c, r + t)



def _kde_2d_record(args, kw):
    xs = to_list(args[0])
    ys = to_list(args[1])
    n_grid = kw.get("n_grid", 60)
    if not xs:
        return {"type": "kde_2d", "_xs": xs, "_ys": ys, "_grid": [], "opts": kw}
    bw = kw.get("bw")
    bw_x = bw if bw else silverman_bw(xs)
    bw_y = bw if bw else silverman_bw(ys)
    x_lo = min(xs) - 3 * bw_x; x_hi = max(xs) + 3 * bw_x
    y_lo = min(ys) - 3 * bw_y; y_hi = max(ys) + 3 * bw_y
    grid = _kde2d_grid(xs, ys, n_grid, bw_x, bw_y, x_lo, x_hi, y_lo, y_hi)
    return {"type": "kde_2d", "_xs": xs, "_ys": ys, "_grid": grid,
            "_extent": (x_lo, x_hi, y_lo, y_hi), "opts": kw}


def _kde_2d_xdomain(a): return a["_xs"]
def _kde_2d_ydomain(a): return a["_ys"]


def _kde_2d_draw(a, ctx):
    g = a["_grid"]
    if not g:
        return ""
    n = len(g)
    levels = a["opts"].get("levels")
    flat = [v for row in g for v in row]
    if levels is None:
        vmax = max(flat)
        levels = [vmax * f for f in (0.1, 0.25, 0.5, 0.75, 0.9)]
    cmap_name = a["opts"].get("cmap")
    color_opt = a["opts"].get("color")
    lw = a["opts"].get("linewidth", 1.2)
    if cmap_name:
        cm = colormap(cmap_name)
        norm = _ContinuousNorm(min(levels), max(levels), "linear")
    x0, x1, y0, y1 = a["_extent"]
    dxd = (x1 - x0) / (n - 1)
    dyd = (y1 - y0) / (n - 1)
    out = []
    for lvl in levels:
        if cmap_name:
            r, gn, b = cm(norm.to_unit(lvl))
            col = f"rgb({r},{gn},{b})"
        else:
            col = color_opt or ctx.color or "#1f77b4"
        for r in range(n - 1):
            for c in range(n - 1):
                vtl = g[r][c]; vtr = g[r][c + 1]
                vbr = g[r + 1][c + 1]; vbl = g[r + 1][c]
                code = ((1 if vtl >= lvl else 0)
                        | ((1 if vtr >= lvl else 0) << 1)
                        | ((1 if vbr >= lvl else 0) << 2)
                        | ((1 if vbl >= lvl else 0) << 3))
                for (e1, e2) in _MS_CASES.get(code, []):
                    p1 = _edge_pt(e1, r, c, vtl, vtr, vbr, vbl, lvl)
                    p2 = _edge_pt(e2, r, c, vtl, vtr, vbr, vbl, lvl)
                    px1 = ctx.x_scale(x0 + p1[0] * dxd)
                    py1 = ctx.y_scale(y0 + p1[1] * dyd)
                    px2 = ctx.x_scale(x0 + p2[0] * dxd)
                    py2 = ctx.y_scale(y0 + p2[1] * dyd)
                    out.append(segment(px1, py1, px2, py2, color=col, width=lw))
    return "".join(out)


add_artist(ArtistSpec(
    name="kde_2d",
    record=_kde_2d_record,
    xdomain=_kde_2d_xdomain,
    ydomain=_kde_2d_ydomain,
    draw=_kde_2d_draw,
    uses_color_cycle=False,
    default_color="#1f77b4",
))
