"""Baseline SVG regression tests for the regression artist/topic.

    pytest tests/test_chart_regression.py
    pytest tests/test_chart_regression.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_regression():
    rng = random.Random(11)
    xs = [i * 0.5 for i in range(40)]
    ys = [1.2 + 0.7 * x + rng.gauss(0, 1.0) for x in xs]
    c = pt.chart(data_width=300, data_height=220,
                 title="linear regression", xlabel="x", ylabel="y",
                 legend=True)
    c.scatter(data={"x": xs, "y": ys}, x="x", y="y", label="data")
    c.regression(data={"x": xs, "y": ys}, x="x", y="y", label="fit ± 95 % CI")
    c.legend()
    return c


def chart_regression_color():
    """OLS regression: one line + band per color level."""
    import pandas as pd
    rng = random.Random(22)
    rows = []
    for g, (slope, intercept) in zip(["A", "B", "C"],
                                       [(1.5, 0.0), (-0.5, 3.0), (0.8, -1.5)]):
        for _ in range(60):
            x = rng.uniform(0, 4)
            rows.append({"x": x,
                         "y": slope * x + intercept + rng.gauss(0, 0.4),
                         "g": g})
    df = pd.DataFrame(rows)
    c = pt.chart(df, x="x", y="y", color="g",
                 data_width=320, data_height=240,
                 title="per-color regression",
                 xlabel="x", ylabel="y", legend=True)
    c.scatter(size=2, alpha=0.5)
    c.regression()
    c.legend()
    return c


def chart_regression_order2():
    rng = random.Random(28)
    xs = [i * 0.25 for i in range(48)]
    ys = [0.5 * x * x - 2.5 * x + 1 + rng.gauss(0, 1.2) for x in xs]
    c = pt.chart(data_width=300, data_height=220,
                 title="polynomial regression (order=2)",
                 xlabel="x", ylabel="y", legend=True)
    c.scatter(data={"x": xs, "y": ys}, x="x", y="y", size=2, alpha=0.6,
              label="data")
    c.regression(data={"x": xs, "y": ys}, x="x", y="y", order=2,
                 label="quadratic fit")
    c.legend()
    return c


def chart_regression_lowess():
    """LOWESS tracks the nonlinear signal and (via the robustifying
    iterations) shrugs off the two spike outliers. Line only — no band."""
    rng = random.Random(30)
    xs = [i * 0.05 for i in range(200)]
    ys = [math.sin(x) + 0.4 * math.sin(3 * x) + rng.gauss(0, 0.3)
          for x in xs]
    ys[20] += 4
    ys[150] -= 5
    df = {"x": xs, "y": ys}
    c = pt.chart(data_width=300, data_height=220,
                 title="LOWESS smoother",
                 xlabel="x", ylabel="y", legend=True)
    c.scatter(data=df, x="x", y="y", size=1.5, alpha=0.5, color="#555555")
    c.regression(data=df, x="x", y="y", lowess=True, frac=0.3,
                 label="lowess (frac=0.3)")
    c.regression(data=df, x="x", y="y", lowess=True, frac=0.7, color="C1",
                 label="lowess (frac=0.7)")
    return c


def chart_regression_robust():
    """Huber IRLS shrugs off the outlier cluster that drags plain OLS."""
    rng = random.Random(29)
    xs = [i * 0.2 for i in range(40)]
    ys = [1.0 + 0.8 * x + rng.gauss(0, 0.4) for x in xs]
    for i in (5, 12, 19, 26):  # contaminate a few rows upward
        ys[i] += 8.0
    df = {"x": xs, "y": ys}
    c = pt.chart(data_width=300, data_height=220,
                 title="robust (Huber) vs OLS",
                 xlabel="x", ylabel="y", legend=True)
    c.scatter(data=df, x="x", y="y", size=2.5, alpha=0.6, color="#555555")
    c.regression(data=df, x="x", y="y", color="C1", label="OLS")
    c.regression(data=df, x="x", y="y", robust=True, n_boot=100,
                 color="C0", label="Huber")
    c.legend()
    return c


PLOTS = {
    "regression": chart_regression,
    "regression_color": chart_regression_color,
    "regression_order2": chart_regression_order2,
    "regression_lowess": chart_regression_lowess,
    "regression_robust": chart_regression_robust,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_regression_baseline(name, fn, baseline_compare):
    baseline_compare("chart_regression", name, fn().to_svg())


def test_regression_order2_recovers_parabola():
    from plotlet.artists.regression import _fit_generic
    xs = [i * 0.5 for i in range(20)]
    ys = [2.0 * x * x - 3.0 * x + 1.0 for x in xs]   # exact, no noise
    fit = _fit_generic(xs, ys, order=2)
    for g, m in zip(fit["grid"], fit["mid"]):
        assert abs(m - (2.0 * g * g - 3.0 * g + 1.0)) < 1e-6
    # zero residual → the band collapses onto the line
    assert all(abs(h - l) < 1e-6 for h, l in zip(fit["hi"], fit["lo"]))


def test_regression_robust_ignores_outliers():
    from plotlet.artists.regression import _fit_generic
    xs = [i * 0.5 for i in range(30)]
    ys = [1.0 + 2.0 * x for x in xs]
    for i in (3, 11, 17):
        ys[i] += 50.0
    robust = _fit_generic(xs, ys, robust=True, n_boot=20)
    ols = _fit_generic(xs, ys, order=2)  # generic OLS path, distorted

    def max_err(fit):
        return max(abs(m - (1.0 + 2.0 * g))
                   for g, m in zip(fit["grid"], fit["mid"]))

    assert max_err(robust) < 0.5
    assert max_err(ols) > 2.0


def test_regression_order_validation():
    df = {"x": [1, 2, 3], "y": [1, 2, 3]}
    for bad in (0, 1.5, "2"):
        c = pt.chart(df)
        c.regression(x="x", y="y", order=bad)
        with pytest.raises(ValueError, match="order="):
            c.to_svg()
