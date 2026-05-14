"""Custom artist: pointplot.

Categorical x with a point at the group estimate and a vertical CI bar;
consecutive groups are connected so trends across an ordered category
set jump out. Seaborn's `pointplot`.

CI options:
  - `ci="t"`     -> t-distribution CI on the mean (analytic; the
                    classic textbook bar).
  - `ci="boot"`  -> percentile bootstrap CI (default 1 000 resamples).
                    Works for any estimator.
  - `ci=None`    -> no CI, just points and connectors.

API:
    c.pointplot(cats, values_per_cat,
                estimator="mean", ci="t", level=0.95, n_boot=1000,
                size=4, capsize=4)
"""

SUMMARY = "Categorical point estimate + analytic-t (or bootstrap) CI bar + connecting line."

import math
import random
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from scipy.stats import t as _t_dist


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
    s = sorted(xs); n = len(s)
    if n == 0: return float("nan")
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def pointplot_record(args, kw):
    cats = to_list(args[0])
    groups = [list(to_list(g)) for g in args[1]]
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
            lo, hi = _t_ci_mean(g, level); los.append(lo); his.append(hi)
        else:
            lo, hi = _bootstrap_ci(g, est_fn, level, n_boot, rng)
            los.append(lo); his.append(hi)
    return {"type": "pointplot", "cats": cats, "_ests": ests,
            "_los": los, "_his": his, "opts": kw}


def pointplot_xdomain(a): return a["cats"]


def pointplot_ydomain(a):
    out = list(a["_ests"])
    out += [v for v in a["_los"] if v == v]
    out += [v for v in a["_his"] if v == v]
    return out


def pointplot_draw(a, ctx):
    col = ctx.color
    r = a["opts"].get("size", 4)
    capsize = a["opts"].get("capsize", 4)
    lw = a["opts"].get("linewidth", 1.4)
    out = []
    pts = []
    for cat, est, lo, hi in zip(a["cats"], a["_ests"], a["_los"], a["_his"]):
        if est != est:
            continue
        cx = ctx.x_scale(cat); py = ctx.y_scale(est)
        if lo == lo and hi == hi:
            py_lo = ctx.y_scale(lo); py_hi = ctx.y_scale(hi)
            out.append(
                f'<line x1="{cx:.2f}" x2="{cx:.2f}" y1="{py_lo:.2f}" y2="{py_hi:.2f}" '
                f'stroke="{col}" stroke-width="{lw}"/>'
                f'<line x1="{cx - capsize / 2:.2f}" x2="{cx + capsize / 2:.2f}" '
                f'y1="{py_lo:.2f}" y2="{py_lo:.2f}" stroke="{col}" stroke-width="{lw}"/>'
                f'<line x1="{cx - capsize / 2:.2f}" x2="{cx + capsize / 2:.2f}" '
                f'y1="{py_hi:.2f}" y2="{py_hi:.2f}" stroke="{col}" stroke-width="{lw}"/>'
            )
        pts.append((cx, py))
    if len(pts) >= 2:
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{lw}"/>')
    for x, y in pts:
        out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{col}"/>')
    return "".join(out)


def pointplot_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    return (
        f'<line x1="{x0}" x2="{x0 + 22}" y1="{y_mid}" y2="{y_mid}" '
        f'stroke="{col}" stroke-width="1.4"/>'
        f'<circle cx="{x0 + 11}" cy="{y_mid}" r="3" fill="{col}"/>'
    )


pt.add_artist(pt.ArtistSpec(
    name="pointplot",
    record=pointplot_record,
    xdomain=pointplot_xdomain,
    ydomain=pointplot_ydomain,
    draw=pointplot_draw,
    legend_swatch=pointplot_legend_swatch,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    rng = random.Random(0)
    cats = ["1 wk", "2 wk", "4 wk", "8 wk", "12 wk"]
    control = [[rng.gauss(5 + 0.05 * i, 1.0) for _ in range(20)] for i in range(5)]
    drug    = [[rng.gauss(5 + 0.4 * i, 1.0) for _ in range(20)] for i in range(5)]
    c = pt.chart()
    c.xscale("category", order=cats)
    c.pointplot(cats, control, label="control")
    c.pointplot(cats, drug, label="drug")
    c.title("Response over time").xlabel("timepoint").ylabel("score").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
