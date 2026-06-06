"""Contour-line isolines on a 2-D scalar grid via marching squares.

Pre-computed grid input — the companion to `kde_2d` (which estimates a
grid from data). The classic 2-D analytic-function viewer — useful for
posterior surfaces, energy landscapes, and 2-D KDE visualisations.

API: c.contour(grid, levels=[...], extent=(x0, x1, y0, y1))

`grid` is a 2-D nested list with shape (nrows, ncols). `levels` defaults
to 5 evenly-spaced values between grid min/max.

Styling kwargs:
  levels=None        list of iso-density level values
  extent=None        (x0, x1, y0, y1) data-space bounds; defaults to grid index
  cmap=None          colormap name for colouring lines by level
  color=None         single fallback colour when cmap is unset
  linewidth=1.2      contour stroke width
"""
from ..registry import ArtistSpec, add_artist
from ..draw import segment
from ..draw import colormap, ContinuousNorm
from ..utils import to_list_2d


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


def _resolve_levels(grid, opts):
    """Resolve `levels` once at record time so draw and legend_gradient
    share a single source of truth. Mirrors the historical lazy fallback
    (5 evenly-spaced between grid min/max)."""
    levels = opts.get("levels")
    if levels is not None:
        return list(levels)
    flat = [v for row in grid for v in row if v == v]
    if not flat:
        return []
    lo, hi = min(flat), max(flat)
    return [lo + (hi - lo) * i / 6 for i in range(1, 6)]


def _contour_record(args, kw):
    grid = to_list_2d(args[0])
    nrows = len(grid); ncols = len(grid[0]) if grid else 0
    levels = _resolve_levels(grid, kw)
    record = {"type": "contour", "grid": grid,
              "_nrows": nrows, "_ncols": ncols,
              "_levels": levels, "opts": kw}
    if levels:
        record["_vmin"] = min(levels)
        record["_vmax"] = max(levels)
    return record


def _contour_xdomain(a):
    ext = a["opts"].get("extent")
    if ext: return [ext[0], ext[1]]
    return [0, a["_ncols"] - 1]


def _contour_ydomain(a):
    ext = a["opts"].get("extent")
    if ext: return [ext[2], ext[3]]
    return [0, a["_nrows"] - 1]


def _contour_draw(a, ctx):
    grid = a["grid"]
    nr = a["_nrows"]; nc = a["_ncols"]
    levels = a["_levels"]
    if not levels:
        return ""
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
        cm = colormap(cmap_name)
        norm = ContinuousNorm(a["_vmin"], a["_vmax"], "linear")
    out = []
    for lvl in levels:
        if cmap_name:
            r, g, b = cm(norm.to_unit(lvl))
            col = f"rgb({r},{g},{b})"
        elif color_opt:
            col = color_opt
        else:
            col = ctx.color or "#1f77b4"
        for r in range(nr - 1):
            for c in range(nc - 1):
                vtl = grid[r][c]; vtr = grid[r][c + 1]
                vbr = grid[r + 1][c + 1]; vbl = grid[r + 1][c]
                code = ((1 if vtl >= lvl else 0)
                        | ((1 if vtr >= lvl else 0) << 1)
                        | ((1 if vbr >= lvl else 0) << 2)
                        | ((1 if vbl >= lvl else 0) << 3))
                for (e1, e2) in _MS_CASES.get(code, []):
                    p1 = _edge_pt(e1, r, c, vtl, vtr, vbr, vbl, lvl)
                    p2 = _edge_pt(e2, r, c, vtl, vtr, vbr, vbl, lvl)
                    x1 = x0d + p1[0] * dxd; y1 = y0d + p1[1] * dyd
                    x2 = x0d + p2[0] * dxd; y2 = y0d + p2[1] * dyd
                    out.append(segment(ctx.x_scale(x1), ctx.y_scale(y1),
                                       ctx.x_scale(x2), ctx.y_scale(y2),
                                       color=col, width=lw))
    return "".join(out)


def _contour_legend_gradient(a):
    """Describe contour's continuous level→color mapping when `cmap=` is
    set — None otherwise so a non-cmap contour (single fallback color)
    contributes nothing to the legend."""
    if not a["opts"].get("cmap") or not a.get("_levels"):
        return None
    legend_opts = a["opts"].get("legend") or {}
    return {
        "kind": "continuous",
        "cmap": a["opts"]["cmap"],
        "vmin": a["_vmin"],
        "vmax": a["_vmax"],
        "norm": "linear",
        "center": None,
        "label": legend_opts.get("label"),
        "ticks": legend_opts.get("ticks", a["_levels"]),
    }


add_artist(ArtistSpec(
    name="contour",
    record=_contour_record,
    xdomain=_contour_xdomain,
    ydomain=_contour_ydomain,
    draw=_contour_draw,
    legend_gradient=_contour_legend_gradient,
    uses_color_cycle=False,
    default_color="#1f77b4",
))
