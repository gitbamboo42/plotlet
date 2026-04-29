#!/usr/bin/env python3
"""Baseline SVG regression tests for the old chained `pt.figure()` API.

    python tests/test_old.py            # check vs. baselines, exit 1 on mismatch
    python tests/test_old.py --update   # regenerate baselines (review diff!)
    python tests/test_old.py --gallery  # write baseline_images/old/index.html

Mirrors `notebooks/01_basics_old.ipynb`. Kept under regression test because the
figure() API is still a public surface, even though `pt.chart(df, ...)` is the
preferred entry point — see `test_chart.py`. Runner plumbing lives in `_runner.py`.
"""
from __future__ import annotations

import math
import random
import sys

import plotlet as pt

import _runner


def _xs():
    return [i * 0.1 for i in range(64)]


def line():
    xs = _xs()
    return (pt.figure()
        .plot(xs, [math.sin(x) for x in xs], label="sin(x)")
        .plot(xs, [math.cos(x) for x in xs], label="cos(x)", linestyle="--")
        .xlabel("x").ylabel("y").title("line plot")
        .grid(True).legend())


def scatter():
    rng = random.Random(0)
    xs = [rng.random() * 10 for _ in range(80)]
    ys = [x * 0.6 + (rng.random() - 0.5) * 4 for x in xs]
    return (pt.figure()
        .scatter(xs, ys, s=30, alpha=0.6, label="points")
        .xlabel("x").ylabel("y").title("scatter").legend())


def bar():
    return (pt.figure()
        .bar(["A", "B", "C", "D", "E"], [4, 7, 2, 9, 5], color="C0")
        .ylabel("count").title("bar chart"))


def histogram():
    rng = random.Random(7)
    data = [rng.gauss(0, 1) for _ in range(2000)]
    return (pt.figure()
        .hist(data, bins=30, color="C2")
        .xlabel("value").ylabel("count").title("histogram"))


def fill_between():
    xs = _xs()
    mean  = [math.sin(x) for x in xs]
    lower = [m - 0.3 for m in mean]
    upper = [m + 0.3 for m in mean]
    return (pt.figure()
        .fill_between(xs, lower, upper, color="C0", alpha=0.25, label="band")
        .plot(xs, mean, color="C0", label="mean")
        .xlabel("x").ylabel("y").title("fill_between").legend())


def styles():
    xs = [i * 0.5 for i in range(22)]
    return (pt.figure()
        .plot(xs, [math.sin(x) for x in xs],
              linestyle="-",  marker="o", label="solid + o")
        .plot(xs, [math.sin(x) + 1.2 for x in xs],
              linestyle="--", marker="s", label="dashed + s")
        .plot(xs, [math.sin(x) + 2.4 for x in xs],
              linestyle=":",  marker="^", label="dotted + ^")
        .legend().grid(True).title("markers + linestyles"))


def log_scale():
    xs = list(range(1, 200))
    ys = [x * x for x in xs]
    return (pt.figure()
        .plot(xs, ys, color="C3")
        .yscale("log").xlabel("x").ylabel("log y")
        .title("yscale = log").grid(True))


def xlim_ylim():
    xs = _xs()
    return (pt.figure()
        .plot(xs, [math.sin(x) for x in xs], color="C4")
        .xlim(2, 5).ylim(-1.2, 1.2)
        .title("custom xlim / ylim").grid(True))


PLOTS = {
    "line":         line,
    "scatter":      scatter,
    "bar":          bar,
    "histogram":    histogram,
    "fill_between": fill_between,
    "styles":       styles,
    "log_scale":    log_scale,
    "xlim_ylim":    xlim_ylim,
}


if __name__ == "__main__":
    sys.exit(_runner.run("old", PLOTS))
