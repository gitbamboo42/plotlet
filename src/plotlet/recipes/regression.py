"""Custom artist: linear regression with confidence ribbon.

Fits y ~ x by closed-form OLS, draws the fit line, and shades a
confidence band around it using the exact Student-t critical value at
n - 2 degrees of freedom. Equivalent to `geom_smooth(method="lm")` and
seaborn `regplot`.

API: c.regression(xs, ys, level=0.95, n_grid=80).
The scatter is not drawn here — overlay your own `c.scatter(xs, ys)`.

Math:
    slope b = Σ((x - x̄)(y - ȳ)) / Σ((x - x̄)²)
    intercept a = ȳ - b·x̄
    residual σ² = SSE / (n - 2)
    se(ŷ(x)) = σ · sqrt(1/n + (x - x̄)² / Σ(x - x̄)²)
    t · se for the band, t = t_{α/2, n-2}.
"""

SUMMARY = "OLS fit line plus Student-t confidence ribbon."

import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from scipy.stats import t as _t_dist


def _fit_ols(xs, ys):
    n = len(xs)
    xm = sum(xs) / n; ym = sum(ys) / n
    sxx = sum((x - xm) ** 2 for x in xs) or 1e-12
    sxy = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = ym - b * xm
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    sse = sum(r * r for r in resid)
    sigma2 = sse / max(n - 2, 1)
    return a, b, xm, sxx, math.sqrt(sigma2), n


def regression_record(args, kw):
    xs = to_list(args[0])
    ys = to_list(args[1])
    a, b, xm, sxx, sigma, n = _fit_ols(xs, ys)
    return {"type": "regression", "xs": xs, "ys": ys,
            "_a": a, "_b": b, "_xm": xm, "_sxx": sxx,
            "_sigma": sigma, "_n": n, "opts": kw}


def regression_xdomain(a): return a["xs"]


def regression_ydomain(a):
    if not a["xs"]:
        return []
    level = a["opts"].get("level", 0.95)
    df = max(a["_n"] - 2, 1)
    crit = _t_dist.ppf((1 + level) / 2, df)
    lo, hi = min(a["xs"]), max(a["xs"])
    return [a["_a"] + a["_b"] * lo - crit * a["_sigma"],
            a["_a"] + a["_b"] * hi + crit * a["_sigma"]]


def regression_draw(a, ctx):
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
    a0, b0, xm, sxx, sigma, n = a["_a"], a["_b"], a["_xm"], a["_sxx"], a["_sigma"], a["_n"]
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
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in band) + " Z"
    out = [f'<path d="{d}" fill="{col}" fill-opacity="{fill_alpha}"/>']
    line_pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in mid]
    d2 = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in line_pts)
    out.append(f'<path d="{d2}" fill="none" stroke="{col}" stroke-width="{lw}"/>')
    return "".join(out)


def regression_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    return (
        f'<rect x="{x0}" y="{y_mid - 5}" width="22" height="10" '
        f'fill="{col}" fill-opacity="0.2"/>'
        f'<line x1="{x0}" x2="{x0 + 22}" y1="{y_mid}" y2="{y_mid}" '
        f'stroke="{col}" stroke-width="1.8"/>'
    )


pt.add_artist(pt.ArtistSpec(
    name="regression",
    record=regression_record,
    xdomain=regression_xdomain,
    ydomain=regression_ydomain,
    draw=regression_draw,
    legend_swatch=regression_legend_swatch,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(6)
    xs = [i * 0.5 for i in range(40)]
    ys = [1.2 + 0.7 * x + random.gauss(0, 1.0) for x in xs]
    c = pt.chart()
    c.scatter(xs, ys, label="data")
    c.regression(xs, ys, level=0.95, label="fit ± 95 % CI")
    c.title("Linear regression").xlabel("x").ylabel("y").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
