"""Circular

A radial dendrogram and a heatmap ring stacked on one leaf axis --
the annotated-heatmap shape, wrapped onto a circle.
"""
import random

import plotlet as pt
from plotlet import aes
from plotlet.cluster import layout_tree

rng = random.Random(0)
profiles = [[2.0, 1.5, 0.0, -1.0, 0.5, 1.0],
            [-1.0, 0.0, 2.0, 0.5, -1.5, 0.0],
            [0.5, -1.5, -1.0, 2.0, 1.5, -0.5]]
labels, matrix = [], []
for i in range(16):
    labels.append(f"L{i:02d}")
    matrix.append([p + rng.gauss(0, 0.6) for p in profiles[i % 3]])

# Read the leaf order from a local tree so the heatmap columns land at
# the same angles as the dendrogram leaves.
_, _, leaf_order = layout_tree(pt.linkage(matrix, labels=labels,
                                          method="ward"))
row_by_label = dict(zip(labels, matrix))
data = {"leaf": leaf_order}
for j in range(len(matrix[0])):
    data[f"f{j}"] = [row_by_label[l][j] for l in leaf_order]

tree_ring = pt.chart(xlim=(0, 1))
tree_ring.add_dendrogram(data=matrix, labels=labels, method="ward",
                         orientation="bottom", color="#3B3B4F")

hm_ring = pt.chart(xlim=(0, 1), ylim=(0, 1))
hm_ring.add_heatmap(data=data, mapping=aes(x="leaf"),
                    values=[f"f{j}" for j in range(len(matrix[0]))],
                    cmap="RdBu_r", center=0)

pile = (hm_ring / tree_ring).coordinate(
    pt.CircularCoordinate(r_inner=0.08, wrap_gap_deg=4))
pile.heights([1.0, 2.2])

c = pile.title("circular annotated heatmap")
