"""hg38 chord-link demo — reproduction of pycirclize's section 4-2.

Reference: https://moshi4.github.io/pyCirclize/circos_plot/ — section
"4-2. Segmental Dups Link".

24 human chromosomes as sectors, segmental-duplication links drawn as
Bezier chords through the inner disc. Following pycirclize's example,
links are filtered to only `chr1` / `chr8` / `chr16` sources and
inter-chromosomal only — the raw file has 5990 links across all
chromosomes, which fills the disc with noise.

Data: `data/hg38_chr.bed` (chromosome lengths) and
`data/hg38_genomic_link.tsv` (pairs of `(chrom, start, end)` ranges).
Both ends of each link are ranges; we collapse to midpoints for the
chord endpoints.
"""
from pathlib import Path

import pandas as pd

import plotlet as pt
import plotlet.extensions.chord_links        # noqa
import plotlet.extensions.annotation_strip   # noqa

DATA = Path(__file__).parent / "data"

chroms = pd.read_csv(DATA / "hg38_chr.bed", sep="\t")
chroms.columns = ["chrom", "start", "end", "name"]
CHROMS  = chroms["chrom"].tolist()
LENGTHS = chroms["end"].tolist()

links = pd.read_csv(
    DATA / "hg38_genomic_link.tsv", sep="\t", header=None,
    names=["src_chrom", "src_start", "src_end",
           "dst_chrom", "dst_start", "dst_end"],
)
# Match pycirclize's filter: only inter-chrom links sourced from these
# three chromosomes. Without it the disc fills with ~6000 chords and
# the visual collapses to noise.
HIGHLIGHTED = ("chr1", "chr8", "chr16")
links = links[
    links["src_chrom"].isin(HIGHLIGHTED) &
    (links["src_chrom"] != links["dst_chrom"])
].reset_index(drop=True)

# Range → midpoint per endpoint. Some rows have start > end (strand-
# reversed); midpoint is order-agnostic.
links["src"] = (links["src_start"] + links["src_end"]) / 2
links["dst"] = (links["dst_start"] + links["dst_end"]) / 2


W = H = 700
XL = (0, sum(LENGTHS))

R_INNER = 0.95
GAP_PX  = 4

# Per-chrom palette: 24 evenly-spaced hsv colors, matching pycirclize's
# ColorCycler.set_cmap("hsv") + get_color_list(N) call.
def _hsv_palette(names):
    lut = pt.draw.colormap_lut("hsv")          # 768-byte LUT (256 RGB triplets)
    n = len(names)
    out = {}
    for j, name in enumerate(names):
        i = min(int(j * 256 / (n - 1)), 255)   # mirrors np.linspace(0, 256, n)
        out[name] = f"#{lut[i*3]:02x}{lut[i*3+1]:02x}{lut[i*3+2]:02x}"
    return out

CHROM_COLORS = _hsv_palette(CHROMS)

# UCSC standard cytoband stain colors (matches the convention pycirclize
# bakes into add_cytoband_tracks).
CYTOBAND_COLORS = {
    "gneg":    "#ffffff",
    "gpos25":  "#c8c8c8",
    "gpos50":  "#969696",
    "gpos75":  "#646464",
    "gpos100": "#000000",
    "acen":    "#d92626",
    "gvar":    "#a0a0a0",
    "stalk":   "#a0a0a0",
}
cytobands = pd.read_csv(DATA / "hg38_cytoband.tsv", sep="\t")
cytobands.columns = ["chrom", "start", "end", "name", "stain"]
# Drop chromosomes not in the BED (e.g. chrM is in cytoband but not in
# the hg38_chr.bed sector list).
cytobands = cytobands[cytobands["chrom"].isin(CHROMS)].reset_index(drop=True)

arcs = pt.chart(links, xlim=XL, data_width=W, data_height=H)
arcs.sectors(pt.Sectors(names=CHROMS, lengths=LENGTHS, gap=GAP_PX),
             column="src_chrom", label=False)
arcs.chord_links(x1="src", x2="dst",
                 x1_sector="src_chrom", x2_sector="dst_chrom",
                 color="src_chrom", palette=CHROM_COLORS,
                 width=1.0, alpha=0.5)

ring = pt.chart(cytobands, xlim=XL, ylim=(0, 1), data_width=W, data_height=H)
ring.sectors(pt.Sectors(names=CHROMS, lengths=LENGTHS, gap=GAP_PX, fontsize=11),
             column="chrom")
ring.annotation_strip(x1="start", x2="end",
                      value="stain", palette=CYTOBAND_COLORS)

# Per-chrom ticks every 40 Mb, matching pycirclize's
# `xticks_by_interval(40000000, label_formatter=...)`. Positions are
# per-sector LOCAL; `Sectors.expand_ticks` replicates them across every
# chromosome and drops any tick past a chromosome's length.
TICK_MB = 40
tick_pos = list(range(0, max(LENGTHS) + 1, TICK_MB * 1_000_000))
tick_lbl = [f"{v // 1_000_000} Mb" for v in tick_pos]
ring.xticks(tick_pos, tick_lbl, fontsize=7, rotation=90)

# Wrap the ring in pt.grid so .coordinate(...) lands on a Layout and
# triggers the inner-disc routing in CircularCoordinate.render_layout.
circle = pt.grid([[ring]]).coordinate(
    pt.CircularCoordinate(r_inner=R_INNER, inner=arcs)
)


# ---- Linear unrolling — same data, same artists, no coord ----
#
# Same panels as the circular version, stacked top→bottom:
#   1. cytoband strip (annotation_strip + per-chrom ticks + chrom names)
#   2. chord arcs (chord_links)
# share_x("col") joins the x-axis so sector chrome only renders once.

LW, LH_CYTO, LH_ARC = 900, 30, 120

# Sectors recorded per chart so each artist's record-time remap sees
# them — `attach_above` shares the x-scale at render time but doesn't
# back-propagate to record-time state.
sectors_spec = pt.Sectors(names=CHROMS, lengths=LENGTHS, gap=8, fontsize=11, rotation=90)

p_cyto = pt.chart(cytobands, xlim=XL,
                  data_width=LW, data_height=LH_CYTO)
p_cyto.sectors(sectors_spec, column="chrom")
p_cyto.annotation_strip(x1="start", x2="end",
                        value="stain", palette=CYTOBAND_COLORS)
p_cyto.xticks(tick_pos, tick_lbl, fontsize=7, rotation=90)

p_arc = pt.chart(links, xlim=XL,
                 data_width=LW, data_height=LH_ARC)
p_arc.sectors(sectors_spec, column="src_chrom")
p_arc.chord_links(x1="src", x2="dst",
                  x1_sector="src_chrom", x2_sector="dst_chrom",
                  color="src_chrom", palette=CHROM_COLORS,
                  width=1.0, alpha=0.5)

# `attach_above` with `gap=0` glues p_arc flush against p_cyto (same
# idiom as a dendrogram sitting on top of a heatmap).
linear = p_cyto.attach_above(p_arc, gap=0)


out_dir = Path(__file__).parent / "output"
out_dir.mkdir(exist_ok=True)
circle_svg = out_dir / "hg38_chord_circle.svg"
linear_svg = out_dir / "hg38_chord_linear.svg"
circle.save_svg(str(circle_svg))
linear.save_svg(str(linear_svg))
print(f"wrote {circle_svg}")
print(f"wrote {linear_svg}")
