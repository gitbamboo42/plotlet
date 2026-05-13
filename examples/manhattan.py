"""Custom artist: Manhattan plot (GWAS).

Scatter of -log₁₀(p) vs cumulative genomic position, colored alternately
by chromosome, with a horizontal threshold for genome-wide significance
(5e-8 by convention). The defining figure of every GWAS paper.

API:
    c.manhattan(chroms, positions, pvalues,
                colors=("#3a86ff", "#9bb6e8"),
                sig=5e-8, suggestive=1e-5)

`chroms` is per-SNP chromosome label (int or str). `positions` is bp
position within chromosome. `pvalues` is the raw p value; the artist
plots -log₁₀(p). Chromosome boundaries are computed from each chrom's
max position so x is continuous left-to-right.
"""

SUMMARY = 'GWAS scatter of −log₁₀(p) vs cumulative genomic position, chromosomes alternated by color.'
import math
from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist
from plotlet.font import _text_path


def manhattan_record(args, kw):
    chroms = _to_pylist(args[0])
    pos = _to_pylist(args[1])
    pvals = _to_pylist(args[2])
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
        out.append(
            f'<circle cx="{ctx.x_scale(x):.2f}" cy="{ctx.y_scale(y):.2f}" '
            f'r="{size}" fill="{col}"/>'
        )
    # Genome-wide threshold.
    if sig is not None:
        y_sig = ctx.y_scale(-math.log10(sig))
        out.append(
            f'<line x1="{ctx.x_scale(0):.2f}" '
            f'x2="{ctx.x_scale(a["_total"]):.2f}" '
            f'y1="{y_sig:.2f}" y2="{y_sig:.2f}" stroke="#d62728" '
            f'stroke-width="1" stroke-dasharray="6,3"/>'
        )
    if suggestive is not None:
        y_sug = ctx.y_scale(-math.log10(suggestive))
        out.append(
            f'<line x1="{ctx.x_scale(0):.2f}" '
            f'x2="{ctx.x_scale(a["_total"]):.2f}" '
            f'y1="{y_sug:.2f}" y2="{y_sug:.2f}" stroke="#888" '
            f'stroke-width="1" stroke-dasharray="3,3"/>'
        )
    # Chromosome labels under each block.
    for ch, cx in a["_centers"].items():
        out.append(_text_path(str(ch), ctx.x_scale(cx),
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


if __name__ == "__main__":
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
    c = pt.chart(data_width=720, data_height=260)
    c.manhattan(chroms, positions, pvals, sig=5e-8, suggestive=1e-5)
    c.title("GWAS Manhattan plot").ylabel("−log₁₀(p)")
    c.xticks([])  # chromosome labels drawn inside the artist
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
