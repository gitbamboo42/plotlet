"""Custom artist: ROC curve.

For a binary classifier with real-valued scores, plot TPR vs FPR as the
score threshold sweeps. Includes the diagonal "random" reference and
computes AUC via trapezoidal integration. Overlay multiple classifiers
to compare (each `c.roc(...)` call gets its own color and legend entry).

API:
    c.roc(y_true, y_score, label=...)

`y_true` is 0/1; `y_score` is a numeric score (higher = predict 1).
AUC is appended to the label if it's set, so the legend reads like
"my-model (AUC = 0.87)".
"""

SUMMARY = 'ROC curve with trapezoidal AUC computed inline and appended to the legend label.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import polyline, segment


def roc_record(args, kw):
    y_true = to_list(args[0])
    y_score = to_list(args[1])
    # Sort by score descending, sweep threshold from high to low.
    paired = sorted(zip(y_score, y_true), key=lambda p: -p[0])
    n_pos = sum(1 for _, t in paired if t == 1)
    n_neg = len(paired) - n_pos
    if n_pos == 0 or n_neg == 0:
        return {"type": "roc", "_fpr": [0, 1], "_tpr": [0, 1], "_auc": 0.5,
                "opts": kw}
    tps = 0; fps = 0
    fpr = [0.0]; tpr = [0.0]
    prev_score = None
    for s, t in paired:
        if prev_score is not None and s != prev_score:
            fpr.append(fps / n_neg); tpr.append(tps / n_pos)
        if t == 1: tps += 1
        else: fps += 1
        prev_score = s
    fpr.append(1.0); tpr.append(1.0)
    # Trapezoidal AUC.
    auc = 0.0
    for i in range(1, len(fpr)):
        auc += (fpr[i] - fpr[i - 1]) * (tpr[i] + tpr[i - 1]) / 2
    # Augment label with AUC if user gave one.
    kw = dict(kw)
    if kw.get("label"):
        kw["label"] = f"{kw['label']} (AUC = {auc:.3f})"
    else:
        kw["label"] = f"AUC = {auc:.3f}"
    return {"type": "roc", "_fpr": fpr, "_tpr": tpr, "_auc": auc, "opts": kw}


def roc_xdomain(a): return [0, 1]
def roc_ydomain(a): return [0, 1]


def roc_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.6)
    out = []
    pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(a["_fpr"], a["_tpr"])]
    out.append(polyline(pts, color=col, width=lw))
    # Diagonal: draw it only once (with the first artist). The simplest
    # convention: every roc artist also draws the diagonal, but in a
    # consistent gray, which overplots cleanly. To keep the SVG lean,
    # add a tiny marker: only the first instance draws it.
    if a["opts"].get("_first", True):
        out.append(segment(ctx.x_scale(0), ctx.y_scale(0),
                           ctx.x_scale(1), ctx.y_scale(1),
                           color="#888", width=0.8, dash="4,3"))
    return "".join(out)


def roc_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    return segment(x0, y_mid, x0 + 22, y_mid, color=col, width=1.6)


pt.add_artist(pt.ArtistSpec(
    name="roc",
    record=roc_record,
    xdomain=roc_xdomain,
    ydomain=roc_ydomain,
    draw=roc_draw,
    legend_swatch=roc_legend_swatch,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random, math
    random.seed(9)
    n_pos, n_neg = 200, 200
    # Simulate scores: positives drawn from N(1, 1), negatives from N(0, 1).
    pos = [(1, random.gauss(1.2, 1.0)) for _ in range(n_pos)]
    neg = [(0, random.gauss(0, 1.0)) for _ in range(n_neg)]
    paired = pos + neg
    y_true = [t for t, _ in paired]
    y_score_good = [s for _, s in paired]
    # A weaker model: add noise.
    y_score_weak = [s + random.gauss(0, 0.7) for s in y_score_good]
    c = pt.chart(data_width=320, data_height=320)
    c.roc(y_true, y_score_good, label="strong model")
    c.roc(y_true, y_score_weak, label="weak model", _first=False)
    c.title("ROC curves").xlabel("FPR").ylabel("TPR").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
