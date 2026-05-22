"""Custom artist: MA plot (Bland-Altman for sequencing).

Scatter of M = log₂(a / b) (log fold change) vs A = ½ · log₂(a · b)
(mean expression), with significance thresholds and reference y = 0.
The RNA-seq sibling of `volcano`: where volcano emphasizes p-values,
MA emphasizes signal magnitude across the expression range and makes
intensity-dependent bias (sequencing's bane) visible at a glance.

API:
    c.ma(mean_log_expr, log2_fc, padj=None,
         padj_threshold=0.05, fc_threshold=1.0,
         sig_color="#d62728", ns_color="#999999")

If `padj` is given, points pass the threshold filter on adjusted p-value
*and* |log2 fc|; otherwise only |log2 fc| is used.
"""

SUMMARY = 'RNA-seq MA plot: log₂ fold change vs mean log expression, with significance thresholds.'

import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import circle, segment


def ma_record(args, kw):
    mean_expr = to_list(args[0])
    log2_fc = to_list(args[1])
    padj = kw.get("padj")
    if padj is not None:
        padj = to_list(padj)
    return {"type": "ma", "_a": mean_expr, "_m": log2_fc, "_padj": padj,
            "opts": kw}


def ma_xdomain(a): return a["_a"]
def ma_ydomain(a):
    fc_th = a["opts"].get("fc_threshold", 1.0)
    return list(a["_m"]) + [-fc_th * 1.5, fc_th * 1.5]


def ma_draw(a, ctx):
    fc_th = a["opts"].get("fc_threshold", 1.0)
    padj_th = a["opts"].get("padj_threshold", 0.05)
    sig_col = a["opts"].get("sig_color", "#d62728")
    ns_col = a["opts"].get("ns_color", "#999999")
    size = a["opts"].get("size", 2.5)
    out = []
    # Color rule: padj < threshold AND |fc| > threshold (if padj given);
    # else just |fc|.
    for i, (ae, m) in enumerate(zip(a["_a"], a["_m"])):
        if a["_padj"] is not None:
            p = a["_padj"][i]
            sig = (p < padj_th) and (abs(m) > fc_th)
        else:
            sig = abs(m) > fc_th
        col = sig_col if sig else ns_col
        out.append(circle(ctx.x_scale(ae), ctx.y_scale(m), size,
                          fill=col, alpha=0.7))
    # Reference y = 0.
    x_lo = ctx.x_scale(min(a["_a"]))
    x_hi = ctx.x_scale(max(a["_a"]))
    y_zero = ctx.y_scale(0)
    out.append(segment(x_lo, y_zero, x_hi, y_zero, color="#444", width=0.8))
    # Fold-change threshold dashes at +/- fc_th.
    for sign in (-1, 1):
        y_th = ctx.y_scale(sign * fc_th)
        out.append(segment(x_lo, y_th, x_hi, y_th,
                           color="#888", width=0.8, dash="4,3"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="ma",
    record=ma_record,
    xdomain=ma_xdomain,
    ydomain=ma_ydomain,
    draw=ma_draw,
    uses_color_cycle=False,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    n = 3000
    A = []; M = []; P = []
    for _ in range(n):
        a = random.uniform(0, 14)
        # Most genes near zero fc with mild dispersion that's higher at low expr.
        sigma = 0.3 + 1.5 / (1 + a)
        m = random.gauss(0, sigma)
        if random.random() < 0.03:  # ~3 % true DE genes
            m += random.choice([-1, 1]) * random.uniform(1.0, 4.0)
            p = 10 ** -random.uniform(3, 12)
        else:
            p = 10 ** -random.uniform(0, 2)
        A.append(a); M.append(m); P.append(p)
    c = pt.chart()
    c.ma(A, M, padj=P, fc_threshold=1.0, padj_threshold=0.01)
    c.title("MA plot").xlabel("mean log₂ expression").ylabel("log₂ fold change")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
