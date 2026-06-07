"""Custom artist: Manhattan plot (GWAS).

Scatter of -log₁₀(p) vs cumulative genomic position, colored alternately
by chromosome, with a horizontal threshold for genome-wide significance
(5e-8 by convention). The defining figure of every GWAS paper.

API:
    c.manhattan(data=df, chrom="col", pos="col", pvalue="col",
                colors=("#3a86ff", "#9bb6e8"),
                sig=5e-8, suggestive=1e-5)

`chrom` is per-SNP chromosome label (int or str). `pos` is bp position
within chromosome. `pvalue` is the raw p value; the artist plots
-log₁₀(p). Chromosome boundaries are computed from each chrom's max
position so x is continuous left-to-right.
"""

SUMMARY = 'GWAS scatter of −log₁₀(p) vs cumulative genomic position, chromosomes alternated by color.'
import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import text_path, circle, segment


def manhattan_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "manhattan requires long-form input: "
            "c.manhattan(data=df, chrom='col', pos='col', pvalue='col')."
        )
    data = kw.pop("data", None)
    chrom_col = kw.pop("chrom", None)
    pos_col = kw.pop("pos", None)
    pvalue_col = kw.pop("pvalue", None)
    if data is None or chrom_col is None or pos_col is None or pvalue_col is None:
        raise TypeError("manhattan requires data=, chrom=, pos=, pvalue=.")
    chroms = to_list(data[chrom_col])
    pos = to_list(data[pos_col])
    pvals = to_list(data[pvalue_col])
    # Group by chrom keeping order of first appearance.
    seen = []
    by_chrom = {}
    for ch, p, pv in zip(chroms, pos, pvals):
        if ch not in by_chrom:
            seen.append(ch); by_chrom[ch] = []
        by_chrom[ch].append((p, pv))
    # Build cumulative offsets so each chrom's positions are appended.
    offsets = {}; cum = 0; centers = {}
    for ch in seen:
        offsets[ch] = cum
        max_p = max(p for p, _ in by_chrom[ch])
        centers[ch] = cum + max_p / 2
        cum += max_p
    # Flatten to cumulative-x and y = -log10(p).
    xs_cum = []; ys_log = []; chrom_idx = []
    for i, ch in enumerate(seen):
        for p, pv in by_chrom[ch]:
            xs_cum.append(offsets[ch] + p)
            ys_log.append(-math.log10(pv) if pv > 0 else 0)
            chrom_idx.append(i)
    return {"type": "manhattan", "_xs": xs_cum, "_ys": ys_log,
            "_chrom_idx": chrom_idx, "_seen": seen, "_centers": centers,
            "_total": cum, "opts": kw}


def manhattan_xdomain(a):
    return [0, a["_total"]]


def manhattan_ydomain(a):
    sig = a["opts"].get("sig", 5e-8)
    sig_y = -math.log10(sig)
    return list(a["_ys"]) + [0, sig_y + 1]


def manhattan_draw(a, ctx):
    colors = a["opts"].get("colors", ("#3a86ff", "#9bb6e8"))
    size = a["opts"].get("size", 2)
    sig = a["opts"].get("sig", 5e-8)
    suggestive = a["opts"].get("suggestive")
    out = []
    for x, y, idx in zip(a["_xs"], a["_ys"], a["_chrom_idx"]):
        col = colors[idx % len(colors)]
        out.append(circle(ctx.x_scale(x), ctx.y_scale(y), size, fill=col))
    # Genome-wide threshold.
    if sig is not None:
        y_sig = ctx.y_scale(-math.log10(sig))
        out.append(segment(ctx.x_scale(0), y_sig,
                           ctx.x_scale(a["_total"]), y_sig,
                           color="#d62728", width=1, dash="6,3"))
    if suggestive is not None:
        y_sug = ctx.y_scale(-math.log10(suggestive))
        out.append(segment(ctx.x_scale(0), y_sug,
                           ctx.x_scale(a["_total"]), y_sug,
                           color="#888", width=1, dash="3,3"))
    # Chromosome labels under each block.
    for ch, cx in a["_centers"].items():
        out.append(text_path(str(ch), ctx.x_scale(cx),
                              ctx.y_scale(0) + 14, 9, anchor="middle"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="manhattan",
    record=manhattan_record,
    xdomain=manhattan_xdomain,
    ydomain=manhattan_ydomain,
    draw=manhattan_draw,
    uses_color_cycle=False,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(4)
    # Simulate ~22 chromosomes with decreasing size.
    chroms, positions, pvals = [], [], []
    for c_id in range(1, 23):
        chrom_size = int(250_000_000 * (1 - 0.025 * (c_id - 1)))
        n_snps = 200
        for _ in range(n_snps):
            chroms.append(c_id)
            positions.append(random.randint(0, chrom_size))
            # Most p-values are large; occasional hit.
            if random.random() < 0.003:
                pvals.append(10 ** -random.uniform(7, 15))
            else:
                pvals.append(10 ** -random.uniform(0, 5))
    df = {"chrom": chroms, "pos": positions, "pvalue": pvals}
    c = pt.chart(data_width=720, data_height=260)
    c.manhattan(df, chrom="chrom", pos="pos", pvalue="pvalue",
                sig=5e-8, suggestive=1e-5)
    c.title("GWAS Manhattan plot").ylabel("−log₁₀(p)")
    c.xticks([])  # chromosome labels drawn inside the artist
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
