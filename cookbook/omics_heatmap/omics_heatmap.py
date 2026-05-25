"""Annotated heatmap: top categorical track + left dendrogram + shared
legend on the right.

This is the canonical "ComplexHeatmap-style" layout, built from plotlet
primitives — no edits to plotlet's source. The recipe shape:

    [        top group strip       ]
    [ left dend ][   heatmap body   ][ legend ]

Mechanics:

- Rows are clustered with scipy; the leaf permutation reorders the matrix
  so a left-side dendrogram lines up with heatmap rows.
- The top strip is a tiny custom artist (`annotation_strip`) registered
  inline. One call per unique category produces one legend swatch each.
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
from plotlet.artists import _to_pylist


# ---------- custom artist: categorical annotation strip ----------------
# A horizontal strip of colored cells. One record per unique category, so
# the layout legend gets one swatch per group. Spans the row y=[0, 1] in
# data coords; x positions are integer cell indices (matching imshow's).

def annotation_strip_record(args, kw):
    return {
        "type": "annotation_strip",
        "positions": _to_pylist(args[0]),
        "opts": kw,
    }


def annotation_strip_xdomain(a):
    pos = a["positions"]
    return [min(pos), max(pos) + 1] if pos else []


def annotation_strip_ydomain(a):
    return [0, 1]


def annotation_strip_draw(a, ctx):
    color = a["opts"].get("color") or ctx.color
    y0 = ctx.y_scale(0); y1 = ctx.y_scale(1)
    top, h = min(y0, y1), abs(y1 - y0)
    parts = []
    for i in a["positions"]:
        x0 = ctx.x_scale(i); x1 = ctx.x_scale(i + 1)
        parts.append(
            f'<rect x="{min(x0, x1):.2f}" y="{top:.2f}" '
            f'width="{abs(x1 - x0):.2f}" height="{h:.2f}" fill="{color}"/>'
        )
    return "".join(parts)


def annotation_strip_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        col = a["opts"].get("color") or a["_color"]
        return (f'<rect x="{x0}" y="{y_mid - 5}" width="22" height="10" '
                f'fill="{col}"/>')
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


pt.add_artist(pt.ArtistSpec(
    name="annotation_strip",
    record=annotation_strip_record,
    xdomain=annotation_strip_xdomain,
    ydomain=annotation_strip_ydomain,
    draw=annotation_strip_draw,
    legend_entries=annotation_strip_legend_entries,
    uses_color_cycle=False,
))


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

    # Top: one annotation_strip call per unique group → one legend swatch
    # each. Palette is matplotlib's tab10 first three colors via pt.TAB10
    # (so the cookbook stays in matplotlib's visual vocabulary).
    group_colors = {"ctrl": pt.TAB10[0], "treat": pt.TAB10[1], "resist": pt.TAB10[2]}
    top = pt.chart(title="Treatment", data_width=420, data_height=14)
    for grp, col in group_colors.items():
        positions = [i for i, g in enumerate(col_groups) if g == grp]
        top.annotation_strip(positions, color=col, label=grp)
    # Strip is a decoration — no spines, no ticks. Inherits the column
    # scale from the heatmap via share_x.
    top.spines(left=False, right=False, top=False, bottom=False)
    top.xticks([])
    top.yticks([])

    # Left dendrogram. Pass the same linkage used to reorder rows so the
    # tree matches the reordered heatmap exactly.
    tree = pt.chart(data_width=60, data_height=260)
    tree.dendrogram(linkage=Z_rows, orient="left")

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
    ]).share_x("col").share_y("row")

    out = Path(__file__).with_suffix(".svg")
    fig.save_svg(out)
    print(f"wrote {out}")
