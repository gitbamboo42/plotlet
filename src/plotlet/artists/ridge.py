"""Ridgeline / joyplot — stacked, vertically-offset KDE curves.

Seaborn's deprecated `kdeplot(..., multiple="stack")` and R's
`ggridges::geom_density_ridges`. Each series gets its own baseline on y;
densities are KDE-shaped via a Gaussian kernel. Handy for showing
distributions across many groups.

The whole stack is rendered as one artist so it owns its own y-baselines.
Categories are placed at integer y; densities are scaled to a fraction of
the row spacing.

API (long-form only):
  c.ridge(data=df, x="label", y="value")
  c.ridge(data=df, x="label", y="value", color="cohort")  # overlaid
                                                          # sub-densities
                                                          # per row

Aesthetics:
  color=         literal fill color OR column name → one overlaid KDE per
                 level within each row (ggridges fill= second factor)
  palette=       maps levels → colors when `color=` is a column

Styling kwargs:
  overlap=1.4    height of each ridge as a fraction of row spacing
                 (>1 lets neighbouring ridges overlap)
  bw=None        bandwidth override; defaults to Silverman's rule
  n_grid=200     KDE evaluation grid resolution
  alpha=0.6      fill opacity
"""
from ..registry import ArtistSpec, add_artist
from ..draw import coord, path, rect, text_path
from .._spec import _LEGSPEC
from ..utils import silverman_bw, kde_1d, categorical_groups, resolve_aes
from ._shared import group_color


def _ridge_record(args, kw):
    if args:
        raise TypeError(
            "ridge requires long-form input: "
            "c.ridge(data=df, x='label', y='value')."
        )
    data = kw.pop("data", None)
    x = kw.pop("x", None)
    y = kw.pop("y", None)
    if data is None or x is None or y is None:
        raise TypeError("ridge requires data=, x=, y=.")
    color = kw.pop("color", None)
    color_kind, color_value = resolve_aes(data, color)
    group_col = color if color_kind == "column" else None
    if color_kind == "literal" and color_value is not None:
        kw["color"] = color_value
    labels, groups, vals = categorical_groups(data, x, y, group_col)
    return {"type": "ridge", "labels": labels, "groups": groups,
            "vals": vals, "opts": kw}


def _ridge_xdomain(a):
    return [v for row in a["vals"] for g in row for v in g]


def _ridge_ydomain(a):
    n = len(a["labels"])
    overlap = a["opts"].get("overlap", 1.4)
    return [0, n - 1 + overlap]


def _ridge_draw(a, ctx):
    opts = a["opts"]
    groups = a["groups"]
    palette = opts.get("palette")
    fill_alpha = opts.get("alpha", 0.6)
    overlap = opts.get("overlap", 1.4)
    n_grid = opts.get("n_grid", 200)
    flat = [v for row in a["vals"] for g in row for v in g]
    if not flat:
        return ""
    lo, hi = min(flat), max(flat)
    pad = (hi - lo) * 0.05 or 1.0
    lo -= pad; hi += pad
    grid = [lo + (hi - lo) * i / (n_grid - 1) for i in range(n_grid)]
    out = []
    n = len(a["labels"])
    for i, (label, row) in enumerate(zip(a["labels"], a["vals"])):
        if not any(row):
            continue
        # One KDE per sub-group, normalized by the row's tallest peak so
        # overlaid sub-densities stay height-comparable within the row.
        dens = []
        for vals in row:
            if not vals:
                dens.append(None)
                continue
            bw = opts.get("bw") or silverman_bw(vals)
            dens.append(kde_1d(vals, grid, bw))
        peaks = [max(d) for d in dens if d is not None]
        dmax = (max(peaks) if peaks else 0) or 1.0
        baseline_y = n - 1 - i
        y_base = ctx.y_scale(baseline_y)
        x_right = ctx.x_scale(grid[-1])
        x_left = ctx.x_scale(grid[0])
        for j, d in enumerate(dens):
            if d is None:
                continue
            col = group_color(groups, palette, j, ctx.color)
            pts = []
            for gx, dy in zip(grid, d):
                px = ctx.x_scale(gx)
                py = ctx.y_scale(baseline_y + (dy / dmax) * overlap)
                pts.append(f"{coord(px)},{coord(py)}")
            path_d = ("M" + " L".join(pts)
                      + f" L{coord(x_right)},{coord(y_base)} L{coord(x_left)},{coord(y_base)} Z")
            out.append(path(path_d, fill=col, stroke=col, stroke_width=1,
                            fill_alpha=fill_alpha, stroke_alpha=1))
        out.append(text_path(label, ctx.x_scale(lo) + 4,
                             ctx.y_scale(baseline_y) - 3, 11, anchor="start"))
    return "".join(out)


def _ridge_legend_entries(a):
    groups = a["groups"]
    if groups == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    fill_alpha = opts.get("alpha", 0.6)
    sw = _LEGSPEC["swatch_width"]
    entries = []
    for j, g in enumerate(groups):
        col = group_color(groups, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return rect(x0, y_mid - 5, sw, 10, fill=_col, alpha=fill_alpha)
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="ridge",
    record=_ridge_record,
    xdomain=_ridge_xdomain,
    ydomain=_ridge_ydomain,
    draw=_ridge_draw,
    legend_entries=_ridge_legend_entries,
    uses_color_cycle=True,
))
