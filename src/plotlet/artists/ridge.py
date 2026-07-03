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

Styling kwargs:
  overlap=1.4    height of each ridge as a fraction of row spacing
                 (>1 lets neighbouring ridges overlap)
  bw=None        bandwidth override; defaults to Silverman's rule
  n_grid=200     KDE evaluation grid resolution
  alpha=0.6      fill opacity
"""
from ..registry import ArtistSpec, add_artist
from ..draw import coord, path, text_path
from ..utils import silverman_bw, kde_1d, categorical_groups


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
    labels, _, vals = categorical_groups(data, x, y)
    groups = [v[0] for v in vals]  # one value-list per label (no sub-grouping)
    return {"type": "ridge", "labels": labels, "groups": groups, "opts": kw}


def _ridge_xdomain(a):
    return [v for g in a["groups"] for v in g]


def _ridge_ydomain(a):
    n = len(a["labels"])
    overlap = a["opts"].get("overlap", 1.4)
    return [0, n - 1 + overlap]


def _ridge_draw(a, ctx):
    col = ctx.color
    fill_alpha = a["opts"].get("alpha", 0.6)
    overlap = a["opts"].get("overlap", 1.4)
    n_grid = a["opts"].get("n_grid", 200)
    flat = [v for g in a["groups"] for v in g]
    if not flat:
        return ""
    lo, hi = min(flat), max(flat)
    pad = (hi - lo) * 0.05 or 1.0
    lo -= pad; hi += pad
    grid = [lo + (hi - lo) * i / (n_grid - 1) for i in range(n_grid)]
    out = []
    n = len(a["labels"])
    for i, (label, vals) in enumerate(zip(a["labels"], a["groups"])):
        if not vals:
            continue
        bw = a["opts"].get("bw") or silverman_bw(vals)
        d = kde_1d(vals, grid, bw)
        dmax = max(d) or 1.0
        baseline_y = n - 1 - i
        pts = []
        for gx, dy in zip(grid, d):
            px = ctx.x_scale(gx)
            py = ctx.y_scale(baseline_y + (dy / dmax) * overlap)
            pts.append(f"{coord(px)},{coord(py)}")
        x_right = ctx.x_scale(grid[-1])
        x_left = ctx.x_scale(grid[0])
        y_base = ctx.y_scale(baseline_y)
        path_d = ("M" + " L".join(pts)
                  + f" L{coord(x_right)},{coord(y_base)} L{coord(x_left)},{coord(y_base)} Z")
        out.append(path(path_d, fill=col, stroke=col, stroke_width=1,
                        fill_alpha=fill_alpha, stroke_alpha=1))
        out.append(text_path(label, ctx.x_scale(lo) + 4,
                             ctx.y_scale(baseline_y) - 3, 11, anchor="start"))
    return "".join(out)


add_artist(ArtistSpec(
    name="ridge",
    record=_ridge_record,
    xdomain=_ridge_xdomain,
    ydomain=_ridge_ydomain,
    draw=_ridge_draw,
    uses_color_cycle=True,
))
