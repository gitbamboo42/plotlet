"""Heatmap list: two heatmaps sharing rows. The anchor (LEFT) drives row
order and split gaps via `c.sectors(..., axis="y")` and attached
dendrogram; the follower (RIGHT) inherits both through `share_y()`.

Plotlet analog of ComplexHeatmap's `ht1 + ht2` heatmap-list pattern.

Run:
    python cookbook/heatmaps/heatmap_list.py
"""
from pathlib import Path
import random

import plotlet as pt
import plotlet.extensions.annotation_strip  # noqa: F401


def make_data(seed=0):
    rng = random.Random(seed)
    pathway_genes = {
        "Apoptosis":  ["BAX", "BCL2", "CASP3", "CASP8", "CASP9", "TP53"],
        "Cell cycle": ["CCND1", "CDK4", "RB1", "E2F1", "CDKN1A", "MYC"],
        "Immune":     ["IL6", "TNF", "IFNG", "IL10", "CD8A", "CD4"],
    }
    treat_effect = {"Apoptosis": 1.5, "Cell cycle": -1.2, "Immune": 0.8}

    ctrl_samples = [f"C{i+1}" for i in range(6)]
    trt_samples  = [f"T{i+1}" for i in range(6)]

    ctrl_matrix, trt_matrix = [], []
    genes, pathways = [], []
    for path, gs in pathway_genes.items():
        gene_responses = {g: rng.gauss(treat_effect[path], 0.4) for g in gs}
        for gene in gs:
            genes.append(gene)
            pathways.append(path)
            ctrl_matrix.append([rng.gauss(0.0, 0.4) for _ in ctrl_samples])
            trt_matrix.append([rng.gauss(0.0, 0.4) + gene_responses[gene]
                               + rng.gauss(0, 0.3) for _ in trt_samples])
    return genes, pathways, ctrl_samples, trt_samples, ctrl_matrix, trt_matrix


if __name__ == "__main__":
    genes, pathways, ctrl_s, trt_s, ctrl_m, trt_m = make_data()

    # Cluster on control alone — baseline view; treated reads as overlay.
    row_tree = pt.cluster_split(ctrl_m, split=pathways, labels=genes,
                                method="ward")

    path_palette = {"Apoptosis": "C2", "Cell cycle": "C1", "Immune": "C4"}

    left_tree = pt.chart(data_width=80)
    left_tree.dendrogram(tree=row_tree, orient="left", parent=True)
    left_strip = pt.chart(data_width=14)
    left_strip.annotation_strip({"gene": genes, "pathway": pathways},
                                position="gene", value="pathway",
                                palette=path_palette, orient="y")

    # Group parallel pathway labels into the {cluster: [members]} shape
    # that c.sectors() expects. Only the anchor declares sectors;
    # share_y delivers the partition to the follower.
    row_clusters = {}
    for g, p in zip(genes, pathways):
        row_clusters.setdefault(p, []).append(g)

    left = pt.chart(title="Control", data_width=180, data_height=320)
    left.sectors(row_clusters, axis="y", divider=False, label=False)
    left.heatmap(ctrl_m,
                 xticklabels=ctrl_s, yticklabels=genes,
                 cmap="RdBu_r", center=0, vmin=-3, vmax=3,
                 linewidth=0.5,
                 legend={"label": "expression"})
    left.attach_left(left_strip, left_tree)

    right = pt.chart(title="Treated", data_width=180, data_height=320)
    right.heatmap(trt_m,
                  xticklabels=trt_s, yticklabels=genes,
                  cmap="RdBu_r", center=0, vmin=-3, vmax=3,
                  linewidth=0.5,
                  legend=False)

    # annotation_strip with text= draws glyphs, so share_y's tick-label
    # suppression doesn't eat gene names on the seam.
    right_labels = pt.chart(data_width=70)
    right_labels.annotation_strip({"gene": genes}, position="gene", value="gene",
                                  text=True, orient="y", side="left")
    right.attach_right(right_labels)

    fig = (left | right | pt.legend(
        left, left_strip,
        names={left_strip: "Pathway", left: None},
    )).share_y()

    out = Path(__file__).with_suffix(".svg")
    fig.save_svg(out)
    print(f"wrote {out}")
