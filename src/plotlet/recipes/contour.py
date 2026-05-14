"""Custom artist: contour lines on a 2-D grid.

Marching-squares isolines for a regular grid of scalar values. The
classic 2-D analytic-function viewer (matplotlib's `plt.contour`).
Useful for posterior surfaces, energy landscapes, and 2-D KDE
visualizations.

API:
    c.contour(grid, levels=[...], extent=(x0, x1, y0, y1), cmap=None,
              color="#1f77b4", linewidth=1.2)

`grid` is a 2-D nested-list with shape (nrows, ncols). `levels` is a
list of scalar threshold values; one line is drawn per level.
"""

SUMMARY = 'Contour-line isolines on a 2-D scalar grid via marching squares.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list_2d
from plotlet.draw.colormaps import colormap, _ContinuousNorm


# Marching squares lookup: which edges are crossed for each of the 16
# possible corner-classification cases. Edges are numbered 0=top, 1=right,
# 2=bottom, 3=left. Each case yields 0, 1, or 2 line segments as a list
# of (edge_a, edge_b) pairs.
_MS_CASES = {
    0: [], 15: [],
    1: [(3, 2)], 14: [(3, 2)],
    2: [(2, 1)], 13: [(2, 1)],
    3: [(3, 1)], 12: [(3, 1)],
    4: [(0, 1)], 11: [(0, 1)],
    5: [(3, 0), (2, 1)], 10: [(3, 2), (0, 1)],
    6: [(0, 2)], 9: [(0, 2)],
    7: [(3, 0)], 8: [(3, 0)],
}


def _interp(t, p1, p2):
    return p1 + t * (p2 - p1)


def _edge_point(edge, r, c, dx, dy, v_tl, v_tr, v_br, v_bl, lvl):
    """Pixel-coord (x, y) where `edge` crosses `lvl` in this cell."""
    if edge == 0:  # top: top-left to top-right
        t = (lvl - v_tl) / (v_tr - v_tl) if v_tr != v_tl else 0.5
        return (c + t, r)
    if edge == 1:  # right
        t = (lvl - v_tr) / (v_br - v_tr) if v_br != v_tr else 0.5
        return (c + 1, r + t)
    if edge == 2:  # bottom
        t = (lvl - v_bl) / (v_br - v_bl) if v_br != v_bl else 0.5
        return (c + t, r + 1)
    # edge == 3: left
    t = (lvl - v_tl) / (v_bl - v_tl) if v_bl != v_tl else 0.5
    return (c, r + t)


def contour_record(args, kw):
    grid = to_list_2d(args[0])
    nrows = len(grid); ncols = len(grid[0]) if grid else 0
    return {"type": "contour", "grid": grid, "_nrows": nrows, "_ncols": ncols,
            "opts": kw}


def contour_xdomain(a):
    ext = a["opts"].get("extent")
    if ext: return [ext[0], ext[1]]
    return [0, a["_ncols"] - 1]


def contour_ydomain(a):
    ext = a["opts"].get("extent")
    if ext: return [ext[2], ext[3]]
    return [0, a["_nrows"] - 1]


def contour_draw(a, ctx):
    grid = a["grid"]
    nr = a["_nrows"]; nc = a["_ncols"]
    flat = [v for row in grid for v in row if v == v]
    levels = a["opts"].get("levels")
    if levels is None:
        if not flat:
            return ""
        lo, hi = min(flat), max(flat)
        levels = [lo + (hi - lo) * i / 6 for i in range(1, 6)]
    color_opt = a["opts"].get("color")
    cmap_name = a["opts"].get("cmap")
    lw = a["opts"].get("linewidth", 1.2)
    ext = a["opts"].get("extent")
    if ext:
        x0d, x1d, y0d, y1d = ext
        dxd = (x1d - x0d) / max(nc - 1, 1)
        dyd = (y1d - y0d) / max(nr - 1, 1)
    else:
        x0d, y0d = 0, 0; dxd, dyd = 1, 1
    if cmap_name:
        cm = colormap(cmap_name); norm = _ContinuousNorm(min(levels), max(levels), "linear")
    out = []
    for li, lvl in enumerate(levels):
        if cmap_name:
            r, g, b = cm(norm.to_unit(lvl))
            col = f"rgb({r},{g},{b})"
        elif color_opt:
            col = color_opt
        else:
            col = ctx.color or "#1f77b4"
        for r in range(nr - 1):
            for c in range(nc - 1):
                v_tl = grid[r][c]; v_tr = grid[r][c + 1]
                v_br = grid[r + 1][c + 1]; v_bl = grid[r + 1][c]
                code = ((1 if v_tl >= lvl else 0) |
                        ((1 if v_tr >= lvl else 0) << 1) |
                        ((1 if v_br >= lvl else 0) << 2) |
                        ((1 if v_bl >= lvl else 0) << 3))
                for (e1, e2) in _MS_CASES.get(code, []):
                    p1 = _edge_point(e1, r, c, 1, 1, v_tl, v_tr, v_br, v_bl, lvl)
                    p2 = _edge_point(e2, r, c, 1, 1, v_tl, v_tr, v_br, v_bl, lvl)
                    # Map grid (col, row) -> data (x, y).
                    x1 = x0d + p1[0] * dxd; y1 = y0d + p1[1] * dyd
                    x2 = x0d + p2[0] * dxd; y2 = y0d + p2[1] * dyd
                    out.append(
                        f'<line x1="{ctx.x_scale(x1):.2f}" '
                        f'y1="{ctx.y_scale(y1):.2f}" '
                        f'x2="{ctx.x_scale(x2):.2f}" '
                        f'y2="{ctx.y_scale(y2):.2f}" '
                        f'stroke="{col}" stroke-width="{lw}"/>'
                    )
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="contour",
    record=contour_record,
    xdomain=contour_xdomain,
    ydomain=contour_ydomain,
    draw=contour_draw,
    uses_color_cycle=False,
    default_color="#1f77b4",
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import math
    # 2-D anisotropic Gaussian + small secondary peak.
    n = 60
    grid = []
    for i in range(n):
        row = []
        for j in range(n):
            x = -3 + 6 * j / (n - 1)
            y = -3 + 6 * i / (n - 1)
            v = (math.exp(-(x * x + 1.5 * y * y) / 2)
                 + 0.5 * math.exp(-((x - 1.5) ** 2 + (y + 1.5) ** 2) / 0.6))
            row.append(v)
        grid.append(row)
    c = pt.chart(data_width=320, data_height=320)
    c.contour(grid, extent=(-3, 3, -3, 3), cmap="viridis",
              levels=[0.05, 0.1, 0.2, 0.4, 0.6, 0.8])
    c.title("Contour plot").xlabel("x").ylabel("y")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
