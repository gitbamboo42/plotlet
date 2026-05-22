"""OLS fit line plus Student-t confidence ribbon. ggplot2's geom_smooth(method='lm').

Fits y ~ x by closed-form OLS, draws the fit line, and shades a confidence
band using the exact Student-t critical value at n - 2 degrees of freedom.
The scatter is not drawn here — overlay your own `c.scatter(xs, ys)`.

API: c.regression(xs, ys)

Styling kwargs:
  level=0.95     confidence level for the band
  n_grid=80      grid resolution for evaluating the band
  alpha=0.2      ribbon fill opacity
  linewidth=1.8  fit line stroke width
  label=None     legend label (no legend entry when absent)

Math:
    slope b = Σ((x - x̄)(y - ȳ)) / Σ((x - x̄)²)
    intercept a = ȳ - b·x̄
    residual σ² = SSE / (n - 2)
    se(ŷ(x)) = σ · sqrt(1/n + (x - x̄)² / Σ(x - x̄)²)
    t · se for the band, t = t_{α/2, n-2}
"""
import math

from scipy.stats import t as _t_dist

from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from ..draw import polygon, polyline, rect, segment


def _fit_ols(xs, ys):
    n = len(xs)
    xm = sum(xs) / n
    ym = sum(ys) / n
    sxx = sum((x - xm) ** 2 for x in xs) or 1e-12
    sxy = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = ym - b * xm
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    sse = sum(r * r for r in resid)
    sigma2 = sse / max(n - 2, 1)
    return a, b, xm, sxx, math.sqrt(sigma2), n


def _regression_record(args, kw):
    xs = to_list(args[0])
    ys = to_list(args[1])
    a, b, xm, sxx, sigma, n = _fit_ols(xs, ys)
    return {"type": "regression", "xs": xs, "ys": ys,
            "_a": a, "_b": b, "_xm": xm, "_sxx": sxx,
            "_sigma": sigma, "_n": n, "opts": kw}


def _regression_xdomain(a): return a["xs"]


def _regression_ydomain(a):
    if not a["xs"]:
        return []
    level = a["opts"].get("level", 0.95)
    df = max(a["_n"] - 2, 1)
    crit = _t_dist.ppf((1 + level) / 2, df)
    lo, hi = min(a["xs"]), max(a["xs"])
    return [a["_a"] + a["_b"] * lo - crit * a["_sigma"],
            a["_a"] + a["_b"] * hi + crit * a["_sigma"]]


def _regression_draw(a, ctx):
    col = ctx.color
    fill_alpha = a["opts"].get("alpha", 0.2)
    lw = a["opts"].get("linewidth", 1.8)
    level = a["opts"].get("level", 0.95)
    n_grid = a["opts"].get("n_grid", 80)
    if a["_n"] < 3 or not a["xs"]:
        return ""
    df = a["_n"] - 2
    crit = _t_dist.ppf((1 + level) / 2, df)
    lo, hi = min(a["xs"]), max(a["xs"])
    grid = [lo + (hi - lo) * i / (n_grid - 1) for i in range(n_grid)]
    a0, b0, xm, sxx, sigma, n = (a["_a"], a["_b"], a["_xm"],
                                  a["_sxx"], a["_sigma"], a["_n"])
    upper, lower, mid = [], [], []
    for x in grid:
        yhat = a0 + b0 * x
        se = sigma * math.sqrt(1 / n + (x - xm) ** 2 / sxx)
        upper.append((x, yhat + crit * se))
        lower.append((x, yhat - crit * se))
        mid.append((x, yhat))
    pts_top = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in upper]
    pts_bot = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in lower]
    band = pts_top + pts_bot[::-1]
    out = [polygon(band, fill=col, alpha=fill_alpha)]
    line_pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in mid]
    out.append(polyline(line_pts, color=col, width=lw))
    return "".join(out)


def _regression_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(_a, _ctx, _x0, _y_mid):
        col = _a.get("_color", _ctx.color)
        return (rect(_x0, _y_mid - 5, 22, 10, fill=col, alpha=0.2)
                + segment(_x0, _y_mid, _x0 + 22, _y_mid, color=col, width=1.8))
    return [{"label": label, "color": None, "paint": paint}]


add_artist(ArtistSpec(
    name="regression",
    record=_regression_record,
    xdomain=_regression_xdomain,
    ydomain=_regression_ydomain,
    draw=_regression_draw,
    legend_entries=_regression_legend_entries,
))
