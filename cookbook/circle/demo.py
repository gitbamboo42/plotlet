"""Circos-style demo — 7 chromosomes as sectors, 4 data tracks as rings,
intra-chrom links drawn through the inner disc.

The same `c.chord_links(...)` artist works in both the circular inner
disc (Bezier chords through the center) and the linear strip below the
tracks (half-ellipse arcs above the axis) — the coordinate decides how
the curves render.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import plotlet as pt
import plotlet.extensions.numeric_bar   # noqa
import plotlet.extensions.chord_links   # noqa

CHROMS  = ["chr1", "chr2", "chr3", "chr4", "chr5", "chr6", "chr7"]
LENGTHS = [249, 242, 198, 190, 181, 170, 159]  # Mb, real human values
BIN_MB  = 5
rng = np.random.default_rng(42)


# ---- one DataFrame, one row per (chrom, 5-Mb bin) ----

df = pd.concat([
    pd.DataFrame({"chrom": chrom,
                  "pos": np.arange(BIN_MB / 2, length - BIN_MB / 2, BIN_MB)})
    for chrom, length in zip(CHROMS, LENGTHS)
], ignore_index=True)

df["gene_density"] = rng.poisson(12, len(df))                          # genes per bin
df["gc"]           = (42 + 6 * np.sin(2 * np.pi * df.pos / 60)
                      + rng.normal(0, 1.5, len(df))).clip(30, 60)      # GC %
df["mutations"]    = rng.poisson(3, len(df))                           # mutations per bin
df["depth"]        = (30 + rng.gamma(2, 8, len(df))).clip(0, 80)       # sequencing depth


# ---- synthetic links: intra-chrom + cross-chrom translocations ----

link_rows = []
for chrom, L in zip(CHROMS, LENGTHS):                    # one intra-chrom per chrom
    a, b = sorted(rng.uniform(0.05 * L, 0.95 * L, 2))
    link_rows.append({"src_chrom": chrom, "dst_chrom": chrom,
                      "src": a, "dst": b, "kind": "intra"})
for _ in range(8):                                       # 8 cross-chrom pairs
    s, d = rng.choice(CHROMS, 2, replace=False)
    s_pos = rng.uniform(0.05, 0.95) * LENGTHS[CHROMS.index(s)]
    d_pos = rng.uniform(0.05, 0.95) * LENGTHS[CHROMS.index(d)]
    link_rows.append({"src_chrom": s, "dst_chrom": d,
                      "src": s_pos, "dst": d_pos, "kind": "trans"})
links = pd.DataFrame(link_rows)


# ---- circular layout: 4 concentric rings + inner-disc chords ----

W = H = 500
XL = (0, sum(LENGTHS))

c1 = pt.chart(df, xlim=XL, ylim=(0, 30), data_width=W, data_height=H)
c1.scatter(x="pos", y="gene_density", color="#534AB7", size=2, alpha=0.6)

c2 = pt.chart(df, xlim=XL, ylim=(30, 60), data_width=W, data_height=H)
c2.line(x="pos", y="gc", group="chrom", color="#1D9E75", width=1.5)

c3 = pt.chart(df, xlim=XL, ylim=(0, 10), data_width=W, data_height=H)
c3.numeric_bar(x="pos", y="mutations", width=4, color="#D9534F", alpha=0.85)

c4 = pt.chart(df, xlim=XL, ylim=(0, 80), data_width=W, data_height=H)
c4.line(x="pos", y="depth", group="chrom", color="#E0A030", width=1.5)

arcs = pt.chart(links, xlim=XL, data_width=W, data_height=H)
# `c.sectors(...)` must come before any artist call that needs sector
# remap — chart-level sectors record in user-call order (only the
# layout-level `Layout.sectors(...)` inserts at the front). Labels off:
# the rings already show them. Dividers auto-off via crosses_sectors=True
# on chord_links — walls would cut through chords.
arcs.sectors(pt.Sectors(names=CHROMS, lengths=LENGTHS, gap=2),
             column="src_chrom", label=False)
arcs.chord_links(x1="src", x2="dst",
                 x1_sector="src_chrom", x2_sector="dst_chrom",
                 color="kind", width=1.5, alpha=0.75)

circle_panel = (c1 / c2 / c3 / c4).coordinate(
    pt.CircularCoordinate(r_inner=0.3, wrap_gap_deg=5, inner=arcs)
).sectors(pt.Sectors(names=CHROMS, lengths=LENGTHS, gap=2), column="chrom")


# ---- linear comparison ----

p1 = pt.chart(df, ylabel="genes/bin", xlim=XL, ylim=(0, 30),
              data_width=400, data_height=110)
p1.scatter(x="pos", y="gene_density", color="#534AB7", size=3, alpha=0.6)

p2 = pt.chart(df, ylabel="GC%", xlim=XL, ylim=(30, 60),
              data_width=400, data_height=110)
p2.line(x="pos", y="gc", group="chrom", color="#1D9E75", width=1.5)

p3 = pt.chart(df, ylabel="mutations", xlim=XL, ylim=(0, 10),
              data_width=400, data_height=110)
p3.numeric_bar(x="pos", y="mutations", width=4, color="#D9534F", alpha=0.85)

p4 = pt.chart(df, ylabel="depth", xlim=XL, ylim=(0, 80),
              data_width=400, data_height=110)
p4.line(x="pos", y="depth", group="chrom", color="#E0A030", width=1.5)

p_arcs = pt.chart(links, ylabel="links", xlabel="position (Mb)", xlim=XL,
                  data_width=400, data_height=80)
p_arcs.chord_links(x1="src", x2="dst",
                   x1_sector="src_chrom", x2_sector="dst_chrom",
                   color="kind", width=1.5, alpha=0.75)
p_arcs.yticks([])

linear_panel = pt.grid([[p1], [p2], [p3], [p4], [p_arcs]]).share_x("col").sectors(
    pt.Sectors(names=CHROMS, lengths=LENGTHS, gap=0), column="chrom")


out = Path(__file__).parent / "output" / "combined.svg"
(circle_panel | linear_panel).save_svg(str(out))
print(f"wrote {out}")
