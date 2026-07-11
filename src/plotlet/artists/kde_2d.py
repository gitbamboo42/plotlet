"""2-D Gaussian KDE iso-density contours from a scatter sample.

Estimates a smooth 2-D density from (xs, ys) using a separable Gaussian kernel
on a regular grid, then draws iso-density contours via marching squares. The
visual cousin of hexbin for smaller, smoother samples.

Differs from the cookbook contour recipe, which expects a pre-computed 2-D
scalar grid. Here the grid is estimated from data.

API: c.kde_2d(data=df, x='col', y='col')

Aesthetics:
  color=             literal contour color OR column name → one density
                     per level, single-colored (seaborn kdeplot hue)
  palette=           maps levels → colors when `color=` is a column

Styling kwargs:
  n_grid=60          KDE evaluation grid resolution (n × n)
  bw=None            bandwidth override; defaults to Silverman's rule per axis
  levels=None        list of iso-density levels; defaults to 5 quantile levels
  fill=False         True fills the level regions (seaborn kdeplot fill=True)
                     instead of stroking iso-lines
  cmap=None          colormap name for coloring contours by level
                     (mutually exclusive with column-driven color=)
  alpha=None         fill opacity (fill=True only); defaults to 1 with cmap,
                     0.25 for a single-color fill so levels stack visibly
  linewidth=1.2      contour stroke width
"""
import math

from ..registry import ArtistSpec, add_artist
from ..draw import segment, rect
from ..draw import colormap, ContinuousNorm
from ..draw import TAB10
from .._spec import _LEGSPEC
from ..utils import to_list, silverman_bw, resolve_aes, long_form_xy
from ._marching import MS_CASES as _MS_CASES
from ._marching import edge_pt as _edge_pt
from ._marching import filled_levels_svg


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


def _resolve_levels(grid, opts):
    """Resolve `levels` once at record time so draw and legend_gradient
    share a single source of truth. Mirrors the historical lazy fallback
    (5 fixed quantile-style fractions of grid max)."""
    levels = opts.get("levels")
    if levels is not None:
        return list(levels)
    flat = [v for row in grid for v in row]
    if not flat:
        return []
    vmax = max(flat)
    return [vmax * f for f in (0.1, 0.25, 0.5, 0.75, 0.9)]


def _kde_2d_build(xs, ys, kw):
    """One estimated-density record from a materialized (xs, ys) sample."""
    n_grid = kw.get("n_grid", 60)
    if not xs:
        return {"type": "kde_2d", "_xs": xs, "_ys": ys, "_grid": [],
                "_levels": [], "opts": kw}
    bw = kw.get("bw")
    bw_x = bw if bw else silverman_bw(xs)
    bw_y = bw if bw else silverman_bw(ys)
    x_lo = min(xs) - 3 * bw_x; x_hi = max(xs) + 3 * bw_x
    y_lo = min(ys) - 3 * bw_y; y_hi = max(ys) + 3 * bw_y
    grid = _kde2d_grid(xs, ys, n_grid, bw_x, bw_y, x_lo, x_hi, y_lo, y_hi)
    levels = _resolve_levels(grid, kw)
    record = {"type": "kde_2d", "_xs": xs, "_ys": ys, "_grid": grid,
              "_extent": (x_lo, x_hi, y_lo, y_hi),
              "_levels": levels, "opts": kw}
    if levels:
        record["_vmin"] = min(levels)
        record["_vmax"] = max(levels)
    return record


def _kde_2d_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "kde_2d requires long-form input: "
            "c.kde_2d(data=df, x='col', y='col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    if data is None or x_col is None or y_col is None:
        raise TypeError("kde_2d requires data=, x=, y=.")
    color = kw.pop("color", None)
    color_kind, color_value = resolve_aes(data, color)
    palette = kw.pop("palette", None)
    if color_kind == "column":
        if kw.get("cmap"):
            raise TypeError(
                "kde_2d: cmap= colors contours by density level; with "
                "color= column grouping each group is single-colored — "
                "pass palette= instead."
            )
        groups, xy = long_form_xy(data, x_col, y_col, color)
        records = []
        for j, (g, (xs, ys)) in enumerate(zip(groups, xy)):
            opts = dict(kw)
            opts["palette"] = palette
            opts["label"] = str(g)
            rec = _kde_2d_build(xs, ys, opts)
            rec["groups"] = groups
            rec["_j"] = j
            records.append(rec)
        return records
    if color_value is not None:
        kw["color"] = color_value
    xs = to_list(data[x_col])
    ys = to_list(data[y_col])
    return _kde_2d_build(xs, ys, kw)


def _kde_2d_xdomain(a): return a["_xs"]
def _kde_2d_ydomain(a): return a["_ys"]


def _kde_2d_draw(a, ctx):
    g = a["_grid"]
    if not g:
        return ""
    n = len(g)
    levels = a["_levels"]
    if not levels:
        return ""
    cmap_name = a["opts"].get("cmap")
    color_opt = a["opts"].get("color")
    lw = a["opts"].get("linewidth", 1.2)
    if cmap_name:
        cm = colormap(cmap_name)
        norm = ContinuousNorm(a["_vmin"], a["_vmax"], "linear")
    x0, x1, y0, y1 = a["_extent"]
    dxd = (x1 - x0) / (n - 1)
    dyd = (y1 - y0) / (n - 1)
    if a["opts"].get("fill"):
        alpha = a["opts"].get("alpha", 1.0 if cmap_name else 0.25)
        return filled_levels_svg(
            g, n, n, levels, cmap_name=cmap_name,
            color=color_opt or ctx.color or TAB10[0], alpha=alpha,
            x0d=x0, y0d=y0, dxd=dxd, dyd=dyd,
            x_scale=ctx.x_scale, y_scale=ctx.y_scale)
    out = []
    for lvl in levels:
        if cmap_name:
            r, gn, b = cm(norm.to_unit(lvl))
            col = f"rgb({r},{gn},{b})"
        else:
            col = color_opt or ctx.color or TAB10[0]
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


def _kde_2d_legend_gradient(a):
    """Describe kde_2d's continuous level→color mapping when `cmap=` is
    set — None otherwise so a non-cmap kde_2d (single fallback color)
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


def _kde_2d_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    sw = _LEGSPEC["swatch_width"]
    if a["opts"].get("fill"):
        alpha = a["opts"].get("alpha", 0.25)
        def paint(_a, _ctx, x0, y_mid):
            col = _a.get("_color", _ctx.color)
            return rect(x0, y_mid - 5, sw, 10, fill=col, alpha=alpha)
    else:
        lw = a["opts"].get("linewidth", 1.2)
        def paint(_a, _ctx, x0, y_mid):
            col = _a.get("_color", _ctx.color)
            return segment(x0, y_mid, x0 + sw, y_mid, color=col, width=lw)
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


add_artist(ArtistSpec(
    name="kde_2d",
    record=_kde_2d_record,
    xdomain=_kde_2d_xdomain,
    ydomain=_kde_2d_ydomain,
    draw=_kde_2d_draw,
    legend_entries=_kde_2d_legend_entries,
    legend_gradient=_kde_2d_legend_gradient,
    uses_color_cycle=False,
    default_color=TAB10[0],
))
