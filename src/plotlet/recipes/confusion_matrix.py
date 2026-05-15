"""Custom artist: confusion matrix.

A heatmap of (predicted, actual) class pairs, with the cell counts
printed inside each square and either raw counts or row-normalized
percentages on the color scale. Conceptually it's an annotated heatmap
specialized for classifier evaluation — but evaluation has its own
conventions (rows = true class, cols = predicted class, axis labels
specific, diagonal emphasized) that justify a dedicated recipe.

API: c.confusion_matrix(y_true, y_pred, classes=None, normalize="row").
- `classes` — explicit class label order; defaults to sorted unique values.
- `normalize` — "row" (per true class) | "col" | "all" | None (raw counts).
"""

SUMMARY = "Classifier evaluation heatmap: counts (or row-normalized rates) of true vs predicted class."

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw.colormaps import colormap, _ContinuousNorm
from plotlet.draw import rect, text_path


def cm_record(args, kw):
    y_true = to_list(args[0])
    y_pred = to_list(args[1])
    classes = kw.get("classes")
    if classes is None:
        classes = sorted(set(y_true) | set(y_pred))
    idx = {c: i for i, c in enumerate(classes)}
    n = len(classes)
    counts = [[0] * n for _ in range(n)]
    for t, p in zip(y_true, y_pred):
        counts[idx[t]][idx[p]] += 1
    normalize = kw.get("normalize", "row")
    if normalize == "row":
        mat = [[(c / sum(row)) if sum(row) else 0 for c in row] for row in counts]
    elif normalize == "col":
        col_tot = [sum(counts[r][c] for r in range(n)) for c in range(n)]
        mat = [[counts[r][c] / col_tot[c] if col_tot[c] else 0
                for c in range(n)] for r in range(n)]
    elif normalize == "all":
        tot = sum(sum(row) for row in counts) or 1
        mat = [[c / tot for c in row] for row in counts]
    else:
        mat = [list(row) for row in counts]
    return {"type": "confusion_matrix", "_counts": counts, "_mat": mat,
            "_classes": classes, "opts": kw}


def cm_xdomain(a): return a["_classes"]
def cm_ydomain(a): return a["_classes"]


def _luminance(rgb):
    return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255


def cm_draw(a, ctx):
    classes = a["_classes"]
    mat = a["_mat"]
    counts = a["_counts"]
    cmap_name = a["opts"].get("cmap", "Blues")
    cmap = colormap(cmap_name)
    flat = [v for row in mat for v in row]
    vmax = a["opts"].get("vmax", max(flat) if flat else 1)
    norm = _ContinuousNorm(0, vmax or 1, "linear")
    normalize = a["opts"].get("normalize", "row")
    bw = getattr(ctx.x_scale, "bandwidth", 1.0)
    bh = getattr(ctx.y_scale, "bandwidth", 1.0)
    out = []
    for r, cls_t in enumerate(classes):
        for k, cls_p in enumerate(classes):
            v = mat[r][k]
            cnt = counts[r][k]
            cx = ctx.x_scale(cls_p)
            cy = ctx.y_scale(cls_t)
            rgb = cmap(norm.to_unit(v))
            fill = f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
            out.append(rect(cx - bw / 2, cy - bh / 2, bw, bh, fill=fill))
            txt_col = "#ffffff" if _luminance(rgb) < 0.55 else "#000000"
            if normalize:
                label = f"{v:.2f}\n({cnt})" if a["opts"].get("show_counts", True) else f"{v:.2f}"
            else:
                label = f"{cnt}"
            # Split on newline for two-line labels.
            for li, line in enumerate(label.split("\n")):
                out.append(text_path(line, cx, cy + 4 + li * 11,
                                      10, anchor="middle", color=txt_col))
    return "".join(out)


def cm_legend_gradient(a):
    return {"kind": "continuous",
            "cmap": a["opts"].get("cmap", "Blues"),
            "vmin": 0, "vmax": max(v for row in a["_mat"] for v in row) or 1,
            "norm": "linear",
            "label": a["opts"].get("normalize") or "count"}


pt.add_artist(pt.ArtistSpec(
    name="confusion_matrix",
    record=cm_record,
    xdomain=cm_xdomain,
    ydomain=cm_ydomain,
    draw=cm_draw,
    uses_color_cycle=False,
    legend_gradient=cm_legend_gradient,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    classes = ["cat", "dog", "bird", "fish"]
    # Strong on the diagonal, with some confusion between cat/dog and bird/fish.
    confusion_rates = {
        "cat":  {"cat": 0.80, "dog": 0.15, "bird": 0.03, "fish": 0.02},
        "dog":  {"cat": 0.10, "dog": 0.85, "bird": 0.03, "fish": 0.02},
        "bird": {"cat": 0.05, "dog": 0.05, "bird": 0.75, "fish": 0.15},
        "fish": {"cat": 0.05, "dog": 0.05, "bird": 0.20, "fish": 0.70},
    }
    y_true, y_pred = [], []
    for cls in classes:
        for _ in range(120):
            y_true.append(cls)
            r = random.random(); cum = 0
            for p_cls, p in confusion_rates[cls].items():
                cum += p
                if r <= cum:
                    y_pred.append(p_cls); break
    c = pt.chart(data_width=300, data_height=300)
    c.xscale("category", order=classes)
    # Plotlet places the first category at the top of the y axis, so passing
    # `classes` directly gives the top→bottom reading order we want.
    c.yscale("category", order=classes)
    c.confusion_matrix(y_true, y_pred, classes=classes, normalize="row")
    c.title("Confusion matrix").xlabel("predicted").ylabel("true")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
