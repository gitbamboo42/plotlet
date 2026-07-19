"""Baseline tests for the annotation_strip artist.

Three heatmap-attached charts cover band+palette and block mode on a
categorical x axis; the rest of the suite covers the feature matrix:
cmap mode (+ gradient legend), interval mode (x1=/x2=), orientation="y",
numeric width= mode, the side/rotation text anchors, absent_fill/missing
values, and the circular path.
"""
import plotlet as pt
from _chart_helpers import _by_label, _tidy_heatmap
import pytest


def strip_cmap_band():
    # Continuous cmap fill with a NaN (missing → absent_fill) and the
    # gradient legend. Covers the record-side vmin/vmax range, the
    # cmap+norm draw path, and legend_gradient.
    c = pt.chart(data_height=14)
    c.annotation_strip({"col": [f"c{i+1}" for i in range(6)],
                        "v": [0.1, 2.5, float("nan"), 1.2, 3.0, 0.7]},
                       position="col", value="v", cmap="viridis",
                       absent_fill="#eee", name="Score")
    return pt.grid([[c, pt.legend()]])


def strip_interval_text():
    # Cytoband-style variable-width intervals: x1=/x2= extents, centered
    # per-cell text, and the interval frame-defaults branch (spines stay
    # on, position ticks dropped).
    c = pt.chart(title="interval strip", data_height=20)
    c.annotation_strip({"start": [0, 30, 50, 90], "end": [30, 50, 90, 120],
                        "stain": ["gneg", "gpos", "gneg", "acen"]},
                       x1="start", x2="end", value="stain",
                       palette={"gneg": "#eee", "gpos": "#666", "acen": "#c33"},
                       text=True)
    return c


def strip_orient_y_left():
    # Vertical column strip: orientation="y" transposition and the
    # side="left" text anchor.
    c = pt.chart(data_width=18)
    c.annotation_strip({"row": ["r1", "r2", "r3", "r4"],
                        "g": ["A", "A", "B", "B"]},
                       position="row", value="g", orientation="y",
                       palette={"A": "#1f77b4", "B": "#ff7f0e"},
                       text=True, side="left", text_color="white")
    return c


def strip_numeric_width_rot():
    # Numeric uniform positions with scalar width= (time-series regime
    # tags) and rotated bottom-side text (the "start"-anchor branch).
    c = pt.chart(data_height=26)
    c.annotation_strip({"pos": [0, 1, 2, 3, 4, 5],
                        "tag": ["u", "u", "d", "d", "u", "d"]},
                       position="pos", value="tag", width=1.0,
                       palette={"u": "#8dd3c7", "d": "#fb8072"},
                       text=True, rotation=90)
    return c


def strip_fill_label():
    # Decorative single-color strip: fill= constant + one legend entry
    # via label= (no palette, no cmap).
    c = pt.chart(data_height=14)
    c.annotation_strip({"col": ["a", "b", "c", "d"],
                        "v": ["k", "k", "k", "k"]},
                       position="col", value="v",
                       fill="#8da0cb", label="track")
    return pt.grid([[c, pt.legend()]])


def strip_ring_interval():
    # Interval strip on a ring (ideogram-style): covers the warp rect
    # projection and the tangent-rotated text anchors.
    c = pt.chart(title="ideogram — ring")
    c.coordinate(pt.CircularCoordinate())
    c.annotation_strip({"start": [0, 30, 50, 90], "end": [30, 50, 90, 120],
                        "stain": ["gneg", "gpos", "gneg", "acen"]},
                       x1="start", x2="end", value="stain",
                       palette={"gneg": "#eee", "gpos": "#666", "acen": "#c33"},
                       text=True)
    return c


def chart_heatmap_split_attached():
    # Top strip + top bar both share x with the split heatmap, so they
    # inherit the column reorder and the 6-px gaps via the shared scale
    # — no per-artist split kwargs on the attachments. The legend on the
    # right auto-harvests across all leaves (continuous gradient from the
    # heatmap, discrete swatches from the strip).
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


PLOTS = {
    "heatmap_split_attached": chart_heatmap_split_attached,
    "heatmap_block_titles": chart_heatmap_block_titles,
    "heatmap_block_filled": chart_heatmap_block_filled,
    "cmap_band":         strip_cmap_band,
    "interval_text":     strip_interval_text,
    "orient_y_left":     strip_orient_y_left,
    "numeric_width_rot": strip_numeric_width_rot,
    "fill_label":        strip_fill_label,
    "ring_interval":     strip_ring_interval,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_annotation_strip_baseline(name, fn, baseline_compare):
    baseline_compare("chart_annotation_strip", name, fn().to_svg())
