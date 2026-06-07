"""Annotated heatmap: gene expression by pathway × treatment, with row /
column dendrograms, condition / pathway annotation strips and a unified
legend.

Run:
    python cookbook/heatmaps/heatmap.py
"""
from pathlib import Path
import random

import plotlet as pt
import plotlet.extensions.annotation_strip  # registers c.annotation_strip


def make_data(seed=0):
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

    # Interleave C/T input order so the column reorder is visible.
    samples, conditions = [], []
    for i in range(18):
        if i % 2 == 0:
            samples.append(f"C{i // 2 + 1}"); conditions.append("Control")
        else:
            samples.append(f"T{i // 2 + 1}"); conditions.append("Treated")

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


if __name__ == "__main__":
    matrix, genes, pathways, samples, conditions = make_data()

    row_tree = pt.cluster_split(matrix, split=pathways, labels=genes,
                                method="ward")
    col_tree = pt.cluster_split(transpose(matrix), split=conditions,
                                labels=samples, method="ward")

    cond_palette = {"Control": "C0", "Treated": "C3"}
    path_palette = {"Apoptosis": "C2", "Cell cycle": "C1", "Immune": "C4"}

    top_tree = pt.chart(data_height=90)
    top_tree.dendrogram(tree=col_tree, orient="top", parent=True)

    top_strip = pt.chart(data_height=14)
    top_strip.annotation_strip({"sample": samples, "condition": conditions},
                               position="sample", value="condition",
                               palette=cond_palette)

    left_tree = pt.chart(data_width=110)
    left_tree.dendrogram(tree=row_tree, orient="left", parent=True)

    left_strip = pt.chart(data_width=14)
    left_strip.annotation_strip({"gene": genes, "pathway": pathways},
                                position="gene", value="pathway",
                                palette=path_palette, orient="y")

    hm = pt.chart(title="Gene expression: treatment effect by pathway",
                  data_width=440, data_height=320)
    hm.heatmap(matrix,
               xticklabels=samples, yticklabels=genes,
               column_split=conditions, row_split=pathways,
               cmap="RdBu_r", center=0,
               border=False,
               linewidth=0.5,
               legend={"label": "expression"})

    hm.attach_above(top_strip, top_tree)
    hm.attach_left(left_strip, left_tree)

    fig = (hm | pt.legend(
        top_strip, left_strip, hm,
        names={top_strip: "Condition", left_strip: "Pathway", hm: None},
    )).touch()

    out = Path(__file__).with_suffix(".svg")
    fig.save_svg(out)
    print(f"wrote {out}")
