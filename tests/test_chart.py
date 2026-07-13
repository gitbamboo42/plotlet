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


def _by_label(items, labels):
    """Group `items` by parallel `labels`, preserving first-seen group order.
    Returns ``{group: [items, ...]}`` — the categorical-Sectors shape."""
    out = {}
    for it, lbl in zip(items, labels):
        out.setdefault(lbl, []).append(it)
    return out


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
                 xlabel="t", ylabel="value", legend=True, gridlines=True)
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
                 xlabel="t", ylabel="v", legend=True, gridlines=True)
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
                 xlabel="x", ylabel="y", legend=True, gridlines=True)
    c.scatter(x="x", y="y", color="group", size=3, alpha=0.6)
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
    c.legend()
    return c


def chart_imshow_png():
    data = [[math.sin(r * 0.07) + math.cos(c * 0.05) for c in range(160)]
            for r in range(120)]
    c = pt.chart(title="imshow (PNG path, magma)", xlabel="col", ylabel="row")
    c.imshow(data, cmap="magma")
    c.legend()
    return c


def chart_imshow_diverging():
    data = [[(r - 7) * (c - 7) for c in range(15)] for r in range(15)]
    c = pt.chart(title="imshow (bwr, extent, vmin/vmax)",
                 xlabel="x", ylabel="y")
    c.imshow(data, cmap="bwr", extent=(-1.5, 1.5, -1.5, 1.5),
             vmin=-49, vmax=49)
    c.legend()
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
    c.legend()
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


def chart_imshow_user_cmap():
    # register_colormap flows through both the imshow cell path and the
    # gradient legend; center=0 pins the white anchor to zero on the
    # asymmetric range, so anchoring stays the norm's job.
    pt.register_colormap("bwr2_demo", ["#2166ac", "#f7f7f7", "#b2182b"])
    data = [[(r - 4) * 0.5 + (c - 4) * 0.7 for c in range(12)] for r in range(10)]
    c = pt.chart(title="user colormap (bwr2_demo)", xlabel="x", ylabel="y")
    c.imshow(data, cmap="bwr2_demo", center=0, legend={"label": "value"})
    c.legend()
    return c


def chart_imshow_log_norm():
    # Multi-decade dynamic range — without log, all but the brightest
    # cells render near-black; with log, structure across decades shows.
    # Legend ticks are powers of 10.
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


def chart_xticks_top_share_x():
    # share_x="col" v-stack where the BOTTOM panel flips x-axis to top.
    # Without joined-pair routing of top-label suppression, the bottom
    # panel's tick label glyphs would render unanchored at the joint
    # between the two panels. With the fix, those labels suppress and
    # only the upper panel's bottom-edge labels remain at the shared
    # edge (which here is the default bottom side of the upper panel).
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    df2 = {"x": xs, "y": [math.cos(t) for t in xs]}
    top = pt.chart(df, ylabel="sin").line(x="x", y="y")
    bot = pt.chart(df2, xlabel="x", ylabel="cos").line(x="x", y="y")
    bot.xticks(side="top")
    return pt.grid([[top], [bot]]).share_x("col")


def chart_xticks_flipped_sides():
    # x-axis on top, y-axis on right — matches ggplot2 `position="top"` /
    # plotly `side="top"`. Margins, xlabel/ylabel and title all follow.
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    c = pt.chart(df, title="x on top, y on right",
                 xlabel="x", ylabel="y")
    c.line(x="x", y="y")
    c.xticks(side="top")
    c.yticks(side="right")
    return c


def chart_xticks_inward():
    # Inward tick direction — matplotlib-style ticks pointing into the data
    # area. Just covers `direction="in"`; default outward look is in every
    # other test.
    xs = [i * 0.1 for i in range(64)]
    df = {"x": xs, "y": [math.sin(t) for t in xs]}
    c = pt.chart(df, title="inward ticks", xlabel="x", ylabel="y")
    c.line(x="x", y="y")
    c.xticks(direction="in")
    c.yticks(direction="in")
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
                 xlabel="t", ylabel="v", legend=True, gridlines=True)
    c.axhspan(-0.5, 0.5, color="C2")
    c.axvspan(2.0, 3.5)
    c.line(x="t", y="v", label="sin(t)")
    c.axhline(0)
    c.axhline(0.8, color="red", linestyle="--", label="upper")
    c.axvline(math.pi, color="gray", linestyle=":")
    return c


def chart_axline():
    """Infinite reference lines in arbitrary directions: the y=x identity
    line via slope=, a two-point line, both clipped to the frame."""
    rng = random.Random(31)
    obs = [i * 0.5 + rng.gauss(0, 0.6) for i in range(20)]
    pred = [v + rng.gauss(0, 0.5) for v in obs]
    c = pt.chart(data_width=260, data_height=220,
                 title="observed vs predicted",
                 xlabel="observed", ylabel="predicted", legend=True)
    c.scatter(data={"o": obs, "p": pred}, x="o", y="p", size=2.5, alpha=0.7)
    c.axline((0, 0), slope=1, linestyle="--", label="y = x")
    c.axline((0, 8), (8, 4), color="C3", label="two-point")
    return c


def chart_long_title():
    # Title text wider than the data region: measure-driven margin grows
    # left and right so the centered title doesn't spill off-canvas.
    # data_width=180 is small; title is ~360 px wide → ~90 px overhang each side.
    c = pt.chart(data_width=180, data_height=140,
                 title="A very wide title that exceeds the data region width",
                 xlabel="x", ylabel="y")
    c.line(data={"x": [1, 2, 3, 4, 5], "y": [1, 2, 4, 8, 16]}, x="x", y="y")
    return c


def chart_long_ylabel():
    # ylabel rendered rotated -90 around the data area's vertical center;
    # text longer than data_height spills past top and bottom. Margin
    # should grow on top *and* bottom by half the overhang. Title is
    # included so we can verify the vertical overhang doesn't displace
    # the title from its natural slot above the data area.
    c = pt.chart(data_width=200, data_height=120,
                 title="long ylabel + title",
                 ylabel="Signal intensity (log10 normalized units per sample)",
                 xlabel="time")
    c.line(data={"x": [0, 1, 2, 3], "y": [3.2, 4.1, 4.9, 5.5]}, x="x", y="y")
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
    c.scatter(data={"x": xs, "y": ys}, x="x", y="y")
    c.text(data={"x": xs, "y": ys, "label": ["A", "B", "C", "D", "E"]}, x="x", y="y", label="label", dy=-10, ha="center")
    c.annotate("peak", xy=(3, 9.5), color="C3", ha="center")
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
    c = pt.chart(title="response by level", xlabel="level", ylabel="response")
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


class _MockDF:
    # Tiny stand-in for a pandas DataFrame so the DataFrameLite / duck-typed
    # `.values`/`.columns`/`.index` path gets exercised without a pandas dep.
    def __init__(self, values, index, columns):
        self.values = values
        self.index = index
        self.columns = columns


def _tidy_heatmap(matrix, xlabels, ylabels, xname="col"):
    """Wide `matrix[y][x]` + axis labels → tidy dict for the heatmap's
    long-form input: each x label is a table row (→ a heatmap column),
    each y label is a value column (→ a track)."""
    data = {xname: list(xlabels)}
    for i, yl in enumerate(ylabels):
        data[yl] = list(matrix[i])
    return data


def _mock_tidy_df(tidy):
    """Wrap a tidy dict in a `_MockDF` (columns + row-major values) to
    exercise the DataFrameLite normalization path."""
    cols = list(tidy.keys())
    n = len(next(iter(tidy.values())))
    values = [[tidy[c][r] for c in cols] for r in range(n)]
    return _MockDF(values, index=list(range(n)), columns=cols)


def chart_heatmap_labeled():
    # Long-form heatmap: string `x` column → categorical x band labels,
    # value columns → track rows.
    data = [[math.sin(r * 0.6) * math.cos(c * 0.4) for c in range(8)]
            for r in range(6)]
    rows = [f"r{i}" for i in range(6)]
    cols = [f"c{i}" for i in range(8)]
    c = pt.chart(title="heatmap (labeled rows/cols)",
                 xlabel="condition", ylabel="sample")
    c.heatmap(data=_tidy_heatmap(data, cols, rows, xname="condition"),
              x="condition", values=rows, cmap="viridis")
    c.legend()
    return c


def chart_heatmap_dataframe():
    rng = random.Random(1)
    n_rows, n_cols = 5, 7
    values = [[rng.gauss(0, 1) for _ in range(n_cols)] for _ in range(n_rows)]
    samples  = [f"sample_{i}" for i in range(n_rows)]
    features = [f"feature_{j}" for j in range(n_cols)]
    tidy = _tidy_heatmap(values, features, samples, xname="feature")
    c = pt.chart(title="heatmap (DataFrame branch, diverging cmap)")
    c.heatmap(data=_mock_tidy_df(tidy), x="feature", values=samples,
              cmap="bwr", center=0)
    c.xticks(rotation=45)
    c.legend()
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
    c.heatmap(data=_tidy_heatmap(data, labels, labels, xname="var"),
              x="var", values=labels,
              cmap="RdBu_r", vmin=-1, vmax=1, annot=True, fmt="+.2f",
              legend={"label": "corr"})
    c.legend(True)
    return c


def chart_heatmap_categorical():
    rows    = ["R1", "R2", "R3", "R4", "R5"]
    samples = ["S1", "S2", "S3", "S4", "S5", "S6"]
    matrix = [
        ["Alpha", "None",   "Gamma", "None",   "Alpha", None    ],
        ["None",  "Beta",   "None",  "Alpha",  "None",  "Delta" ],
        ["Delta", "None",   "None",  "Delta",  "Beta",  "None"  ],
        ["None",  "Alpha",  "Delta", None,     "None",  "Alpha" ],
        ["Beta",  "Delta",  "Alpha", "Gamma",  "None",  "None"  ],
    ]
    palette = {
        "None":   "#e8e8e8",
        "Alpha":  "#3a6dbf",
        "Beta":   "#c0392b",
        "Gamma":  "#e67e22",
        "Delta":  "#27ae60",
    }
    c = pt.chart(title="heatmap (categorical palette, absent=grey)",
                 xlabel="sample", ylabel="row")
    c.heatmap(data=_tidy_heatmap(matrix, samples, rows, xname="sample"),
              x="sample", values=rows,
              palette=palette, absent_fill="#dddddd")
    c.xticks(rotation=45)
    c.legend()
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
    c.heatmap(data=_tidy_heatmap(matrix, cols, rows, xname="col"),
              x="col", values=rows, cmap="viridis", absent_fill="#ff9999")
    c.legend()
    return c


def chart_heatmap_palette_annot():
    # Palette-mode annot renders numeric labels verbatim (identifiers /
    # counts, not measurements) — no fmt applied, unlike the cmap path,
    # where 990000 would come out as "9.9e+05".
    samples = [f"s{i}" for i in range(4)]
    rows = ["mut", "wt"]
    matrix = [["hit", "miss", "hit", "hit"],
              ["miss", "hit", "miss", "hit"]]
    counts = [[1234, 8, 250, 42],
              [3, 990000, 17, 5]]
    c = pt.chart(title="palette heatmap (verbatim numeric annot)")
    c.heatmap(data=_tidy_heatmap(matrix, samples, rows, xname="s"),
              x="s", values=rows,
              palette={"hit": "#4477aa", "miss": "#ee6677"}, annot=counts)
    c.legend()
    return c


def chart_heatmap_continuous_x():
    # Numeric `x` column → continuous linear x-axis (numeric ticks, not
    # category bands); value columns are categorical track rows.
    matrix = [[math.sin(0.5 * c + r) for c in range(10)] for r in range(6)]
    xs = [float(i) for i in range(10)]
    tracks = [f"r{i}" for i in range(6)]
    c = pt.chart(title="heatmap (continuous x)",
                 xlabel="x position", ylabel="track")
    c.heatmap(data=_tidy_heatmap(matrix, xs, tracks, xname="x"),
              x="x", values=tracks, cmap="viridis")
    c.legend()
    return c


def chart_heatmap_continuous_x_cat_y():
    # Annotation-track shape: continuous x (aligns to a scatter under
    # share_x), categorical track rows down the side.
    matrix = [[math.sin(0.4 * c + r) for c in range(12)] for r in range(3)]
    xs = [float(i) for i in range(12)]
    tracks = ["t1", "t2", "t3"]
    c = pt.chart(title="heatmap (continuous x, categorical tracks)",
                 xlabel="x position")
    c.heatmap(data=_tidy_heatmap(matrix, xs, tracks, xname="x"),
              x="x", values=tracks, cmap="magma")
    c.legend()
    return c


def chart_heatmap_continuous_uneven():
    # Unevenly spaced x → cell edges inferred as neighbor midpoints, so
    # each column gets a different width.
    matrix = [[1.0, 2.0, 3.0, 4.0, 5.0]]
    xs = [0.0, 1.0, 3.0, 6.0, 10.0]
    c = pt.chart(title="heatmap (uneven continuous x)", xlabel="t")
    c.heatmap(data=_tidy_heatmap(matrix, xs, ["v"], xname="t"),
              x="t", values=["v"], cmap="viridis", annot=True)
    c.legend()
    return c


def chart_heatmap_continuous_nan():
    # NaN/None on a continuous-position grid still routes to absent_fill,
    # never the imshow black.
    matrix = [
        [1.0, float("nan"), 3.0, None],
        [None, 2.0, 5.0, 4.0],
    ]
    xs = [0.0, 1.0, 2.0, 3.0]
    c = pt.chart(title="heatmap (continuous + NaN → absent_fill)",
                 xlabel="x")
    c.heatmap(data=_tidy_heatmap(matrix, xs, ["a", "b"], xname="x"),
              x="x", values=["a", "b"], cmap="viridis", absent_fill="#ff9999")
    c.legend()
    return c


def chart_heatmap_split():
    # Annotated-heatmap row + column clusters via c.sectors. Both
    # grouping vectors are deliberately interleaved so the auto
    # cluster-and-gap reordering is exercised on both axes — rows regroup
    # to A,A,A / B,B,B / C,C and cols regroup to X,X,X / Y,Y,Y,Y,Y /
    # Z,Z,Z,Z. The uneven block sizes (3-3-2 rows × 3-5-4 cols) make the
    # gaps obvious.
    nrows, ncols = 8, 12
    matrix = [[r * ncols + c for c in range(ncols)] for r in range(nrows)]
    row_labels = [f"r{i+1}" for i in range(nrows)]
    col_labels = [f"c{i+1}" for i in range(ncols)]
    row_groups = ["A", "B", "A", "C", "A", "B", "C", "B"]
    col_groups = ["X", "Y", "Z", "X", "Y", "Z", "Y", "Z",
                  "X", "Y", "Z", "Y"]
    c = pt.chart(title="heatmap (row + column clusters)")
    c.sectors(_by_label(col_labels, col_groups), axis="x",
              divider=False, label=False)
    c.sectors(_by_label(row_labels, row_groups), axis="y",
              divider=False, label=False)
    c.heatmap(data=_tidy_heatmap(matrix, col_labels, row_labels, xname="col"),
              x="col", values=row_labels, annot=True)
    c.legend()
    return c


def chart_dendrogram_split():
    """Two-level cluster + split-driven heatmap.

    The dendrogram runs scipy on each group (within-block topology + leaf
    order) and on the per-group centroids (between-block order), then
    exposes the full leaf order via `axis_order`. The heatmap below has
    the *same* grouping vector — its `frame_defaults` order is the
    first-seen clustering, which loses to the dendrogram's `axis_order`
    in the new precedence rule. Group X has a low signature, Y mid, Z
    high; the centroid cluster should arrange the blocks in that order.
    """
    import random
    rng = random.Random(7)
    nrows_hm, ncols_hm = 6, 12
    col_labels = [f"c{i+1}" for i in range(ncols_hm)]
    col_groups = ["X", "Y", "Z", "X", "Y", "Z", "Y", "Z",
                  "X", "Y", "Z", "Y"]
    sig = {"X": 0.0, "Y": 5.0, "Z": 10.0}
    matrix = [[sig[col_groups[c]] + rng.gauss(0, 0.3)
               for c in range(ncols_hm)]
              for _ in range(nrows_hm)]
    # Transpose: dendrogram clusters cols-of-heatmap as its observations.
    data_t = [[matrix[r][c] for r in range(nrows_hm)] for c in range(ncols_hm)]

    tree = pt.chart(data_height=60)
    tree.dendrogram(data_t, labels=col_labels, orientation="top",
                    clusters=col_groups, method="ward")

    hm = pt.chart(title="dendrogram-driven split heatmap",
                  data_width=420, data_height=180)
    hm.sectors(_by_label(col_labels, col_groups), axis="x",
               divider=False, label=False)
    row_labels = [f"r{i+1}" for i in range(nrows_hm)]
    hm.heatmap(data=_tidy_heatmap(matrix, col_labels, row_labels, xname="col"),
               x="col", values=row_labels,
               cmap="viridis", legend={"label": "value"})
    hm.attach_above(tree)
    return pt.grid([[hm, pt.legend()]]).gap(0)


def chart_dendrogram_split_parent():
    """Both axes split + parent-tree on both sides: the curved_tree
    extension on top, the built-in dendrogram on the left. Same grouping
    vector flows to each tree via `clusters=`, and the panel declares
    `c.sectors(...)` once on each axis for the visual gap whitespace —
    both trees and the heatmap pick up the dendrogram's between-cluster
    order through the artist `axis_order` precedence rule.

    Stresses `cluster.fit_parent` on both orientation=top and
    orientation=left, and on both renderers (built-in `dendrogram`,
    extension `curved_tree`) — one per side — so a regression on either
    renderer or on the public cluster API trips this baseline.

    Row names sit right of the heatmap (`yticks(side="right")` on the
    host, `yticks(labels=False)` on the tree so they don't draw twice) —
    the only baseline covering `side=` interacting with attachments."""
    import random
    import plotlet.extensions.curved_tree  # registers c.curved_tree
    rng = random.Random(7)
    nrows_hm, ncols_hm = 9, 12
    col_labels = [f"c{i+1}" for i in range(ncols_hm)]
    row_labels = [f"r{i+1}" for i in range(nrows_hm)]
    col_groups = ["X", "Y", "Z", "X", "Y", "Z", "Y", "Z",
                  "X", "Y", "Z", "Y"]
    row_groups = ["A", "B", "C", "A", "B", "C", "B", "C", "A"]
    col_sig = {"X": 0.0, "Y": 5.0, "Z": 10.0}
    row_sig = {"A": 0.0, "B": 2.0, "C": 4.0}
    matrix = [[col_sig[col_groups[c]] + row_sig[row_groups[r]] + rng.gauss(0, 0.3)
               for c in range(ncols_hm)]
              for r in range(nrows_hm)]
    # Observations for the dendrograms: rows for the left tree, the
    # transpose for the top tree.
    data_top = [[matrix[r][c] for r in range(nrows_hm)] for c in range(ncols_hm)]
    data_left = matrix

    top_c = pt.chart(data_height=90)
    top_c.curved_tree(data_top, labels=col_labels, orientation="top",
                      clusters=col_groups, method="ward", parent=True)

    left_d = pt.chart(data_width=100)
    left_d.dendrogram(data_left, labels=row_labels, orientation="left",
                      clusters=row_groups, method="ward", parent=True)
    left_d.yticks(labels=False)

    hm = pt.chart(title="split heatmap with parent trees on both sides",
                  data_width=360, data_height=240)
    hm.yticks(side="right")
    hm.sectors(_by_label(col_labels, col_groups), axis="x",
               divider=False, label=False)
    hm.sectors(_by_label(row_labels, row_groups), axis="y",
               divider=False, label=False)
    hm.heatmap(data=_tidy_heatmap(matrix, col_labels, row_labels, xname="col"),
               x="col", values=row_labels,
               cmap="viridis", legend={"label": "value"})
    hm.attach_above(top_c)
    hm.attach_left(left_d)

    return pt.grid([[hm, pt.legend()]]).gap(0)


def chart_heatmap_split_attached():
    # Top strip + top bar both share x with the split heatmap, so they
    # inherit the column reorder and the 6-px gaps via the shared scale
    # — no per-artist split kwargs on the attachments. The legend on the
    # right auto-harvests across all leaves (continuous gradient from the
    # heatmap, discrete swatches from the strip).
    import plotlet.extensions.annotation_strip  # registers c.annotation_strip
    nrows, ncols = 8, 12
    matrix = [[r * ncols + c for c in range(ncols)] for r in range(nrows)]
    col_labels = [f"c{i+1}" for i in range(ncols)]
    row_labels = [f"r{i+1}" for i in range(nrows)]
    row_groups = ["A", "B", "A", "C", "A", "B", "C", "B"]
    col_groups = ["X", "Y", "Z", "X", "Y", "Z", "Y", "Z",
                  "X", "Y", "Z", "Y"]
    palette = {"X": pt.TAB10[0], "Y": pt.TAB10[1], "Z": pt.TAB10[2]}
    col_sums = [sum(matrix[r][c] for r in range(nrows)) for c in range(ncols)]

    bar = pt.chart({"col": col_labels, "sum": col_sums},
                   data_height=40, ylabel="sum")
    bar.bar(x="col", y="sum", fill="#555")

    strip = pt.chart(data_height=14)
    strip.annotation_strip({"col": col_labels, "group": col_groups},
                           position="col", value="group",
                           palette=palette, name="group")

    hm = pt.chart(title="heatmap (split + attached)",
                  data_width=420, data_height=240)
    hm.sectors(_by_label(col_labels, col_groups), axis="x",
               divider=False, label=False)
    hm.sectors(_by_label(row_labels, row_groups), axis="y",
               divider=False, label=False)
    hm.heatmap(data=_tidy_heatmap(matrix, col_labels, row_labels, xname="col"),
               x="col", values=row_labels,
               legend={"label": "value"})
    # First arg sits closest to the host; order outward is strip, bar.
    hm.attach_above(strip, bar)

    return pt.grid([[hm, pt.legend()]]).gap(0)


def chart_heatmap_block_titles():
    # Block-mode annotation_strip on top of a column-split heatmap:
    # one text label per group, no fill, no border. The shared scale
    # places labels at the centre of each column block.
    import plotlet.extensions.annotation_strip
    nrows, ncols = 6, 9
    matrix = [[r * ncols + c for c in range(ncols)] for r in range(nrows)]
    col_labels = [f"c{i+1}" for i in range(ncols)]
    row_labels = [f"r{i+1}" for i in range(nrows)]
    col_groups = ["alpha"] * 3 + ["beta"] * 4 + ["gamma"] * 2

    titles = pt.chart(data_height=18)
    titles.annotation_strip({"col": col_labels, "group": col_groups},
                            position="col", value="group",
                            mode="block", text=True)

    hm = pt.chart(data_width=360, data_height=180)
    hm.sectors(_by_label(col_labels, col_groups), axis="x",
               divider=False, label=False)
    hm.heatmap(data=_tidy_heatmap(matrix, col_labels, row_labels, xname="col"),
               x="col", values=row_labels,
               legend={"label": "value"})
    hm.attach_above(titles)

    return pt.grid([[hm, pt.legend()]]).gap(0)


def chart_heatmap_block_filled():
    # Block-mode strip with palette fill, white text, and a black
    # border outlining each block — the full filled-titles look.
    import plotlet.extensions.annotation_strip
    nrows, ncols = 6, 9
    matrix = [[r * ncols + c for c in range(ncols)] for r in range(nrows)]
    col_labels = [f"c{i+1}" for i in range(ncols)]
    row_labels = [f"r{i+1}" for i in range(nrows)]
    col_groups = ["alpha"] * 3 + ["beta"] * 4 + ["gamma"] * 2
    palette = {"alpha": pt.TAB10[0], "beta": pt.TAB10[1], "gamma": pt.TAB10[2]}

    block = pt.chart(data_height=22)
    block.annotation_strip({"col": col_labels, "group": col_groups},
                           position="col", value="group",
                           mode="block", palette=palette, text=True,
                           text_color="white", cell_border="#222")

    hm = pt.chart(data_width=360, data_height=180)
    hm.sectors(_by_label(col_labels, col_groups), axis="x",
               divider=False, label=False)
    hm.heatmap(data=_tidy_heatmap(matrix, col_labels, row_labels, xname="col"),
               x="col", values=row_labels,
               legend={"label": "value"})
    hm.attach_above(block)

    return pt.grid([[hm, pt.legend()]]).gap(0)


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

    def _sr_record(**kw):
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

    def _sp_record(**kw):
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
    c.legend()
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
    c.line(data={"x": xs, "y": ys}, x="x", y="y", curve="linear", marker="o", label="linear")
    c.line(data={"x": xs, "y": [v + 2 for v in ys]}, x="x", y="y", curve="step-after", marker="o", label="step-after")
    c.line(data={"x": xs, "y": [v + 4 for v in ys]}, x="x", y="y", curve="step-before", marker="o", label="step-before")
    c.line(data={"x": xs, "y": [v + 6 for v in ys]}, x="x", y="y", curve="step-mid", marker="o", label="step-mid")
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
    c.fill_between(data={"x": xs, "y1": lo, "y2": hi}, x="x", y1="y1", y2="y2",
                   curve="step-after", fill="C0", alpha=0.3, label="step band")
    df_area = {"x": xs, "y": [1.0, 1.3, 1.7, 2.0, 1.6, 1.4]}
    c.area(data=df_area, x="x", y="y", curve="step-after",
           color="C1", alpha=0.5, label="step area")
    return c


def chart_rect():
    # Mixed scalar / list inputs — broadcast covers the multi-track,
    # gantt-style, and interval-model use cases that motivated adding rect.
    # Also exercises color= (outline) + linewidth so the stroke path is
    # covered.
    c = pt.chart(title="rect (broadcast + outline)",
                 xlabel="x", ylabel="y", legend=True)
    c.rect([0, 2, 4, 6], 0, [1.5, 1.5, 1.5, 1.5], 2, fill="C0",
           alpha=0.6, label="intervals")
    c.rect(0.5, 2.5, 7, 1, fill="C1", alpha=0.3,
           color="C3", linewidth=1.5, label="overlay")
    c.rect(3, 0.2, 1, 1.6, fill="none", color="black",
           linewidth=2, label="outline")
    return c


def chart_polygon():
    # Two polygons composed in one chart: a filled triangle (color cycle)
    # and an outlined diamond (fill="none"). Polygon auto-closes — the
    # last vertex doesn't need to repeat the first.
    c = pt.chart(title="polygon", xlabel="x", ylabel="y", legend=True)
    c.polygon([0, 2, 1], [0, 0, 2], alpha=0.5, label="triangle")
    c.polygon([3, 4, 3, 2], [1, 2, 3, 2], fill="none", linewidth=2,
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
    c = pt.chart(title="dendrogram (orientation=top)", data_height=180)
    c.dendrogram(_dendro_sample(), method="ward")
    return c


def chart_dendrogram_left():
    c = pt.chart(title="dendrogram (orientation=left)", data_width=240)
    c.dendrogram(_dendro_sample(), method="ward", orientation="left")
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
    # Italic axis-tick labels via fontstyle — renders with the real
    # DejaVuSans-Oblique face (synthetic skew is only the fallback for
    # path-loaded fonts with no italic sibling).
    df = {"label": ["alpha", "beta", "gamma", "delta", "epsilon"],
          "rate": [0.42, 0.35, 0.28, 0.21, 0.18]}
    c = pt.chart(data_width=320, data_height=200,
                 title="italic labels", ylabel="rate")
    c.bar(data=df, x="label", y="rate", fill="#5599aa")
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
    sizes = [random.uniform(7, 10) for _ in range(n)]
    # Deliberate bleeders along the upper-right edges.
    xs    += [9.7, 9.5, 9.8, 8.6, 7.4]
    ys    += [9.5, 9.8, 7.4, 9.7, 9.5]
    sizes += [13, 14, 13, 14, 13]
    c = pt.chart(data_width=320, data_height=240, clip=False,
                 title="clip=False",
                 xlabel="x", ylabel="y",
                 xlim=(0, 10), ylim=(0, 10))
    c.scatter(data={"x": xs, "y": ys}, x="x", y="y", size=sizes, color="C0", alpha=0.6)
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
    c.step(data={"x": xs, "y": [1, 3, 2, 5, 4, 3, 6, 5]}, x="x", y="y", where="post", label="post")
    c.step(data={"x": xs, "y": [1.5, 3.5, 2.5, 5.5, 4.5, 3.5, 6.5, 5.5]},
           x="x", y="y", where="pre", label="pre", color="C1")
    c.step(data={"x": xs, "y": [2, 4, 3, 6, 5, 4, 7, 6]}, x="x", y="y", where="mid", label="mid", color="C2")
    return c


def chart_text_bbox():
    # Text labels with a background box — readable over dense data.
    xs = [i * 0.1 for i in range(120)]
    ys = [math.sin(x * 3) * math.exp(-x * 0.1) for x in xs]
    c = pt.chart(data_width=420, data_height=200, title="text bbox",
                 xlabel="t", ylabel="y")
    c.line(data={"x": xs, "y": ys}, x="x", y="y")
    c.annotate("plain", xy=(2.0, 0.5), fontsize=12)
    c.annotate("on white", xy=(4.0, 0.5), fontsize=12, bbox=True)
    c.annotate("tinted", xy=(6.0, 0.5), fontsize=12,
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
    c.line(data={"x": xs, "y": ys}, x="x", y="y")
    max_i = ys.index(max(ys))
    # Label sits left of the peak (ha="right" → glyphs extend left from
    # the anchor): margins only reserve chrome space, so a left-anchored
    # label this close to the right edge would run off the canvas.
    c.annotate("global max",
               xy=(xs[max_i], ys[max_i]),
               xytext=(xs[max_i] - 1.5, ys[max_i] + 0.3), ha="right")
    c.annotate("first zero",
               xy=(math.pi, 0),
               xytext=(math.pi - 2, 0.6), ha="center")
    # dx/dy nudge the label end in screen space (arrow tail follows);
    # rotation spins the text around its anchor, arrow unrotated.
    min_i = ys.index(min(ys))
    c.annotate("global min",
               xy=(xs[min_i], ys[min_i]),
               xytext=(xs[min_i], ys[min_i]), dx=14, dy=-10)
    c.annotate("rotated",
               xy=(6.0, ys[30]),
               xytext=(6.0, ys[30] + 0.8), ha="center", rotation=30)
    return c


def chart_ticks_step():
    c = pt.chart(data_width=400, data_height=170,
                 title="step=0.25", xlabel="x", ylabel="y", gridlines=True)
    c.line(data={"x": [0, 0.5, 1.0, 1.5, 2.0], "y": [0, 1, 4, 9, 16]}, x="x", y="y", marker="o")
    c.xticks(step=0.25)
    return c


def chart_ticks_count():
    c = pt.chart(data_width=400, data_height=170,
                 title="count=4", xlabel="x", ylabel="y", gridlines=True)
    c.line(data={"x": list(range(11)), "y": [i * i for i in range(11)]}, x="x", y="y", marker="o")
    c.xticks(count=4)
    return c


def chart_minor_ticks_linear():
    c = pt.chart(data_width=400, data_height=180,
                 title="minor ticks", xlabel="x", ylabel="y", gridlines=True)
    c.line(data={"x": [0, 1, 2, 3, 4, 5], "y": [0, 1, 4, 9, 16, 25]}, x="x", y="y", marker="o")
    c.xticks(minor=True)
    c.yticks(minor=True)
    return c


def chart_power10_math_text():
    # power10 log ticks + unicode super/subscripts in axis labels +
    # italic in-plot text — the math-text vocabulary in one baseline.
    c = pt.chart(data_width=400, data_height=190, title="math text",
                 xlabel="dose (mol·L" + pt.superscript("-1") + ")",
                 ylabel="H" + pt.subscript("2") + "O flux (kg·m"
                        + pt.superscript("-2") + ")")
    c.line(data={"x": [1, 10, 100, 1000, 10000],
                 "y": [0.001, 0.01, 0.1, 1, 10]}, x="x", y="y", marker="o")
    c.xscale("log")
    c.yscale("log")
    c.xticks(format="power10")
    c.yticks(format="power10")
    c.text(data={"x": [10], "y": [1], "s": ["BRCA1"]}, x="x", y="y",
           label="s", fontstyle="italic")
    return c


def chart_subtitle_caption():
    # Subtitle stacks under the title (smaller); caption is the
    # outermost bottom element, right-aligned (ggplot's labs(caption=)).
    c = pt.chart(data_width=340, data_height=170,
                 title="Fuel efficiency", subtitle="highway, 1999-2008",
                 caption="Source: EPA", xlabel="displ", ylabel="hwy")
    c.scatter(data={"x": [1.8, 2.0, 2.8, 3.1, 4.2, 5.3],
                    "y": [29, 31, 26, 27, 23, 20]}, x="x", y="y")
    return c


def chart_minor_grid():
    # which="both": thin minor lines between the major ones, auto
    # positions on the linear axes without minor ticks enabled.
    c = pt.chart(data_width=400, data_height=180,
                 title="minor grid", xlabel="x", ylabel="y", gridlines="both")
    c.line(data={"x": [0, 1, 2, 3, 4, 5], "y": [0, 1, 4, 9, 16, 25]}, x="x", y="y", marker="o")
    return c


def chart_minor_grid_log():
    # log x: minor gridlines at the 2..9 decade multipliers, drawn from
    # c.gridlines(which=) with explicit minor ticks shown too.
    c = pt.chart(data_width=400, data_height=180,
                 title="minor grid log", xlabel="freq", ylabel="amp")
    c.line(data={"x": [1, 10, 100, 1000, 10000], "y": [1, 5, 12, 25, 60]}, x="x", y="y", marker="o")
    c.xscale("log")
    c.xticks(minor=True)
    c.gridlines(which="both")
    return c


def chart_minor_ticks_log():
    c = pt.chart(data_width=400, data_height=180,
                 title="minor ticks log", xlabel="freq", ylabel="amp")
    c.line(data={"x": [1, 10, 100, 1000, 10000], "y": [1, 5, 12, 25, 60]}, x="x", y="y", marker="o")
    c.xscale("log")
    c.xticks(minor=True)
    return c


def chart_reverse_y():
    # Reversed y axis: classic oceanography depth profile (0 on top).
    times = list(range(8))
    depths = [10, 28, 65, 130, 220, 360, 480, 620]
    c = pt.chart(data_width=320, data_height=180,
                 title="depth profile", xlabel="time", ylabel="depth (m)")
    c.line(data={"x": times, "y": depths}, x="x", y="y", marker="o")
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
    # a linear band around 0. Signed-magnitude domains.
    xs = [-2000, -250, -25, -2, -0.5, 0, 0.5, 2, 25, 250, 2000]
    ys = [abs(x) ** 0.5 for x in xs]
    c = pt.chart(data_width=400, data_height=180,
                 title="symlog axis", xlabel="signed magnitude", ylabel="sqrt(|x|)")
    c.scatter(data={"x": xs, "y": ys}, x="x", y="y", size=2.5)
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
    g.scatter(x="bill_length", y="bill_depth", size=2)
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


def chart_facet_grid_two_factor():
    # row= x col= grid: one grid row per sex, one column per stage, shared
    # axes. The (F, mid) combination has no rows -> blank cell.
    random.seed(13)
    df = {"x": [], "y": [], "sex": [], "stage": []}
    for sex in ("M", "F"):
        for stage in ("early", "mid", "late"):
            if sex == "F" and stage == "mid":
                continue
            for _ in range(18):
                df["x"].append(random.gauss(0, 1) + (1.5 if sex == "F" else 0))
                df["y"].append(random.gauss(0, 1) + (2 if stage == "late" else 0))
                df["sex"].append(sex)
                df["stage"].append(stage)
    g = pt.facet(df, row="sex", col="stage",
                 data_width=150, data_height=110,
                 xlabel="x", ylabel="y")
    g.scatter(x="x", y="y", size=2)
    return g


def chart_hist_stack():
    rng = random.Random(21)
    df = {
        "value": ([rng.gauss(0, 1) for _ in range(600)]
                  + [rng.gauss(1.8, 0.7) for _ in range(400)]),
        "group": ["ctrl"] * 600 + ["treat"] * 400,
    }
    c = pt.chart(df, title="hist stacked", xlabel="value", ylabel="count",
                 legend=True)
    c.hist(x="value", fill="group", bins=24, position="stack")
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
    c.hist(x="value", fill="group", bins=12, position="dodge")
    return c


def chart_hist_binwidth_cumulative():
    rng = random.Random(22)
    df = {"v": [rng.gauss(0, 1) for _ in range(500)]}
    c = pt.chart(df, title="hist binwidth= + cumulative CDF",
                 xlabel="v", ylabel="cdf")
    c.hist(x="v", binwidth=0.25, binrange=(-3, 3),
           cumulative=True, density=True, fill="C0")
    return c


def chart_aspect_equal():
    # Data-space aspect lock: the ring reads as a circle because one
    # x unit and one y unit render the same pixel length (the requested
    # data_height is rederived from the resolved domains).
    angles = [i * math.pi / 36 for i in range(72)]
    df = {"x": [3 * math.cos(a) for a in angles],
          "y": [3 * math.sin(a) for a in angles]}
    c = pt.chart(df, title="aspect('equal') — circles stay circular",
                 data_width=320, data_height=200, xlabel="x", ylabel="y")
    c.scatter(x="x", y="y", size=2)
    c.aspect("equal")
    return c


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
    c.scatter(x="x", y="y", size="mass", sizes=(2, 8))
    c.legend()
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
    c.line(data={"x": list(range(8)), "y": [0.05, 0.12, 0.18, 0.27, 0.42, 0.55, 0.71, 0.88]}, x="x", y="y")
    c.yticks(format="{:.0%}")
    return c


def chart_tick_format_named():
    # Named formatter: `pt.formatters.money` handles the K/M compaction.
    c = pt.chart(data_width=320, data_height=180,
                 title="revenue", xlabel="month", ylabel="revenue")
    c.line(data={"x": list(range(8)), "y": [1200, 4500, 8300, 18000, 45000, 92000, 410000, 1_250_000]}, x="x", y="y")
    c.yticks(format="money")
    return c


def chart_time_axis_dates():
    # Auto-detect: date values on x → time scale, calendar-aligned ticks.
    dates = [datetime.date(2024, 1, 1) + datetime.timedelta(days=30 * i) for i in range(12)]
    vals  = [10, 12, 9, 15, 18, 22, 25, 21, 17, 14, 12, 11]
    c = pt.chart(data_width=400, data_height=180,
                 title="2024 monthly units", ylabel="units", gridlines=True)
    c.line(data={"x": dates, "y": vals}, x="x", y="y", marker="o")
    return c


def chart_time_axis_hours():
    # Hour-resolution datetimes on the y-axis — labels stack vertically so a
    # full day's worth of "HH:MM" ticks have room without rotation.
    base = datetime.datetime(2024, 6, 1, 0, 0, tzinfo=datetime.timezone.utc)
    times = [base + datetime.timedelta(hours=i) for i in range(0, 25, 2)]
    vals  = [math.sin(i / 4) * 5 + 10 for i in range(len(times))]
    c = pt.chart(data_width=220, data_height=320,
                 title="signal over a day", xlabel="value", ylabel="time (UTC)")
    c.line(data={"x": vals, "y": times}, x="x", y="y")
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
    c.legend()
    return c


def chart_violin():
    rng = random.Random(1)
    rows = []
    for group in ("ctrl", "+drug", "low", "high"):
        for trt, shift in (("A", 0.0), ("B", 1.2)):
            mu = {"ctrl": 5, "+drug": 4, "low": 7, "high": 5.5}[group] + shift
            sd = {"ctrl": 1, "+drug": 0.8, "low": 1.4, "high": 1.0}[group]
            for _ in range(80):
                rows.append({"grp": group, "trt": trt,
                             "value": rng.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=380, data_height=220,
                 title="violin fill", xlabel="group", ylabel="value",
                 legend=True)
    c.xscale("category", order=["ctrl", "+drug", "low", "high"])
    c.violin(data=data, x="grp", y="value", fill="trt",
             palette={"A": "#3F97C5", "B": "#F99917"}, inner="box")
    c.legend()
    return c


def chart_swarm():
    rng = random.Random(2)
    rows = []
    for group in ("A", "B", "C", "D"):
        for series, shift in (("a", 0.0), ("b", 0.8)):
            mu = {"A": 3.0, "B": 4.5, "C": 5.2, "D": 6.0}[group] + shift
            sd = {"A": 0.6, "B": 0.7, "C": 0.5, "D": 0.9}[group]
            for _ in range(20):
                rows.append({"group": group, "series": series,
                             "value": rng.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=360, data_height=220,
                 title="swarm fill", xlabel="group", ylabel="value",
                 legend=True)
    c.xscale("category", order=["A", "B", "C", "D"])
    c.swarm(data=data, x="group", y="value", fill="series",
            palette={"a": "#3F97C5", "b": "#F99917"})
    c.legend()
    return c


def chart_strip():
    rng = random.Random(3)
    rows = []
    for cond in ("A", "B", "C", "D"):
        for series, shift in (("a", 0.0), ("b", 0.8)):
            mu = {"A": 3.0, "B": 4.5, "C": 5.2, "D": 6.1}[cond] + shift
            sd = {"A": 0.8, "B": 1.0, "C": 0.6, "D": 1.2}[cond]
            for _ in range(25):
                rows.append({"cond": cond, "series": series,
                             "value": rng.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=360, data_height=220,
                 title="strip fill", xlabel="condition", ylabel="value",
                 legend=True)
    c.xscale("category", order=["A", "B", "C", "D"])
    c.strip(data=data, x="cond", y="value", fill="series",
            palette={"a": "#3F97C5", "b": "#F99917"})
    c.legend()
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
    c.legend()
    return c


def chart_ecdf():
    rng = random.Random(8)
    a = [rng.gauss(0, 1) for _ in range(200)]
    b = [rng.gauss(0.6, 1.3) for _ in range(200)]
    c = pt.chart(data_width=300, data_height=200,
                 title="ECDF", xlabel="value", ylabel="F̂(x)",
                 legend=True)
    c.ecdf(data={"x": a}, x="x", label="control")
    c.ecdf(data={"x": b}, x="x", label="treatment")
    c.legend()
    return c


def chart_rug():
    rng = random.Random(9)
    vals = [rng.gauss(0, 1) for _ in range(150)]
    c = pt.chart(data_width=300, data_height=200,
                 title="density + rug", xlabel="value", ylabel="density")
    c.density_1d(data={"x": vals}, x="x", fill=True)
    c.rug(data={"x": vals}, x="x", color="#444444")
    return c


def chart_density_1d():
    rng = random.Random(10)
    a = [rng.gauss(0, 1) for _ in range(300)]
    b = [rng.gauss(1.2, 1.3) for _ in range(300)]
    c = pt.chart(data_width=300, data_height=200,
                 title="density", xlabel="value", ylabel="density",
                 legend=True)
    c.density_1d(data={"x": a}, x="x", label="control", fill=True)
    c.density_1d(data={"x": b}, x="x", label="treatment", fill=True)
    c.legend()
    return c


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


def chart_kde_2d():
    rng = random.Random(12)
    n = 200
    xs = ([rng.gauss(-1, 0.7) for _ in range(n)]
          + [rng.gauss(1.2, 1.0) for _ in range(n)])
    ys = ([rng.gauss(0, 1.0) for _ in range(n)]
          + [rng.gauss(2, 0.8) for _ in range(n)])
    c = pt.chart(data_width=300, data_height=260,
                 title="2-D KDE", xlabel="x", ylabel="y")
    c.scatter(data={"x": xs, "y": ys}, x="x", y="y", size=1.2, alpha=0.25, color="#444444")
    c.kde_2d(data={"x": xs, "y": ys}, x="x", y="y", n_grid=40, cmap="viridis")
    c.legend()
    return c


def chart_hexbin():
    rng = random.Random(13)
    n = 3000
    xs = [rng.gauss(0, 1) + rng.gauss(0, 0.4) for _ in range(n)]
    ys = [x + rng.gauss(0, 1) for x in xs]
    c = pt.chart(data_width=300, data_height=260,
                 title="hexbin", xlabel="x", ylabel="y")
    c.hexbin(data={"x": xs, "y": ys}, x="x", y="y", gridsize=22)
    return c | pt.legend(c)


def chart_freqpoly():
    rng = random.Random(14)
    a = [rng.gauss(0, 1) for _ in range(400)]
    b = [rng.gauss(1, 1.4) for _ in range(400)]
    c = pt.chart(data_width=300, data_height=200,
                 title="frequency polygon", xlabel="value", ylabel="count",
                 legend=True)
    c.freqpoly(data={"x": a}, x="x", bins=25, label="control")
    c.freqpoly(data={"x": b}, x="x", bins=25, label="treatment")
    c.legend()
    return c


def chart_contour():
    c = pt.chart(data_width=300, data_height=300,
                 title="contour", xlabel="x", ylabel="y")
    c.contour(_peaks_grid(), extent=(-3, 3, -3, 3), cmap="viridis",
              levels=[0.05, 0.1, 0.2, 0.4, 0.6, 0.8])
    c.legend()
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
    c.qq(data={"s": sample}, sample="s", dist="normal")
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
    c.legend()
    return c


def chart_bar_dodge():
    df = _bar_quarterly_df()
    c = pt.chart(data_width=320, data_height=200,
                 title="bar dodge", ylabel="$M", legend=True)
    c.bar(data=df, x="quarter", y="value", fill="series", position="dodge")
    c.legend()
    return c


def chart_named_palette():
    df = _bar_quarterly_df()
    c = pt.chart(data_width=320, data_height=200,
                 title='named palette ("Set2")', ylabel="$M", legend=True)
    c.bar(data=df, x="quarter", y="value", fill="series", position="dodge",
          palette="Set2")
    c.legend()
    return c


def chart_bar_fill():
    df = _bar_quarterly_df()
    c = pt.chart(data_width=300, data_height=200,
                 title="bar fill (100%)", ylabel="share", legend=True)
    c.bar(data=df, x="quarter", y="value", fill="series", position="fill")
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
    c.bar(x="quarter", y="value", fill="series", color="black",
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
    c.bar(data=df, x="cat", y="mean", fill="C0", yerr=("lo", "hi"))
    return c


def chart_bar_dodge_yerr():
    # The canonical grouped mean±err figure. position defaults to
    # "dodge" when yerr= is given; whiskers share the dodge slot centers.
    df = _bar_quarterly_df()
    df["sd"] = [round(0.4 + 0.08 * v, 2) for v in df["value"]]
    c = pt.chart(data_width=320, data_height=200,
                 title="bar dodge ± yerr", ylabel="$M", legend=True)
    c.bar(data=df, x="quarter", y="value", fill="series", yerr="sd")
    c.legend()
    return c


def chart_bar_h_xerr():
    # Horizontal bars take xerr= (the value axis is x); also exercises
    # ecolor= and capsize= overrides.
    df = {"cat": ["alpha", "beta", "gamma"], "mean": [4.2, 5.6, 3.1],
          "err": [0.5, 1.1, 0.4]}
    c = pt.chart(data_width=300, data_height=180,
                 title="bar horizontal ± xerr", xlabel="mean")
    c.bar(data=df, x="cat", y="mean", orientation="h", xerr="err",
          ecolor="gray", capsize=3)
    return c


def chart_errorbar_grouped():
    # color= column → one series per level, dodged within each band,
    # per-group legend entries.
    df = _bar_quarterly_df()
    df["sd"] = [round(0.4 + 0.08 * v, 2) for v in df["value"]]
    c = pt.chart(data_width=320, data_height=200,
                 title="errorbar grouped (dodged)", ylabel="$M", legend=True)
    c.errorbar(data=df, x="quarter", y="value", yerr="sd", color="series")
    c.legend()
    return c


def chart_bar_errorbar_aligned():
    # Composition check: an independently dodged errorbar lands on the
    # same slot centers as bar position="dodge" (width/gap defaults
    # match). Whiskers here are darker than the translucent bars.
    df = _bar_quarterly_df()
    df["sd"] = [round(0.4 + 0.08 * v, 2) for v in df["value"]]
    c = pt.chart(data_width=320, data_height=200,
                 title="bar + errorbar share dodge slots", ylabel="$M")
    c.bar(data=df, x="quarter", y="value", fill="series", position="dodge",
          alpha=0.45)
    c.errorbar(data=df, x="quarter", y="value", yerr="sd", color="series",
               marker=None)
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
    c.legend()
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
    c = pt.chart(df, x="t", y="v",
                 data_width=320, data_height=200,
                 title="redundant color + linestyle",
                 xlabel="t", ylabel="v", legend=True)
    c.line(color="cohort", linestyle="cohort", linewidth=1.6)
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
    c = pt.chart(df, x="t", y="v",
                 data_width=320, data_height=200,
                 title="color + alpha by cohort",
                 xlabel="t", ylabel="v", legend=True)
    c.line(color="cohort", alpha="cohort", linewidth=1.8)
    c.legend()
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
    c.strip(size=3, alpha=0.5)
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
    c.legend()
    return c


def _legend_position_chart(position):
    """A two-line chart with an outside-positioned in-frame legend. Used
    by the legend_outside_* baselines to exercise each `position=` value
    — the data region stays at the user-requested size; the canvas grows
    on the named side to accommodate the legend block."""
    xs = _xs()
    c = pt.chart(title=f"legend {position}",
                 xlabel="t", ylabel="value", gridlines=True,
                 data_width=300, data_height=180)
    c.line(data={"x": xs, "y": [math.sin(x) for x in xs]}, x="x", y="y", label="sin(t)")
    c.line(data={"x": xs, "y": [math.cos(x) for x in xs]}, x="x", y="y", label="cos(t)", linestyle="--")
    c.legend(position=position)
    return c


def chart_legend_outside_right():  return _legend_position_chart("right")
def chart_legend_outside_left():   return _legend_position_chart("left")
def chart_legend_outside_top():    return _legend_position_chart("top")
def chart_legend_outside_bottom(): return _legend_position_chart("bottom")


def chart_legend_ncols_bottom():
    # `c.legend(position="bottom", ncols=3)` — 9 series that would make
    # a single horizontal row far wider than the 300 px chart wrap into
    # a 3-column grid (filled down-then-across), centered below the
    # x-axis band like the single-row bottom legend.
    xs = _xs()
    c = pt.chart(title="legend bottom ncols=3",
                 xlabel="t", ylabel="value", gridlines=True,
                 data_width=300, data_height=180)
    for k in range(9):
        c.line(data={"x": xs, "y": [math.sin(x + k * 0.35) + k * 0.15 for x in xs]},
               x="x", y="y", label=f"phase-{k}")
    c.legend(position="bottom", ncols=3)
    return c


def chart_circular_overlay():
    """`Layout.coordinate(CircularCoordinate)` — overlay semantics.

    Three single-artist charts stacked with `/`. Under a CircularCoordinate
    container, `/` means "overlay each leaf into its own concentric band"
    (not vertical stack) — equal bands by default, `.heights([...])` to
    weight them. The explicit `data_diameter` sizes the data annulus
    exactly (non-default, exercising the knob). The per-band clip stops
    each ring's data from bleeding into neighbours.
    """
    import math
    ts = [i / 60 for i in range(61)]
    sine = [0.5 + 0.4 * math.sin(2 * math.pi * t) for t in ts]
    bar_xs = [(i + 0.5) / 20 for i in range(20)]
    bar_ys = [0.2 + 0.6 * abs(math.cos(math.pi * x)) for x in bar_xs]

    outer = pt.chart(xlim=(0, 1), ylim=(0, 1))
    outer.line(data={"x": ts, "y": sine}, x="x", y="y",
               color="C0", linewidth=1.5)

    middle = pt.chart(xlim=(0, 1), ylim=(0, 1))
    middle.fill_between(data={"x": ts, "lo": [v - 0.1 for v in sine],
                              "hi": [v + 0.1 for v in sine]},
                        x="x", y1="lo", y2="hi",
                        fill="C2", alpha=0.3)

    inner = pt.chart(xlim=(0, 1), ylim=(0, 1))
    inner.scatter(data={"x": ts, "y": sine}, x="x", y="y",
                  color="C3", size=2.5, alpha=0.7)

    return (outer / middle / inner).coordinate(
        pt.CircularCoordinate(data_diameter=240, r_inner=0.20)
    )


def chart_multiline_labels():
    """`\\n` in title / xlabel / ylabel — each extra line adds one
    `line_height` to the label's block, margins grow to fit, and every
    line is anchored (centered) independently."""
    xs = _xs()
    df = {"t": xs, "sin": [math.sin(x) for x in xs]}
    c = pt.chart(df, title="two-line title:\nsecond line",
                 xlabel="time\n(seconds)", ylabel="amplitude\n(unitless)",
                 gridlines=True)
    c.line(x="t", y="sin")
    return c


def _peaks_grid(n=60):
    """Two-bump analytic surface shared by the contour-fill baselines."""
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
    return grid


def chart_contour_filled():
    c = pt.chart(data_width=300, data_height=300,
                 title="filled contour", xlabel="x", ylabel="y")
    c.contour(_peaks_grid(), extent=(-3, 3, -3, 3), cmap="viridis",
              levels=[0.05, 0.1, 0.2, 0.4, 0.6, 0.8], fill=True)
    c.legend()
    return c


def chart_kde_2d_filled_color():
    """kde_2d color= grouping: one single-colored filled density per level."""
    rng = random.Random(23)
    n = 150
    rows_x, rows_y, rows_g = [], [], []
    for g, (mx, my) in zip(["A", "B"], [(-1.0, 0.0), (1.3, 1.8)]):
        for _ in range(n):
            rows_x.append(rng.gauss(mx, 0.8))
            rows_y.append(rng.gauss(my, 0.7))
            rows_g.append(g)
    df = {"x": rows_x, "y": rows_y, "g": rows_g}
    c = pt.chart(data_width=300, data_height=260,
                 title="grouped 2-D KDE (filled)", xlabel="x", ylabel="y",
                 legend=True)
    c.kde_2d(data=df, x="x", y="y", color="g", fill=True, n_grid=40)
    c.legend()
    return c


def chart_hist2d():
    rng = random.Random(24)
    n = 3000
    xs = [rng.gauss(0, 1) for _ in range(n)]
    ys = [x * 0.6 + rng.gauss(0, 0.8) for x in xs]
    c = pt.chart(data_width=300, data_height=260,
                 title="2-D histogram", xlabel="x", ylabel="y")
    c.hist2d(data={"x": xs, "y": ys}, x="x", y="y", bins=25)
    return c | pt.legend(c)


def chart_bar_count():
    """stat='count' — seaborn countplot; rows per (category, group), stacked."""
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
    c.bar(data=df, x="outcome", stat="count", fill="arm")
    c.legend()
    return c


def chart_bar_mean_ci():
    """stat='mean' — seaborn barplot; grouped means dodged with t CI bars."""
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
    c.bar(data=df, x="dose", y="resp", stat="mean", fill="arm")
    c.legend()
    return c


def chart_line_estimator():
    """estimator='mean': replicate rows collapse per x with a CI band —
    seaborn lineplot's aggregation, split by color level."""
    rng = random.Random(27)
    rows_t, rows_v, rows_g = [], [], []
    for g, slope in zip(["ctrl", "trt"], [0.4, 1.0]):
        for t in range(10):
            for _ in range(12):
                rows_t.append(t); rows_g.append(g)
                rows_v.append(slope * t + rng.gauss(0, 1.0))
    df = {"t": rows_t, "v": rows_v, "g": rows_g}
    c = pt.chart(df, x="t", y="v",
                 data_width=320, data_height=200,
                 title="line estimator='mean' ± 95 % CI",
                 xlabel="t", ylabel="v", legend=True)
    c.line(color="g", estimator="mean")
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


def chart_pointplot_color():
    """pointplot color= grouping — one series + CI per level (seaborn hue)."""
    rng = random.Random(30)
    cats = ["1 wk", "2 wk", "4 wk", "8 wk"]
    rows_t, rows_s, rows_a = [], [], []
    for arm, slope in zip(["control", "drug"], [0.04, 0.45]):
        for i, t in enumerate(cats):
            for _ in range(20):
                rows_t.append(t); rows_a.append(arm)
                rows_s.append(rng.gauss(5.0 + slope * i, 1.0))
    df = {"t": rows_t, "score": rows_s, "arm": rows_a}
    c = pt.chart(data_width=320, data_height=200,
                 title="pointplot color=", xlabel="timepoint",
                 ylabel="score", legend=True)
    c.xscale("category", order=cats)
    c.pointplot(data=df, x="t", y="score", color="arm")
    c.legend()
    return c


def chart_ridge_color():
    """ridge color= grouping — overlaid sub-densities per row."""
    rng = random.Random(32)
    rows_m, rows_v, rows_g = [], [], []
    for i, month in enumerate(["Jan", "Feb", "Mar", "Apr"]):
        for g, shift in zip(["day", "night"], [0.0, 4.0]):
            for _ in range(150):
                rows_m.append(month); rows_g.append(g)
                rows_v.append(rng.gauss(15 + i * 2 + shift, 2.5))
    df = {"month": rows_m, "temp": rows_v, "period": rows_g}
    c = pt.chart(data_width=320, data_height=260,
                 title="grouped ridge", xlabel="temperature", legend=True)
    c.ridge(data=df, x="month", y="temp", color="period", overlap=1.6)
    c.yticks([])
    c.legend()
    return c


def chart_qq_color():
    """qq color= grouping — per-level quantiles and robust reference lines."""
    rng = random.Random(33)
    rows_v, rows_g = [], []
    for _ in range(120):
        rows_v.append(rng.gauss(0, 1)); rows_g.append("normal-ish")
    for _ in range(120):
        rows_v.append(rng.gauss(0, 1) + 0.8 * (rng.expovariate(1) - 1))
        rows_g.append("skewed")
    df = {"v": rows_v, "g": rows_g}
    c = pt.chart(data_width=280, data_height=240,
                 title="grouped Q-Q vs N(0, 1)",
                 xlabel="theoretical quantile",
                 ylabel="sample quantile", legend=True)
    c.qq(data=df, sample="v", color="g")
    c.legend()
    return c


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
    "axline":              chart_axline,
    "category_x_scatter":  chart_category_x_scatter,
    "category_x_order":    chart_category_x_order,
    "category_y_scatter":  chart_category_y_scatter,
    "category_y_order":    chart_category_y_order,
    "hide_yticks":         chart_hide_yticks,
    "xticks_rotation":     chart_xticks_rotation,
    "xticks_flipped_sides": chart_xticks_flipped_sides,
    "xticks_top_share_x":  chart_xticks_top_share_x,
    "xticks_inward":       chart_xticks_inward,
    "xticks_marks_off":    chart_xticks_marks_off,
    "xticks_explicit":     chart_xticks_explicit,
    "category_padding_0":  chart_category_padding_zero,
    "imshow_rect":         chart_imshow_rect,
    "imshow_png":          chart_imshow_png,
    "imshow_diverging":    chart_imshow_diverging,
    "imshow_origin_upper": chart_imshow_origin_upper,
    "imshow_center":       chart_imshow_diverging_center,
    "imshow_log":          chart_imshow_log_norm,
    "imshow_user_cmap":    chart_imshow_user_cmap,
    "heatmap_labeled":     chart_heatmap_labeled,
    "heatmap_dataframe":   chart_heatmap_dataframe,
    "heatmap_annot":       chart_heatmap_annot,
    "heatmap_categorical": chart_heatmap_categorical,
    "heatmap_nan":         chart_heatmap_nan,
    "heatmap_palette_annot": chart_heatmap_palette_annot,
    "heatmap_continuous_x":       chart_heatmap_continuous_x,
    "heatmap_continuous_x_cat_y": chart_heatmap_continuous_x_cat_y,
    "heatmap_continuous_uneven":  chart_heatmap_continuous_uneven,
    "heatmap_continuous_nan":     chart_heatmap_continuous_nan,
    "heatmap_split":          chart_heatmap_split,
    "heatmap_split_attached": chart_heatmap_split_attached,
    "heatmap_block_titles":   chart_heatmap_block_titles,
    "heatmap_block_filled":   chart_heatmap_block_filled,
    "dendrogram_split":          chart_dendrogram_split,
    "dendrogram_split_parent":   chart_dendrogram_split_parent,
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
    "circular_overlay":    chart_circular_overlay,
    "dendrogram_top":      chart_dendrogram_top,
    "dendrogram_left":     chart_dendrogram_left,
    "dendrogram_styled":   chart_dendrogram_styled,
    "dendrogram_labeled":  chart_dendrogram_labeled,
    "tick_format_string":  chart_tick_format_string,
    "tick_format_named":    chart_tick_format_named,
    "time_axis_dates":     chart_time_axis_dates,
    "time_axis_hours":     chart_time_axis_hours,
    "scatter_size":        chart_scatter_size,
    "scatter_size_style_color": chart_scatter_size_style_color,
    "facet_scatter":       chart_facet_scatter,
    "facet_wrap_two_rows": chart_facet_wrap_two_rows,
    "facet_grid_two_factor": chart_facet_grid_two_factor,
    "hist_stack":          chart_hist_stack,
    "hist_dodge":          chart_hist_dodge,
    "hist_binwidth_cumulative": chart_hist_binwidth_cumulative,
    "aspect_equal":        chart_aspect_equal,
    "symlog_x":            chart_symlog_x,
    "sqrt_y":              chart_sqrt_y,
    "reverse_y":           chart_reverse_y,
    "minor_ticks_linear":  chart_minor_ticks_linear,
    "minor_ticks_log":     chart_minor_ticks_log,
    "minor_grid":          chart_minor_grid,
    "minor_grid_log":      chart_minor_grid_log,
    "subtitle_caption":    chart_subtitle_caption,
    "power10_math_text":   chart_power10_math_text,
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
    "legend_ncols_bottom":   chart_legend_ncols_bottom,
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
    "named_palette":         chart_named_palette,
    "bar_fill":              chart_bar_fill,
    "bar_long_fill":         chart_bar_long_fill,
    "bar_yerr":              chart_bar_yerr,
    "bar_dodge_yerr":        chart_bar_dodge_yerr,
    "bar_h_xerr":            chart_bar_h_xerr,
    "errorbar_grouped":      chart_errorbar_grouped,
    "bar_errorbar_aligned":  chart_bar_errorbar_aligned,
    "area_stack":            chart_area_stack,
    "scatter_long_color":    chart_scatter_long_color,
    "density_1d_long_color": chart_density_1d_long_color,
    "aes_inheritance":       chart_aes_inheritance,
    "regression_color":      chart_regression_color,
    "line_group":            chart_line_group,
    "line_linetype":         chart_line_linetype,
    "line_alpha":            chart_line_alpha,
    "multiline_labels":      chart_multiline_labels,
    "contour_filled":        chart_contour_filled,
    "kde_2d_filled_color":   chart_kde_2d_filled_color,
    "hist2d":                chart_hist2d,
    "bar_count":             chart_bar_count,
    "bar_mean_ci":           chart_bar_mean_ci,
    "line_estimator":        chart_line_estimator,
    "regression_order2":     chart_regression_order2,
    "regression_lowess":     chart_regression_lowess,
    "regression_robust":     chart_regression_robust,
    "pointplot_color":       chart_pointplot_color,
    "ridge_color":           chart_ridge_color,
    "qq_color":              chart_qq_color,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_baseline(name, fn, baseline_compare):
    baseline_compare("chart", name, fn().to_svg())


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


def test_bar_err_rejects_stack():
    df = _bar_quarterly_df()
    df["sd"] = [0.5] * len(df["value"])
    c = pt.chart()
    c.bar(data=df, x="quarter", y="value", fill="series", yerr="sd",
          position="stack")
    with pytest.raises(ValueError, match="position='dodge'"):
        c.to_svg()


def test_bar_err_rejects_duplicate_rows():
    df = {"cat": ["a", "a"], "v": [1, 2], "sd": [0.1, 0.2]}
    c = pt.chart()
    c.bar(data=df, x="cat", y="v", yerr="sd")
    with pytest.raises(ValueError, match="one row per"):
        c.to_svg()


def test_bar_err_matches_orientation():
    df = {"cat": ["a", "b"], "v": [1, 2], "sd": [0.1, 0.2]}
    c = pt.chart()
    c.bar(data=df, x="cat", y="v", xerr="sd")
    with pytest.raises(TypeError, match="yerr"):
        c.to_svg()
    c = pt.chart()
    c.bar(data=df, x="cat", y="v", orientation="h", yerr="sd")
    with pytest.raises(TypeError, match="xerr"):
        c.to_svg()


# ---------------------------------------------------------------------------
# hist binning vocabulary + position (no baselines)


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
        c.hist(x="v", fill="g", bins=[0, 1], position=position)
        import re
        m = re.search(r'data-plotlet-ylim="([^"]*)"', c.to_svg())
        return float(m.group(1).split(",")[1])

    assert ylim_hi("stack") >= 5
    assert ylim_hi("overlay") < 5


def test_hist_weights_column():
    df = {"v": [0.5, 0.5, 1.5], "w": [2.0, 3.0, 5.0]}
    c = pt.chart(df)
    c.hist(x="v", bins=[0, 1, 2], weights="w")
    assert 'data-plotlet-count-max="5"' in c.to_svg()


def test_hist_rejects_bad_binning_combos():
    def render(**kw):
        c = pt.chart({"v": [1, 2, 3]})
        c.hist(x="v", **kw)
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


# ---------------------------------------------------------------------------
# two-factor facet grid (no baselines)


def _facet_grid_df():
    # 2x2 factor space with the (F, b) combination absent.
    return {
        "x": [1, 2, 3, 4, 5, 6],
        "y": [1, 2, 3, 4, 5, 6],
        "r": ["M", "M", "M", "M", "F", "F"],
        "c": ["a", "a", "b", "b", "a", "a"],
    }


def test_facet_grid_missing_combo_is_blank():
    g = pt.facet(_facet_grid_df(), row="r", col="c")
    g.scatter(x="x", y="y")
    assert g.to_svg().count('data-plotlet-kind="panel"') == 3


def test_facet_single_factor_orientation():
    import re

    def panel_origins(**facet_kw):
        g = pt.facet(_facet_grid_df(), **facet_kw)
        g.scatter(x="x", y="y")
        boxes = re.findall(r'data-plotlet-panel-bbox="([^"]*)"', g.to_svg())
        return [tuple(float(v) for v in b.split(",")[:2]) for b in boxes]

    rows = panel_origins(row="r")     # stacked: same x, distinct y
    assert len(rows) == 2
    assert rows[0][0] == rows[1][0] and rows[0][1] != rows[1][1]
    cols = panel_origins(col="c")     # side by side: distinct x, same y
    assert len(cols) == 2
    assert cols[0][0] != cols[1][0] and cols[0][1] == cols[1][1]


def test_facet_mode_validation():
    df = _facet_grid_df()
    with pytest.raises(TypeError, match="not both"):
        pt.facet(df, by="r", col="c")
    with pytest.raises(TypeError, match="requires by="):
        pt.facet(df)
    with pytest.raises(TypeError, match="col_wrap= applies to by="):
        pt.facet(df, row="r", col_wrap=2)


def test_facet_grid_json_roundtrip():
    import json
    from plotlet._journal import to_json, from_json

    def build():
        g = pt.facet(_facet_grid_df(), row="r", col="c")
        g.scatter(x="x", y="y")
        return g

    node = from_json(json.loads(json.dumps(to_json(build()))))
    assert node.to_svg() == build().to_svg()


# ---------------------------------------------------------------------------
# data-space aspect-ratio lock (no baselines)


def _unit_px_ratio(svg):
    """px-per-y-unit divided by px-per-x-unit for the (single) panel."""
    import re
    w, h = [float(v) for v in re.search(
        r'data-plotlet-data-area="([^"]*)"', svg).group(1).split(",")[2:4]]
    x0, x1 = [float(v) for v in re.search(
        r'data-plotlet-xlim="([^"]*)"', svg).group(1).split(",")]
    y0, y1 = [float(v) for v in re.search(
        r'data-plotlet-ylim="([^"]*)"', svg).group(1).split(",")]
    return (h / (y1 - y0)) / (w / (x1 - x0))


def test_aspect_locks_unit_ratio():
    df = {"x": [0, 10], "y": [0, 5]}
    for r in (1.0, 2.0, 0.5):
        c = pt.chart(df, data_width=300, data_height=137)
        c.scatter(x="x", y="y")
        c.aspect(r)
        assert abs(_unit_px_ratio(c.to_svg()) - r) < 1e-9
    c = pt.chart(df, data_width=300)
    c.scatter(x="x", y="y")
    c.aspect("equal")
    assert abs(_unit_px_ratio(c.to_svg()) - 1.0) < 1e-9


def test_aspect_survives_fit():
    # The derived dim rounds to whole pixels, so after fit() the lock is
    # exact to half a pixel over the panel, not to float precision.
    c = pt.chart({"x": [0, 10], "y": [0, 5]}, data_width=300)
    c.scatter(x="x", y="y")
    c.aspect("equal")
    assert abs(_unit_px_ratio(c.fit(canvas_width=180).to_svg()) - 1.0) < 0.01


def test_aspect_anchor_height_propagates_to_share_class():
    import re
    a = pt.chart({"x": [0, 10], "y": [0, 5]}, data_width=200)
    a.scatter(x="x", y="y")
    a.aspect("equal")
    b = pt.chart({"x": [0, 10], "y": [0, 5]}, data_width=200)
    b.scatter(x="x", y="y")
    svg = (a | b).share_y().to_svg()
    heights = [box.split(",")[3] for box in
               re.findall(r'data-plotlet-data-area="([^"]*)"', svg)]
    assert len(heights) == 2 and heights[0] == heights[1]


def test_aspect_validation():
    c = pt.chart({"x": ["a", "b"], "y": [1, 2]})
    c.bar(x="x", y="y")
    c.aspect(1)
    with pytest.raises(ValueError, match="same scale kind"):
        c.to_svg()

    c = pt.chart({"x": [1, 100], "y": [0, 5]})
    c.scatter(x="x", y="y")
    c.xscale("log")
    c.aspect(1)
    with pytest.raises(ValueError, match="same scale kind"):
        c.to_svg()

    c = pt.chart({"x": [0, 1], "y": [0, 1]})
    c.scatter(x="x", y="y")
    c.aspect(-2)
    with pytest.raises(ValueError, match="positive"):
        c.to_svg()

    a = pt.chart({"x": [0, 1], "y": [0, 1]})
    a.scatter(x="x", y="y")
    b = pt.chart({"x": [0, 1], "y": [0, 1]})
    b.scatter(x="x", y="y")
    b.aspect(1)
    fig = (a | b).share_x(True).share_y(True)
    with pytest.raises(ValueError, match="sharing both axes"):
        fig.to_svg()


def test_facet_aspect_lock():
    # facet defaults share_x=share_y=True and replays aspect() onto every
    # panel; the forced anchor dims satisfy the lock (same union domains),
    # so this must render — with the ratio holding in each panel.
    import re
    g = pt.facet(_facet_grid_df(), col="c")
    g.scatter(x="x", y="y")
    g.aspect("equal")
    svg = g.to_svg()
    areas = re.findall(r'data-plotlet-data-area="([^"]*)"', svg)
    xlims = re.findall(r'data-plotlet-xlim="([^"]*)"', svg)
    ylims = re.findall(r'data-plotlet-ylim="([^"]*)"', svg)
    assert len(areas) == 2
    for area, xl, yl in zip(areas, xlims, ylims):
        w, h = [float(v) for v in area.split(",")[2:4]]
        x0, x1 = [float(v) for v in xl.split(",")]
        y0, y1 = [float(v) for v in yl.split(",")]
        assert abs((h / (y1 - y0)) / (w / (x1 - x0)) - 1.0) < 0.01


# ---------------------------------------------------------------------------
# multi-line title / axis labels (no baselines)


def test_multiline_label_geometry():
    """`\\n` in title / xlabel / ylabel grows the figure by exactly one
    `line_height` per extra line on the matching side, and the recorded
    text-block regions are one `line_height` taller / wider."""
    from plotlet.draw import line_height, measure_text, text_block_height
    from plotlet._spec import _FONTSPEC
    from plotlet.render import natural_size

    # measure_text on multi-line = widest line; block height adds one
    # line_height per extra line on top of the bare size.
    assert measure_text("ab\nabcdef", 14) == measure_text("abcdef", 14)
    assert text_block_height("ab", 14) == 14
    assert text_block_height("ab\ncd\nef", 14) == 14 + 2 * line_height(14)

    def cell(title, xlabel, ylabel):
        c = pt.chart(title=title, xlabel=xlabel, ylabel=ylabel,
                     data_width=200, data_height=140)
        c.line(data={"x": [0, 1, 2], "y": [1, 0, 2]}, x="x", y="y")
        return c

    W0, H0 = natural_size(pt.to_ir(cell("t", "x", "y")))
    W1, H1 = natural_size(pt.to_ir(cell("t\nt2", "x\nx2", "y\ny2")))
    lh_title = line_height(_FONTSPEC["title_size"])
    lh_label = line_height(_FONTSPEC["label_size"])
    assert abs((H1 - H0) - (lh_title + lh_label)) <= 1   # title + xlabel lines
    assert abs((W1 - W0) - lh_label) <= 1                # ylabel line

    two = cell("t\nt2", "x\nx2", "y\ny2")
    two.to_svg()
    regs = {r["name"]: r for r in two.regions() if r["name"] in
            ("title", "xlabel", "ylabel", "panel")}
    one = cell("t", "x", "y")
    one.to_svg()
    regs1 = {r["name"]: r for r in one.regions() if r["name"] in
             ("title", "xlabel", "ylabel")}
    assert abs(regs["title"]["bbox"][3] - (regs1["title"]["bbox"][3] + lh_title)) < 0.01
    assert abs(regs["xlabel"]["bbox"][3] - (regs1["xlabel"]["bbox"][3] + lh_label)) < 0.01
    # ylabel is rotated 90° — the extra line grows its screen WIDTH.
    assert abs(regs["ylabel"]["bbox"][2] - (regs1["ylabel"]["bbox"][2] + lh_label)) < 0.01

    # No label block may bleed into the panel.
    px, py, pw, ph = regs["panel"]["bbox"]
    tx, ty, tw, th = regs["title"]["bbox"]
    assert ty + th <= py
    xx, xy, xw, xh = regs["xlabel"]["bbox"]
    assert xy >= py + ph
    yx, yy, yw, yh = regs["ylabel"]["bbox"]
    assert yx + yw <= px


# ---------------------------------------------------------------------------
# heatmap input validation + encoding structure (no baselines)


def test_heatmap_unsorted_x_matches_sorted():
    # Tidy rows carry no order contract — record sorts by x, so any row
    # order renders the same SVG.
    a = pt.chart()
    a.heatmap(data={"x": [0.0, 2.0, 1.0, 3.0], "v": [10, 20, 30, 40]}, x="x")
    b = pt.chart()
    b.heatmap(data={"x": [0.0, 1.0, 2.0, 3.0], "v": [10, 30, 20, 40]}, x="x")
    assert a.to_svg() == b.to_svg()


def test_heatmap_unsorted_x_permutes_annot():
    # A custom 2-D annot is [track][position] in input order and must be
    # permuted along with the columns.
    a = pt.chart()
    a.heatmap(data={"x": [1.0, 0.0], "v": [7.0, 5.0]}, x="x",
              annot=[["b", "a"]])
    b = pt.chart()
    b.heatmap(data={"x": [0.0, 1.0], "v": [5.0, 7.0]}, x="x",
              annot=[["a", "b"]])
    assert a.to_svg() == b.to_svg()


def test_heatmap_rejects_bad_continuous_x():
    # Duplicate, NaN, or numbers-mixed-with-None x would silently produce
    # zero-width / NaN / mislabeled cells — all raise instead.
    for xs in ([1.0, 1.0, 2.0],
               [0.0, float("nan"), 2.0],
               [0.5, None, 1.0]):
        c = pt.chart()
        c.heatmap(data={"x": xs, "v": [1, 2, 3]}, x="x")
        with pytest.raises(ValueError):
            c.to_svg()


def test_heatmap_rejects_unknown_kwargs():
    c = pt.chart()
    c.heatmap(data={"x": ["a"], "v": [1]}, x="x", xticklabels=["a"])
    # The record signature is the kwarg allow-list — Python rejects
    # unknown names at replay.
    with pytest.raises(TypeError, match="xticklabels"):
        c.to_svg()


def test_heatmap_rejects_non_dict_palette():
    # A chart-level palette list (meant for color-cycling marks) is
    # injected into the heatmap call by aes inheritance — reject it
    # clearly instead of crashing on `_palette.items()` at draw.
    c = pt.chart(data={"x": [0.0, 1.0], "v": [1.0, 2.0]}, x="x",
                 palette=["#111111", "#222222"])
    c.heatmap()
    with pytest.raises(TypeError, match="palette"):
        c.to_svg()


def test_heatmap_inherited_y_not_a_track():
    # A chart-level y binding must not be swept into the value tracks.
    c = pt.chart(data={"x": ["a", "b"], "v": [1.0, 2.0], "w": [3.0, 4.0]},
                 x="x", y="w")
    c.heatmap()
    assert 'rows="1"' in c.to_svg()


def test_heatmap_numeric_x_categorical_scale_raises():
    # Categorical sectors force a category x scale, which maps numeric
    # cell edges to NaN — every cell would render invisible.
    c = pt.chart()
    c.sectors({"A": [1, 2], "B": [3]}, axis="x")
    c.heatmap(data={"id": [1, 2, 3], "t": [1.0, 2.0, 3.0]}, x="id")
    with pytest.raises(ValueError, match="categorical x scale"):
        c.to_svg()


def test_heatmap_numpy_scalar_x_is_continuous():
    # numpy scalars don't subclass int/float; the numbers.Real-based
    # dispatch must still classify an int64 column as continuous.
    np = pytest.importorskip("numpy")
    xs = list(np.arange(3))    # np.int64 elements, as DataFrameLite yields
    c = pt.chart()
    c.heatmap(data={"x": xs, "v": [1.0, 2.0, 3.0]}, x="x")
    assert 'x-axis="continuous"' in c.to_svg()


def _big_continuous_heatmap(with_y_sectors):
    tracks = [f"t{i}" for i in range(20)]
    data = {"x": [float(i) for i in range(501)]}
    for r, name in enumerate(tracks):
        data[name] = [math.sin(0.01 * i + r) for i in range(501)]
    c = pt.chart(data_width=400, data_height=300)
    if with_y_sectors:
        c.sectors({"A": tracks[:10], "B": tracks[10:]}, axis="y",
                  divider=False, label=False)
    c.heatmap(data=data, x="x", values=tracks, cmap="viridis")
    return c.to_svg()


def test_heatmap_large_grid_encoding_matches_markup():
    # Plain large grid (>imshow_max_rects) → one PNG, attr says so.
    svg = _big_continuous_heatmap(with_y_sectors=False)
    assert svg.count("<image") == 1
    assert 'data-encoding="png-embedded"' in svg
    # y sector splits force rects — a single stretched image would paint
    # over the gap and shift rows off their bands — and the attr follows
    # the actual markup.
    svg = _big_continuous_heatmap(with_y_sectors=True)
    assert "<image" not in svg
    assert 'data-encoding="rects"' in svg


def test_heatmap_large_categorical_ring_uses_rects():
    # The warp guard is dtype-independent: a big categorical-x heatmap on
    # a Circular panel must not fall back to a flat unwarped <image>.
    tracks = [f"t{i}" for i in range(20)]
    data = {"x": [f"c{i}" for i in range(501)]}
    for r, name in enumerate(tracks):
        data[name] = [math.sin(0.01 * i + r) for i in range(501)]
    c = pt.chart(data_width=300, data_height=300)
    c.coordinate(pt.CircularCoordinate(r_inner=0.3))
    c.heatmap(data=data, x="x", values=tracks, cmap="viridis")
    assert "<image" not in c.to_svg()


# ---------- notebook display / PNG rasterization ----------

def _png_dims(png: bytes) -> tuple[int, int]:
    """Width/height straight from the IHDR chunk."""
    import struct
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", png[16:24])


def test_repr_mimebundle_png():
    c = pt.chart(title="t")
    c.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    data, meta = c._repr_mimebundle_()
    png = data["image/png"]
    w, h = meta["image/png"]["width"], meta["image/png"]["height"]
    # metadata carries the logical (1x) size off the svg root tag
    svg = c.to_svg()
    assert f'width="{w}" height="{h}"' in svg[:200]
    # pixels are rendered at _REPR_SCALE x the logical size
    from plotlet.chart import _REPR_SCALE
    assert _png_dims(png) == (w * _REPR_SCALE, h * _REPR_SCALE)
    # deterministic — same journal, byte-identical PNG
    data2, _ = c._repr_mimebundle_()
    assert data2["image/png"] == png


def test_save_png_scale(tmp_path):
    c = pt.chart(title="t")
    c.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    from plotlet.chart import _svg_size
    w, h = _svg_size(c.to_svg())
    c.save_png(tmp_path / "one.png")
    c.save_png(tmp_path / "two.png", scale=2)
    assert _png_dims((tmp_path / "one.png").read_bytes()) == (w, h)
    assert _png_dims((tmp_path / "two.png").read_bytes()) == (2 * w, 2 * h)


def test_png_paints_figure_background():
    # The background rect must survive rasterization (the reason it is a
    # real rect, not CSS). Check the top-left pixel of an RGBA PNG by
    # decoding the first scanline with zlib — no image library needed.
    import struct, zlib

    def corner_rgba(png):
        assert png[25] == 6  # IHDR color type: RGBA
        # walk chunks to the IDAT payload
        pos, idat = 8, b""
        while pos < len(png):
            (ln,), typ = struct.unpack(">I", png[pos:pos + 4]), png[pos + 4:pos + 8]
            if typ == b"IDAT":
                idat += png[pos + 8:pos + 8 + ln]
            pos += 12 + ln
        raw = zlib.decompress(idat)
        # first pixel of the first scanline: every PNG filter type
        # reduces to the raw value (no left/up neighbours to add)
        return tuple(raw[1:5])

    c = pt.chart(title="t")
    c.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    from plotlet.chart import _svg_to_png
    assert corner_rgba(_svg_to_png(c.to_svg())) == (255, 255, 255, 255)

    d = pt.chart(theme="dark", title="t")
    d.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    assert corner_rgba(_svg_to_png(d.to_svg())) == (31, 31, 31, 255)


def test_show_rejects_unknown_format():
    c = pt.chart(title="t")
    c.line(data={"x": [1, 2], "y": [1, 2]}, x="x", y="y")
    with pytest.raises(ValueError, match="png.*svg"):
        c.show(format="jpeg")


# ---------------------------------------------------------------------------
# category <metadata> block — CDATA escaping (no baselines)


def test_category_metadata_survives_cdata_breakout():
    # A category label containing `]]>` must not terminate the CDATA
    # section early — that would leave raw markup outside it (injection)
    # and break XML parsing.
    import json
    import xml.etree.ElementTree as ET
    label = ']]><script>alert(1)</script>'
    c = pt.chart({"cat": ["a", label], "v": [1, 2]})
    c.bar(x="cat", y="v")
    svg = c.to_svg()
    root = ET.fromstring(svg)
    assert not [el for el in root.iter() if el.tag.endswith("script")]
    # the label round-trips inside the metadata block's JSON payload
    meta = [el for el in root.iter()
            if el.tag.endswith("metadata")
            and el.get("data-plotlet-payload") == "xcategories"]
    assert len(meta) == 1
    assert json.loads(meta[0].text) == ["a", label]
    # clean=True strips the whole block despite the split CDATA sections
    cleaned = c.to_svg(clean=True)
    assert "<metadata" not in cleaned and "CDATA" not in cleaned
    assert "script" not in cleaned


def test_fit_scales_insets():
    # Insets are placed by an axes-fraction rect but sized absolutely —
    # fit() must scale them with the host or they overflow their
    # declared fraction of the shrunken panel.
    c = pt.chart({"x": [1, 2, 3], "y": [1, 4, 9]},
                 data_width=400, data_height=300)
    c.line(x="x", y="y")
    ins = c.inset((0.6, 0.6, 0.35, 0.35))
    ins.line(data={"x": [1, 2], "y": [2, 1]}, x="x", y="y")

    fitted = c.fit(canvas_width=250)
    host_ratio = fitted._data_width / c._data_width
    inset_ratio = fitted._insets[0][1]._data_width / ins._data_width
    assert abs(host_ratio - inset_ratio) < 0.05


def test_hexbin_colorbar_matches_drawn_counts():
    # The colorbar must label the range the cells were actually colored
    # with. It used to default to a record-time density guess
    # (n / (gridsize²/4)) — for clustered data the real max is far
    # higher, so the legend silently labeled the wrong range.
    c = pt.chart({"x": [1.0] * 100, "y": [2.0] * 100}, legend=True)
    c.hexbin(x="x", y="y")   # every point lands in one cell: true max 100
    labels = [r["meta"].get("text") for r in c.regions()
              if r["kind"] == "text" and r["name"] == "legend-text"]
    assert labels == ["0", "50", "100"]


def test_swarm_drops_nan():
    # NaN has no position: it used to emit cy="nan" circles and degrade
    # collision placement of every neighboring point.
    nan = float("nan")
    c = pt.chart({"cat": ["a", "a", "a", "b"], "v": [1.0, nan, 2.0, nan]})
    c.swarm(x="cat", y="v")
    svg = c.to_svg()
    assert "nan" not in svg
    assert svg.count("<circle") == 2


def test_log_scale_single_point_domain():
    # lo == hi padding must stay positive on log scales — the linear
    # ±0.5 pad used to push a value < 0.5 to a negative bound and crash
    # with "log scale needs strictly positive domain".
    import re
    c = pt.chart({"x": [0.3], "y": [1.0]})
    c.scatter(x="x", y="y")
    c.xscale("log")
    m = re.search(r'data-plotlet-xlim="([^"]*)"', c.to_svg())
    lo, hi = (float(v) for v in m.group(1).split(","))
    assert 0 < lo < 0.3 < hi


def test_clean_strips_metadata_containing_close_tag():
    # A label containing a literal `</metadata>` sits legally inside CDATA;
    # clean=True must strip to the block's real terminator, not the label.
    label = "</metadata>x"
    c = pt.chart({"cat": [label, "b"], "v": [1, 2]})
    c.bar(x="cat", y="v")
    cleaned = c.to_svg(clean=True)
    assert "metadata" not in cleaned and "CDATA" not in cleaned


# ---------------------------------------------------------------------------
# bar stat= aggregation (no baselines)


def test_bar_stat_count_heights():
    df = {"cat": ["a", "a", "b", "a"]}
    c = pt.chart(df)
    c.bar(x="cat", stat="count")
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
        c.bar(x="cat", y="v", stat="mean", **kw)
        m = re.search(r'data-plotlet-ylim="([^"]*)"', c.to_svg())
        return float(m.group(1).split(",")[1])

    _, ci_hi = t_ci_mean(vals, 0.95)   # mean 2.5, CI well past 4
    assert ylim_hi() >= ci_hi
    assert ylim_hi(ci=None) < ci_hi


def test_bar_stat_validation():
    df = {"cat": ["a", "b"], "v": [1, 2]}

    def bar(**kw):
        c = pt.chart(df)
        c.bar(x="cat", **kw)
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
    c.bar(x="cat", y="v", stat="mean", fill="g", position="stack")
    with pytest.raises(ValueError, match="stacked means"):
        c.to_svg()


# ---------------------------------------------------------------------------
# line estimator= aggregation (no baselines)


def test_line_estimator_aggregates():
    df = {"x": [0, 0, 1, 1], "y": [1.0, 3.0, 2.0, 6.0]}
    c = pt.chart(df)
    c.line(x="x", y="y", estimator="mean", ci=None)
    svg = c.to_svg()
    assert 'data-plotlet-n="2"' in svg
    assert 'data-plotlet-estimator="mean"' in svg
    assert 'data-plotlet-y-max="4"' in svg   # mean of (2, 6)


def test_line_ci_band_extends_domain():
    import re
    df = {"x": [0, 0, 0, 1, 1, 1], "y": [1, 2, 3, 4, 5, 6]}

    def ylim_hi(**kw):
        c = pt.chart(df)
        c.line(x="x", y="y", estimator="mean", **kw)
        m = re.search(r'data-plotlet-ylim="([^"]*)"', c.to_svg())
        return float(m.group(1).split(",")[1])

    assert ylim_hi() > 7        # t CI on mean(4,5,6) reaches ~7.5
    assert ylim_hi(ci=None) < 7


def test_line_ci_band_clips_on_log_scale():
    import re
    # all-positive data whose t CI lower bound goes negative
    df = {"x": [0, 0, 0, 1, 1, 1], "y": [1.0, 10.0, 100.0, 2.0, 20.0, 200.0]}
    c = pt.chart(df)
    c.line(x="x", y="y", estimator="mean")
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

    def line(fn="line", **kw):
        c = pt.chart(df)
        getattr(c, fn)(x="x", y="y", **kw)
        c.to_svg()

    with pytest.raises(TypeError, match="apply with estimator"):
        line(ci="t")
    with pytest.raises(ValueError, match="estimator="):
        line(estimator="max")
    with pytest.raises(ValueError, match="curve"):
        line(fn="step", estimator="mean")
    with pytest.raises(ValueError, match="ci='x'"):
        line(estimator="mean", ci="x")


# ---------------------------------------------------------------------------
# regression order= / robust= (no baselines)


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


# ---------------------------------------------------------------------------
# hist2d (no baselines)


def test_hist2d_counts_and_transparent_empties():
    import re
    df = {"x": [0.5, 0.5, 1.5, 2.5], "y": [0.5, 0.5, 0.5, 1.5]}
    c = pt.chart(df)
    c.hist2d(x="x", y="y", bins=([0, 1, 2, 3], [0, 1, 2]))
    svg = c.to_svg()
    assert 'data-plotlet-count-max="2"' in svg
    assert 'data-plotlet-bins-x="3"' in svg
    assert 'data-plotlet-bins-y="2"' in svg
    # 3 occupied cells drawn, 3 empty cells transparent (no rect at all)
    assert len(re.findall(r'fill="rgb\(', svg)) == 3


def test_hist2d_validation():
    df = {"x": [1, 2], "y": [1, 2]}
    c = pt.chart(df)
    c.hist2d(x="x", y="y", bins=5, binwidth=0.5)
    with pytest.raises(TypeError, match="bins= or binwidth="):
        c.to_svg()


def test_hist2d_two_item_bins():
    # bins=[0, 5] is a shared edge sequence (0 can't be a bin count) —
    # the int form must mean the same as the float form, not (0, 5) counts
    df = {"x": [1.0, 2.0, 4.0], "y": [1.0, 2.0, 4.0]}
    for edges in ([0, 5], [0.0, 5.0]):
        c = pt.chart(df)
        c.hist2d(x="x", y="y", bins=edges)
        svg = c.to_svg()
        assert 'data-plotlet-bins-x="1"' in svg
        assert 'data-plotlet-count-max="3"' in svg
    # a valid 2-int pair keeps the numpy (x_bins, y_bins) meaning
    c = pt.chart(df)
    c.hist2d(x="x", y="y", bins=[2, 5])
    svg = c.to_svg()
    assert 'data-plotlet-bins-x="2"' in svg
    assert 'data-plotlet-bins-y="5"' in svg


def test_utils_all_names_exist():
    # `from plotlet.utils import *` must not raise — every exported
    # name has to exist (the removed `histogram` lingered here once)
    import plotlet.utils as utils
    for name in utils.__all__:
        assert hasattr(utils, name), name


def test_attach_above_promotes_subtitle():
    def build(**chart_kw):
        host = pt.chart({"x": [1, 2, 3], "y": [1, 2, 3]}, **chart_kw)
        host.scatter(x="x", y="y")
        top = pt.chart(data_height=30)
        top.line(data={"x": [1, 2, 3], "y": [1, 2, 1]}, x="x", y="y")
        host.attach_above(top)
        return host.regions()

    def named(regions, name):
        return [r for r in regions if r["name"] == name]

    def panels_top(regions):
        return min(r["bbox"][1] for r in named(regions, "panel"))

    # title + subtitle promote together above the attached panel
    regions = build(title="Tmain", subtitle="Ssub")
    (sub,) = named(regions, "subtitle")      # promoted, not drawn twice
    (title,) = named(regions, "title")
    assert sub["bbox"][1] < panels_top(regions)
    assert title["bbox"][1] < sub["bbox"][1]
    # a subtitle-only host promotes too
    regions = build(subtitle="Ssub")
    (sub,) = named(regions, "subtitle")
    assert sub["bbox"][1] < panels_top(regions)


def test_hist2d_cell_color_matches_legend_norm():
    # vmin=0 must reach the norm untouched — the old `vmin or 1e-9`
    # rewrite nudged count=1 with vmax=2 across the t=0.5 LUT boundary,
    # so cells and the legend gradient disagreed by one LUT level
    df = {"x": [0.5], "y": [0.5]}
    c = pt.chart(df)
    c.hist2d(x="x", y="y", bins=([0, 1], [0, 1]), vmin=0, vmax=2)
    r, g, b = pt.colormap("viridis")(0.5)
    assert f'fill="rgb({r},{g},{b})"' in c.to_svg()


def test_hist2d_all_nan_column_is_empty():
    # valid x + all-NaN y must take the same empty-record path all-NaN x
    # does, not crash in min([])
    nan = float("nan")
    for xs, ys in (([1.0, 2.0], [nan, nan]), ([nan, nan], [1.0, 2.0])):
        c = pt.chart({"x": xs, "y": ys})
        c.hist2d(x="x", y="y")
        assert 'data-plotlet-n="0"' in c.to_svg()


def test_hist2d_binwidth_pair():
    df = {"x": [0.25, 1.25], "y": [0.5, 2.5]}
    c = pt.chart(df)
    c.hist2d(x="x", y="y", binwidth=(0.5, 1.0), binrange=((0, 2), (0, 3)))
    svg = c.to_svg()
    assert 'data-plotlet-bins-x="4"' in svg
    assert 'data-plotlet-bins-y="3"' in svg


# ---------------------------------------------------------------------------
# filled contours (no baselines)


def test_filled_level_polys():
    from plotlet.artists._marching import filled_level_polys
    # fully-inside 2x3 grid → one merged rectangle per cell row
    polys = filled_level_polys([[1, 1, 1], [1, 1, 1]], 0.5, 2, 3)
    assert polys == [[(0, 0), (2, 0), (2, 1), (0, 1)]]
    # saddle (TL/BR inside) → two disconnected triangles, matching the
    # iso-line topology
    polys = filled_level_polys([[1.0, 0.0], [0.0, 1.0]], 0.5, 2, 2)
    assert len(polys) == 2 and all(len(p) == 3 for p in polys)
    # nothing above the level → nothing drawn
    assert filled_level_polys([[0.0, 0.0], [0.0, 0.0]], 0.5, 2, 2) == []


def test_contour_fill_replaces_lines():
    import re
    grid = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
    c = pt.chart()
    c.contour(grid, levels=[0.5], fill=True, cmap="viridis")
    svg = c.to_svg()
    body = re.search(
        r'<g[^>]*data-plotlet-type="contour"[^>]*>(.*?)</g>', svg, re.S
    ).group(1)
    assert "<path" in body and "<line" not in body


def test_contour_nan_cells_masked():
    from plotlet.artists._marching import filled_level_polys
    nan = float("nan")
    # NaN corner masks its cells; the finite half of the grid still fills
    polys = filled_level_polys([[1, 1, nan], [1, 1, nan]], 0.5, 2, 3)
    assert polys == [[(0, 0), (1, 0), (1, 1), (0, 1)]]
    # end-to-end: no NaN coordinate ever reaches the path data
    grid = [[0, 0, 0], [0, 1, nan], [0, 0, 0]]
    for fill in (True, False):
        c = pt.chart()
        c.contour(grid, levels=[0.5], fill=fill, cmap="viridis")
        svg = c.to_svg()
        assert "nan" not in svg
        assert 'data-plotlet-type="contour"' in svg


# ---------------------------------------------------------------------------
# color= grouping: pointplot / ridge / kde_2d / qq (no baselines)


def test_pointplot_rejects_unknown_ci():
    # pointplot used to fall through to the bootstrap branch on any
    # unknown ci=; it now shares bar/line's validation
    c = pt.chart({"t": ["a", "a"], "v": [1, 2]})
    c.pointplot(x="t", y="v", ci="x")
    with pytest.raises(ValueError, match="ci='x'"):
        c.to_svg()


def test_pointplot_color_series():
    import re
    df = {"t": ["a", "a", "b", "b"], "v": [1, 2, 3, 4], "g": ["x", "y", "x", "y"]}
    c = pt.chart(df)
    c.pointplot(x="t", y="v", color="g", ci=None)
    fills = set(re.findall(r'<circle[^>]*fill="(#[0-9a-f]+)"', c.to_svg()))
    assert {"#1f77b4", "#ff7f0e"} <= fills


def test_ridge_color_series():
    import re
    df = {"m": ["Jan"] * 8, "v": [1, 2, 3, 4, 11, 12, 13, 14],
          "g": ["day"] * 4 + ["night"] * 4}
    c = pt.chart(df)
    c.ridge(x="m", y="v", color="g")
    fills = set(re.findall(r'<path[^>]*fill="(#[0-9a-f]+)"', c.to_svg()))
    assert {"#1f77b4", "#ff7f0e"} <= fills


def test_kde_2d_color_grouping():
    df = {"x": [0.0, 0.1, 0.2, 5.0, 5.1, 5.2],
          "y": [0.0, 0.1, 0.2, 5.0, 5.1, 5.2],
          "g": ["a", "a", "a", "b", "b", "b"]}
    c = pt.chart(df)
    c.kde_2d(x="x", y="y", color="g", n_grid=12)
    assert c.to_svg().count('data-plotlet-type="kde_2d"') == 2

    c = pt.chart(df)
    c.kde_2d(x="x", y="y", color="g", cmap="viridis")
    with pytest.raises(TypeError, match="palette="):
        c.to_svg()


def test_qq_color_grouping():
    import re
    rng = random.Random(1)
    df = {"v": [rng.gauss(0, 1) for _ in range(40)],
          "g": ["a", "b"] * 20}
    c = pt.chart(df)
    c.qq(sample="v", color="g")
    svg = c.to_svg()
    assert svg.count('data-plotlet-type="qq"') == 2
    # each group's robust reference line takes the group color
    dashed = re.findall(r'<line[^>]*stroke="(#[0-9a-f]+)"[^>]*stroke-dasharray',
                        svg)
    assert {"#1f77b4", "#ff7f0e"} <= set(dashed)
