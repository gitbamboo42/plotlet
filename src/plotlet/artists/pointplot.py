"""Categorical point estimate + CI bar + connecting line. Seaborn's pointplot.

CI options:
  ci="t"     -> t-distribution CI on the mean (analytic; classic textbook bar).
  ci="boot"  -> percentile bootstrap CI (default 1 000 resamples). Works for
                any estimator.
  ci=None    -> no CI, just points and connectors.

API (long-form only):
  c.pointplot(data=df, x="cat", y="value")
  c.pointplot(data=df, x="cat", y="value", color="group")   # one series per level

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
from ..utils import (categorical_groups, resolve_aes, quantile,
                     t_ci_mean, bootstrap_ci)
from ..draw import segment, circle, polyline, errorbar_v
from ._shared import group_color


def _pointplot_record(args, kw):
    if args:
        raise TypeError(
            "pointplot requires long-form input: "
            "c.pointplot(data=df, x='col', y='col')."
        )
    data = kw.pop("data", None)
    x = kw.pop("x", None)
    y = kw.pop("y", None)
    if data is None or x is None or y is None:
        raise TypeError("pointplot requires data=, x=, y=.")
    color = kw.pop("color", None)
    color_kind, color_value = resolve_aes(data, color)
    group_col = color if color_kind == "column" else None
    if color_kind == "literal" and color_value is not None:
        kw["color"] = color_value
    cats, groups, vals = categorical_groups(data, x, y, group_col)
    estimator = kw.get("estimator", "mean")
    ci = kw.get("ci", "t")
    level = kw.get("level", 0.95)
    n_boot = kw.get("n_boot", 1000)
    rng = random.Random(kw.get("seed", 0))
    est_fn = ((lambda xs: sum(xs) / len(xs) if xs else float("nan"))
              if estimator == "mean" else (lambda xs: quantile(xs, 0.5)))
    ests = [[est_fn(vals[i][j]) for i in range(len(cats))]
            for j in range(len(groups))]
    los = [[None] * len(cats) for _ in groups]
    his = [[None] * len(cats) for _ in groups]
    for j in range(len(groups)):
        for i in range(len(cats)):
            g = vals[i][j]
            if ci is None or not g:
                los[j][i] = float("nan"); his[j][i] = float("nan")
            elif ci == "t" and estimator == "mean":
                los[j][i], his[j][i] = t_ci_mean(g, level)
            else:
                los[j][i], his[j][i] = bootstrap_ci(g, est_fn, level,
                                                    n_boot, rng)
    return {"type": "pointplot", "cats": cats, "groups": groups,
            "_ests": ests, "_los": los, "_his": his, "opts": kw}


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
