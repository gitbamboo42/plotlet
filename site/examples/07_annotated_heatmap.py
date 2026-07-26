"""Annotated heatmap

Central heatmap, clustering dendrogram on top, shared legend on the
right. The dendrogram orders the columns; the sector split adds the
gaps between cluster blocks.
"""
import random

import plotlet as pt
from plotlet import aes

rng = random.Random(7)
genes = [f"gene {i + 1}" for i in range(6)]
samples = [f"s{i + 1}" for i in range(12)]
groups = ["X", "Y", "Z", "X", "Y", "Z", "Y", "Z", "X", "Y", "Z", "Y"]
level = {"X": 0.0, "Y": 5.0, "Z": 10.0}
matrix = [[level[groups[j]] + rng.gauss(0, 0.4) for j in range(12)]
          for _ in genes]

# The dendrogram clusters heatmap columns, so it sees the transpose.
by_sample = [[matrix[r][j] for r in range(len(genes))] for j in range(12)]
tree = pt.chart(data_height=60)
tree.add_dendrogram(by_sample, labels=samples, orientation="top",
                    clusters=groups, method="ward")

by_group = {}
for s, g in zip(samples, groups):
    by_group.setdefault(g, []).append(s)

hm = pt.chart(title="expression by sample", data_width=420, data_height=180)
hm.sectors(by_group, axis="x", divider=False, label=False)
data = {"sample": samples}
for r, gene in enumerate(genes):
    data[gene] = matrix[r]
hm.add_heatmap(data=data, mapping=aes(x="sample"), values=genes,
               cmap="viridis", legend={"label": "expression"})
hm.attach_above(tree)

c = pt.grid([[hm, pt.legend()]]).gap(0)
