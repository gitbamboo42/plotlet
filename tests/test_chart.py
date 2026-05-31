"""Baseline SVG regression tests for the `pt.chart(df, ...)` API.

    pytest tests/test_chart.py           # check vs. baselines
    pytest tests/test_chart.py --update  # regenerate baselines (review diff!)
    python tests/gen_gallery.py chart    # write baseline_images/chart/index.html

The compare/update plumbing lives in `conftest.py`'s `baseline_compare`
fixture; gallery emission is a separate script.
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


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


def chart_color():
    xs = _xs()
    n = len(xs)
    df = {
        "t":      xs + xs,
        "v":      [math.sin(x) for x in xs] + [math.cos(x) for x in xs],
        "series": ["sin"] * n + ["cos"] * n,
    }
    c = pt.chart(df, title="color split",
                 xlabel="t", ylabel="v", legend=True, grid=True)
    c.line(x="t", y="v", color="series")
    return c


def chart_scatter_color():
    rng = random.Random(0)
    n = 60
    df = {
        "x":     [rng.random() * 10 for _ in range(2 * n)],
        "y":     [rng.random() * 10 for _ in range(2 * n)],
        "group": ["A"] * n + ["B"] * n,
    }
    c = pt.chart(df, title="scatter color",
                 xlabel="x", ylabel="y", legend=True, grid=True)
    c.scatter(x="x", y="y", color="group", s=30, alpha=0.6)
    return c


def chart_bar():
    df = {"category": ["A", "B", "C", "D", "E"], "count": [4, 7, 2, 9, 5]}
    c = pt.chart(df, title="bar from table", ylabel="count")
    c.bar(x="category", y="count", fill="C0")
    return c


def chart_hist():
    rng = random.Random(7)
    df = {"value": [rng.gauss(0, 1) for _ in range(2000)]}
    c = pt.chart(df, title="histogram from table",
                 xlabel="value", ylabel="count")
    c.hist(x="value", bins=30, fill="C2")
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
    c.fill_between(x="x", y1="lo", y2="hi", fill="C0", alpha=0.25, label="band")
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
    # the geometric midpoint of [-2, 8]. Explicit position="left" also
    # exercises the inline-colorbar left-side tick rendering.
    data = [[(r - 4) * 0.5 + (c - 4) * 0.7 for c in range(12)] for r in range(10)]
    c = pt.chart(title="imshow center=0", xlabel="x", ylabel="y")
    c.imshow(data, cmap="RdBu_r", center=0, vmin=-2, vmax=8,
             legend={"label": "value"})
    c.legend(True, position="left")
    return c


def chart_imshow_log_norm():
    # Multi-decade dynamic range — without log, all but the brightest
    # cells render near-black; with log, structure across decades shows.
    # Legend ticks are powers of 10. Default position="inside" auto-flips
    # to "right" for gradient-bearing charts (an inside colorbar is
    # incoherent), so this exercises the auto-flip path.
    data = [[10 ** (0.05 * r + 0.05 * c) for c in range(20)] for r in range(15)]
    c = pt.chart(title="imshow norm='log'", xlabel="x", ylabel="y")
    c.imshow(data, cmap="magma", norm="log",
             legend={"label": "intensity"})
    c.legend(True)
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
    c.bar(x="sample", y="count", fill="C2")
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
    c.bar(x="sample", y="stage", fill="C1")
    c.ylim(0, 1)
    c.yticks([])
    return c


def chart_xticks_rotation():
    # Rotate category labels that would crowd horizontally.
    df = {"month": ["Jan", "Feb", "Mar", "Apr", "May"],
          "count": [12, 7, 19, 14, 9]}
    c = pt.chart(df, data_width=320, data_height=180,
                 title="rotated x labels", ylabel="count")
    c.bar(x="month", y="count", fill="C0")
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
    c.bar(x="x", y="v", fill="C0")
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
    # should grow on top *and* bottom by half the overhang. Title is
    # included so we can verify the vertical overhang doesn't displace
    # the title from its natural slot above the data area.
    c = pt.chart(data_width=200, data_height=120,
                 title="long ylabel + title",
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
    # Vertical error bars: symmetric (column) and asymmetric (tuple of columns).
    df_meas = {"x": [1, 2, 3, 4, 5, 6],
               "y": [2.1, 3.4, 4.0, 3.8, 5.1, 6.2],
               "sd": [0.4, 0.3, 0.6, 0.5, 0.4, 0.7]}
    df_model = {"x": [1.2, 2.2, 3.2, 4.2, 5.2, 6.2],
                "y": [1.5, 2.6, 3.3, 4.7, 5.9, 6.8],
                "lo": [0.2, 0.3, 0.2, 0.4, 0.3, 0.5],
                "hi": [0.5, 0.4, 0.6, 0.3, 0.5, 0.4]}
    c = pt.chart(title="error bars", xlabel="x", ylabel="y", legend=True)
    c.errorbar(data=df_meas, x="x", y="y", yerr="sd", label="measurement")
    c.errorbar(data=df_model, x="x", y="y", yerr=("lo", "hi"),
               marker="s", label="model")
    return c


def chart_errorbar_category_x():
    # Categorical x + numeric yerr — common "bar with error bars" pattern.
    df = {"cat":  ["control", "low", "mid", "high"],
          "mean": [2.1, 3.4, 4.6, 5.2],
          "sd":   [0.3, 0.4, 0.5, 0.6]}
    c = pt.chart(title="dose response", xlabel="dose", ylabel="response")
    c.bar(data=df, x="cat", y="mean", fill="#cccccc")
    c.errorbar(data=df, x="cat", y="mean", yerr="sd")
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


def chart_heatmap_annot():
    # annot=True overlays each cell's value; annot_color="auto" picks
    # white text on dark cells, black on light, via luminance. Inline
    # colorbar via chart.legend(True) — auto-flips inside → right for
    # the gradient — the canonical correlation-matrix look without the
    # composition workaround.
    n = 6
    data = [[math.cos((i - j) * 0.4) for j in range(n)] for i in range(n)]
    labels = [f"v{i}" for i in range(n)]
    c = pt.chart(title="correlation matrix (annot=True)")
    c.heatmap(data, xticklabels=labels, yticklabels=labels,
              cmap="RdBu_r", vmin=-1, vmax=1, annot=True, fmt="+.2f",
              legend={"label": "corr"})
    c.legend(True)
    return c


def chart_heatmap_categorical():
    genes   = ["TP53", "KRAS", "EGFR", "BRAF", "PIK3CA"]
    samples = ["S1", "S2", "S3", "S4", "S5", "S6"]
    matrix = [
        ["Missense", "WT",        "Frameshift", "WT",        "Missense", None      ],
        ["WT",       "Nonsense",  "WT",          "Missense",  "WT",       "CNV"     ],
        ["CNV",      "WT",        "WT",          "CNV",       "Nonsense", "WT"      ],
        ["WT",       "Missense",  "CNV",         None,        "WT",       "Missense"],
        ["Nonsense", "CNV",       "Missense",    "Frameshift","WT",       "WT"      ],
    ]
    palette = {
        "WT":         "#e8e8e8",
        "Missense":   "#3a6dbf",
        "Nonsense":   "#c0392b",
        "Frameshift": "#e67e22",
        "CNV":        "#27ae60",
    }
    c = pt.chart(title="heatmap (categorical palette, absent=grey)",
                 xlabel="sample", ylabel="gene")
    c.heatmap(matrix, xticklabels=samples, yticklabels=genes,
              palette=palette, absent_fill="#dddddd")
    c.xticks(rotation=45)
    c.legend(position="right")
    return c


def chart_heatmap_nan():
    import math
    cols = ["A", "B", "C", "D"]
    rows = ["r1", "r2", "r3"]
    matrix = [
        [1.0,       float("nan"), 3.0,  None],
        [None,      2.0,          None, 4.0 ],
        [float("nan"), 1.5,       2.5,  None],
    ]
    c = pt.chart(title="heatmap (NaN/None → absent_fill)")
    c.heatmap(matrix, xticklabels=cols, yticklabels=rows,
              cmap="viridis", absent_fill="#ff9999")
    return c


def chart_split_rect():
    # Row 1 "sym":     n=1..8, symmetric=True  — cuts land on corners.
    # Row 2 "n":       n=1..8, symmetric=False — equal arc length.
    # Row 3 "rotate":  n=4, start sweeps 0..7/8.
    # Row 4 "weights": n=4, first sector weight grows 1..8.
    from plotlet import draw
    from plotlet.registry import ArtistSpec, add_artist

    _SR_COLORS = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
                  "#59a14f", "#edc948", "#b07aa1", "#ff9da7"]
    _COLS = [str(k) for k in range(8)]
    _ROWS = ["sym", "n", "rotate", "weights"]

    def _sr_record(args, kw):
        return {"type": "split_rect_demo", "opts": kw}

    def _sr_xdomain(a): return _COLS
    def _sr_ydomain(a): return _ROWS

    def _sr_draw(a, ctx):
        out = []
        bw = ctx.x_scale.bandwidth
        bh = ctx.y_scale.bandwidth
        for k, col in enumerate(_COLS):
            cx = ctx.x_scale(col)
            for row in _ROWS:
                cy = ctx.y_scale(row)
                px, py = cx - bw / 2, cy - bh / 2
                if row == "sym":
                    n = k + 1
                    for i in range(n):
                        out.append(draw.split_rect(
                            px, py, bw, bh, n, i,
                            fill=_SR_COLORS[i % len(_SR_COLORS)], padding=2,
                            symmetric=True))
                elif row == "n":
                    n = k + 1
                    for i in range(n):
                        out.append(draw.split_rect(
                            px, py, bw, bh, n, i,
                            fill=_SR_COLORS[i % len(_SR_COLORS)], padding=2))
                elif row == "rotate":
                    for i in range(4):
                        out.append(draw.split_rect(
                            px, py, bw, bh, 4, i,
                            fill=_SR_COLORS[i], padding=2, start=k / 8))
                elif row == "weights":
                    wts = [k + 1, 1, 1, 1]
                    for i in range(4):
                        out.append(draw.split_rect(
                            px, py, bw, bh, 4, i,
                            fill=_SR_COLORS[i], padding=2, weights=wts))
        return "".join(out)

    add_artist(ArtistSpec(
        name="split_rect_demo",
        record=_sr_record,
        xdomain=_sr_xdomain,
        ydomain=_sr_ydomain,
        draw=_sr_draw,
    ))
    c = pt.chart(data_width=480, data_height=280,
                 title="draw.split_rect — symmetric / arc / rotate / weights")
    c.split_rect_demo()
    c.xticks(marks=False)
    c.yticks(marks=False)
    return c


def chart_split_pie():
    # Row 1 "n":       n=1..8 equal sectors.
    # Row 2 "rotate":  n=4, start sweeps 0..7/8.
    # Row 3 "weights": n=4, first sector weight grows 1..8.
    # Row 4 "gap":     n=4, gap grows 0..14°.
    from plotlet import draw
    from plotlet.registry import ArtistSpec, add_artist

    _SP_COLORS = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
                  "#59a14f", "#edc948", "#b07aa1", "#ff9da7"]
    _COLS = [str(k) for k in range(8)]
    _ROWS = ["n", "rotate", "weights", "gap"]

    def _sp_record(args, kw):
        return {"type": "split_pie_demo", "opts": kw}

    def _sp_xdomain(a): return _COLS
    def _sp_ydomain(a): return _ROWS

    def _sp_draw(a, ctx):
        out = []
        bw = ctx.x_scale.bandwidth
        bh = ctx.y_scale.bandwidth
        for k, col in enumerate(_COLS):
            cx = ctx.x_scale(col)
            for row in _ROWS:
                cy = ctx.y_scale(row)
                px, py = cx - bw / 2, cy - bh / 2
                if row == "n":
                    n = k + 1
                    for i in range(n):
                        out.append(draw.split_pie(
                            px, py, bw, bh, n, i,
                            fill=_SP_COLORS[i % len(_SP_COLORS)], padding=2))
                elif row == "rotate":
                    for i in range(4):
                        out.append(draw.split_pie(
                            px, py, bw, bh, 4, i,
                            fill=_SP_COLORS[i], padding=2, start=k / 8))
                elif row == "weights":
                    wts = [k + 1, 1, 1, 1]
                    for i in range(4):
                        out.append(draw.split_pie(
                            px, py, bw, bh, 4, i,
                            fill=_SP_COLORS[i], padding=2, weights=wts))
                elif row == "gap":
                    for i in range(4):
                        out.append(draw.split_pie(
                            px, py, bw, bh, 4, i,
                            fill=_SP_COLORS[i], padding=2, gap=k * 2))
        return "".join(out)

    add_artist(ArtistSpec(
        name="split_pie_demo",
        record=_sp_record,
        xdomain=_sp_xdomain,
        ydomain=_sp_ydomain,
        draw=_sp_draw,
    ))
    c = pt.chart(data_width=480, data_height=280,
                 title="draw.split_pie — n / rotate / weights / gap")
    c.split_pie_demo()
    c.xticks(marks=False)
    c.yticks(marks=False)
    return c


def chart_imshow_annot_custom():
    # annot=<2D array> for independent labels; annot_color fixed.
    # Mixes numbers (formatted via fmt) and strings (verbatim).
    data = [[i + j for j in range(4)] for i in range(3)]
    annot = [["a", "b", "c", "d"],
             [1.0, 2.5, 3.75, 4.125],
             ["x", "y", "z", "w"]]
    c = pt.chart(title="imshow (custom annot, fixed color)")
    c.imshow(data, cmap="viridis", origin="upper",
             annot=annot, fmt=".1f", annot_color="#222222", annot_fontsize=12)
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
    c.fill_between(xs, lo, hi, curve="step-after", fill="C0",
                   alpha=0.3, label="step band")
    df_area = {"x": xs, "y": [1.0, 1.3, 1.7, 2.0, 1.6, 1.4]}
    c.area(data=df_area, x="x", y="y", curve="step-after",
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
    df = {"t": xs,
          "sin": [math.sin(x) for x in xs],
          "cos_shifted": [math.cos(x) - 0.5 for x in xs]}
    c = pt.chart(title="area (base=0 and base=-0.5)",
                 xlabel="t", ylabel="y", legend=True)
    c.area(data=df, x="t", y="sin", color="C0", alpha=0.3, label="sin")
    c.area(data=df, x="t", y="cos_shifted", base=-0.5,
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
    c.xticks(rotation=90)
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
    c.bar(x="sample", y="count", fill="C0")
    c.xticks(rotation=45)
    return c


def chart_xticks_fontstyle_italic():
    # Common bio convention: gene names rendered in italics. DejaVu Sans
    # ships no real italic, so plotlet synthesizes a -12° oblique skew at
    # render time (same approach matplotlib uses).
    df = {"gene": ["TP53", "KRAS", "BRAF", "PIK3CA", "EGFR"],
          "mut_rate": [0.42, 0.35, 0.28, 0.21, 0.18]}
    c = pt.chart(data_width=320, data_height=200,
                 title="italic gene names", ylabel="mut rate")
    c.bar(data=df, x="gene", y="mut_rate", fill="#5599aa")
    c.xticks(fontstyle="italic")
    return c


def chart_xticks_decoration():
    # CSS-style text-decoration on tick labels: underline / line-through /
    # overline. Each is rendered as a stroke line at the conventional
    # offset relative to the baseline / cap-top.
    df = {"cat": ["under", "strike", "over"], "val": [3, 4, 5]}
    c = pt.chart(data_width=260, data_height=160,
                 title="tick label decorations")
    c.bar(data=df, x="cat", y="val", fill="#5599aa")
    # Single-axis-wide style; mixing three on one chart isn't currently
    # supported (would need per-tick override).
    c.xticks(decoration="underline")
    c.yticks(decoration="line-through")
    return c


def chart_xticks_rotation_negative():
    # Negative rotation (CW on screen) — labels must extend BELOW the
    # tick into the bottom margin, not upward into the data area. Older
    # behavior used anchor="end" for all rotations, which pushed CW-
    # rotated labels into the chart body.
    df = {"sample": ["Sample-1", "Sample-2", "Sample-3", "Sample-4"],
          "value":  [10, 20, 15, 25]}
    c = pt.chart(data_width=300, data_height=180,
                 title="negative rotation stays below data",
                 xlabel="samples", ylabel="value")
    c.bar(data=df, x="sample", y="value", fill="#888")
    c.xticks(rotation=-90)
    return c


def chart_clip_data_area():
    # clip=False with full spines so the bleeding is visible — most
    # markers sit inside the data area, but a handful near the
    # upper-right edges extend past the spines into the margin space.
    # The default clip=True crops those halves at the data boundary.
    random.seed(3)
    n = 24
    xs = [random.uniform(0.5, 9.5) for _ in range(n)]
    ys = [random.uniform(0.5, 9.5) for _ in range(n)]
    sizes = [random.uniform(200, 400) for _ in range(n)]
    # Deliberate bleeders along the upper-right edges.
    xs    += [9.7, 9.5, 9.8, 8.6, 7.4]
    ys    += [9.5, 9.8, 7.4, 9.7, 9.5]
    sizes += [700, 800, 650, 750, 650]
    c = pt.chart(data_width=320, data_height=240, clip=False,
                 title="clip=False",
                 xlabel="x", ylabel="y",
                 xlim=(0, 10), ylim=(0, 10))
    c.scatter(xs, ys, s=sizes, color="C0", alpha=0.6)
    return c


def chart_inset_zoom():
    # Long-tail bar distribution: the first two categories dwarf the rest,
    # making the tail unreadable in the parent. The inset shows only the
    # tail (C through J) at a zoomed y-range so those bars become legible.
    labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    counts = [950, 320, 80, 45, 28, 18, 12, 8, 5, 3]
    df = {"category": labels, "count": counts}
    df_tail = {"category": labels[2:], "count": counts[2:]}
    c = pt.chart(data_width=440, data_height=240,
                 title="long-tail distribution",
                 xlabel="category", ylabel="count")
    c.bar(data=df, x="category", y="count")
    inset = c.inset(rect=(0.4, 0.45, 0.55, 0.45),
                    ylim=(0, 100))
    inset.bar(data=df_tail, x="category", y="count")
    return c


def chart_step():
    # step() sugar — all three where= modes.
    xs = list(range(8))
    c = pt.chart(data_width=400, data_height=180,
                 title="step modes", xlabel="x", ylabel="y", legend=True)
    c.step(xs, [1, 3, 2, 5, 4, 3, 6, 5], where="post", label="post")
    c.step(xs, [1.5, 3.5, 2.5, 5.5, 4.5, 3.5, 6.5, 5.5], where="pre",
           label="pre", color="C1")
    c.step(xs, [2, 4, 3, 6, 5, 4, 7, 6], where="mid", label="mid", color="C2")
    return c


def chart_text_bbox():
    # Text labels with a background box — readable over dense data.
    xs = [i * 0.1 for i in range(120)]
    ys = [math.sin(x * 3) * math.exp(-x * 0.1) for x in xs]
    c = pt.chart(data_width=420, data_height=200, title="text bbox",
                 xlabel="t", ylabel="y")
    c.line(xs, ys)
    c.text(2.0, 0.5, "plain", fontsize=12)
    c.text(4.0, 0.5, "on white", fontsize=12, bbox=True)
    c.text(6.0, 0.5, "tinted", fontsize=12,
           bbox={"facecolor": "#ffe", "edgecolor": "#888", "pad": 4, "alpha": 0.95})
    c.annotate("peak", xy=(xs[3], ys[3]), xytext=(0.6, 0.85),
               bbox={"facecolor": "#fff", "edgecolor": "#555", "pad": 3})
    return c


def chart_annotate():
    # Text label + arrow to a data point. Both endpoints in data coords.
    xs = [i * 0.2 for i in range(40)]
    ys = [math.sin(x) + math.sin(2 * x) * 0.4 for x in xs]
    c = pt.chart(data_width=400, data_height=200,
                 title="annotate", xlabel="x", ylabel="y")
    c.line(xs, ys)
    max_i = ys.index(max(ys))
    c.annotate("global max",
               xy=(xs[max_i], ys[max_i]),
               xytext=(xs[max_i] + 1.5, ys[max_i] + 0.3))
    c.annotate("first zero",
               xy=(math.pi, 0),
               xytext=(math.pi - 2, 0.6), ha="center")
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
    df = {"bin": ["A", "B", "C", "D", "E", "F", "G"],
          "count": [1, 9, 25, 49, 100, 256, 484]}
    c = pt.chart(data_width=320, data_height=180,
                 title="sqrt y", xlabel="bin", ylabel="count")
    c.bar(data=df, x="bin", y="count")
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


def chart_scatter_size_style_color():
    # size + style + color compose. Each column drives a separate aesthetic.
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
                 title="color + size + style", xlabel="x", ylabel="y",
                 legend=True)
    c.scatter(x="x", y="y", color="group", size="mass", style="group")
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


def chart_time_axis_dates():
    # Auto-detect: date values on x → time scale, calendar-aligned ticks.
    dates = [datetime.date(2024, 1, 1) + datetime.timedelta(days=30 * i) for i in range(12)]
    vals  = [10, 12, 9, 15, 18, 22, 25, 21, 17, 14, 12, 11]
    c = pt.chart(data_width=400, data_height=180,
                 title="2024 monthly units", ylabel="units", grid=True)
    c.line(dates, vals, marker="o")
    return c


def chart_time_axis_hours():
    # Hour-resolution datetimes on the y-axis — labels stack vertically so a
    # full day's worth of "HH:MM" ticks have room without rotation.
    base = datetime.datetime(2024, 6, 1, 0, 0, tzinfo=datetime.timezone.utc)
    times = [base + datetime.timedelta(hours=i) for i in range(0, 25, 2)]
    vals  = [math.sin(i / 4) * 5 + 10 for i in range(len(times))]
    c = pt.chart(data_width=220, data_height=320,
                 title="signal over a day", xlabel="value", ylabel="time (UTC)")
    c.line(vals, times)
    return c


def chart_boxplot():
    rng = random.Random(0)
    rows = []
    for group in ("ctrl", "low", "mid", "high"):
        for trt, shift in (("A", 0.0), ("B", 1.4)):
            mu = {"ctrl": 5, "low": 6, "mid": 7.5, "high": 9}[group] + shift
            sd = {"ctrl": 1, "low": 1.2, "mid": 1.5, "high": 1.8}[group]
            for _ in range(30):
                rows.append({"group": group, "trt": trt,
                             "score": rng.gauss(mu, sd)})
    rows += [{"group": "low", "trt": "A", "score": 12},
             {"group": "high", "trt": "B", "score": 16}]
    data = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=380, data_height=220,
                 title="boxplot fill", xlabel="group", ylabel="score",
                 legend=True)
    c.xscale("category", order=["ctrl", "low", "mid", "high"])
    c.boxplot(data=data, x="group", y="score", fill="trt",
              palette={"A": "#3F97C5", "B": "#F99917"})
    c.legend(position="right")
    return c


def chart_violin():
    rng = random.Random(1)
    rows = []
    for genotype in ("wt", "+drug", "ko", "rescue"):
        for trt, shift in (("A", 0.0), ("B", 1.2)):
            mu = {"wt": 5, "+drug": 4, "ko": 7, "rescue": 5.5}[genotype] + shift
            sd = {"wt": 1, "+drug": 0.8, "ko": 1.4, "rescue": 1.0}[genotype]
            for _ in range(80):
                rows.append({"geno": genotype, "trt": trt,
                             "expr": rng.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=380, data_height=220,
                 title="violin fill", xlabel="genotype", ylabel="expression",
                 legend=True)
    c.xscale("category", order=["wt", "+drug", "ko", "rescue"])
    c.violin(data=data, x="geno", y="expr", fill="trt",
             palette={"A": "#3F97C5", "B": "#F99917"}, inner="box")
    c.legend(position="right")
    return c


def chart_swarm():
    rng = random.Random(2)
    rows = []
    for group in ("A", "B", "C", "D"):
        for trt, shift in (("ctrl", 0.0), ("dose", 0.8)):
            mu = {"A": 3.0, "B": 4.5, "C": 5.2, "D": 6.0}[group] + shift
            sd = {"A": 0.6, "B": 0.7, "C": 0.5, "D": 0.9}[group]
            for _ in range(20):
                rows.append({"group": group, "trt": trt,
                             "value": rng.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=360, data_height=220,
                 title="swarm fill", xlabel="group", ylabel="value",
                 legend=True)
    c.xscale("category", order=["A", "B", "C", "D"])
    c.swarm(data=data, x="group", y="value", fill="trt",
            palette={"ctrl": "#3F97C5", "dose": "#F99917"})
    c.legend(position="right")
    return c


def chart_strip():
    rng = random.Random(3)
    rows = []
    for cond in ("A", "B", "C", "D"):
        for trt, shift in (("ctrl", 0.0), ("dose", 0.8)):
            mu = {"A": 3.0, "B": 4.5, "C": 5.2, "D": 6.1}[cond] + shift
            sd = {"A": 0.8, "B": 1.0, "C": 0.6, "D": 1.2}[cond]
            for _ in range(25):
                rows.append({"cond": cond, "trt": trt,
                             "value": rng.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=360, data_height=220,
                 title="strip fill", xlabel="condition", ylabel="value",
                 legend=True)
    c.xscale("category", order=["A", "B", "C", "D"])
    c.strip(data=data, x="cond", y="value", fill="trt",
            palette={"ctrl": "#3F97C5", "dose": "#F99917"})
    c.legend(position="right")
    return c


def chart_pointplot():
    rng = random.Random(7)
    cats = ["1 wk", "2 wk", "4 wk", "8 wk"]
    # Generate values in the same RNG order as the original wide-form to
    # preserve byte-identical baselines.
    ctrl_t, ctrl_score = [], []
    for i, t in enumerate(cats):
        for _ in range(20):
            ctrl_t.append(t); ctrl_score.append(rng.gauss(5.0 + 0.04 * i, 1.0))
    drug_t, drug_score = [], []
    for i, t in enumerate(cats):
        for _ in range(20):
            drug_t.append(t); drug_score.append(rng.gauss(5.0 + 0.45 * i, 1.0))
    c = pt.chart(data_width=320, data_height=200,
                 title="pointplot", xlabel="timepoint", ylabel="score",
                 legend=True)
    c.xscale("category", order=cats)
    c.pointplot(data={"t": ctrl_t, "score": ctrl_score},
                x="t", y="score", label="control")
    c.pointplot(data={"t": drug_t, "score": drug_score},
                x="t", y="score", label="drug")
    c.legend(position="right")
    return c


def chart_ecdf():
    rng = random.Random(8)
    a = [rng.gauss(0, 1) for _ in range(200)]
    b = [rng.gauss(0.6, 1.3) for _ in range(200)]
    c = pt.chart(data_width=300, data_height=200,
                 title="ECDF", xlabel="value", ylabel="F̂(x)",
                 legend=True)
    c.ecdf(a, label="control")
    c.ecdf(b, label="treatment")
    c.legend(position="right")
    return c


def chart_rug():
    rng = random.Random(9)
    vals = [rng.gauss(0, 1) for _ in range(150)]
    c = pt.chart(data_width=300, data_height=200,
                 title="density + rug", xlabel="value", ylabel="density")
    c.density_1d(vals, fill=True)
    c.rug(vals, color="#444444")
    return c


def chart_density_1d():
    rng = random.Random(10)
    a = [rng.gauss(0, 1) for _ in range(300)]
    b = [rng.gauss(1.2, 1.3) for _ in range(300)]
    c = pt.chart(data_width=300, data_height=200,
                 title="density", xlabel="value", ylabel="density",
                 legend=True)
    c.density_1d(a, label="control", fill=True)
    c.density_1d(b, label="treatment", fill=True)
    c.legend(position="right")
    return c


def chart_regression():
    rng = random.Random(11)
    xs = [i * 0.5 for i in range(40)]
    ys = [1.2 + 0.7 * x + rng.gauss(0, 1.0) for x in xs]
    c = pt.chart(data_width=300, data_height=220,
                 title="linear regression", xlabel="x", ylabel="y",
                 legend=True)
    c.scatter(xs, ys, label="data")
    c.regression(xs, ys, label="fit ± 95 % CI")
    c.legend(position="right")
    return c


def chart_kde_2d():
    rng = random.Random(12)
    n = 200
    xs = ([rng.gauss(-1, 0.7) for _ in range(n)]
          + [rng.gauss(1.2, 1.0) for _ in range(n)])
    ys = ([rng.gauss(0, 1.0) for _ in range(n)]
          + [rng.gauss(2, 0.8) for _ in range(n)])
    c = pt.chart(data_width=300, data_height=260,
                 title="2-D KDE", xlabel="x", ylabel="y")
    c.scatter(xs, ys, s=5, alpha=0.25, color="#444444")
    c.kde_2d(xs, ys, n_grid=40, cmap="viridis")
    return c


def chart_hexbin():
    rng = random.Random(13)
    n = 3000
    xs = [rng.gauss(0, 1) + rng.gauss(0, 0.4) for _ in range(n)]
    ys = [x + rng.gauss(0, 1) for x in xs]
    c = pt.chart(data_width=300, data_height=260,
                 title="hexbin", xlabel="x", ylabel="y")
    c.hexbin(xs, ys, gridsize=22)
    return c | pt.legend(c)


def chart_freqpoly():
    rng = random.Random(14)
    a = [rng.gauss(0, 1) for _ in range(400)]
    b = [rng.gauss(1, 1.4) for _ in range(400)]
    c = pt.chart(data_width=300, data_height=200,
                 title="frequency polygon", xlabel="value", ylabel="count",
                 legend=True)
    c.freqpoly(a, bins=25, label="control")
    c.freqpoly(b, bins=25, label="treatment")
    c.legend(position="right")
    return c


def chart_contour():
    import math
    n = 60
    grid = []
    for i in range(n):
        row = []
        for j in range(n):
            x = -3 + 6 * j / (n - 1)
            y = -3 + 6 * i / (n - 1)
            v = (math.exp(-(x * x + 1.5 * y * y) / 2)
                 + 0.5 * math.exp(-((x - 1.5) ** 2 + (y + 1.5) ** 2) / 0.6))
            row.append(v)
        grid.append(row)
    c = pt.chart(data_width=300, data_height=300,
                 title="contour", xlabel="x", ylabel="y")
    c.contour(grid, extent=(-3, 3, -3, 3), cmap="viridis",
              levels=[0.05, 0.1, 0.2, 0.4, 0.6, 0.8])
    return c


def chart_ridge():
    rng = random.Random(15)
    labels = ["Jan", "Feb", "Mar", "Apr", "May"]
    rows_label, rows_value = [], []
    for i, lbl in enumerate(labels):
        for _ in range(200):
            rows_label.append(lbl)
            rows_value.append(rng.gauss(20 + i, 3))
    df = {"month": rows_label, "value": rows_value}
    c = pt.chart(data_width=320, data_height=260,
                 title="ridge", xlabel="value")
    c.ridge(data=df, x="month", y="value", overlap=1.6)
    c.yticks([])
    return c


def chart_qq():
    rng = random.Random(16)
    sample = [rng.gauss(0, 1) + 0.2 * (rng.expovariate(1) - 1)
              for _ in range(150)]
    c = pt.chart(data_width=280, data_height=240,
                 title="Q-Q vs N(0, 1)",
                 xlabel="theoretical quantile",
                 ylabel="sample quantile")
    c.qq(sample, dist="normal")
    return c


def _bar_quarterly_df():
    cats = ["Q1", "Q2", "Q3", "Q4"]
    labels = ["A", "B", "C"]
    series = [
        [12, 18, 15, 22],
        [ 8, 14, 16, 18],
        [ 5,  7,  9, 11],
    ]
    rows = []
    for i, cat in enumerate(cats):
        for j, lbl in enumerate(labels):
            rows.append({"quarter": cat, "series": lbl, "value": series[j][i]})
    return {"quarter": [r["quarter"] for r in rows],
            "series":  [r["series"] for r in rows],
            "value":   [r["value"] for r in rows]}


def chart_bar_stack():
    df = _bar_quarterly_df()
    c = pt.chart(data_width=300, data_height=200,
                 title="bar stack", ylabel="$M", legend=True)
    c.bar(data=df, x="quarter", y="value", fill="series", position="stack")
    c.legend(position="right")
    return c


def chart_bar_dodge():
    df = _bar_quarterly_df()
    c = pt.chart(data_width=320, data_height=200,
                 title="bar dodge", ylabel="$M", legend=True)
    c.bar(data=df, x="quarter", y="value", fill="series", position="dodge")
    c.legend(position="right")
    return c


def chart_bar_fill():
    df = _bar_quarterly_df()
    c = pt.chart(data_width=300, data_height=200,
                 title="bar fill (100%)", ylabel="share", legend=True)
    c.bar(data=df, x="quarter", y="value", fill="series", position="fill")
    c.legend(position="right")
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
    c.bar(x="quarter", y="value", fill="series", color="black",
          position="dodge")
    c.legend(position="right")
    return c


def chart_scatter_long_color():
    import pandas as pd
    rng = random.Random(17)
    n = 60
    rows = []
    for g, (mx, my) in zip(["a", "b", "c"], [(0, 0), (2, 1), (1, 2.5)]):
        for _ in range(n):
            rows.append({"x": rng.gauss(mx, 0.6),
                         "y": rng.gauss(my, 0.6),
                         "group": g})
    df = pd.DataFrame(rows)
    c = pt.chart(data_width=300, data_height=240,
                 title="scatter (long-form, color)",
                 xlabel="x", ylabel="y", legend=True)
    c.scatter(data=df, x="x", y="y", color="group")
    c.legend(position="right")
    return c


def chart_density_1d_long_color():
    import pandas as pd
    rng = random.Random(18)
    rows = []
    for g, mu in zip(["control", "treatment"], [0, 1.2]):
        for _ in range(300):
            rows.append({"val": rng.gauss(mu, 1.0), "group": g})
    df = pd.DataFrame(rows)
    c = pt.chart(data_width=320, data_height=200,
                 title="density (long-form, color)",
                 xlabel="value", ylabel="density", legend=True)
    c.density_1d(data=df, x="val", color="group", fill=True)
    c.legend(position="right")
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
    c.scatter(s=14, alpha=0.5)
    c.regression()
    c.legend(position="right")
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
    c = pt.chart(df, x="t", y="value",
                 data_width=320, data_height=200,
                 title="trajectories: color by cohort, group by subject",
                 xlabel="t", ylabel="value", legend=True)
    c.line(color="cohort", group="subject", alpha=0.7)
    c.legend(position="right")
    return c


def chart_line_linetype():
    # `linetype=col` cycles dash patterns per level. When `linetype`
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
    c = pt.chart(df, x="t", y="v",
                 data_width=320, data_height=200,
                 title="redundant color + linetype",
                 xlabel="t", ylabel="v", legend=True)
    c.line(color="cohort", linetype="cohort", linewidth=1.6)
    c.legend(position="right")
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
    c = pt.chart(df, x="t", y="v",
                 data_width=320, data_height=200,
                 title="color + alpha by cohort",
                 xlabel="t", ylabel="v", legend=True)
    c.line(color="cohort", alpha="cohort", linewidth=1.8)
    c.legend(position="right")
    return c


def chart_aes_inheritance():
    """Chart-level aes (x=, y=, color=, fill=) inherited by multiple artist calls,
    ggplot-style. The boxplot+strip overlay is the canonical use case."""
    import pandas as pd
    rng = random.Random(20)
    rows = []
    for g in ["A", "B", "C"]:
        mu = {"A": 0, "B": 1.5, "C": 0.7}[g]
        for _ in range(40):
            rows.append({"group": g, "value": rng.gauss(mu, 0.6)})
    df = pd.DataFrame(rows)
    c = pt.chart(df, x="group", y="value",
                 data_width=320, data_height=240,
                 title="aes inheritance (boxplot + strip)")
    c.boxplot()
    c.strip(s=3, alpha=0.5)
    return c


def chart_area_stack():
    import math
    xs = list(range(0, 30))
    series_data = {
        "coal":       [max(0, 100 - 2 * x + 5 * math.sin(x / 3)) for x in xs],
        "gas":        [50 + 10 * math.sin(x / 4 + 1) for x in xs],
        "nuclear":    [40 for _ in xs],
        "renewables": [5 + 2.5 * x + 8 * math.sin(x / 5) for x in xs],
    }
    rows_year, rows_src, rows_val = [], [], []
    for x in xs:
        for src, vals in series_data.items():
            rows_year.append(x); rows_src.append(src)
            rows_val.append(vals[x])
    c = pt.chart(data_width=320, data_height=220,
                 title="generation mix", xlabel="year", ylabel="TWh",
                 legend=True)
    c.area(data={"year": rows_year, "source": rows_src, "twh": rows_val},
           x="year", y="twh", fill="source")
    c.legend(position="right")
    return c


def _legend_position_chart(position):
    """A two-line chart with an outside-positioned in-frame legend. Used
    by the legend_outside_* baselines to exercise each `position=` value
    — the data region stays at the user-requested size; the canvas grows
    on the named side to accommodate the legend block."""
    xs = _xs()
    c = pt.chart(title=f"legend {position}",
                 xlabel="t", ylabel="value", grid=True,
                 data_width=300, data_height=180)
    c.line(xs, [math.sin(x) for x in xs], label="sin(t)")
    c.line(xs, [math.cos(x) for x in xs], label="cos(t)", linestyle="--")
    c.legend(position=position)
    return c


def chart_legend_outside_right():  return _legend_position_chart("right")
def chart_legend_outside_left():   return _legend_position_chart("left")
def chart_legend_outside_top():    return _legend_position_chart("top")
def chart_legend_outside_bottom(): return _legend_position_chart("bottom")


PLOTS = {
    "table":               chart_table,
    "color":               chart_color,
    "scatter_color":       chart_scatter_color,
    "bar":                 chart_bar,
    "hist":                chart_hist,
    "fill_between":        chart_fill_between,
    "curve_steps":         chart_curve_steps,
    "curve_fills":         chart_curve_fills,
    "rect":                chart_rect,
    "split_rect":          chart_split_rect,
    "split_pie":           chart_split_pie,
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
    "heatmap_annot":       chart_heatmap_annot,
    "heatmap_categorical": chart_heatmap_categorical,
    "heatmap_nan":         chart_heatmap_nan,
    "imshow_annot_custom": chart_imshow_annot_custom,
    "long_title":          chart_long_title,
    "long_ylabel":         chart_long_ylabel,
    "long_rotated_xticks": chart_long_rotated_xticks,
    "xticks_fontstyle_italic": chart_xticks_fontstyle_italic,
    "xticks_decoration":       chart_xticks_decoration,
    "xticks_rotation_negative": chart_xticks_rotation_negative,
    "despined":            chart_despined,
    "restyled_spines":     chart_restyled_spines,
    "hlines_vlines":       chart_hlines_vlines,
    "text":                chart_text,
    "errorbar":            chart_errorbar,
    "errorbar_category_x":  chart_errorbar_category_x,
    "plot_alpha":          chart_plot_alpha,
    "dendrogram_top":      chart_dendrogram_top,
    "dendrogram_left":     chart_dendrogram_left,
    "dendrogram_styled":   chart_dendrogram_styled,
    "dendrogram_labeled":  chart_dendrogram_labeled,
    "tick_format_string":  chart_tick_format_string,
    "tick_format_callable": chart_tick_format_callable,
    "time_axis_dates":     chart_time_axis_dates,
    "time_axis_hours":     chart_time_axis_hours,
    "scatter_size":        chart_scatter_size,
    "scatter_size_style_color": chart_scatter_size_style_color,
    "facet_scatter":       chart_facet_scatter,
    "facet_wrap_two_rows": chart_facet_wrap_two_rows,
    "symlog_x":            chart_symlog_x,
    "sqrt_y":              chart_sqrt_y,
    "reverse_y":           chart_reverse_y,
    "minor_ticks_linear":  chart_minor_ticks_linear,
    "minor_ticks_log":     chart_minor_ticks_log,
    "ticks_step":          chart_ticks_step,
    "ticks_count":         chart_ticks_count,
    "annotate":            chart_annotate,
    "text_bbox":           chart_text_bbox,
    "step":                chart_step,
    "inset_zoom":          chart_inset_zoom,
    "clip_data_area":      chart_clip_data_area,
    "legend_outside_right":  chart_legend_outside_right,
    "legend_outside_left":   chart_legend_outside_left,
    "legend_outside_top":    chart_legend_outside_top,
    "legend_outside_bottom": chart_legend_outside_bottom,
    "boxplot":               chart_boxplot,
    "violin":                chart_violin,
    "swarm":                 chart_swarm,
    "strip":                 chart_strip,
    "pointplot":             chart_pointplot,
    "ecdf":                  chart_ecdf,
    "rug":                   chart_rug,
    "density_1d":            chart_density_1d,
    "regression":            chart_regression,
    "kde_2d":                chart_kde_2d,
    "hexbin":                chart_hexbin,
    "freqpoly":              chart_freqpoly,
    "contour":               chart_contour,
    "ridge":                 chart_ridge,
    "qq":                    chart_qq,
    "bar_stack":             chart_bar_stack,
    "bar_dodge":             chart_bar_dodge,
    "bar_fill":              chart_bar_fill,
    "bar_long_fill":         chart_bar_long_fill,
    "area_stack":            chart_area_stack,
    "scatter_long_color":    chart_scatter_long_color,
    "density_1d_long_color": chart_density_1d_long_color,
    "aes_inheritance":       chart_aes_inheritance,
    "regression_color":      chart_regression_color,
    "line_group":            chart_line_group,
    "line_linetype":         chart_line_linetype,
    "line_alpha":            chart_line_alpha,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_baseline(name, fn, baseline_compare):
    baseline_compare("chart", name, fn().to_svg())
