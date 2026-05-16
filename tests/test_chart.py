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


def chart_imshow_origin_upper():
    # origin="upper" opts into matrix-style display (row 0 at top). The
    # panel's y-axis auto-inverts so tick "0" lands at the top next to
    # row 0 — labels and image rows stay aligned, matching matplotlib.
    # Asymmetric ramp makes the flip vs. the default ("lower") obvious.
    data = [[r + 0.4 * c for c in range(20)] for r in range(15)]
    c = pt.chart(title="imshow origin='upper'", xlabel="x", ylabel="y")
    c.imshow(data, cmap="viridis", origin="upper",
             extent=(0, 20, 0, 15))
    return c


def chart_imshow_diverging_center():
    # Asymmetric range (-2 to 8) with center=0 — colorbar shows zero
    # pinned to the middle of the strip even though zero is far from
    # the geometric midpoint of [-2, 8]. Composed with pt.legend() so
    # the gradient strip (where the new norm shows up) is rendered.
    data = [[(r - 4) * 0.5 + (c - 4) * 0.7 for c in range(12)] for r in range(10)]
    c = pt.chart(title="imshow center=0", xlabel="x", ylabel="y")
    c.imshow(data, cmap="RdBu_r", center=0, vmin=-2, vmax=8,
             legend={"label": "value"})
    return c | pt.legend(c)


def chart_imshow_log_norm():
    # Multi-decade dynamic range — without log, all but the brightest
    # cells render near-black; with log, structure across decades shows.
    # Legend ticks are powers of 10.
    data = [[10 ** (0.05 * r + 0.05 * c) for c in range(20)] for r in range(15)]
    c = pt.chart(title="imshow norm='log'", xlabel="x", ylabel="y")
    c.imshow(data, cmap="magma", norm="log",
             legend={"label": "intensity"})
    return c | pt.legend(c)


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
    c = pt.chart(df, data_width=320, data_height=24, title="metadata strip",
                 ylabel="stage")
    c.bar(x="sample", y="stage", color="C1")
    c.ylim(0, 1)
    c.yticks([])
    return c


def chart_xticks_rotation():
    # Rotate category labels that would crowd horizontally.
    df = {"month": ["Jan", "Feb", "Mar", "Apr", "May"],
          "count": [12, 7, 19, 14, 9]}
    c = pt.chart(df, data_width=320, data_height=180,
                 title="rotated x labels", ylabel="count")
    c.bar(x="month", y="count", color="C0")
    c.xticks(rotation=45)
    return c


def chart_xticks_inward_full_frame():
    # Opt back into the legacy matplotlib look: inward ticks plus top/right
    # ticks enabled. Default is outward + bottom/left only.
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    c = pt.chart(df, title="inward ticks, full frame (legacy look)",
                 xlabel="x", ylabel="y")
    c.line(x="x", y="y")
    c.xticks(direction="in", top=True)
    c.yticks(direction="in", right=True)
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
    c = pt.chart(df, data_width=320, data_height=60, title="padding=0 (contiguous)")
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


def chart_long_title():
    # Title text wider than the data region: measure-driven margin grows
    # left and right so the centered title doesn't spill off-canvas.
    # data_width=180 is small; title is ~360 px wide → ~90 px overhang each side.
    c = pt.chart(data_width=180, data_height=140,
                 title="A very wide title that exceeds the data region width",
                 xlabel="x", ylabel="y")
    c.line([1, 2, 3, 4, 5], [1, 2, 4, 8, 16])
    return c


def chart_long_ylabel():
    # ylabel rendered rotated -90 around the data area's vertical center;
    # text longer than data_height spills past top and bottom. Margin
    # should grow on top *and* bottom by half the overhang.
    c = pt.chart(data_width=200, data_height=120,
                 ylabel="Gene expression (log10 normalized counts per million)",
                 xlabel="time")
    c.line([0, 1, 2, 3], [3.2, 4.1, 4.9, 5.5])
    return c


def chart_despined():
    # `c.spines(top=False, right=False)` mirrors matplotlib's despine. Tick
    # marks on hidden sides drop too — an unanchored stub reads as a render
    # bug. Tick labels (left/bottom) are unchanged.
    xs = _xs()
    df = {"t": xs, "v": [math.sin(x) for x in xs]}
    c = pt.chart(df, title="despined frame", xlabel="t", ylabel="v")
    c.line(x="t", y="v")
    c.spines(top=False, right=False)
    return c


def chart_restyled_spines():
    # Per-side dict syntax: visible by default, color/width override the
    # spec.json defaults. Tick marks adopt the same side's stroke for
    # visual consistency.
    xs = _xs()
    df = {"t": xs, "v": [math.sin(x) for x in xs]}
    c = pt.chart(df, title="restyled spines", xlabel="t", ylabel="v")
    c.line(x="t", y="v")
    c.spines(top=False, right=False,
             left={"color": "red", "width": 1.5},
             bottom={"color": "gray"})
    return c


def chart_hlines_vlines():
    # Bounded segment artists in data coordinates. Unlike axhline/axvline
    # they participate in autoscaling and use the color cycle.
    c = pt.chart(title="hlines / vlines", xlabel="x", ylabel="y", legend=True)
    c.hlines([1, 2, 3], 0, 5, label="thresholds", linestyle="--")
    c.vlines([1.5, 3.5], 0.5, 3.5, label="markers", color="C3")
    return c


def chart_text():
    # Data-anchored text labels. Single-point and batched-list forms.
    xs = [1, 2, 3, 4, 5]
    ys = [3, 7, 4, 9, 5]
    c = pt.chart(title="text annotations", xlabel="x", ylabel="y")
    c.scatter(xs, ys)
    c.text(xs, ys, ["A", "B", "C", "D", "E"], dy=-10, ha="center")
    c.text(3, 9.5, "peak", color="C3", ha="center")
    return c


def chart_errorbar():
    # Vertical + horizontal error bars, symmetric and asymmetric.
    xs = [1, 2, 3, 4, 5, 6]
    ys = [2.1, 3.4, 4.0, 3.8, 5.1, 6.2]
    yerr = [0.4, 0.3, 0.6, 0.5, 0.4, 0.7]
    c = pt.chart(title="error bars", xlabel="x", ylabel="y", legend=True)
    c.errorbar(xs, ys, yerr=yerr, label="measurement")
    c.errorbar([1.2, 2.2, 3.2, 4.2, 5.2, 6.2],
               [1.5, 2.6, 3.3, 4.7, 5.9, 6.8],
               yerr=([0.2, 0.3, 0.2, 0.4, 0.3, 0.5],
                     [0.5, 0.4, 0.6, 0.3, 0.5, 0.4]),
               marker="s", label="model")
    return c


def chart_plot_alpha():
    # alpha now propagates to both the stroke and (if present) markers.
    xs = _xs()
    df = {"t": xs, "v": [math.sin(x) for x in xs],
          "w": [math.cos(x) for x in xs]}
    c = pt.chart(df, title="plot alpha", xlabel="t", ylabel="value",
                 legend=True)
    c.line(x="t", y="v", alpha=0.3, label="alpha=0.3")
    c.line(x="t", y="w", alpha=1.0, label="alpha=1")
    return c


def chart_heatmap_labeled():
    # DataFrame-aware heatmap: explicit row/col labels via xticklabels /
    # yticklabels (no pandas dep in tests). Cells render at int+0.5 centers
    # on a linear axis with origin="upper" so row 0 lands at the top.
    data = [[math.sin(r * 0.6) * math.cos(c * 0.4) for c in range(8)]
            for r in range(6)]
    rows = [f"r{i}" for i in range(6)]
    cols = [f"c{i}" for i in range(8)]
    c = pt.chart(title="heatmap (labeled rows/cols)",
                 xlabel="condition", ylabel="sample")
    c.heatmap(data, xticklabels=cols, yticklabels=rows, cmap="viridis")
    return c


class _MockDF:
    # Tiny stand-in for a pandas DataFrame so the .values / .columns / .index
    # branch gets a baseline test without adding pandas as a test dep.
    def __init__(self, values, index, columns):
        self.values = values
        self.index = index
        self.columns = columns


def chart_heatmap_dataframe():
    rng = random.Random(1)
    n_rows, n_cols = 5, 7
    values = [[rng.gauss(0, 1) for _ in range(n_cols)] for _ in range(n_rows)]
    df = _MockDF(values,
                 index=[f"sample_{i}" for i in range(n_rows)],
                 columns=[f"feature_{j}" for j in range(n_cols)])
    c = pt.chart(title="heatmap (DataFrame branch, diverging cmap)")
    c.heatmap(df, cmap="bwr", center=0)
    c.xticks(rotation=45)
    return c


def chart_curve_steps():
    # All three step modes on the same axes, plus the default linear.
    # Markers stay at the original data points regardless of mode — they
    # mark where the values are; the step shape just chooses how to
    # connect them.
    xs = [0, 1, 2, 3, 4, 5]
    ys = [1, 3, 2, 5, 4, 6]
    c = pt.chart(title="curve= modes", xlabel="x", ylabel="y",
                 legend=True, grid=True)
    c.line(xs, ys, curve="linear",      marker="o", label="linear")
    c.line(xs, [v + 2 for v in ys],  curve="step-after",  marker="o", label="step-after")
    c.line(xs, [v + 4 for v in ys],  curve="step-before", marker="o", label="step-before")
    c.line(xs, [v + 6 for v in ys],  curve="step-mid",    marker="o", label="step-mid")
    return c


def chart_curve_fills():
    # curve= on fill_between and area. Use case: a sensor reading band
    # that holds between samples (step-after) — diagonal interpolation
    # would imply smooth transitions the data doesn't have.
    xs = [0, 1, 2, 3, 4, 5]
    lo = [0.5, 0.8, 1.2, 1.5, 1.1, 0.9]
    hi = [1.5, 1.8, 2.2, 2.5, 2.1, 1.9]
    c = pt.chart(title="curve= on fill_between / area",
                 xlabel="t", ylabel="value", legend=True)
    c.fill_between(xs, lo, hi, curve="step-after", color="C0",
                   alpha=0.3, label="step band")
    c.area(xs, [1.0, 1.3, 1.7, 2.0, 1.6, 1.4], curve="step-after",
           color="C1", alpha=0.5, label="step area")
    return c


def chart_rect():
    # Mixed scalar / list inputs — broadcast covers the genome-track,
    # gantt-style, and gene-model use cases that motivated adding rect.
    # Also exercises edgecolor + linewidth so the outline path is covered.
    c = pt.chart(title="rect (broadcast + edgecolor)",
                 xlabel="x", ylabel="y", legend=True)
    c.rect([0, 2, 4, 6], 0, [1.5, 1.5, 1.5, 1.5], 2, color="C0",
           alpha=0.6, label="intervals")
    c.rect(0.5, 2.5, 7, 1, color="C1", alpha=0.3,
           edgecolor="C3", linewidth=1.5, label="overlay")
    c.rect(3, 0.2, 1, 1.6, fill=False, edgecolor="black",
           linewidth=2, label="outline")
    return c


def chart_polygon():
    # Two polygons composed in one chart: a filled triangle (color cycle)
    # and an outlined diamond (fill=False). Polygon auto-closes — the
    # last vertex doesn't need to repeat the first.
    c = pt.chart(title="polygon", xlabel="x", ylabel="y", legend=True)
    c.polygon([0, 2, 1], [0, 0, 2], alpha=0.5, label="triangle")
    c.polygon([3, 4, 3, 2], [1, 2, 3, 2], fill=False, linewidth=2,
              label="diamond")
    return c


def chart_area():
    # Area under a curve (base=0, default) and area between a curve and
    # a non-zero baseline. Same artist, different `base=`.
    xs = _xs()
    c = pt.chart(title="area (base=0 and base=-0.5)",
                 xlabel="t", ylabel="y", legend=True)
    c.area(xs, [math.sin(x) for x in xs], color="C0", alpha=0.3,
           label="sin")
    c.area(xs, [math.cos(x) - 0.5 for x in xs], base=-0.5,
           color="C3", alpha=0.4, label="cos shifted")
    return c


def _dendro_sample():
    rng = random.Random(0)
    return [[rng.gauss(0, 1) for _ in range(4)] for _ in range(8)]


def chart_dendrogram_top():
    c = pt.chart(title="dendrogram (orient=top)", data_height=180)
    c.dendrogram(_dendro_sample(), method="ward")
    return c


def chart_dendrogram_left():
    c = pt.chart(title="dendrogram (orient=left)", data_width=240)
    c.dendrogram(_dendro_sample(), method="ward", orient="left")
    return c


def chart_dendrogram_styled():
    # Demonstrates the opt-in path: dendrogram's spineless default is
    # restored to a height axis. Also exercises color / linewidth kwargs.
    c = pt.chart(title="dendrogram with restored height axis",
                 ylabel="height", data_height=180)
    c.dendrogram(_dendro_sample(), method="average",
                 color="C3", linewidth=1.4)
    c.spines(left=True)
    c.yticks(None)
    return c


def chart_dendrogram_labeled():
    labels = ["sample_" + ch for ch in "ABCDEFGH"]
    c = pt.chart(title="dendrogram with labels", data_height=200)
    c.dendrogram(_dendro_sample(), method="ward", labels=labels)
    return c


def chart_long_rotated_xticks():
    # Long x-tick labels rotated 45° — the rotated bbox height grows the
    # bottom margin so labels don't overflow the canvas. Without rotation
    # they'd crowd horizontally; without measure-driven they'd spill past
    # the bottom edge.
    df = {"sample": ["sample_alpha_2024", "sample_beta_2024", "sample_gamma_2024",
                      "sample_delta_2024", "sample_epsilon_2024"],
          "count":  [12, 7, 19, 14, 9]}
    c = pt.chart(df, data_width=300, data_height=180,
                 title="long rotated x-tick labels", ylabel="count")
    c.bar(x="sample", y="count", color="C0")
    c.xticks(rotation=45)
    return c


def chart_ticks_step():
    c = pt.chart(data_width=400, data_height=170,
                 title="step=0.25", xlabel="x", ylabel="y", grid=True)
    c.line([0, 0.5, 1.0, 1.5, 2.0], [0, 1, 4, 9, 16], marker="o")
    c.xticks(step=0.25)
    return c


def chart_ticks_count():
    c = pt.chart(data_width=400, data_height=170,
                 title="count=4", xlabel="x", ylabel="y", grid=True)
    c.line(list(range(11)), [i * i for i in range(11)], marker="o")
    c.xticks(count=4)
    return c


def chart_minor_ticks_linear():
    c = pt.chart(data_width=400, data_height=180,
                 title="minor ticks", xlabel="x", ylabel="y", grid=True)
    c.line([0, 1, 2, 3, 4, 5], [0, 1, 4, 9, 16, 25], marker="o")
    c.xticks(minor=True)
    c.yticks(minor=True)
    return c


def chart_minor_ticks_log():
    c = pt.chart(data_width=400, data_height=180,
                 title="minor ticks log", xlabel="freq", ylabel="amp")
    c.line([1, 10, 100, 1000, 10000], [1, 5, 12, 25, 60], marker="o")
    c.xscale("log")
    c.xticks(minor=True)
    return c


def chart_reverse_y():
    # Reversed y axis: classic oceanography depth profile (0 on top).
    times = list(range(8))
    depths = [10, 28, 65, 130, 220, 360, 480, 620]
    c = pt.chart(data_width=320, data_height=180,
                 title="depth profile", xlabel="time", ylabel="depth (m)")
    c.line(times, depths, marker="o")
    c.yscale("linear", reverse=True)
    return c


def chart_sqrt_y():
    # sqrt scale on y compresses large counts while keeping small ones visible.
    c = pt.chart(data_width=320, data_height=180,
                 title="sqrt y", xlabel="bin", ylabel="count")
    c.bar(["A", "B", "C", "D", "E", "F", "G"], [1, 9, 25, 49, 100, 256, 484])
    c.yscale("sqrt")
    return c


def chart_symlog_x():
    # Symlog on x: spans both signs across many orders of magnitude, with
    # a linear band around 0. Volcano-style domains.
    xs = [-2000, -250, -25, -2, -0.5, 0, 0.5, 2, 25, 250, 2000]
    ys = [abs(x) ** 0.5 for x in xs]
    c = pt.chart(data_width=400, data_height=180,
                 title="symlog axis", xlabel="signed magnitude", ylabel="sqrt(|x|)")
    c.scatter(xs, ys, s=24)
    c.xscale("symlog", linthresh=1.0)
    return c


def chart_facet_scatter():
    # Facet by category: one panel per unique value, shared axes, titles
    # default to the group label.
    random.seed(11)
    species = ["setosa", "versicolor", "virginica"]
    n_each = 24
    df = {
        "bill_length": [random.gauss(5, 1) + i * 2 for i in range(3) for _ in range(n_each)],
        "bill_depth":  [random.gauss(3, 0.4) + i * 0.5 for i in range(3) for _ in range(n_each)],
        "species":     [s for s in species for _ in range(n_each)],
    }
    g = pt.facet(df, by="species", col_wrap=3,
                 data_width=180, data_height=140,
                 xlabel="bill_length", ylabel="bill_depth")
    g.scatter(x="bill_length", y="bill_depth", s=18)
    return g


def chart_facet_wrap_two_rows():
    # 5 groups + col_wrap=3 → 2x3 grid with one empty trailing cell.
    random.seed(12)
    groups = ["A", "B", "C", "D", "E"]
    n = 30
    df = {
        "x": [i * 0.2 for _ in groups for i in range(n)],
        "y": [math.sin(i * 0.2) * (1.0 + gi * 0.3) + random.uniform(-0.3, 0.3)
              for gi, _ in enumerate(groups) for i in range(n)],
        "g": [grp for grp in groups for _ in range(n)],
    }
    g = pt.facet(df, by="g", col_wrap=3,
                 data_width=160, data_height=110,
                 xlabel="x", ylabel="y")
    g.line(x="x", y="y")
    return g


def chart_scatter_size():
    # size= maps a numeric column to per-point area.
    random.seed(1)
    df = {
        "x":    list(range(40)),
        "y":    [math.sin(i / 5) + random.uniform(-0.2, 0.2) for i in range(40)],
        "mass": [abs(math.cos(i / 4)) * 50 + 5 for i in range(40)],
    }
    c = pt.chart(df, data_width=400, data_height=200,
                 title="bubble", xlabel="x", ylabel="y")
    c.scatter(x="x", y="y", size="mass", sizes=(15, 250))
    return c


def chart_scatter_size_style_hue():
    # size + style + hue compose. Each column drives a separate aesthetic.
    random.seed(2)
    n = 36
    groups = ["alpha", "beta", "gamma"]
    df = {
        "x":     [random.uniform(0, 10) for _ in range(n)],
        "y":     [random.uniform(0, 10) for _ in range(n)],
        "mass":  [random.uniform(5, 50) for _ in range(n)],
        "group": [groups[i % 3] for i in range(n)],
    }
    c = pt.chart(df, data_width=400, data_height=240,
                 title="hue + size + style", xlabel="x", ylabel="y",
                 legend=True)
    c.scatter(x="x", y="y", hue="group", size="mass", style="group")
    return c


def chart_tick_format_string():
    # Format string: '{:.0%}' renders y-ticks as percentages.
    c = pt.chart(data_width=320, data_height=180,
                 title="completion rate", xlabel="week", ylabel="rate")
    c.line(list(range(8)), [0.05, 0.12, 0.18, 0.27, 0.42, 0.55, 0.71, 0.88])
    c.yticks(format="{:.0%}")
    return c


def chart_tick_format_callable():
    # Callable format: turn dollars into compact K/M suffixed labels.
    def _money(v):
        if v >= 1_000_000: return f"${v/1_000_000:.1f}M"
        if v >= 1_000:     return f"${v/1_000:.0f}K"
        return f"${v:.0f}"
    c = pt.chart(data_width=320, data_height=180,
                 title="revenue", xlabel="month", ylabel="revenue")
    c.line(list(range(8)), [1200, 4500, 8300, 18000, 45000, 92000, 410000, 1_250_000])
    c.yticks(format=_money)
    return c


PLOTS = {
    "table":               chart_table,
    "hue":                 chart_hue,
    "scatter_hue":         chart_scatter_hue,
    "bar":                 chart_bar,
    "hist":                chart_hist,
    "fill_between":        chart_fill_between,
    "curve_steps":         chart_curve_steps,
    "curve_fills":         chart_curve_fills,
    "rect":                chart_rect,
    "polygon":             chart_polygon,
    "area":                chart_area,
    "reflines":            chart_reflines,
    "category_x_scatter":  chart_category_x_scatter,
    "category_x_order":    chart_category_x_order,
    "category_y_scatter":  chart_category_y_scatter,
    "category_y_order":    chart_category_y_order,
    "hide_yticks":         chart_hide_yticks,
    "xticks_rotation":     chart_xticks_rotation,
    "xticks_inward_full":  chart_xticks_inward_full_frame,
    "xticks_marks_off":    chart_xticks_marks_off,
    "xticks_explicit":     chart_xticks_explicit,
    "category_padding_0":  chart_category_padding_zero,
    "imshow_rect":         chart_imshow_rect,
    "imshow_png":          chart_imshow_png,
    "imshow_diverging":    chart_imshow_diverging,
    "imshow_origin_upper": chart_imshow_origin_upper,
    "imshow_center":       chart_imshow_diverging_center,
    "imshow_log":          chart_imshow_log_norm,
    "heatmap_labeled":     chart_heatmap_labeled,
    "heatmap_dataframe":   chart_heatmap_dataframe,
    "long_title":          chart_long_title,
    "long_ylabel":         chart_long_ylabel,
    "long_rotated_xticks": chart_long_rotated_xticks,
    "despined":            chart_despined,
    "restyled_spines":     chart_restyled_spines,
    "hlines_vlines":       chart_hlines_vlines,
    "text":                chart_text,
    "errorbar":            chart_errorbar,
    "plot_alpha":          chart_plot_alpha,
    "dendrogram_top":      chart_dendrogram_top,
    "dendrogram_left":     chart_dendrogram_left,
    "dendrogram_styled":   chart_dendrogram_styled,
    "dendrogram_labeled":  chart_dendrogram_labeled,
    "tick_format_string":  chart_tick_format_string,
    "tick_format_callable": chart_tick_format_callable,
    "scatter_size":        chart_scatter_size,
    "scatter_size_style_hue": chart_scatter_size_style_hue,
    "facet_scatter":       chart_facet_scatter,
    "facet_wrap_two_rows": chart_facet_wrap_two_rows,
    "symlog_x":            chart_symlog_x,
    "sqrt_y":              chart_sqrt_y,
    "reverse_y":           chart_reverse_y,
    "minor_ticks_linear":  chart_minor_ticks_linear,
    "minor_ticks_log":     chart_minor_ticks_log,
    "ticks_step":          chart_ticks_step,
    "ticks_count":         chart_ticks_count,
}


if __name__ == "__main__":
    sys.exit(_runner.run("chart", PLOTS))
