"""Baseline SVG regression tests for the bar artist/topic.

    pytest tests/test_chart_bar.py
    pytest tests/test_chart_bar.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest
from _chart_helpers import _bar_quarterly_df


def chart_bar():
    df = {"category": ["A", "B", "C", "D", "E"], "count": [4, 7, 2, 9, 5]}
    c = pt.chart(df, title="bar from table", ylabel="count")
    c.add_bar(aes(x="category", y="count"), fill="C0")
    return c


def chart_bar_stack():
    df = _bar_quarterly_df()
    c = pt.chart(data_width=300, data_height=200,
                 title="bar stack", ylabel="$M", legend=True)
    c.add_bar(data=df, mapping=aes(x="quarter", y="value", fill="series"), position="stack")
    c.legend()
    return c


def chart_bar_dodge():
    df = _bar_quarterly_df()
    c = pt.chart(data_width=320, data_height=200,
                 title="bar dodge", ylabel="$M", legend=True)
    c.add_bar(data=df, mapping=aes(x="quarter", y="value", fill="series"), position="dodge")
    c.legend()
    return c


def chart_named_palette():
    df = _bar_quarterly_df()
    c = pt.chart(data_width=320, data_height=200,
                 title='named palette ("Set2")', ylabel="$M", legend=True)
    c.add_bar(data=df, mapping=aes(x="quarter", y="value", fill="series"), position="dodge",
          palette="Set2")
    c.legend()
    return c


def chart_bar_fill():
    df = _bar_quarterly_df()
    c = pt.chart(data_width=300, data_height=200,
                 title="bar fill (100%)", ylabel="share", legend=True)
    c.add_bar(data=df, mapping=aes(x="quarter", y="value", fill="series"), position="fill")
    c.legend()
    return c


def chart_bar_long_fill():
    # Long-form: `fill="col"` drives grouping; `color="black"` paints
    # the stroke (new flexibility — previously inexpressible).
    import pandas as pd
    rows = []
    for q, vals in zip(["Q1", "Q2", "Q3", "Q4"],
                        [(12, 8, 5), (18, 14, 7), (15, 16, 9), (22, 18, 11)]):
        for s, v in zip(["A", "B", "C"], vals):
            rows.append({"quarter": q, "series": s, "value": v})
    df = pd.DataFrame(rows)
    c = pt.chart(df, data_width=320, data_height=200,
                 title="bar long-form (fill=col, outlined)",
                 ylabel="$M", legend=True)
    c.add_bar(aes(x="quarter", y="value", fill="series"), color="black",
          position="dodge")
    c.legend()
    return c


def chart_bar_yerr():
    # Ungrouped bars with asymmetric error bars (tuple-of-columns spec);
    # whiskers sit at band centers.
    df = {"cat": ["a", "b", "c", "d"], "mean": [4.2, 5.6, 3.1, 6.4],
          "lo": [0.5, 1.1, 0.4, 0.9], "hi": [0.8, 0.6, 1.2, 0.5]}
    c = pt.chart(data_width=300, data_height=200,
                 title="bar ± yerr (asymmetric)", ylabel="mean")
    c.add_bar(data=df, mapping=aes(x="cat", y="mean"), fill="C0", yerr=("lo", "hi"))
    return c


def chart_bar_dodge_yerr():
    # The canonical grouped mean±err figure. position defaults to
    # "dodge" when yerr= is given; whiskers share the dodge slot centers.
    df = _bar_quarterly_df()
    df["sd"] = [round(0.4 + 0.08 * v, 2) for v in df["value"]]
    c = pt.chart(data_width=320, data_height=200,
                 title="bar dodge ± yerr", ylabel="$M", legend=True)
    c.add_bar(data=df, mapping=aes(x="quarter", y="value", fill="series", yerr="sd"))
    c.legend()
    return c


def chart_bar_h_xerr():
    # Horizontal bars take xerr= (the value axis is x); also exercises
    # ecolor= and capsize= overrides.
    df = {"cat": ["alpha", "beta", "gamma"], "mean": [4.2, 5.6, 3.1],
          "err": [0.5, 1.1, 0.4]}
    c = pt.chart(data_width=300, data_height=180,
                 title="bar horizontal ± xerr", xlabel="mean")
    c.add_bar(data=df, mapping=aes(x="cat", y="mean", xerr="err"), orientation="h",
          ecolor="gray", capsize=3)
    return c


def chart_bar_errorbar_aligned():
    # Composition check: an independently dodged errorbar lands on the
    # same slot centers as bar position="dodge" (width/gap defaults
    # match). Whiskers here are darker than the translucent bars.
    df = _bar_quarterly_df()
    df["sd"] = [round(0.4 + 0.08 * v, 2) for v in df["value"]]
    c = pt.chart(data_width=320, data_height=200,
                 title="bar + errorbar share dodge slots", ylabel="$M")
    c.add_bar(data=df, mapping=aes(x="quarter", y="value", fill="series"), position="dodge",
          alpha=0.45)
    c.add_errorbar(data=df, mapping=aes(x="quarter", y="value", yerr="sd", color="series"),
               marker=None)
    return c


def chart_bar_count():
    """stat='count' — one row per (category, group), stacked count bars."""
    rng = random.Random(25)
    outcomes = ["responder", "partial", "non-responder"]
    arms = ["placebo", "drug"]
    rows_o, rows_a = [], []
    for arm, weights in zip(arms, [(2, 3, 5), (5, 3, 2)]):
        for _ in range(80):
            rows_o.append(rng.choices(outcomes, weights=weights)[0])
            rows_a.append(arm)
    df = {"outcome": rows_o, "arm": rows_a}
    c = pt.chart(data_width=300, data_height=220,
                 title="bar stat='count'", ylabel="rows", legend=True)
    c.add_bar(data=df, mapping=aes(x="outcome", fill="arm"), stat="count")
    c.legend()
    return c


def chart_bar_mean_ci():
    """stat='mean' — grouped means dodged with t CI bars."""
    rng = random.Random(26)
    rows_c, rows_g, rows_v = [], [], []
    for cat, base in zip(["low", "mid", "high"], [3.0, 5.0, 8.0]):
        for g, shift in zip(["ctrl", "trt"], [0.0, 1.2]):
            for _ in range(15):
                rows_c.append(cat); rows_g.append(g)
                rows_v.append(rng.gauss(base + shift, 1.0))
    df = {"dose": rows_c, "arm": rows_g, "resp": rows_v}
    c = pt.chart(data_width=300, data_height=220,
                 title="bar stat='mean' ± 95 % CI",
                 xlabel="dose", ylabel="response", legend=True)
    c.add_bar(data=df, mapping=aes(x="dose", y="resp", fill="arm"), stat="mean")
    c.legend()
    return c


def chart_bar_bottom():
    # Nonzero baseline: bars rise from bottom=2 (the value domain
    # includes the baseline), and a single-series label= drives the
    # one-entry legend paint path.
    df = {"month": ["Jan", "Feb", "Mar", "Apr"], "temp": [3.2, 4.1, 7.8, 12.6]}
    c = pt.chart(data_width=300, data_height=200,
                 title="bar bottom=2 baseline", ylabel="°C", legend=True)
    c.add_bar(data=df, mapping=aes(x="month", y="temp"), fill="C1", bottom=2, label="2016")
    c.legend()
    return c


def chart_bar_fill_eq_x():
    # fill= names the x column itself — redundant grouping: each bar at
    # full slot width in its own color, one legend entry per category
    # (seaborn's classic per-category coloring).
    df = {"tool": ["hammer", "saw", "drill"], "uses": [14, 9, 17]}
    c = pt.chart(data_width=300, data_height=200,
                 title="bar fill=x (per-category colors)", ylabel="uses",
                 legend=True)
    c.add_bar(data=df, mapping=aes(x="tool", y="uses", fill="tool"), position="dodge")
    c.legend()
    return c


def chart_bar_h_stack():
    # Horizontal stacked: categories on the y band axis, values stack
    # along x from 0.
    df = _bar_quarterly_df()
    c = pt.chart(data_width=300, data_height=200,
                 title="bar horizontal stack", xlabel="$M", legend=True)
    c.add_bar(data=df, mapping=aes(x="quarter", y="value", fill="series"), position="stack",
          orientation="h")
    c.legend()
    return c


PLOTS = {
    "bar": chart_bar,
    "bar_stack": chart_bar_stack,
    "bar_dodge": chart_bar_dodge,
    "named_palette": chart_named_palette,
    "bar_fill": chart_bar_fill,
    "bar_long_fill": chart_bar_long_fill,
    "bar_yerr": chart_bar_yerr,
    "bar_dodge_yerr": chart_bar_dodge_yerr,
    "bar_h_xerr": chart_bar_h_xerr,
    "bar_errorbar_aligned": chart_bar_errorbar_aligned,
    "bar_count": chart_bar_count,
    "bar_mean_ci": chart_bar_mean_ci,
    "bar_bottom": chart_bar_bottom,
    "bar_fill_eq_x": chart_bar_fill_eq_x,
    "bar_h_stack": chart_bar_h_stack,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_bar_baseline(name, fn, baseline_compare):
    baseline_compare("chart_bar", name, fn().to_svg())


def test_bar_err_rejects_stack():
    df = _bar_quarterly_df()
    df["sd"] = [0.5] * len(df["value"])
    c = pt.chart()
    c.add_bar(data=df, mapping=aes(x="quarter", y="value", fill="series", yerr="sd"),
          position="stack")
    with pytest.raises(ValueError, match="position='dodge'"):
        c.to_svg()


def test_bar_err_rejects_duplicate_rows():
    df = {"cat": ["a", "a"], "v": [1, 2], "sd": [0.1, 0.2]}
    c = pt.chart()
    c.add_bar(data=df, mapping=aes(x="cat", y="v", yerr="sd"))
    with pytest.raises(ValueError, match="one row per"):
        c.to_svg()


def test_bar_err_matches_orientation():
    df = {"cat": ["a", "b"], "v": [1, 2], "sd": [0.1, 0.2]}
    c = pt.chart()
    c.add_bar(data=df, mapping=aes(x="cat", y="v", xerr="sd"))
    with pytest.raises(TypeError, match="yerr"):
        c.to_svg()
    c = pt.chart()
    c.add_bar(data=df, mapping=aes(x="cat", y="v", yerr="sd"), orientation="h")
    with pytest.raises(TypeError, match="xerr"):
        c.to_svg()


def test_bar_stat_count_heights():
    df = {"cat": ["a", "a", "b", "a"]}
    c = pt.chart(df)
    c.add_bar(aes(x="cat"), stat="count")
    svg = c.to_svg()
    assert 'data-plotlet-y-max="3"' in svg
    assert 'data-plotlet-y-min="1"' in svg


def test_bar_stat_mean_ci_extends_domain():
    import re
    from plotlet.utils import t_ci_mean
    vals = [1.0, 2.0, 3.0, 4.0]
    df = {"cat": ["a"] * 4, "v": vals}

    def ylim_hi(**kw):
        c = pt.chart(df)
        c.add_bar(aes(x="cat", y="v"), stat="mean", **kw)
        m = re.search(r'data-plotlet-ylim="([^"]*)"', c.to_svg())
        return float(m.group(1).split(",")[1])

    _, ci_hi = t_ci_mean(vals, 0.95)   # mean 2.5, CI well past 4
    assert ylim_hi() >= ci_hi
    assert ylim_hi(ci=None) < ci_hi


def test_bar_stat_validation():
    df = {"cat": ["a", "b"], "v": [1, 2]}

    def bar(**kw):
        c = pt.chart(df)
        c.add_bar(aes(x="cat"), **kw)
        c.to_svg()

    with pytest.raises(TypeError, match="drop y="):
        bar(y="v", stat="count")
    with pytest.raises(ValueError, match="unknown stat"):
        bar(y="v", stat="max")
    with pytest.raises(TypeError, match="ci= applies"):
        bar(y="v", ci="t")
    with pytest.raises(TypeError, match="drop yerr"):
        bar(y="v", stat="mean", yerr=[0.1, 0.2])
    with pytest.raises(ValueError, match="ci='x'"):
        bar(y="v", stat="mean", ci="x")

    df2 = {"cat": ["a", "a", "b", "b"], "g": ["x", "y", "x", "y"],
           "v": [1, 2, 3, 4]}
    c = pt.chart(df2)
    c.add_bar(aes(x="cat", y="v", fill="g"), stat="mean", position="stack")
    with pytest.raises(ValueError, match="stacked means"):
        c.to_svg()


def test_errorbar_dodge_aligns_with_bar_slots():
    # The load-bearing composition contract: a grouped errorbar's stems
    # land on the same pixel centers as dodged bars over the same table.
    import re
    svg = chart_bar_errorbar_aligned().to_svg()
    centers = [float(m[0]) + float(m[1]) / 2 for m in re.findall(
        r'<rect x="([0-9.]+)" y="[0-9.]+" width="([0-9.]+)" height="[0-9.]+"'
        r' fill="#(?:1f77b4|ff7f0e|2ca02c)"', svg)]
    stems = [float(m[0]) for m in re.findall(
        r'<line x1="([0-9.]+)" x2="([0-9.]+)" y1="[0-9.]+" y2="[0-9.]+"'
        r' stroke="#(?:1f77b4|ff7f0e|2ca02c)"', svg) if m[0] == m[1]]
    assert len(centers) == 12 and len(stems) == 12
    for s in stems:
        assert min(abs(s - c) for c in centers) < 0.02
