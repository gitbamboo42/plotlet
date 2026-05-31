"""Annotated heatmap: ComplexHeatmap-style figure built from plotlet
primitives. Real-world inspiration — gene expression across treated vs.
control samples, grouped by pathway.

Recipe shape:

                  [           top dendrogram (per-pathway + parent)        ]
                  [           condition annotation strip                   ]
    [ row-dend ]  [          heatmap (row + col splits)                    ]  [ legend ]
    [ pathway  ]
    [ strip    ]

Mechanics:

- `pt.cluster_split(data, split=..., labels=...)` clusters within each
  group (pathway / condition) and reorders the groups by centroid
  similarity. The dendrogram artist takes the resulting `SplitTree`
  directly via `tree=`, exposes the final leaf order via `axis_order`,
  and the heatmap picks it up automatically (artist `axis_order`
  beats `frame_defaults` order in core's precedence rule).
- `parent=True` on each dendrogram renders the centroid (between-block)
  tree above the per-block trees, ComplexHeatmap-style. The parent
  leaves drop to each block's apex — no flat horizontal disconnect.
- `attach_above` / `attach_left` auto-share the relevant axis; we
  never need an explicit `share_x` / `share_y` call.
- `pt.legend()` auto-harvests gradient (heatmap) + categorical
  (annotation strips) entries from every leaf in the grid.

Run:
    python cookbook/annotated_heatmap/annotated_heatmap.py
"""
from pathlib import Path
import random

import plotlet as pt
import plotlet.extensions.annotation_strip  # registers c.annotation_strip


# ---------- synthetic data: gene expression vs. treatment --------------

def make_data(seed=0):
    """Three pathways × ten genes × two conditions × nine samples each.

    Treatment shifts the expression of each pathway in a characteristic
    direction (Apoptosis up, Cell cycle down, Immune slightly up); the
    per-gene effect varies around the pathway mean so the within-block
    dendrogram has a real signal to cluster on.
    """
    rng = random.Random(seed)
    pathway_genes = {
        "Apoptosis":  ["BAX", "BCL2", "CASP3", "CASP8", "CASP9", "TP53",
                       "BID", "BAK1", "FADD", "MCL1"],
        "Cell cycle": ["CCND1", "CDK4", "RB1", "E2F1", "CDKN1A", "MYC",
                       "MDM2", "CCNE1", "CDC20", "MKI67"],
        "Immune":     ["IL6", "TNF", "IFNG", "IL10", "CD8A", "CD4",
                       "PDCD1", "CTLA4", "FOXP3", "GZMB"],
    }
    treat_effect = {"Apoptosis": 1.5, "Cell cycle": -1.2, "Immune": 0.8}

    # Sample setup: 9 control then 9 treated, deliberately interleaved
    # in input order so the column reorder is visible in the output.
    n_per_group = 9
    samples = []
    conditions = []
    for i in range(n_per_group * 2):
        # Alternate input order: C1, T1, C2, T2, … to exercise the
        # auto-reorder. The heatmap displays them clustered by condition.
        if i % 2 == 0:
            samples.append(f"C{i // 2 + 1}")
            conditions.append("Control")
        else:
            samples.append(f"T{i // 2 + 1}")
            conditions.append("Treated")

    matrix, row_labels, row_groups = [], [], []
    for path, genes in pathway_genes.items():
        gene_responses = {g: rng.gauss(treat_effect[path], 0.4) for g in genes}
        for gene in genes:
            row_labels.append(gene)
            row_groups.append(path)
            row = []
            for cond in conditions:
                v = rng.gauss(0.0, 0.4)
                if cond == "Treated":
                    v += gene_responses[gene] + rng.gauss(0, 0.3)
                row.append(v)
            matrix.append(row)
    return matrix, row_labels, row_groups, samples, conditions


def transpose(rows):
    return [list(col) for col in zip(*rows)]


# ---------- compose the figure -----------------------------------------

if __name__ == "__main__":
    matrix, genes, pathways, samples, conditions = make_data()

    # One cluster per axis — both used twice (dendrogram + heatmap), so
    # pre-compute once. `tree=` on the dendrogram artist takes a SplitTree
    # directly, skipping any redundant scipy work.
    row_tree = pt.cluster_split(matrix, split=pathways, labels=genes,
                                method="ward")
    col_tree = pt.cluster_split(transpose(matrix), split=conditions,
                                labels=samples, method="ward")

    # Palette for the categorical annotation strips. Pathway palette
    # also drives the row-side strip's legend entries.
    cond_palette = {"Control": pt.TAB10[0], "Treated": pt.TAB10[3]}
    path_palette = {"Apoptosis": pt.TAB10[2], "Cell cycle": pt.TAB10[1],
                    "Immune":    pt.TAB10[4]}

    # Top dendrogram + condition strip — both keyed to sample names so
    # they line up with the heatmap columns via attach_above's auto-share.
    top_tree = pt.chart(data_height=90)
    top_tree.dendrogram(tree=col_tree, orient="top", parent=True)

    top_strip = pt.chart(data_height=14)
    top_strip.annotation_strip(samples, conditions, palette=cond_palette)

    # Left dendrogram + pathway strip — keyed to gene names; attach_left
    # auto-shares y.
    left_tree = pt.chart(data_width=110)
    left_tree.dendrogram(tree=row_tree, orient="left", parent=True)

    left_strip = pt.chart(data_width=14)
    left_strip.annotation_strip(genes, pathways, palette=path_palette,
                                orient="y")

    # Heatmap body — diverging cmap centred at 0, typical for z-scored /
    # log-fold expression. Both splits passed by grouping vector; the
    # dendrograms' `axis_order` drives the final order, and the scale
    # derives gap positions from the groups dicts (see `cluster.py` +
    # `scales._CategoryScale`).
    hm = pt.chart(title="Gene expression: treatment effect by pathway",
                  data_width=440, data_height=320)
    hm.heatmap(matrix,
               xticklabels=samples, yticklabels=genes,
               column_split=conditions, row_split=pathways,
               cmap="RdBu_r", center=0,
               legend={"label": "expression"})

    # First arg sits closest to the host; outermost arg is the dendrogram.
    hm.attach_above(top_strip, top_tree)
    hm.attach_left(left_strip, left_tree)

    # Explicit legend sources let us override the section headers — the
    # annotation strips contribute swatches but we want "Condition" and
    # "Pathway" as their legend titles (the strips themselves have no
    # visible label). The heatmap's section header is suppressed
    # (`names={hm: None}`) because its gradient already carries its own
    # `label="expression"` from `legend={...}`.
    fig = pt.grid([[hm, pt.legend(
        top_strip, left_strip, hm,
        names={top_strip: "Condition", left_strip: "Pathway", hm: None},
    )]]).touch()

    out = Path(__file__).with_suffix(".svg")
    fig.save_svg(out)
    print(f"wrote {out}")
