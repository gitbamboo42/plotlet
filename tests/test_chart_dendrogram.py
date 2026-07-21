"""Baseline SVG regression tests for the dendrogram artist/topic.

    pytest tests/test_chart_dendrogram.py
    pytest tests/test_chart_dendrogram.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest
from _chart_helpers import _by_label, _dendro_sample, _tidy_heatmap


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
    tree.add_dendrogram(data_t, labels=col_labels, orientation="top",
                    clusters=col_groups, method="ward")

    hm = pt.chart(title="dendrogram-driven split heatmap",
                  data_width=420, data_height=180)
    hm.sectors(_by_label(col_labels, col_groups), axis="x",
               divider=False, label=False)
    row_labels = [f"r{i+1}" for i in range(nrows_hm)]
    hm.add_heatmap(data=_tidy_heatmap(matrix, col_labels, row_labels, xname="col"), mapping=aes(x="col"), values=row_labels,
               cmap="viridis", legend={"label": "value"})
    hm.attach_above(tree)
    return pt.grid([[hm, pt.legend()]]).gap(0)


def chart_dendrogram_split_parent():
    """Both axes split + parent-tree on both sides: the test-fixture
    `curved_tree` renderer on top, the built-in dendrogram on the left.
    Same grouping vector flows to each tree via `clusters=`, and the panel
    declares `c.sectors(...)` once on each axis for the visual gap
    whitespace — both trees and the heatmap pick up the dendrogram's
    between-cluster order through the artist `axis_order` precedence rule.

    Stresses `cluster.fit_parent` on both orientation=top and
    orientation=left, and on two independent renderers (built-in
    `dendrogram`, the `_curved_tree` fixture built purely on the public
    cluster API) — one per side — so a regression on either renderer or
    on the public cluster API trips this baseline.

    Row names sit right of the heatmap (`yticks(side="right")` on the
    host, `yticks(labels=False)` on the tree so they don't draw twice) —
    the only baseline covering `side=` interacting with attachments."""
    import random
    import _curved_tree  # noqa: F401 — registers c.add_curved_tree (test fixture)
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
    top_c.add_curved_tree(data_top, labels=col_labels, orientation="top",
                      clusters=col_groups, method="ward", parent=True)

    left_d = pt.chart(data_width=100)
    left_d.add_dendrogram(data_left, labels=row_labels, orientation="left",
                      clusters=row_groups, method="ward", parent=True)
    left_d.yticks(labels=False)

    hm = pt.chart(title="split heatmap with parent trees on both sides",
                  data_width=360, data_height=240)
    hm.yticks(side="right")
    hm.sectors(_by_label(col_labels, col_groups), axis="x",
               divider=False, label=False)
    hm.sectors(_by_label(row_labels, row_groups), axis="y",
               divider=False, label=False)
    hm.add_heatmap(data=_tidy_heatmap(matrix, col_labels, row_labels, xname="col"), mapping=aes(x="col"), values=row_labels,
               cmap="viridis", legend={"label": "value"})
    hm.attach_above(top_c)
    hm.attach_left(left_d)

    return pt.grid([[hm, pt.legend()]]).gap(0)


def chart_dendrogram_top():
    c = pt.chart(title="dendrogram (orientation=top)", data_height=180)
    c.add_dendrogram(_dendro_sample(), method="ward")
    return c


def chart_dendrogram_left():
    c = pt.chart(title="dendrogram (orientation=left)", data_width=240)
    c.add_dendrogram(_dendro_sample(), method="ward", orientation="left")
    return c


def chart_dendrogram_styled():
    # Demonstrates the opt-in path: dendrogram's spineless default is
    # restored to a height axis. Also exercises color / linewidth kwargs.
    c = pt.chart(title="dendrogram with restored height axis",
                 ylabel="height", data_height=180)
    c.add_dendrogram(_dendro_sample(), method="average",
                 color="C3", linewidth=1.4)
    c.spines(left=True)
    c.yticks(None)
    return c


def chart_dendrogram_labeled():
    labels = ["sample_" + ch for ch in "ABCDEFGH"]
    c = pt.chart(title="dendrogram with labels", data_height=200)
    c.add_dendrogram(_dendro_sample(), method="ward", labels=labels)
    c.xticks(rotation=90)
    return c


def chart_dendrogram_palette():
    # Per-group branch color: `palette` maps each group (the `clusters=`
    # label) to a color; the between-cluster trunk (parent=True) stays the
    # neutral default, driven off plotlet's existing two-level block
    # structure.
    import random
    rng = random.Random(5)
    base = {"A": [2, 1, 0, -1, 0.5], "B": [-1, 0, 2, 0.5, -1.5],
            "C": [0.5, -1.5, -1, 2, 1.5]}
    palette = {"A": "#1D9E75", "B": "#E6842A", "C": "#534AB7"}
    items, groups, matrix = [], [], []
    for i in range(24):
        grp = "ABC"[i % 3]
        items.append(f"x{i:02d}")
        groups.append(grp)
        matrix.append([v + rng.gauss(0, 0.5) for v in base[grp]])
    c = pt.chart(title="dendrogram — per-group color", data_height=200)
    c.sectors(_by_label(items, groups), axis="x", divider=False, label=False)
    c.add_dendrogram(matrix, labels=items, clusters=groups, method="ward",
                 palette=palette, parent=True, linewidth=1.3)
    c.xticks(rotation=90)
    return c


PLOTS = {
    "dendrogram_split": chart_dendrogram_split,
    "dendrogram_split_parent": chart_dendrogram_split_parent,
    "dendrogram_top": chart_dendrogram_top,
    "dendrogram_left": chart_dendrogram_left,
    "dendrogram_styled": chart_dendrogram_styled,
    "dendrogram_labeled": chart_dendrogram_labeled,
    "dendrogram_palette": chart_dendrogram_palette,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_dendrogram_baseline(name, fn, baseline_compare):
    baseline_compare("chart_dendrogram", name, fn().to_svg())
