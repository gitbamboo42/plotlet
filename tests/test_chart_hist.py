"""Baseline SVG regression tests for the hist artist/topic.

    pytest tests/test_chart_hist.py
    pytest tests/test_chart_hist.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_hist():
    rng = random.Random(7)
    df = {"value": [rng.gauss(0, 1) for _ in range(2000)]}
    c = pt.chart(df, title="histogram from table",
                 xlabel="value", ylabel="count")
    c.add_hist(x="value", bins=30, fill="C2")
    return c


def chart_hist_stack():
    rng = random.Random(21)
    df = {
        "value": ([rng.gauss(0, 1) for _ in range(600)]
                  + [rng.gauss(1.8, 0.7) for _ in range(400)]),
        "group": ["ctrl"] * 600 + ["treat"] * 400,
    }
    c = pt.chart(df, title="hist stacked", xlabel="value", ylabel="count",
                 legend=True)
    c.add_hist(x="value", fill="group", bins=24, position="stack")
    return c


def chart_hist_dodge():
    rng = random.Random(21)
    df = {
        "value": ([rng.gauss(0, 1) for _ in range(600)]
                  + [rng.gauss(1.8, 0.7) for _ in range(400)]),
        "group": ["ctrl"] * 600 + ["treat"] * 400,
    }
    c = pt.chart(df, title="hist dodged", xlabel="value", ylabel="count",
                 legend=True)
    c.add_hist(x="value", fill="group", bins=12, position="dodge")
    return c


def chart_hist_binwidth_cumulative():
    rng = random.Random(22)
    df = {"v": [rng.gauss(0, 1) for _ in range(500)]}
    c = pt.chart(df, title="hist binwidth= + cumulative CDF",
                 xlabel="v", ylabel="cdf")
    c.add_hist(x="v", binwidth=0.25, binrange=(-3, 3),
           cumulative=True, density=True, fill="C0")
    return c


PLOTS = {
    "hist": chart_hist,
    "hist_stack": chart_hist_stack,
    "hist_dodge": chart_hist_dodge,
    "hist_binwidth_cumulative": chart_hist_binwidth_cumulative,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_hist_baseline(name, fn, baseline_compare):
    baseline_compare("chart_hist", name, fn().to_svg())


def test_hist_bin_helpers():
    from plotlet.utils import hist_bin_edges, hist_bin_counts, hist_transform
    assert hist_bin_edges([0, 10], bins=5) == [0, 2, 4, 6, 8, 10]
    assert hist_bin_edges([0, 1], bins=[0, 1, 4]) == [0, 1, 4]
    assert hist_bin_edges([0, 10], binwidth=2.5) == [0, 2.5, 5.0, 7.5, 10.0]
    assert hist_bin_edges([-99, 99], bins=4, binrange=(0, 8)) == [0, 2, 4, 6, 8]
    # out-of-range / None / NaN values drop; the last bin is right-inclusive
    counts = hist_bin_counts(
        [0.5, 1.5, 1.5, 8, 10, 10, -1, 11, None, float("nan")],
        [0, 2, 4, 6, 8, 10])
    assert counts == [3, 0, 0, 0, 3]
    assert hist_bin_counts([1, 3], [0, 2, 4], weights=[2.0, 0.5]) == [2.0, 0.5]
    assert hist_transform([1, 3], [0, 1, 2], cumulative=True) == [1, 4]
    assert hist_transform([1, 3], [0, 1, 2],
                          density=True, cumulative=True) == [0.25, 1.0]
    assert hist_transform([1, 3], [0, 1, 3], density=True) == [0.25, 0.375]


def test_hist_stack_extends_count_domain():
    # One bin, groups of 3 and 2 rows: stacked bars pile to 5, so the
    # count axis must reach it; overlaid bars top out at 3.
    df = {"v": [0.5] * 3 + [0.6] * 2, "g": ["a"] * 3 + ["b"] * 2}

    def ylim_hi(position):
        c = pt.chart(df)
        c.add_hist(x="v", fill="g", bins=[0, 1], position=position)
        import re
        m = re.search(r'data-plotlet-ylim="([^"]*)"', c.to_svg())
        return float(m.group(1).split(",")[1])

    assert ylim_hi("stack") >= 5
    assert ylim_hi("overlay") < 5


def test_hist_weights_column():
    df = {"v": [0.5, 0.5, 1.5], "w": [2.0, 3.0, 5.0]}
    c = pt.chart(df)
    c.add_hist(x="v", bins=[0, 1, 2], weights="w")
    assert 'data-plotlet-count-max="5"' in c.to_svg()


def test_hist_rejects_bad_binning_combos():
    def render(**kw):
        c = pt.chart({"v": [1, 2, 3]})
        c.add_hist(x="v", **kw)
        c.to_svg()

    with pytest.raises(TypeError, match="bins= or binwidth="):
        render(bins=5, binwidth=0.5)
    with pytest.raises(ValueError, match="strictly increasing"):
        render(bins=[3, 2, 1])
    with pytest.raises(TypeError, match="drop\\s+binrange"):
        render(bins=[0, 1, 2], binrange=(0, 2))
    with pytest.raises(ValueError, match="must be positive"):
        render(binwidth=-1)
    with pytest.raises(ValueError, match="lo < hi"):
        render(binrange=(2, 1))
    with pytest.raises(ValueError, match="histtype='bar'"):
        render(fill=["a", "a", "b"], position="stack", histtype="step")
    with pytest.raises(ValueError, match="weights= has 2 values"):
        render(weights=[1, 2])
