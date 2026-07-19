"""Baseline tests for the annotation_strip artist.

The three heatmap-attached charts in test_chart.py cover band+palette and
block mode on a categorical x axis. This set covers the rest of the
feature matrix: cmap mode (+ gradient legend), interval mode (x1=/x2=),
orientation="y", numeric width= mode, the side/rotation text anchors,
absent_fill/missing values, and the circular path.
"""
import plotlet as pt
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


PLOTS = {
    "cmap_band":         strip_cmap_band,
    "interval_text":     strip_interval_text,
    "orient_y_left":     strip_orient_y_left,
    "numeric_width_rot": strip_numeric_width_rot,
    "fill_label":        strip_fill_label,
    "ring_interval":     strip_ring_interval,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_annotation_strip_baseline(name, fn, baseline_compare):
    baseline_compare("annotation_strip", name, fn().to_svg())
