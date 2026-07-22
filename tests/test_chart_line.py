"""Baseline SVG regression tests for the line artist/topic.

    pytest tests/test_chart_line.py
    pytest tests/test_chart_line.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest
from _chart_helpers import _xs


def chart_table():
    xs = _xs()
    df = {
        "t":   xs,
        "sin": [math.sin(x) for x in xs],
        "cos": [math.cos(x) for x in xs],
    }
    c = pt.chart(df, aes(x="t"), title="chart from table",
                 xlabel="t", ylabel="value", legend=True, gridlines=True)
    c.add_line(aes(y="sin"), label="sin(t)")
    c.add_line(aes(y="cos"), label="cos(t)", linestyle="--")
    return c


def chart_color():
    xs = _xs()
    n = len(xs)
    df = {
        "t":      xs + xs,
        "v":      [math.sin(x) for x in xs] + [math.cos(x) for x in xs],
        "series": ["sin"] * n + ["cos"] * n,
    }
    c = pt.chart(df, aes(x="t", y="v", color="series"), title="color split",
                 xlabel="t", ylabel="v", legend=True, gridlines=True)
    c.add_line()
    return c


def chart_plot_alpha():
    # alpha now propagates to both the stroke and (if present) markers.
    xs = _xs()
    df = {"t": xs, "v": [math.sin(x) for x in xs],
          "w": [math.cos(x) for x in xs]}
    c = pt.chart(df, aes(x="t"), title="plot alpha", xlabel="t", ylabel="value",
                 legend=True)
    c.add_line(aes(y="v"), alpha=0.3, label="alpha=0.3")
    c.add_line(aes(y="w"), alpha=1.0, label="alpha=1")
    return c


def chart_curve_steps():
    # All three step modes on the same axes, plus the default linear.
    # Markers stay at the original data points regardless of mode — they
    # mark where the values are; the step shape just chooses how to
    # connect them.
    xs = [0, 1, 2, 3, 4, 5]
    ys = [1, 3, 2, 5, 4, 6]
    c = pt.chart(title="curve= modes", xlabel="x", ylabel="y",
                 legend=True, gridlines=True)
    df = {"x": xs, "y": ys}
    c.add_line(df, aes(x="x", y="y"), curve="linear", marker="o", label="linear")
    df2 = {"x": xs, "y": [v + 2 for v in ys]}
    c.add_line(df2, aes(x="x", y="y"), curve="step-after", marker="o", label="step-after")
    df3 = {"x": xs, "y": [v + 4 for v in ys]}
    c.add_line(df3, aes(x="x", y="y"), curve="step-before", marker="o", label="step-before")
    df4 = {"x": xs, "y": [v + 6 for v in ys]}
    c.add_line(df4, aes(x="x", y="y"), curve="step-mid", marker="o", label="step-mid")
    return c


def chart_line_group():
    # `group=col` splits into multiple polylines without burning a color
    # channel — every subject gets its own trace but the legend only
    # shows the cohort (color) levels.
    import pandas as pd
    rng = random.Random(31)
    rows = []
    for cohort, mu_slope in zip(["ctrl", "trt"], [0.4, 1.1]):
        for subj in range(5):
            base = rng.gauss(0, 0.3)
            slope = mu_slope + rng.gauss(0, 0.15)
            for t in range(8):
                rows.append({"t": t, "value": base + slope * t + rng.gauss(0, 0.2),
                             "subject": f"{cohort}_{subj}", "cohort": cohort})
    df = pd.DataFrame(rows)
    c = pt.chart(df, aes(x="t", y="value"),
                 data_width=320, data_height=200,
                 title="trajectories: color by cohort, group by subject",
                 xlabel="t", ylabel="value", legend=True)
    c.add_line(aes(color="cohort", group="subject"), alpha=0.7)
    c.legend()
    return c


def chart_line_linetype():
    # `linestyle=col` cycles dash patterns per level. When `linestyle`
    # maps the same column as `color`, the legend swatches inherit the
    # dash pattern — the canonical B&W-safe / colorblind-redundant
    # encoding pattern.
    import pandas as pd
    rng = random.Random(8)
    rows = []
    for cohort, mu in zip(["ctrl", "low_dose", "high_dose"], [0.3, 0.8, 1.4]):
        for t in range(10):
            rows.append({"t": t, "v": mu * t + rng.gauss(0, 0.2),
                         "cohort": cohort})
    df = pd.DataFrame(rows)
    c = pt.chart(df, aes(x="t", y="v"),
                 data_width=320, data_height=200,
                 title="redundant color + linestyle",
                 xlabel="t", ylabel="v", legend=True)
    c.add_line(aes(color="cohort", linestyle="cohort"), linewidth=1.6)
    c.legend()
    return c


def chart_line_alpha():
    # `alpha=col` linearly interpolates per group through `alphas=(lo, hi)`.
    # Default range is (0.3, 1.0) so the first level fades, the last stays
    # fully opaque.
    import pandas as pd
    rng = random.Random(9)
    rows = []
    for cohort, mu in zip(["baseline", "wk4", "wk8", "wk12"],
                          [0.3, 0.7, 1.1, 1.5]):
        for t in range(10):
            rows.append({"t": t, "v": mu * t + rng.gauss(0, 0.2),
                         "cohort": cohort})
    df = pd.DataFrame(rows)
    c = pt.chart(df, aes(x="t", y="v"),
                 data_width=320, data_height=200,
                 title="color + alpha by cohort",
                 xlabel="t", ylabel="v", legend=True)
    c.add_line(aes(color="cohort", alpha="cohort"), linewidth=1.8)
    c.legend()
    return c


def chart_line_estimator():
    """estimator='mean': replicate rows collapse per x with a CI band,
    split by color level."""
    rng = random.Random(27)
    rows_t, rows_v, rows_g = [], [], []
    for g, slope in zip(["ctrl", "trt"], [0.4, 1.0]):
        for t in range(10):
            for _ in range(12):
                rows_t.append(t); rows_g.append(g)
                rows_v.append(slope * t + rng.gauss(0, 1.0))
    df = {"t": rows_t, "v": rows_v, "g": rows_g}
    c = pt.chart(df, aes(x="t", y="v"),
                 data_width=320, data_height=200,
                 title="line estimator='mean' ± 95 % CI",
                 xlabel="t", ylabel="v", legend=True)
    c.add_line(aes(color="g"), estimator="mean")
    c.legend()
    return c


PLOTS = {
    "table": chart_table,
    "color": chart_color,
    "plot_alpha": chart_plot_alpha,
    "curve_steps": chart_curve_steps,
    "line_group": chart_line_group,
    "line_linetype": chart_line_linetype,
    "line_alpha": chart_line_alpha,
    "line_estimator": chart_line_estimator,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_line_baseline(name, fn, baseline_compare):
    baseline_compare("chart_line", name, fn().to_svg())


def test_line_estimator_aggregates():
    df = {"x": [0, 0, 1, 1], "y": [1.0, 3.0, 2.0, 6.0]}
    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line(estimator="mean", ci=None)
    svg = c.to_svg()
    assert 'data-plotlet-n="2"' in svg
    assert 'data-plotlet-estimator="mean"' in svg
    assert 'data-plotlet-y-max="4"' in svg   # mean of (2, 6)


def test_line_ci_band_extends_domain():
    import re
    df = {"x": [0, 0, 0, 1, 1, 1], "y": [1, 2, 3, 4, 5, 6]}

    def ylim_hi(**kw):
        c = pt.chart(df, aes(x="x", y="y"))
        c.add_line(estimator="mean", **kw)
        m = re.search(r'data-plotlet-ylim="([^"]*)"', c.to_svg())
        return float(m.group(1).split(",")[1])

    assert ylim_hi() > 7        # t CI on mean(4,5,6) reaches ~7.5
    assert ylim_hi(ci=None) < 7


def test_line_ci_band_clips_on_log_scale():
    import re
    # all-positive data whose t CI lower bound goes negative
    df = {"x": [0, 0, 0, 1, 1, 1], "y": [1.0, 10.0, 100.0, 2.0, 20.0, 200.0]}
    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line(estimator="mean")
    c.yscale("log")
    svg = c.to_svg()                       # must not raise, no NaN paths
    assert "nan" not in svg
    y0 = float(re.search(
        r'data-plotlet-ylim="([^"]*)"', svg).group(1).split(",")[0])
    assert y0 > 0                          # negative band bound didn't vote
    # the band polygon still draws, clipped at the axis floor
    body = re.search(r'<g[^>]*data-plotlet-type="line"[^>]*>(.*?)</g>',
                     svg, re.S).group(1)
    assert re.search(r'<path[^>]*opacity="0.20"', body)


def test_line_estimator_validation():
    df = {"x": [0, 1], "y": [1, 2]}

    def line(fn="add_line", **kw):
        c = pt.chart(df, aes(x="x", y="y"))
        getattr(c, fn)(**kw)
        c.to_svg()

    with pytest.raises(TypeError, match="apply with estimator"):
        line(ci="t")
    with pytest.raises(ValueError, match="estimator="):
        line(estimator="max")
    with pytest.raises(ValueError, match="curve"):
        line(fn="add_step", estimator="mean")
    with pytest.raises(ValueError, match="ci='x'"):
        line(estimator="mean", ci="x")
