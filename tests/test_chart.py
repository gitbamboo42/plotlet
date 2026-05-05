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


def chart_imshow_rect():
    data = [[math.sin(r * 0.4) * math.cos(c * 0.3) for c in range(20)]
            for r in range(15)]
    c = pt.chart(title="imshow (rect path)", xlabel="col", ylabel="row")
    c.imshow(data, cmap="viridis")
    return c


def chart_imshow_png():
    data = [[math.sin(r * 0.07) + math.cos(c * 0.05) for c in range(160)]
            for r in range(120)]
    c = pt.chart(title="imshow (PNG path, magma)", xlabel="col", ylabel="row")
    c.imshow(data, cmap="magma")
    return c


def chart_imshow_diverging():
    data = [[(r - 7) * (c - 7) for c in range(15)] for r in range(15)]
    c = pt.chart(title="imshow (bwr, extent, vmin/vmax)",
                 xlabel="x", ylabel="y")
    c.imshow(data, cmap="bwr", extent=(-1.5, 1.5, -1.5, 1.5),
             vmin=-49, vmax=49)
    return c


def chart_category_x_scatter():
    # scatter on a categorical x — categories supplied alphabetically by default.
    rng = random.Random(3)
    samples = ["S1", "S2", "S3", "S4"]
    df = {
        "sample": [s for s in samples for _ in range(8)],
        "value":  [rng.gauss(0, 1) for _ in range(32)],
    }
    c = pt.chart(df, title="scatter on categorical x", xlabel="sample", ylabel="value",
                 xscale="category")
    c.scatter(x="sample", y="value", color="C0", alpha=0.6)
    return c


def chart_category_x_order():
    # Explicit order= reorders bars from their default first-appearance.
    df = {"sample": ["S1", "S2", "S3"], "count": [12, 7, 19]}
    c = pt.chart(df, title="bar with explicit category order",
                 xlabel="sample", ylabel="count")
    c.xscale("category", order=["S3", "S1", "S2"])
    c.bar(x="sample", y="count", color="C2")
    return c


def chart_category_y_scatter():
    # scatter on a categorical y — groups stack top-to-bottom.
    rng = random.Random(11)
    groups = ["alpha", "beta", "gamma"]
    df = {
        "group": [g for g in groups for _ in range(10)],
        "x":     [rng.gauss(0, 1) for _ in range(30)],
    }
    c = pt.chart(df, title="scatter on categorical y", xlabel="x", ylabel="group",
                 yscale="category")
    c.scatter(x="x", y="group", color="C3", alpha=0.6)
    return c


def chart_category_y_order():
    # Explicit y order= overrides the default alphabetical layout.
    rng = random.Random(11)
    groups = ["alpha", "beta", "gamma"]
    df = {
        "group": [g for g in groups for _ in range(10)],
        "x":     [rng.gauss(0, 1) for _ in range(30)],
    }
    c = pt.chart(df, title="scatter on categorical y, explicit order",
                 xlabel="x", ylabel="group")
    c.yscale("category", order=["gamma", "alpha", "beta"])
    c.scatter(x="x", y="group", color="C3", alpha=0.6)
    return c


def chart_hide_yticks():
    # Metadata-strip pattern: numeric y for positioning, but ticks suppressed
    # via the matplotlib idiom yticks([]).
    df = {"sample": ["S1", "S2", "S3", "S4"], "stage": [0.5] * 4}
    c = pt.chart(df, canvas_width=400, canvas_height=80, title="metadata strip",
                 ylabel="stage")
    c.bar(x="sample", y="stage", color="C1")
    c.ylim(0, 1)
    c.yticks([])
    return c


def chart_xticks_rotation():
    # Rotate category labels that would crowd horizontally.
    df = {"month": ["Jan", "Feb", "Mar", "Apr", "May"],
          "count": [12, 7, 19, 14, 9]}
    c = pt.chart(df, canvas_width=400, canvas_height=260,
                 title="rotated x labels", ylabel="count")
    c.bar(x="month", y="count", color="C0")
    c.xticks(rotation=45)
    return c


def chart_xticks_outward():
    # Tick marks point outward (matplotlib direction='out').
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    c = pt.chart(df, title="outward tick marks", xlabel="x", ylabel="y")
    c.line(x="x", y="y")
    c.xticks(direction="out")
    c.yticks(direction="out")
    return c


def chart_xticks_marks_off():
    # Hide tick marks but keep labels (compare to xticks([]) which hides both).
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    c = pt.chart(df, title="labels only, no tick marks", xlabel="x", ylabel="y")
    c.line(x="x", y="y")
    c.xticks(marks=False)
    c.yticks(marks=False)
    return c


def chart_xticks_explicit():
    # Explicit positions and labels, plus a fontsize override.
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    c = pt.chart(df, title="explicit ticks", xlabel="x", ylabel="y")
    c.line(x="x", y="y")
    c.xticks([0, math.pi, 2 * math.pi], ["0", "π", "2π"], fontsize=14)
    return c


def chart_category_padding_zero():
    # Contiguous track: cells butt up with no inner gap.
    df = {"x": ["a", "b", "c", "d", "e"], "v": [1, 2, 3, 2, 1]}
    c = pt.chart(df, canvas_width=400, canvas_height=120, title="padding=0 (contiguous)")
    c.xscale("category", padding=0)
    c.bar(x="x", y="v", color="C0")
    return c


def chart_reflines():
    xs = _xs()
    df = {"t": xs, "v": [math.sin(x) for x in xs]}
    c = pt.chart(df, title="reference lines",
                 xlabel="t", ylabel="v", legend=True, grid=True)
    c.axhspan(-0.5, 0.5, color="C2")
    c.axvspan(2.0, 3.5)
    c.line(x="t", y="v", label="sin(t)")
    c.axhline(0)
    c.axhline(0.8, color="red", linestyle="--", label="upper")
    c.axvline(math.pi, color="gray", linestyle=":")
    return c


PLOTS = {
    "table":               chart_table,
    "hue":                 chart_hue,
    "scatter_hue":         chart_scatter_hue,
    "bar":                 chart_bar,
    "hist":                chart_hist,
    "fill_between":        chart_fill_between,
    "reflines":            chart_reflines,
    "category_x_scatter":  chart_category_x_scatter,
    "category_x_order":    chart_category_x_order,
    "category_y_scatter":  chart_category_y_scatter,
    "category_y_order":    chart_category_y_order,
    "hide_yticks":         chart_hide_yticks,
    "xticks_rotation":     chart_xticks_rotation,
    "xticks_outward":      chart_xticks_outward,
    "xticks_marks_off":    chart_xticks_marks_off,
    "xticks_explicit":     chart_xticks_explicit,
    "category_padding_0":  chart_category_padding_zero,
    "imshow_rect":         chart_imshow_rect,
    "imshow_png":          chart_imshow_png,
    "imshow_diverging":    chart_imshow_diverging,
}


if __name__ == "__main__":
    sys.exit(_runner.run("chart", PLOTS))
