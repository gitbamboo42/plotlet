"""Categorical point estimate + CI bar + connecting line. Seaborn's pointplot.

CI options:
  ci="t"     -> t-distribution CI on the mean (analytic; classic textbook bar).
  ci="boot"  -> percentile bootstrap CI (default 1 000 resamples). Works for
                any estimator.
  ci=None    -> no CI, just points and connectors.

API (long-form only):
  c.add_pointplot(data=df, x="cat", y="value")
  c.add_pointplot(data=df, x="cat", y="value", color="group")   # one series per level

Aesthetics:
  color=             literal color OR column name → one series per level
  palette=           maps levels → colors when `color=` is a column

Styling kwargs:
  estimator='mean'   'median' for the central tendency
  ci='t'             see above
  level=0.95         confidence level
  n_boot=1000        bootstrap resamples (ci='boot' only)
  seed=0             RNG seed for bootstrap
  size=4             point radius in pixels
  capsize=4          half-width of CI cap tick in pixels
  linewidth=1.4      line and bar stroke width
  label=None         legend label (overridden by column-driven grouping)
"""
import random

from ..registry import ArtistSpec, add_artist
from ..utils import (pack_opts, categorical_groups, resolve_aes, quantile,
                     validate_ci, ci_bounds)
from ..draw import segment, circle, polyline, errorbar_v
from ..utils import group_color


def _pointplot_record(data=None,
                      # input & aggregation — consumed here at record
                      x=None, y=None, color=None,
                      estimator="mean", ci="t", level=0.95, n_boot=1000,
                      seed=0,
                      # style — packed into opts for the draw/legend side
                      size=None, capsize=None, linewidth=None,
                      palette=None, label=None, legend=None):
    if data is None or x is None or y is None:
        raise TypeError("pointplot requires data=, x=, y=.")
    color_kind, color_value = resolve_aes(data, color)
    group_col = color if color_kind == "column" else None
    opts = pack_opts(size=size, capsize=capsize, linewidth=linewidth,
                     palette=palette, label=label, legend=legend)
    if color_kind == "literal" and color_value is not None:
        opts["color"] = color_value
    cats, groups, vals = categorical_groups(data, x, y, group_col)
    validate_ci("pointplot", ci)
    rng = random.Random(seed)
    est_fn = ((lambda xs: sum(xs) / len(xs) if xs else float("nan"))
              if estimator == "mean" else (lambda xs: quantile(xs, 0.5)))
    ests = [[est_fn(vals[i][j]) for i in range(len(cats))]
            for j in range(len(groups))]
    # `vals` is cats-major; flatten group-major so bounds line up with
    # `_los[j][i]` (and the bootstrap RNG stream stays in j, i order).
    cells = [vals[i][j] for j in range(len(groups)) for i in range(len(cats))]
    flat_lo, flat_hi = ci_bounds(cells, est_fn, estimator,
                                 ci, level, n_boot, rng)
    n = len(cats)
    los = [flat_lo[j * n:(j + 1) * n] for j in range(len(groups))]
    his = [flat_hi[j * n:(j + 1) * n] for j in range(len(groups))]
    return {"type": "pointplot", "cats": cats, "groups": groups,
            "_ests": ests, "_los": los, "_his": his, "opts": opts}


def _pointplot_xdomain(a): return a["cats"]


def _pointplot_ydomain(a):
    out = [v for g in a["_ests"] for v in g]
    out += [v for g in a["_los"] for v in g if v == v]
    out += [v for g in a["_his"] for v in g if v == v]
    return out


def _pointplot_draw(a, ctx):
    opts = a["opts"]
    groups = a["groups"]
    palette = opts.get("palette")
    r = opts.get("size", 4)
    capsize = opts.get("capsize", 4)
    lw = opts.get("linewidth", 1.4)
    out = []
    for j in range(len(groups)):
        col = group_color(groups, palette, j, ctx.color)
        pts = []
        for cat, est, lo, hi in zip(a["cats"], a["_ests"][j],
                                    a["_los"][j], a["_his"][j]):
            if est != est:
                continue
            cx = ctx.x_scale(cat)
            py = ctx.y_scale(est)
            if lo == lo and hi == hi:
                out.append(errorbar_v(cx, ctx.y_scale(lo), ctx.y_scale(hi),
                                      capsize=capsize, color=col, width=lw,
                                      project=ctx.warp))
            pts.append((cx, py))
        out.append(polyline(pts, color=col, width=lw, project=ctx.warp))
        for x, y in pts:
            out.append(circle(x, y, r, fill=col, project=ctx.warp))
    return "".join(out)


def _pointplot_legend_entries(a):
    groups = a["groups"]
    opts = a["opts"]
    if groups == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(_a, _ctx, _x0, _y_mid):
            col = _a.get("_color", _ctx.color)
            return (segment(_x0, _y_mid, _x0 + 22, _y_mid, color=col, width=1.4)
                    + circle(_x0 + 11, _y_mid, 3, fill=col))
        return [{"label": label, "color": None, "paint": paint}]
    palette = opts.get("palette")
    entries = []
    for j, g in enumerate(groups):
        col = group_color(groups, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return (segment(x0, y_mid, x0 + 22, y_mid, color=_col, width=1.4)
                    + circle(x0 + 11, y_mid, 3, fill=_col))
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="pointplot",
    record=_pointplot_record,
    xdomain=_pointplot_xdomain,
    ydomain=_pointplot_ydomain,
    draw=_pointplot_draw,
    legend_entries=_pointplot_legend_entries,
))
