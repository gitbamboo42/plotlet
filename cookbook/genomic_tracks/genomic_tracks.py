"""Genome-wide tracks across chromosome-proportional subplots.

Recipe shape: a 3 × N grid where each column is one chromosome and each
row is one track type. Column widths are proportional to chromosome
length, so the same Mb-distance reads at the same pixel width regardless
of which chromosome it's in.

    [scatter chr1   ][scatter chr2  ]..[chrX  ][chrY]
    [coverage chr1  ][coverage chr2 ]..[chrX  ][chrY]
    [meth chr1      ][meth chr2     ]..[chrX  ][chrY]
       chr1            chr2          .. chrX    chrY

Mechanics:

- `pt.grid(rows, share_x="col", share_y="row")` does the layout:
    * `share_x="col"` — each column's three tracks share their x scale,
      so they read as one continuous panel per chromosome.
    * `share_y="row"` — each row's panels share their y scale across
      chromosomes; only the leftmost (chr1) draws y-tick labels, the
      ylabel, and the left spine. The rest auto-suppress.
    * Inter-track and inter-chromosome gaps come from the per-panel
      `_MARGIN_FLOOR` (4 px each side → 8 px joined) — joined sides
      drop their content reservations naturally, leaving just the floor.
- Top and right spines are off everywhere; x-axis tick marks and
  labels are hidden on every panel (whole-genome scale makes per-Mb
  numbering illegible). The chromosome name sits as the xlabel of the
  bottom row, naming each column.

Three track types are demonstrated, all using built-in artists:

  - **scatter** — sparse per-position values (e.g. per-variant logR).
  - **line** — smoothed coverage across the chromosome.
  - **fill_between with `curve="step-after"`** — binned methylation
    rendered as a step area under a horizontal baseline.

To extend with a custom track type (e.g. SV triangles), register a
new artist via `pt.add_artist(pt.ArtistSpec(...))` — see
`docs/EXTENDING.md`. Once registered, drop it into the same per-column
stack.
"""

SUMMARY = 'Genome-wide tracks across chromosome-proportional subplots.'

from pathlib import Path
import math
import random

import plotlet as pt


# Chromosome lengths in megabases. A trimmed subset (hg38-flavored) keeps
# the recipe short; real workflows pull lengths from a genome-build table
# (UCSC chromInfo, etc.).
CHROMS = [
    ("chr1", 249),
    ("chr2", 242),
    ("chr3", 198),
    ("chrX", 156),
    ("chrY",  57),
]

PX_PER_MB = 1.0      # pixel scale: how many px per Mb of chromosome
TRACK_HEIGHT = 60    # px per track row's data region


# ---------- synthetic data ---------------------------------------------

def make_scatter(length_mb, seed):
    """Sparse per-variant points. A faint signal in the left third
    mimics a focal CNV gain."""
    rng = random.Random(seed)
    n = max(20, int(length_mb * 1.2))
    xs = sorted(rng.uniform(0, length_mb) for _ in range(n))
    ys = [rng.gauss(0, 0.35) + (0.7 if x < length_mb / 3 else 0.0) for x in xs]
    return xs, ys


def make_line(length_mb, seed):
    """Smoothed coverage trace via a random walk re-scaled into [0, 2]."""
    rng = random.Random(seed)
    bins = max(40, int(length_mb / 3))
    xs = [i * length_mb / bins for i in range(bins + 1)]
    v = 0.0
    ys = []
    for _ in xs:
        v += rng.gauss(0, 0.3)
        ys.append(v)
    lo, hi = min(ys), max(ys)
    span = hi - lo or 1.0
    return xs, [(y - lo) / span * 2 for y in ys]


def make_bins(length_mb, seed, bin_mb=8):
    """Binned methylation-style fraction in [0, 1]. Returns step-curve
    coordinates: xs = bin starts (with one extra at the chromosome end)
    so `fill_between(curve="step-after")` draws a flat top per bin."""
    rng = random.Random(seed)
    n = max(4, math.ceil(length_mb / bin_mb))
    edges = [i * length_mb / n for i in range(n + 1)]
    vals  = [rng.uniform(0.15, 0.95) for _ in range(n)]
    # Repeat the last value at the right edge so step-after renders the
    # final bin as a closed rectangle, not an open step.
    step_ys = vals + [vals[-1]]
    return edges, step_ys


# ---------- compose -----------------------------------------------------

def chrom_panel(length_mb, *, ylim, ylabel=None, xlabel=None):
    """Build one cell of the grid — one chromosome × one track row."""
    c = pt.chart(data_width=length_mb * PX_PER_MB, data_height=TRACK_HEIGHT)
    c.spines(top=False, right=False)
    # Hide x-axis tick marks and labels — whole-genome scale makes per-Mb
    # numbering illegible. The chromosome footer label below the bottom
    # row carries each column's identification.
    c.xticks([])
    if ylabel is not None: c.ylabel(ylabel)
    if xlabel is not None: c.xlabel(xlabel)
    c.ylim(*ylim)
    return c


if __name__ == "__main__":
    scatter_row, line_row, meth_row = [], [], []
    for i, (chrom, length) in enumerate(CHROMS):
        is_first = (i == 0)

        sc = chrom_panel(length, ylim=(-1.5, 2.0),
                         ylabel="logR" if is_first else None)
        xs, ys = make_scatter(length, seed=i)
        sc.scatter(xs, ys, s=4, alpha=0.4)

        ln = chrom_panel(length, ylim=(0, 2),
                         ylabel="coverage" if is_first else None)
        xs, ys = make_line(length, seed=i + 10)
        ln.line(xs, ys)

        # Only the bottom row carries an xlabel — it acts as the
        # chromosome footer for that column.
        mt = chrom_panel(length, ylim=(0, 1),
                         ylabel="methylation" if is_first else None,
                         xlabel=chrom)
        edges, step_ys = make_bins(length, seed=i + 20)
        mt.fill_between(edges, [0] * len(edges), step_ys,
                        curve="step-after", alpha=0.6)

        scatter_row.append(sc)
        line_row.append(ln)
        meth_row.append(mt)

    fig = pt.grid(
        [scatter_row, line_row, meth_row],
        share_x="col",                                  # tracks within a chromosome share x
        share_y="row",                                  # chromosomes within a row share y
    )

    out = Path(__file__).with_suffix(".svg")
    fig.save_svg(out)
    print(f"wrote {out}")
