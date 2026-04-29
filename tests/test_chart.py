#!/usr/bin/env python3
"""Baseline SVG regression tests for the `pt.chart(df, ...)` API.

    python tests/test_chart.py            # check vs. baselines, exit 1 on mismatch
    python tests/test_chart.py --update   # regenerate baselines (review diff!)
    python tests/test_chart.py --gallery  # write baseline_images/chart/index.html

The diff/update/gallery plumbing lives in `_runner.py`.
"""
from __future__ import annotations

import math
import random
import sys

import plotlet as pt

import _runner


def _xs():
    return [i * 0.1 for i in range(64)]


def chart_table():
    xs = _xs()
    df = {
        "t":   xs,
        "sin": [math.sin(x) for x in xs],
        "cos": [math.cos(x) for x in xs],
    }
    c = pt.chart(df, title="chart from table",
                 xlabel="t", ylabel="value", legend=True, grid=True)
    c.line(x="t", y="sin", label="sin(t)")
    c.line(x="t", y="cos", label="cos(t)", linestyle="--")
    return c


def chart_hue():
    xs = _xs()
    n = len(xs)
    df = {
        "t":      xs + xs,
        "v":      [math.sin(x) for x in xs] + [math.cos(x) for x in xs],
        "series": ["sin"] * n + ["cos"] * n,
    }
    c = pt.chart(df, title="hue split",
                 xlabel="t", ylabel="v", legend=True, grid=True)
    c.line(x="t", y="v", hue="series")
    return c


def chart_scatter_hue():
    rng = random.Random(0)
    n = 60
    df = {
        "x":     [rng.random() * 10 for _ in range(2 * n)],
        "y":     [rng.random() * 10 for _ in range(2 * n)],
        "group": ["A"] * n + ["B"] * n,
    }
    c = pt.chart(df, title="scatter hue",
                 xlabel="x", ylabel="y", legend=True, grid=True)
    c.scatter(x="x", y="y", hue="group", s=30, alpha=0.6)
    return c


def chart_bar():
    df = {"category": ["A", "B", "C", "D", "E"], "count": [4, 7, 2, 9, 5]}
    c = pt.chart(df, title="bar from table", ylabel="count")
    c.bar(x="category", y="count", color="C0")
    return c


def chart_hist():
    rng = random.Random(7)
    df = {"value": [rng.gauss(0, 1) for _ in range(2000)]}
    c = pt.chart(df, title="histogram from table",
                 xlabel="value", ylabel="count")
    c.hist(x="value", bins=30, color="C2")
    return c


def chart_fill_between():
    xs = _xs()
    df = {
        "x":    xs,
        "mean": [math.sin(x) for x in xs],
        "lo":   [math.sin(x) - 0.3 for x in xs],
        "hi":   [math.sin(x) + 0.3 for x in xs],
    }
    c = pt.chart(df, title="fill_between from table",
                 xlabel="x", ylabel="y", legend=True)
    c.fill_between(x="x", y1="lo", y2="hi", color="C0", alpha=0.25, label="band")
    c.line(x="x", y="mean", color="C0", label="mean")
    return c


PLOTS = {
    "table":        chart_table,
    "hue":          chart_hue,
    "scatter_hue":  chart_scatter_hue,
    "bar":          chart_bar,
    "hist":         chart_hist,
    "fill_between": chart_fill_between,
}


if __name__ == "__main__":
    sys.exit(_runner.run("chart", PLOTS))
