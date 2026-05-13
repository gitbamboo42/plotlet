"""Annotated heatmap: column dendrogram + reordered heatmap.

Recipe shape (vertical stack, x-axis shared so columns line up):

    [ column dendrogram ]
    [    heatmap        ]
    sample labels under heatmap

The pairing is manual — the dendrogram artist doesn't auto-reorder the
heatmap. The caller computes the linkage, asks scipy for the leaf
permutation, reorders the matrix, and composes the two charts with `/`.

`share_x()` joins them with zero gap, and the coord conventions match
out of the box: each leaf occupies the cell `[i, i+1]` with its visual
endpoint at `i + 0.5`, and `chart.heatmap()` puts cell centers at the
same positions.
"""
from pathlib import Path
import random

from scipy.cluster.hierarchy import linkage, dendrogram as _dgram_layout

import plotlet as pt


def make_data(n_rows=6, n_cols=8, seed=0):
    rng = random.Random(seed)
    return [[rng.gauss(0, 1) for _ in range(n_cols)] for _ in range(n_rows)]


def transpose(rows):
    return [list(col) for col in zip(*rows)]


def reorder_cols(data, order):
    return [[row[i] for i in order] for row in data]


if __name__ == "__main__":
    data = make_data(n_rows=6, n_cols=8)
    col_labels = [f"S{i+1}" for i in range(8)]
    row_labels = [f"g{i+1}" for i in range(6)]

    # Cluster columns. linkage() on the transposed matrix treats each
    # column as one observation; the leaf permutation tells us the
    # display order.
    Z = linkage(transpose(data), method="ward")
    leaves = _dgram_layout(Z, no_plot=True)["leaves"]

    reordered = reorder_cols(data, leaves)
    reordered_col_labels = [col_labels[i] for i in leaves]

    # Column dendrogram on top. Pass the precomputed linkage so the
    # tree matches the reordered heatmap exactly.
    top = pt.chart(data_height=70, data_width=400)
    top.dendrogram(linkage=Z)

    # Heatmap of the reordered matrix with row + col labels.
    hm = pt.chart(data_height=180, data_width=400)
    hm.heatmap(reordered,
               xticklabels=reordered_col_labels,
               yticklabels=row_labels,
               cmap="viridis")
    hm.xticks(rotation=45)

    # share_x collapses the inter-panel gap; inner_gap(0) drops the
    # joined-side margin so the dendrogram leaves butt up against the
    # heatmap cells with no whitespace between them.
    fig = (top / hm).share_x().inner_gap(0)

    out = Path(__file__).with_suffix(".svg")
    fig.save_svg(out)
    print(f"wrote {out}")
