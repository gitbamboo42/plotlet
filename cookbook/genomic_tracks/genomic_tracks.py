"""Genome-wide tracks demo.

Stacked, length-weighted faceting built on `c.sectors()`. Each track is
one chart spanning the full genome; the paint callback writes into the
chart with the full DataFrame, and sectors handles the chrom→global x
remap automatically for any artist that takes `data=` and carries the
chrom column.

Patterns shown:
- one-liner `data=`-style painters
  (`lambda c, df, off: c.scatter(data=df, ...)`); sectors auto-remaps the
  x column via the `chrom` tag that rides along in `df`.
- pre-factored painter closures for multi-statement paints
  (`step_paint`, `bar_paint`) — they group by chrom and emit one
  artist call per chrom in **global** coords (positional `xs` lists
  bypass `data=`-driven remap).
- highlight regions passed at the framework level via
  `Track(..., highlight_df=...)` — drawn into every track before the
  paint runs, so all tracks share the same overlay without each paint
  repeating axvspan boilerplate.
- font / size customization via a pre-registered theme passed to
  `plot_tracks(theme=...)`.
- alternating chrom banding via `plot_tracks(style="facecolor")`
  (default); `"spine"` uses dotted sector dividers via
  `c.sectors(..., divider={"linestyle": "dotted", ...})`; `"gap"` opens
  an inter-sector px pad via `c.sectors(..., gap=N)` — same unit as the
  categorical heatmap path so gaps align across mixed-scale tracks.
- log-scale tracks via `Track(..., yscale="log")`.
- `chrom=[...]` / `showX=False` filtering via the framework.
"""

SUMMARY = "Genome-wide tracks as a stacked, sector-partitioned figure."

from pathlib import Path

import numpy as np
import pandas as pd
import plotlet as pt

from track_layout import Track, plot_tracks


# =============================================================================
# Painter helpers
# =============================================================================

def step_paint(start_col, end_col, y_col, *, fill=False,
               alpha=0.9, fill_alpha=0.2):
    """Step-after line with optional zero-baseline fill. Groups per chrom
    so the 'repeat the last value at the right edge' trick closes each
    chrom's trailing bin as a rectangle. xs are emitted in global coords
    via the `offsets` dict — positional list-data bypasses sectors auto-
    remap, so we precompute.

    The trailing close-point gets a tiny inward shift so a bin ending
    exactly at ``chrom_length`` still maps inside this chrom under the
    sectored linear scale's strict-`<` boundary convention (see
    `_SectoredLinearScale.__call__`). Without this, the last step would
    visually extend across the inter-sector gap in gap style."""
    def paint(c, df, offsets):
        for cname, sub in df.groupby("chrom", sort=False):
            if cname not in offsets:
                continue
            off = offsets[cname]
            close_end = float(sub[end_col].iloc[-1])
            eps = max(close_end, 1.0) * 1e-9
            xs = [off + x for x in sub[start_col].tolist()] \
                 + [off + close_end - eps]
            ys = sub[y_col].tolist() + [float(sub[y_col].iloc[-1])]
            if fill:
                c.fill_between(data={"x": xs, "y1": [0] * len(xs), "y2": ys},
                               x="x", y1="y1", y2="y2",
                               curve="step-after", alpha=fill_alpha)
            c.step(data={"x": xs, "y": ys}, x="x", y="y",
                   where="post", alpha=alpha)
    return paint


def bar_paint(start_col, end_col, y_col, *, alpha=0.75):
    """Bar look: filled step-after area, no line on top. Same per-chrom
    grouping + close-point epsilon trick as ``step_paint``."""
    def paint(c, df, offsets):
        for cname, sub in df.groupby("chrom", sort=False):
            if cname not in offsets:
                continue
            off = offsets[cname]
            close_end = float(sub[end_col].iloc[-1])
            eps = max(close_end, 1.0) * 1e-9
            xs = [off + x for x in sub[start_col].tolist()] \
                 + [off + close_end - eps]
            ys = sub[y_col].tolist() + [float(sub[y_col].iloc[-1])]
            c.fill_between(data={"x": xs, "y1": [0] * len(xs), "y2": ys},
                           x="x", y1="y1", y2="y2",
                           curve="step-after", alpha=alpha)
    return paint


def hlines_paint(start_col, end_col, y_col, *, linewidth=1.4, alpha=0.9):
    """Horizontal segments from `start_col` to `end_col` at height `y_col`.
    Positional artist — we precompute global xs from `offsets`."""
    def paint(c, df, offsets):
        x0 = [offsets[r] + s for r, s in zip(df["chrom"], df[start_col])
              if r in offsets]
        x1 = [offsets[r] + e for r, e in zip(df["chrom"], df[end_col])
              if r in offsets]
        ys = [v for r, v in zip(df["chrom"], df[y_col]) if r in offsets]
        c.hlines(ys, x0, x1, linewidth=linewidth, alpha=alpha)
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


# =============================================================================
# Demo
# =============================================================================

if __name__ == "__main__":
    points_df = make_points(GENOME_SIZE)
    segs_df   = make_segments(GENOME_SIZE)
    counts_df = make_counts(GENOME_SIZE)
    gc_df     = make_gc(GENOME_SIZE)

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
              paint=lambda c, df, off: c.scatter(
                  data=df, x="start", y="value", size=4, alpha=0.4),
              ylabel="logR", ylim=(-1.5, 2.0),
              highlight_df=highlight_df),

        Track(segs_df,
              paint=hlines_paint("start", "end", "value"),
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
    ]

    for style, suffix in [("facecolor", ""), ("spine", "_spine"),
                          ("gap", "_gap"), ("boxed", "_boxed")]:
        fig = plot_tracks(tracks, GENOME_SIZE,
                          width=600, track_height=55, gap=8,
                          style=style,
                          theme="genomic_tracks_demo")
        out = Path(__file__).with_name(
            Path(__file__).stem + suffix + ".svg")
        fig.save_svg(out)
        print(f"wrote {out}")
