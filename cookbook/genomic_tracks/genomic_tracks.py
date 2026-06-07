"""Genome-wide tracks demo.

Stacked, length-weighted faceting via the small coordination layer in
[track_layout.py](track_layout.py). Each per-chrom track is a (data, paint)
pair; the paint callback draws whatever you want into one chrom's chart.
The SV triangle is a different shape — one chart spanning the genome —
and lives as its own `SVTriangleTrack` type.

Patterns shown:
- one-liner painters (`lambda c, df: c.scatter(...)`).
- pre-factored painter closures for multi-statement paints
  (`step_paint`, `bar_paint`).
- highlight regions passed at the framework level via
  `Track(..., highlight_df=...)` — drawn into every per-chrom cell before
  the paint runs, so all tracks share the same overlay without each
  paint repeating axvspan boilerplate. SV tracks accept the same kwarg.
- font / size customization via a pre-registered theme passed to
  `plot_tracks(theme=...)`.
- alternating chrom banding via `plot_tracks(style="facecolor")`
  (default); `"spine"` for a dotted-separator look instead.
- log-scale tracks via `Track(..., yscale="log")`.
- `chrom=[...]` / `showX=False` filtering via the framework.
- SV triangle plot — `SVTriangleTrack` mixes into the same `plot_tracks`
  call as per-chrom tracks and renders below them.
"""

SUMMARY = "Genome-wide tracks as stacked, length-weighted faceting."

from pathlib import Path

import numpy as np
import pandas as pd
import plotlet as pt

from track_layout import Track, SVTriangleTrack, plot_tracks


# =============================================================================
# Painter helpers
# =============================================================================

def step_paint(start_col, end_col, y_col, *, fill=False,
               alpha=0.9, fill_alpha=0.2):
    """Step-after line with optional zero-baseline fill. The 'repeat the
    last value at the right edge' trick closes the trailing bin as a
    rectangle rather than leaving it as an open step."""
    def paint(c, df):
        xs = df[start_col].tolist() + [df[end_col].iloc[-1]]
        ys = df[y_col].tolist()    + [df[y_col].iloc[-1]]
        if fill:
            c.fill_between(data={"x": xs, "y1": [0] * len(xs), "y2": ys},
                           x="x", y1="y1", y2="y2",
                           curve="step-after", alpha=fill_alpha)
        c.step(data={"x": xs, "y": ys}, x="x", y="y", where="post", alpha=alpha)
    return paint


def bar_paint(start_col, end_col, y_col, *, alpha=0.75):
    """Bar look: filled step-after area, no line on top. Assumes
    contiguous bins."""
    def paint(c, df):
        xs = df[start_col].tolist() + [df[end_col].iloc[-1]]
        ys = df[y_col].tolist()    + [df[y_col].iloc[-1]]
        c.fill_between(data={"x": xs, "y1": [0] * len(xs), "y2": ys},
                       x="x", y1="y1", y2="y2",
                       curve="step-after", alpha=alpha)
    return paint


# =============================================================================
# Synthetic data
# =============================================================================

GENOME_SIZE = pd.DataFrame([
    ("chr1", 249),
    ("chr2", 242),
    ("chr3", 198),
    ("chrX", 156),
    ("chrY",  57),
], columns=["chrom", "length"])


def make_points(gs, *, bin_mb=1.0, seed=0):
    """Sparse per-position logR-style values. chr1's left third carries
    a +0.7 baseline bump to mimic a focal CNV gain."""
    rng = np.random.default_rng(seed)
    rows = []
    for _, r in gs.iterrows():
        n = max(20, int(r.length / bin_mb))
        xs = np.sort(rng.uniform(0, r.length, size=n))
        ys = rng.normal(0, 0.35, size=n)
        if r.chrom == "chr1":
            mask = xs < r.length / 3
            ys[mask] += 0.7
        rows.append(pd.DataFrame({"chrom": r.chrom, "start": xs, "value": ys}))
    return pd.concat(rows, ignore_index=True)


def make_segments(gs, *, n_segs=6, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for _, r in gs.iterrows():
        edges = np.sort(rng.uniform(0, r.length, size=n_segs * 2))
        starts, ends = edges[0::2], edges[1::2]
        vals = rng.uniform(0.2, 1.8, size=len(starts))
        rows.append(pd.DataFrame({"chrom": r.chrom, "start": starts,
                                  "end": ends, "value": vals}))
    return pd.concat(rows, ignore_index=True)


def make_counts(gs, *, bin_mb=10, seed=2):
    """Poisson counts per 10 Mb bin. chr2 carries a hypermutation spike."""
    rng = np.random.default_rng(seed)
    rows = []
    for _, r in gs.iterrows():
        starts = np.arange(0, r.length, bin_mb)
        ends = np.minimum(starts + bin_mb, r.length)
        counts = rng.poisson(lam=25, size=len(starts)).astype(float)
        if r.chrom == "chr2":
            counts[:3] *= 4
        rows.append(pd.DataFrame({"chrom": r.chrom, "start": starts,
                                  "end": ends, "count": counts}))
    return pd.concat(rows, ignore_index=True)


def make_gc(gs, *, bin_mb=5, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for _, r in gs.iterrows():
        starts = np.arange(0, r.length, bin_mb)
        ends = np.minimum(starts + bin_mb, r.length)
        gc = rng.uniform(0.38, 0.55, size=len(starts))
        rows.append(pd.DataFrame({"chrom": r.chrom, "start": starts,
                                  "end": ends, "value": gc}))
    return pd.concat(rows, ignore_index=True)


def make_svs(gs, *, n_intra=40, n_inter=12, seed=4):
    """BEDPE-like SV table. Local SVs cluster near the triangle bottom;
    a handful of inter-chromosomal events float near the apex."""
    rng = np.random.default_rng(seed)
    chroms = gs["chrom"].tolist()
    lens = dict(zip(gs["chrom"], gs["length"]))
    rows = []
    for _ in range(n_intra):
        ch = chroms[rng.integers(len(chroms))]
        L = lens[ch]
        a = rng.uniform(0, L)
        span = abs(rng.normal(0, L * 0.15))
        b = float(np.clip(a + span, 0, L))
        s1, s2 = sorted([a, b])
        rows.append((ch, s1, s1 + 0.1, ch, s2, s2 + 0.1))
    for _ in range(n_inter):
        i, j = rng.choice(len(chroms), size=2, replace=False)
        ca, cb = chroms[i], chroms[j]
        sa = rng.uniform(0, lens[ca])
        sb = rng.uniform(0, lens[cb])
        rows.append((ca, sa, sa + 0.1, cb, sb, sb + 0.1))
    return pd.DataFrame(rows, columns=["chrom1", "start1", "end1",
                                       "chrom2", "start2", "end2"])


# =============================================================================
# Demo
# =============================================================================

if __name__ == "__main__":
    points_df = make_points(GENOME_SIZE)
    segs_df   = make_segments(GENOME_SIZE)
    counts_df = make_counts(GENOME_SIZE)
    gc_df     = make_gc(GENOME_SIZE)
    svs_df    = make_svs(GENOME_SIZE)

    highlight_df = pd.DataFrame([
        ("chr1", 20, 90),
        ("chr2",  0, 30),
        ("chr3", 60, 95),
    ], columns=["chrom", "start", "end"])

    # Custom font + matplotlib-convention L-frame (left + bottom only).
    # The SV row turns all four sides off explicitly to keep the triangle
    # baseline as its own visual frame.
    pt.register_theme("genomic_tracks_demo", {
        "font": {"family": "Helvetica, Arial, sans-serif",
                 "tick_size": 9, "label_size": 10, "title_size": 11},
        "frame": {"spine_top": False, "spine_right": False},
    })

    tracks = [
        Track(points_df,
              paint=lambda c, df: c.scatter(data={"x": df.start.tolist(),
                                                  "y": df.value.tolist()},
                                            x="x", y="y", s=4, alpha=0.4),
              ylabel="logR", ylim=(-1.5, 2.0),
              highlight_df=highlight_df),

        Track(segs_df,
              paint=lambda c, df: c.hlines(df.value.tolist(),
                                           df.start.tolist(), df.end.tolist(),
                                           linewidth=1.4, alpha=0.9),
              ylabel="coverage", ylim=(0, 2.0),
              highlight_df=highlight_df),

        Track(counts_df,
              paint=bar_paint("start", "end", "count"),
              ylabel="SNV ct", ylim=(0, 120),
              highlight_df=highlight_df),

        Track(gc_df,
              paint=step_paint("start", "end", "value", fill=True),
              ylabel="GC %", ylim=(0.35, 0.60),
              highlight_df=highlight_df),

        SVTriangleTrack(svs_df,
                        highlight_df=highlight_df,
                        s=10, alpha=0.7),
    ]

    for style, suffix in [("facecolor", ""), ("spine", "_spine")]:
        fig = plot_tracks(tracks, GENOME_SIZE,
                          width=600, track_height=55, gap=8,
                          style=style,
                          theme="genomic_tracks_demo")
        out = Path(__file__).with_name(
            Path(__file__).stem + suffix + ".svg")
        fig.save_svg(out)
        print(f"wrote {out}")
