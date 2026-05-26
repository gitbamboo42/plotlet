"""Annotated heatmap: top categorical track + left dendrogram + shared
legend on the right.

This is the canonical "ComplexHeatmap-style" layout, built from plotlet
primitives — no edits to plotlet's source. The recipe shape:

    [        top group strip       ]
    [ left dend ][   heatmap body   ][ legend ]

Mechanics:

- Rows are clustered with scipy; the leaf permutation reorders the matrix
  so a left-side dendrogram lines up with heatmap rows.
- The top strip is `pt.annotation_strip` (registered by importing
  `plotlet.extensions.annotation_strip`). One call covers the whole row;
  the palette dict supplies one legend swatch per group.
- `pt.grid([[...]]).share_x("col").share_y("row")` keeps:
    * top strip ↔ heatmap aligned column-wise (share_x);
    * left dendrogram ↔ heatmap aligned row-wise (share_y).
- `pt.legend()` (no args) auto-harvests from every leaf: the heatmap's
  continuous gradient + the strip's discrete swatches, grouped by chart.
"""
from pathlib import Path
import random

from scipy.cluster.hierarchy import linkage, dendrogram as _dgram_layout

import plotlet as pt
import plotlet.extensions.annotation_strip  # registers c.annotation_strip


# ---------- synthetic data ---------------------------------------------

def make_data(n_genes=15, n_samples=12, seed=0):
    rng = random.Random(seed)
    # Three sample groups, each with a distinct expression signature.
    groups = (["ctrl"] * 4) + (["treat"] * 5) + (["resist"] * 3)
    signature = {
        "ctrl":   lambda g: rng.gauss(0.0, 0.4),
        "treat":  lambda g: rng.gauss(1.2 if g < 6 else -0.8, 0.4),
        "resist": lambda g: rng.gauss(-1.0 if g < 6 else 1.5, 0.4),
    }
    matrix = [[signature[groups[s]](g) for s in range(n_samples)]
              for g in range(n_genes)]
    gene_labels = [f"g{g+1:02d}" for g in range(n_genes)]
    sample_labels = [f"S{s+1:02d}" for s in range(n_samples)]
    return matrix, gene_labels, sample_labels, groups


def transpose(rows):
    return [list(col) for col in zip(*rows)]


def reorder_rows(data, order):
    return [data[i] for i in order]


def reorder_cols(data, order):
    return [[row[i] for i in order] for row in data]


# ---------- compose the figure -----------------------------------------

if __name__ == "__main__":
    matrix, genes, samples, groups = make_data()

    # Cluster rows (genes) and columns (samples). Each leaf permutation
    # tells us the display order from top to bottom (rows) / left to
    # right (cols).
    Z_rows = linkage(matrix, method="ward")
    Z_cols = linkage(transpose(matrix), method="ward")
    row_order = _dgram_layout(Z_rows, no_plot=True)["leaves"]
    col_order = _dgram_layout(Z_cols, no_plot=True)["leaves"]

    reordered = reorder_rows(reorder_cols(matrix, col_order), row_order)
    row_labels = [genes[i] for i in row_order]
    col_labels = [samples[i] for i in col_order]
    col_groups = [groups[i] for i in col_order]

    # Top: one annotation_strip call for the whole row. Both panels live on
    # a category x-scale (sample names), so share_x just lines them up.
    # Palette = matplotlib's tab10 (via pt.TAB10).
    group_colors = {"ctrl": pt.TAB10[0], "treat": pt.TAB10[1], "resist": pt.TAB10[2]}
    top = pt.chart(title="Treatment", data_width=420, data_height=14)
    top.annotation_strip(col_labels, col_groups, palette=group_colors)

    # Left dendrogram. Pass the same linkage used to reorder rows so the
    # tree matches the reordered heatmap exactly, and `labels=` so the
    # dendrogram lives on the same category y-scale as the heatmap to its
    # right (share_y then matches by gene name).
    tree = pt.chart(data_width=60, data_height=260)
    tree.dendrogram(linkage=Z_rows, orient="left", labels=row_labels)

    # Heatmap body. Diverging cmap centered at zero — typical for
    # row-normalized expression.
    hm = pt.chart(title="Expression", data_width=420, data_height=260)
    hm.heatmap(reordered,
               xticklabels=col_labels,
               yticklabels=row_labels,
               cmap="RdBu_r", center=0,
               legend={"label": "z-score"})
    hm.xticks(rotation=45)

    # Annotated-heatmap grid:
    #   share_x="col" → top ↔ hm share x (column 1)
    #   share_y="row" → tree ↔ hm share y (row 1)
    # The share rules already auto-zero the inter-panel gap; joined-side
    # margins also drop to the floor (no content rendered on the joined
    # side), so the strip and tree butt up against the heatmap with just
    # the floor's worth of breathing room. pt.legend() in the bottom-right
    # auto-harvests from every leaf and groups entries by source chart
    # (header = chart.title).
    fig = pt.grid([
        [None, top, None         ],
        [tree, hm,  pt.legend()  ],
    ]).share_x("col").share_y("row").touch()

    out = Path(__file__).with_suffix(".svg")
    fig.save_svg(out)
    print(f"wrote {out}")
