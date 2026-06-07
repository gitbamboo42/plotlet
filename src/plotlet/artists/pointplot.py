"""Categorical point estimate + CI bar + connecting line. Seaborn's pointplot.

CI options:
  ci="t"     -> t-distribution CI on the mean (analytic; classic textbook bar).
  ci="boot"  -> percentile bootstrap CI (default 1 000 resamples). Works for
                any estimator.
  ci=None    -> no CI, just points and connectors.

API (long-form only):
  c.pointplot(data=df, x="cat", y="value")

Styling kwargs:
  estimator='mean'   'median' for the central tendency
  ci='t'             see above
  level=0.95         confidence level
  n_boot=1000        bootstrap resamples (ci='boot' only)
  seed=0             RNG seed for bootstrap
  size=4             point radius in pixels
  capsize=4          half-width of CI cap tick in pixels
  linewidth=1.4      line and bar stroke width
  label=None         legend label (no legend entry when absent)
"""
import math
import random

from scipy.stats import t as _t_dist

from ..registry import ArtistSpec, add_artist
from ..utils import categorical_groups
from ..draw import segment, circle, polyline, errorbar_v


def _t_ci_mean(vals, level):
    n = len(vals)
    if n < 2:
        m = vals[0] if vals else float("nan")
        return m, m
    m = sum(vals) / n
    var = sum((x - m) ** 2 for x in vals) / (n - 1)
    se = math.sqrt(var / n)
    crit = _t_dist.ppf((1 + level) / 2, n - 1)
    return m - crit * se, m + crit * se


def _bootstrap_ci(vals, estimator_fn, level, n_boot, rng):
    if not vals:
        return float("nan"), float("nan")
    n = len(vals)
    boots = [estimator_fn([vals[rng.randrange(n)] for _ in range(n)])
             for _ in range(n_boot)]
    boots.sort()
    alpha = (1 - level) / 2
    return (boots[max(0, int(alpha * n_boot))],
            boots[min(n_boot - 1, int((1 - alpha) * n_boot))])


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return float("nan")
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


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
    cats, _, vals = categorical_groups(data, x, y)
    groups = [v[0] for v in vals]  # one value-list per category (no sub-grouping)
    estimator = kw.get("estimator", "mean")
    ci = kw.get("ci", "t")
    level = kw.get("level", 0.95)
    n_boot = kw.get("n_boot", 1000)
    rng = random.Random(kw.get("seed", 0))
    est_fn = ((lambda xs: sum(xs) / len(xs) if xs else float("nan"))
              if estimator == "mean" else _median)
    ests = [est_fn(g) for g in groups]
    los, his = [], []
    for g in groups:
        if ci is None or not g:
            los.append(float("nan")); his.append(float("nan"))
        elif ci == "t" and estimator == "mean":
            lo, hi = _t_ci_mean(g, level)
            los.append(lo); his.append(hi)
        else:
            lo, hi = _bootstrap_ci(g, est_fn, level, n_boot, rng)
            los.append(lo); his.append(hi)
    return {"type": "pointplot", "cats": cats, "_ests": ests,
            "_los": los, "_his": his, "opts": kw}


def _pointplot_xdomain(a): return a["cats"]


def _pointplot_ydomain(a):
    out = list(a["_ests"])
    out += [v for v in a["_los"] if v == v]
    out += [v for v in a["_his"] if v == v]
    return out


def _pointplot_draw(a, ctx):
    col = ctx.color
    r = a["opts"].get("size", 4)
    capsize = a["opts"].get("capsize", 4)
    lw = a["opts"].get("linewidth", 1.4)
    out = []
    pts = []
    for cat, est, lo, hi in zip(a["cats"], a["_ests"], a["_los"], a["_his"]):
        if est != est:
            continue
        cx = ctx.x_scale(cat)
        py = ctx.y_scale(est)
        if lo == lo and hi == hi:
            out.append(errorbar_v(cx, ctx.y_scale(lo), ctx.y_scale(hi),
                                  capsize=capsize, color=col, width=lw))
        pts.append((cx, py))
    out.append(polyline(pts, color=col, width=lw))
    for x, y in pts:
        out.append(circle(x, y, r, fill=col))
    return "".join(out)


def _pointplot_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(_a, _ctx, _x0, _y_mid):
        col = _a.get("_color", _ctx.color)
        return (segment(_x0, _y_mid, _x0 + 22, _y_mid, color=col, width=1.4)
                + circle(_x0 + 11, _y_mid, 3, fill=col))
    return [{"label": label, "color": None, "paint": paint}]


add_artist(ArtistSpec(
    name="pointplot",
    record=_pointplot_record,
    xdomain=_pointplot_xdomain,
    ydomain=_pointplot_ydomain,
    draw=_pointplot_draw,
    legend_entries=_pointplot_legend_entries,
))
