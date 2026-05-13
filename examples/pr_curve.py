"""Custom artist: precision-recall curve.

The twin of `roc_curve` — preferred when the positive class is rare,
since PR doesn't get fooled by the giant negative pool that makes a
mediocre classifier look great on ROC. AUPR (area under PR) is
trapezoidal-integrated inline and appended to the legend label.

API:
    c.pr(y_true, y_score, label=...)

`y_true` is 0/1; `y_score` is a numeric score (higher = predict 1).
The label string is auto-augmented with "(AUPR = 0.42)" so the legend
reads like a model-comparison table.
"""

SUMMARY = 'Precision-recall curve with trapezoidal AUPR; the imbalanced-classes twin of ROC.'

from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist


def pr_record(args, kw):
    y_true = _to_pylist(args[0])
    y_score = _to_pylist(args[1])
    paired = sorted(zip(y_score, y_true), key=lambda p: -p[0])
    n_pos = sum(1 for _, t in paired if t == 1)
    if n_pos == 0:
        return {"type": "pr", "_rec": [0, 1], "_prec": [0, 0], "_aupr": 0,
                "opts": kw}
    tp = 0; fp = 0
    rec = []; prec = []
    prev_score = None
    for s, t in paired:
        if prev_score is not None and s != prev_score:
            r = tp / n_pos
            p = tp / (tp + fp) if (tp + fp) else 1
            rec.append(r); prec.append(p)
        if t == 1: tp += 1
        else: fp += 1
        prev_score = s
    # Final point at threshold = -inf (all predicted positive).
    rec.append(tp / n_pos)
    prec.append(tp / (tp + fp) if (tp + fp) else 1)
    # AUPR (trapezoidal).
    aupr = 0.0
    for i in range(1, len(rec)):
        aupr += (rec[i] - rec[i - 1]) * (prec[i] + prec[i - 1]) / 2
    kw = dict(kw)
    if kw.get("label"):
        kw["label"] = f"{kw['label']} (AUPR = {aupr:.3f})"
    else:
        kw["label"] = f"AUPR = {aupr:.3f}"
    return {"type": "pr", "_rec": rec, "_prec": prec, "_aupr": aupr, "opts": kw}


def pr_xdomain(a): return [0, 1]
def pr_ydomain(a): return [0, 1]


def pr_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.6)
    pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(a["_rec"], a["_prec"])]
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    out = f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{lw}"/>'
    # Baseline = positive class prevalence (constant line). Drawn once.
    if a["opts"].get("_first", True):
        # Approximate prevalence from the final recall denominator: we don't
        # carry it explicitly, but the convention is dashed at y = base rate.
        # If user passed `prevalence=`, honor it.
        prev = a["opts"].get("prevalence")
        if prev is not None:
            y_prev = ctx.y_scale(prev)
            out += (f'<line x1="{ctx.x_scale(0):.2f}" '
                    f'x2="{ctx.x_scale(1):.2f}" '
                    f'y1="{y_prev:.2f}" y2="{y_prev:.2f}" '
                    f'stroke="#888" stroke-width="0.8" stroke-dasharray="4,3"/>')
    return out


def pr_legend_swatch(a, ctx, x0, y_mid):
    return (f'<line x1="{x0}" x2="{x0 + 22}" y1="{y_mid}" y2="{y_mid}" '
            f'stroke="{a["_color"]}" stroke-width="1.6"/>')


pt.add_artist(pt.ArtistSpec(
    name="pr",
    record=pr_record,
    xdomain=pr_xdomain,
    ydomain=pr_ydomain,
    draw=pr_draw,
    legend_swatch=pr_legend_swatch,
))


if __name__ == "__main__":
    import random
    random.seed(0)
    # Imbalanced: ~5 % positives.
    n_pos, n_neg = 80, 1500
    pos = [(1, random.gauss(1.6, 1.0)) for _ in range(n_pos)]
    neg = [(0, random.gauss(0.0, 1.0)) for _ in range(n_neg)]
    paired = pos + neg
    y_true = [t for t, _ in paired]
    good = [s for _, s in paired]
    weak = [s + random.gauss(0, 1.0) for s in good]
    c = pt.chart(data_width=320, data_height=320)
    prevalence = n_pos / (n_pos + n_neg)
    c.pr(y_true, good, label="strong model", prevalence=prevalence)
    c.pr(y_true, weak, label="weak model", _first=False)
    c.title("Precision-Recall").xlabel("recall").ylabel("precision").legend(True)
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
