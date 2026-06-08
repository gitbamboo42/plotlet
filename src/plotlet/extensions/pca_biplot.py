"""Custom artist: PCA biplot (numpy SVD).

Scatter of samples in the first two principal components, overlaid with
loading arrows showing each original variable's direction in PC space.
The classic "where do the samples live and which variables drive each
axis" plot from multivariate stats.

This version uses `numpy.linalg.svd` on the centered + standardized
data matrix — the textbook PCA path. An earlier version of this recipe
used pure-Python power iteration with deflation; works fine for clean
inputs but gets numerically wobbly on degenerate covariance matrices.

API:
    pca_biplot(matrix, var_names, sample_labels=None, color=None,
               palette=None, scale_loadings=2.5)

`color` is an optional per-sample category vector (same length as the
rows of `matrix`); each unique value gets its own point color.
"""

SUMMARY = "PCA biplot: PC1 vs PC2 scatter with loading arrows. SVD-based via numpy."

from pathlib import Path

import numpy as np

import plotlet as pt
from plotlet.utils import to_list_2d
from plotlet.draw import text_path


# Local label artist so the biplot is self-contained.
def _bplabel_record(args, kw):
    return {"type": "biplot_label",
            "xs": list(args[0]), "ys": list(args[1]),
            "labels": list(args[2]), "opts": kw}


def _bplabel_draw(a, ctx):
    out = []
    col = a["opts"].get("color", "#222")
    fs = a["opts"].get("fontsize", 10)
    dx = a["opts"].get("dx", 4); dy = a["opts"].get("dy", -4)
    for x, y, lab in zip(a["xs"], a["ys"], a["labels"]):
        out.append(text_path(str(lab), ctx.x_scale(x) + dx,
                              ctx.y_scale(y) + dy, fs, anchor="start", color=col))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="biplot_label",
    record=_bplabel_record,
    xdomain=lambda a: a["xs"], ydomain=lambda a: a["ys"],
    draw=_bplabel_draw,
    uses_color_cycle=False, layer="foreground",
))


def pca_biplot(matrix, var_names, sample_labels=None, color=None, palette=None,
               scale_loadings: float = 2.5) -> "pt.Chart":
    X = np.asarray(to_list_2d(matrix), dtype=float)
    # Center and scale (correlation PCA — the standard biplot convention).
    X = (X - X.mean(axis=0)) / (X.std(axis=0, ddof=1) + 1e-12)
    # SVD: X = U S Vᵀ. The PC scores are U·S; the loadings are V (or V·S).
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    pc1 = (U[:, 0] * S[0]).tolist()
    pc2 = (U[:, 1] * S[1]).tolist()
    var_explained = (S ** 2) / (S ** 2).sum()
    # Loadings — Vᵀ row i is the loading vector for PC i.
    loadings_pc1 = Vt[0]
    loadings_pc2 = Vt[1]
    c = pt.chart(data_width=400, data_height=400)
    if color is None:
        c.scatter(data={"x": pc1, "y": pc2}, x="x", y="y", size=2.5, alpha=0.7)
    else:
        df = {"pc1": pc1, "pc2": pc2, "group": list(color)}
        c.scatter(x="pc1", y="pc2", color="group", palette=palette,
                  data=df, size=2.5, alpha=0.7)
        c.legend(True)
    for j, name in enumerate(var_names):
        dx = float(loadings_pc1[j]) * scale_loadings
        dy = float(loadings_pc2[j]) * scale_loadings
        c.line(data={"x": [0, dx], "y": [0, dy]}, x="x", y="y", color="#d62728", linewidth=1.2)
        c.biplot_label([dx], [dy], [name], dx=4, dy=-4, color="#d62728")
    c.axhline(0, color="#cccccc", linewidth=0.6)
    c.axvline(0, color="#cccccc", linewidth=0.6)
    c.title("PCA biplot")
    c.xlabel(f"PC1 ({100 * var_explained[0]:.1f} %)")
    c.ylabel(f"PC2 ({100 * var_explained[1]:.1f} %)")
    return c


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    var_names = ["x1", "x2", "x3", "x4", "x5"]
    rows = []; groups = []
    for cls, c1, c2 in [("A", -2, 0), ("B", 1.5, 1), ("C", 0, -2)]:
        for _ in range(40):
            base = [c1, c2, c1 * 0.5, -c2 * 0.3, c1 - c2]
            rows.append([b + random.gauss(0, 0.5) for b in base])
            groups.append(cls)
    fig = pca_biplot(rows, var_names, color=groups)
    return fig


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
