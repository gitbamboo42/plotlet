"""Custom artist: volcano plot.

Scatter of log₂-fold-change vs -log₁₀(p), with thresholds for "up", "down",
and "not significant" segments and optional labels for the top hits. The
RNA-seq / proteomics / phospho-proteomics workhorse.

API:
    c.volcano(log2fc, pvalues, gene_labels,
              fc_threshold=1.0, p_threshold=0.05,
              up_color="#d62728", down_color="#1f77b4", ns_color="#999999",
              n_label=10)

Points are colored by their location relative to the thresholds. The
top `n_label` points by significance get text labels.
"""

SUMMARY = 'RNA-seq volcano: log₂-FC vs −log₁₀(p), colored by direction, with top-hit labels.'
import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import text_path, circle, segment


def volcano_record(args, kw):
    fc = to_list(args[0])
    pvals = to_list(args[1])
    labels = to_list(args[2]) if len(args) > 2 else [""] * len(fc)
    return {"type": "volcano", "fc": fc, "pvals": pvals, "labels": labels,
            "opts": kw}


def volcano_xdomain(a): return a["fc"]


def volcano_ydomain(a):
    return [-math.log10(p) if p > 0 else 0 for p in a["pvals"]] + [0]


def volcano_draw(a, ctx):
    fc_th = a["opts"].get("fc_threshold", 1.0)
    p_th = a["opts"].get("p_threshold", 0.05)
    up_c = a["opts"].get("up_color", "#d62728")
    dn_c = a["opts"].get("down_color", "#1f77b4")
    ns_c = a["opts"].get("ns_color", "#999999")
    size = a["opts"].get("size", 2.5)
    n_label = a["opts"].get("n_label", 8)
    log_p_th = -math.log10(p_th) if p_th > 0 else 0
    pts = []  # (fc, log_p, label, signif_color)
    for fc, p, lab in zip(a["fc"], a["pvals"], a["labels"]):
        log_p = -math.log10(p) if p > 0 else 0
        if log_p < log_p_th or abs(fc) < fc_th:
            col = ns_c
        elif fc > 0:
            col = up_c
        else:
            col = dn_c
        pts.append((fc, log_p, lab, col))
    out = []
    for fc, log_p, lab, col in pts:
        out.append(circle(ctx.x_scale(fc), ctx.y_scale(log_p), size,
                          fill=col, alpha=0.7))
    # Threshold lines.
    out.append(segment(ctx.x_scale(min(a["fc"])), ctx.y_scale(log_p_th),
                       ctx.x_scale(max(a["fc"])), ctx.y_scale(log_p_th),
                       color="#888", width=0.8, dash="4,3"))
    for sign in (-1, 1):
        x_th = ctx.x_scale(sign * fc_th)
        out.append(segment(x_th, ctx.y_scale(0),
                           x_th, ctx.y_scale(max(p[1] for p in pts) if pts else 1),
                           color="#888", width=0.8, dash="4,3"))
    # Label top-N by significance among the colored (non-NS) points.
    colored = [p for p in pts if p[3] != ns_c and p[2]]
    colored.sort(key=lambda p: -p[1])
    for fc, log_p, lab, col in colored[:n_label]:
        out.append(text_path(lab, ctx.x_scale(fc) + 4,
                              ctx.y_scale(log_p) - 4, 10, anchor="start"))
    return "".join(out)


def volcano_legend_entries(a):
    opts = a["opts"]
    return [
        {"label": opts.get("up_label", "up"),
         "color": opts.get("up_color", "#d62728")},
        {"label": opts.get("down_label", "down"),
         "color": opts.get("down_color", "#1f77b4")},
        {"label": opts.get("ns_label", "n.s."),
         "color": opts.get("ns_color", "#999999")},
    ]


pt.add_artist(pt.ArtistSpec(
    name="volcano",
    record=volcano_record,
    xdomain=volcano_xdomain,
    ydomain=volcano_ydomain,
    draw=volcano_draw,
    uses_color_cycle=False,
    force_zero_y=True,
    legend_entries=volcano_legend_entries,
))


def demo():
    """Build the volcano-plot demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(5)
    n = 1500
    # Mix of background (low |fc|, weak p) and hits (high |fc|, strong p).
    fc = []; pvals = []
    for _ in range(n):
        if random.random() < 0.04:  # ~4 % hits
            sign = random.choice([-1, 1])
            fc.append(sign * random.uniform(1.5, 4.0))
            pvals.append(10 ** -random.uniform(4, 14))
        else:
            fc.append(random.gauss(0, 0.6))
            pvals.append(10 ** -random.uniform(0, 3))
    labels = [f"g{i:04d}" for i in range(n)]
    c = pt.chart()
    c.volcano(fc, pvals, labels, fc_threshold=1.0, p_threshold=0.01, n_label=8)
    c.title("Differential expression").xlabel("log₂ fold change").ylabel("−log₁₀(p)").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
