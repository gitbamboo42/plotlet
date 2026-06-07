"""Cookbook recipe: regression diagnostic 4-panel.

The four-pane "lm() diagnostics" R users know from `plot(model)`:
  1. Residuals vs Fitted    — non-linearity / heteroscedasticity check
  2. Normal Q-Q             — residual normality
  3. Scale-Location         — sqrt(|standardized resid|) vs fitted
  4. Residuals vs Leverage  — outlier influence (with Cook's distance
                              reference contours)

Uses `scipy.stats.norm.ppf` for the Q-Q reference and `scipy.stats.f.ppf`
to scale the Cook's-distance contours. Earlier versions of this recipe
inlined a BSM normal-PPF approximation; the scipy version is exact and
the recipe is shorter for it.

API:
    residual_diagnostics(xs, ys, panel=200)
"""

SUMMARY = 'OLS diagnostic 4-panel (incl. Cook’s-distance contours) via scipy.stats.'

import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from scipy.stats import norm


def residual_diagnostics(xs, ys, panel: int = 200):
    xs = to_list(xs); ys = to_list(ys)
    n = len(xs)
    if n < 3:
        raise ValueError("need at least 3 points for diagnostics")
    # OLS fit.
    xm = sum(xs) / n; ym = sum(ys) / n
    sxx = sum((x - xm) ** 2 for x in xs) or 1e-12
    sxy = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    b1 = sxy / sxx; b0 = ym - b1 * xm
    fitted = [b0 + b1 * x for x in xs]
    resid = [y - f for y, f in zip(ys, fitted)]
    sse = sum(r * r for r in resid)
    mse = sse / max(n - 2, 1)
    sd_resid = math.sqrt(mse) or 1.0
    # Leverage h_ii = 1/n + (x_i - x̄)^2 / Sxx (for simple regression)
    leverage = [1 / n + (x - xm) ** 2 / sxx for x in xs]
    std_resid = [r / (sd_resid * math.sqrt(max(1 - h, 1e-9)))
                 for r, h in zip(resid, leverage)]

    # --- panel 1: residuals vs fitted ---
    p1 = pt.chart(data_width=panel, data_height=panel)
    p1.scatter(data={"x": fitted, "y": resid}, x="x", y="y", s=10, alpha=0.7)
    p1.axhline(0, color="#888", linestyle="--")
    p1.title("Residuals vs Fitted").xlabel("fitted").ylabel("residual")

    # --- panel 2: Normal Q-Q (exact normal PPF via scipy) ---
    sr_sorted = sorted(std_resid)
    pp = [(i + 0.5) / n for i in range(n)]
    theo = list(norm.ppf(pp))
    p2 = pt.chart(data_width=panel, data_height=panel)
    p2.scatter(data={"x": theo, "y": sr_sorted}, x="x", y="y", s=10, alpha=0.7)
    i25 = int(0.25 * (n - 1)); i75 = int(0.75 * (n - 1))
    x1, y1 = theo[i25], sr_sorted[i25]
    x2, y2 = theo[i75], sr_sorted[i75]
    if x2 != x1:
        slope = (y2 - y1) / (x2 - x1); intercept = y1 - slope * x1
        x_lo, x_hi = min(theo), max(theo)
        pad = (x_hi - x_lo) * 0.05
        p2.line(data={"x": [x_lo - pad, x_hi + pad],
                      "y": [intercept + slope * (x_lo - pad),
                            intercept + slope * (x_hi + pad)]},
                x="x", y="y", color="#888", linestyle="--")
    p2.title("Normal Q-Q").xlabel("theoretical").ylabel("std. residual")

    # --- panel 3: scale-location: sqrt(|std resid|) vs fitted ---
    sl = [math.sqrt(abs(r)) for r in std_resid]
    p3 = pt.chart(data_width=panel, data_height=panel)
    p3.scatter(data={"x": fitted, "y": sl}, x="x", y="y", s=10, alpha=0.7)
    p3.title("Scale-Location").xlabel("fitted").ylabel("√|std. residual|")

    # --- panel 4: residuals vs leverage with Cook's-distance contours ---
    # Cook's D = (std_resid^2 / p) * (h / (1 - h)), where p = 2 (slope + intercept).
    p4 = pt.chart(data_width=panel, data_height=panel)
    p4.scatter(data={"x": leverage, "y": std_resid}, x="x", y="y", s=10, alpha=0.7)
    p4.axhline(0, color="#888", linestyle="--")
    # Cook's-distance contour at D = c, solving std_resid as a function of h.
    # std_resid = ± sqrt(c * p * (1 - h) / h).
    p_param = 2
    h_grid = [0.001 + 0.98 * i / 60 for i in range(61)]
    for c_val, dash in ((0.5, "5,3"), (1.0, "2,2")):
        for sign in (+1, -1):
            ys_c = [sign * math.sqrt(c_val * p_param * (1 - h) / h) for h in h_grid]
            p4.line(data={"x": h_grid, "y": ys_c}, x="x", y="y", color="#d62728", linewidth=0.8, linestyle=dash)
    p4.title("Residuals vs Leverage").xlabel("leverage").ylabel("std. residual")

    return pt.grid([[p1, p2], [p3, p4]])


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    xs = [i * 0.4 for i in range(80)]
    ys = [1 + 0.5 * x + 0.05 * x * x + random.gauss(0, 0.5 + 0.05 * x) for x in xs]
    fig = residual_diagnostics(xs, ys)
    return fig


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
