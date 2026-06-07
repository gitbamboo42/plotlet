"""Stacked, length-weighted facet — coordination layer for plot_tracks.

Lay out per-chrom track panels with widths proportional to `gs.length`,
stacked vertically. Each `Track` is a (data, paint) pair plus a few panel
fields; the paint callback `(chart, sub_df) -> None` decides what gets
drawn. `SVTriangleTrack` is a different shape: a triangle plot of SVs
across the whole genome, rendered as N per-chrom slices that share a
column with the per-chrom track rows so the whole figure aligns under
one `share_x("col")`.

This is a cookbook recipe — patterns to copy and modify, not a
configurable product. Most styling decisions (highlights, hue palettes,
fancy spine work) belong in the paint callback. The few framework-level
features here are things that *can't* live in a paint callback:

- **chrom / showX filtering** — operates on `gs` before any panel is
  built; pulled out into `filter_genome_size`.
- **facecolor / spine banding** — per-cell background or per-cell spine
  styling, set at chart construction time, outside the paint.
- **yscale** — chart-level state set before any artist call.

Layout — same for both styles:

  each track row is `(c1 | c2 | ... | cN).share_y().touch()` — chroms
  within a track share y; touch overlaps adjacent canvases by
  `2 * margin_floor` so data regions abut exactly. Tracks stack
  vertically with `/`; the outer composition gets `.share_x("col")` so
  the same chrom column shares x across all rows.

Style — only differs in per-cell decoration:

  - **facecolor**: alternating background bands on per-chrom tracks;
    diamond-checkerboard banding inside the SV triangle.
  - **spine**: dotted left spine on inner cells of per-chrom tracks;
    V-shaped boundary marks inside the SV triangle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

import plotlet as pt


# =============================================================================
# Genome-size filter
# =============================================================================

def filter_genome_size(gs, chrom=(), showX=True, chrom_column="chrom"):
    """Filter `gs` by chromosome selection. Empty `chrom` keeps all
    autosomes + chrX (if `showX`); chrY is always dropped unless asked
    for explicitly via `chrom`."""
    if chrom:
        return gs[gs[chrom_column].isin(list(chrom))].reset_index(drop=True)
    drop = {"chrY"} if showX else {"chrX", "chrY"}
    return gs[~gs[chrom_column].isin(drop)].reset_index(drop=True)


# =============================================================================
# Tracks
# =============================================================================

@dataclass
class Track:
    """A per-chromosome track.

    `paint(chart, sub_df) -> None` draws into one chrom's chart. The
    callback owns the data drawing. Highlight regions are framework-
    level so every track in a figure can share the same `highlight_df`
    without repeating axvspan boilerplate in each paint callback."""
    data: Any
    paint: Callable
    ylabel: str | None = None
    ylim: tuple | None = None
    yscale: str = "linear"          # "linear" or "log"
    height: int = 60
    highlight_df: Any | None = None
    highlight_color: str = "grey"
    highlight_alpha: float = 0.3


@dataclass
class SVTriangleTrack:
    """Triangle plot for structural variants in BEDPE-like format.

    Each SV row contributes one point at `(display_x, display_y)` where
    `display_x = (pos1 + pos2) / 2` (linear genome midpoint) and
    `display_y = |pos1 - pos2| / 2` (half the span). Intra- and inter-
    chromosomal SVs are treated identically. The triangle border is
    `(0,0) - (L,0) - (L/2, L/2)` with L the total genome length in view.

    Both breakpoints are converted to interval midpoints in linear
    genome coordinates using `gs` to compute per-chrom offsets."""
    data: Any
    chrom1_col: str = "chrom1"
    start1_col: str = "start1"
    end1_col:   str = "end1"
    chrom2_col: str = "chrom2"
    start2_col: str = "start2"
    end2_col:   str = "end2"
    s: float = 8
    alpha: float = 0.6
    color: str = "steelblue"
    ylabel: str | None = "SV span"
    highlight_df: Any | None = None
    highlight_color: str = "grey"
    highlight_alpha: float = 0.3


# =============================================================================
# Per-chrom track row
# =============================================================================

# Two-tone band for facecolor style. Light grey on every other chrom —
# matches omicsplot's default and reads as "alternating columns" without
# fighting the data.
_FACECOLOR_EVEN = "white"
_FACECOLOR_ODD  = "#f0f0f0"

# Inner-spine style for spine mode. Dotted grey, thin — visible without
# competing with the data line.
_SPINE_LINESTYLE = "dotted"
_SPINE_COLOR     = "#bbbbbb"


def _build_track_row(track, gs, panel_widths, *, height, style, theme,
                     chrom_column):
    """Build one per-chrom row for a `Track`. Returns the composed row.

    Every cell carries the chrom name as xlabel and clears x-tick marks
    with `xticks([])` — `share_x("col")`'s joined-pair auto-hides xlabels
    on non-bottom rows, so the chrom name renders only at the bottom of
    the figure while tick marks stay suppressed everywhere."""
    chroms  = gs[chrom_column].tolist()
    lengths = gs["length"].tolist()
    per_chrom = {k: sub for k, sub in track.data.groupby(chrom_column)}

    cells = []
    for i, (cname, w, length) in enumerate(zip(chroms, panel_widths, lengths)):
        fc = (_FACECOLOR_EVEN if i % 2 == 0 else _FACECOLOR_ODD) \
            if style == "facecolor" else None
        c = pt.chart(data_width=w, data_height=height, facecolor=fc)
        if theme is not None:
            c.theme(theme)
        # Drop top/right always; for inner cells, suppress the left spine
        # (facecolor mode) or restyle it as a dotted separator (spine mode).
        # plotlet's share_y hide_left only hides labels, not the spine —
        # without an explicit override, touch() would render every cell's
        # left spine at the chrom boundary as a solid black line.
        c.spines(top=False, right=False)
        if i > 0:
            if style == "spine":
                c.spines(left={"color": _SPINE_COLOR, "linestyle": _SPINE_LINESTYLE})
            else:
                c.spines(left=False)
        c.xlim(0, length)
        if track.ylim is not None:
            c.ylim(*track.ylim)
        if track.yscale != "linear":
            c.yscale(track.yscale)
        # share_y is applied to the row below — hide_left on cells i > 0
        # then auto-suppresses the ylabel and ytick labels there. We still
        # *set* ylabel on every cell so the anchor (cell 0) picks it up.
        if track.ylabel is not None:
            c.ylabel(track.ylabel)
        # Chrom name as xlabel on every cell — share_x("col") suppresses
        # all but the bottom-most row. Tick marks off everywhere.
        c.xlabel(cname.replace("chr", ""))
        c.xticks([])
        # Highlights in the background layer so the paint's data lines
        # draw on top of them.
        if track.highlight_df is not None:
            h_chrom = track.highlight_df[track.highlight_df[chrom_column] == cname]
            for _, h in h_chrom.iterrows():
                c.axvspan(h["start"], h["end"],
                          color=track.highlight_color, alpha=track.highlight_alpha)
        sub = per_chrom.get(cname, track.data.iloc[0:0])
        if not sub.empty:
            track.paint(c, sub)
        cells.append(c)

    row = cells[0]
    for c in cells[1:]:
        row = row | c
    # share_y + touch — keeps inner ylabel/tick-label suppression,
    # collapses floor margins between cells. plotlet's `hide_left` from
    # share_y only hides labels, not the spine itself; the per-cell
    # `c.spines(left={...})` override above in spine mode still renders
    # the dotted boundary line at the now-coincident edge.
    row.share_y().touch()
    return row


# =============================================================================
# SV triangle row
# =============================================================================

def _build_offsets(gs, chrom_column="chrom"):
    """Per-chrom linear offsets and the total length. Offsets are the
    cumulative sum of preceding chrom lengths (chrom i starts at
    sum(lengths[:i]))."""
    lengths = gs["length"].to_numpy()
    cum = np.concatenate([[0], np.cumsum(lengths)])
    return dict(zip(gs[chrom_column], cum[:-1])), int(cum[-1])


def _to_linear(chrom_vals, start_vals, end_vals, offsets):
    """Interval midpoint in linear genome coords; None for off-genome rows."""
    return [offsets[c] + (s + e) / 2 if c in offsets else None
            for c, s, e in zip(chrom_vals, start_vals, end_vals)]


def _build_sv_row(sv, gs, panel_widths, *, theme, chrom_column, style):
    """Build the SV triangle as a row of N per-chrom slice charts.

    Each slice carries `xlim(0, chrom_length[i])` — same as the per-chrom
    tracks — so the row joins `share_x("col")` naturally and aligns with
    the per-chrom rows. All slices share `ylim(0, total_len/2)` and the
    same `data_height` (= total_data_width / 2) so the triangle's 45°
    edges render true across the merged frame.

    Geometry that spans multiple chroms (diamond cells, triangle edges,
    highlight strips, scatter) is drawn in every slice using its own
    local coordinates (linear position minus the slice's chrom offset).
    plotlet's default `clip=True` crops the out-of-slice portions, so
    each slice ends up showing only the part that visually falls in its
    column. A quick-reject check skips geometry entirely outside the
    slice — pure perf, no visual effect."""
    offsets, total_len = _build_offsets(gs, chrom_column)
    chroms  = gs[chrom_column].tolist()
    lengths = gs["length"].tolist()

    # Triangle data points: dx in [0, L], dy in [0, L/2]
    pos1 = _to_linear(sv.data[sv.chrom1_col],
                      sv.data[sv.start1_col], sv.data[sv.end1_col], offsets)
    pos2 = _to_linear(sv.data[sv.chrom2_col],
                      sv.data[sv.start2_col], sv.data[sv.end2_col], offsets)
    valid = [(p, q) for p, q in zip(pos1, pos2) if p is not None and q is not None]
    if valid:
        p1, p2 = np.array(valid).T
        dx_lin = (p1 + p2) / 2
        dy_lin = np.abs(p1 - p2) / 2
    else:
        dx_lin = np.array([]); dy_lin = np.array([])

    boundaries = [0]
    for L_i in lengths:
        boundaries.append(boundaries[-1] + L_i)
    L = total_len
    sv_height = sum(panel_widths) / 2          # 2:1 aspect across the merged frame
    n = len(gs)

    cells = []
    for i, (cname, w, length) in enumerate(zip(chroms, panel_widths, lengths)):
        Bi0 = boundaries[i]
        Bi1 = Bi0 + length
        # Quick-reject helper: any vertex inside this slice's linear x range?
        def inside(xs):
            return min(xs) <= Bi1 and max(xs) >= Bi0

        c = pt.chart(data_width=w, data_height=sv_height,
                     xlim=(0, length), ylim=(0, L / 2))
        if theme is not None:
            c.theme(theme)
        c.spines(top=False, right=False, bottom=False, left=False)
        c.xticks([])
        c.yticks([])
        if i == 0 and sv.ylabel:
            c.ylabel(sv.ylabel)

        # --- Banding inside the triangle ---
        if style == "facecolor":
            # Diamond checkerboard from omicsplot: each (a, b) chrom pair
            # gets its own cell, colored by (a+b)%2. Same-chrom diamonds
            # (a==b) are triangles on the bottom edge; off-diagonals are
            # parallelograms floating above. We draw every diamond in
            # every slice; the slice's rectangular clip crops the rest.
            for a in range(n):
                for b in range(a, n):
                    Ba0, Ba1 = boundaries[a], boundaries[a + 1]
                    Bb0, Bb1 = boundaries[b], boundaries[b + 1]
                    fc = _FACECOLOR_EVEN if (a + b) % 2 == 0 else _FACECOLOR_ODD
                    if a == b:
                        xs = [Ba0, (Ba0 + Ba1) / 2, Ba1]
                        ys = [0,   (Ba1 - Ba0) / 2, 0]
                    else:
                        xs = [(Ba0 + Bb0) / 2, (Ba1 + Bb0) / 2,
                              (Ba1 + Bb1) / 2, (Ba0 + Bb1) / 2]
                        ys = [(Bb0 - Ba0) / 2, (Bb0 - Ba1) / 2,
                              (Bb1 - Ba1) / 2, (Bb1 - Ba0) / 2]
                    if not inside(xs):
                        continue
                    c.polygon([x - Bi0 for x in xs], ys,
                              color=fc, edgecolor="none")
        elif style == "spine":
            # V-shape at each inner chrom boundary.
            for col_idx in range(1, n):
                B = boundaries[col_idx]
                xs = [B / 2, B, (L + B) / 2]
                ys = [B / 2, 0, (L - B) / 2]
                if not inside(xs):
                    continue
                c.polyline([x - Bi0 for x in xs], ys,
                           color=_SPINE_COLOR, linestyle=_SPINE_LINESTYLE,
                           linewidth=0.5)

        # --- Highlights: two diagonal strips per region, clipped to triangle ---
        if sv.highlight_df is not None:
            for _, h in sv.highlight_df.iterrows():
                if h["chrom"] not in offsets:
                    continue
                a = offsets[h["chrom"]] + h["start"]
                b = offsets[h["chrom"]] + h["end"]
                for xs, ys in [
                    # 45° strip: clipped at the triangle's right edge `y = L - x`.
                    ([a, b, (L + b) / 2, (L + a) / 2],
                     [0, 0, (L - b) / 2, (L - a) / 2]),
                    # 135° strip: clipped at the triangle's left edge `y = x`.
                    ([a, b, b / 2, a / 2],
                     [0, 0, b / 2, a / 2]),
                ]:
                    if not inside(xs):
                        continue
                    c.polygon([x - Bi0 for x in xs], ys,
                              color=sv.highlight_color, alpha=sv.highlight_alpha,
                              edgecolor="none")

        # --- Triangle border (lines clipped by slice rectangle) ---
        c.polyline([0, length],            [0, 0],     color="black", linewidth=1.0)  # bottom
        c.polyline([-Bi0, L / 2 - Bi0],    [0, L / 2], color="black", linewidth=1.0)  # left edge
        c.polyline([L - Bi0, L / 2 - Bi0], [0, L / 2], color="black", linewidth=1.0)  # right edge

        # --- Scatter (only points whose midpoint falls in this slice) ---
        if len(dx_lin):
            mask = (dx_lin >= Bi0) & (dx_lin < Bi1)
            if mask.any():
                c.scatter(data={"x": (dx_lin[mask] - Bi0).tolist(),
                                "y": dy_lin[mask].tolist()},
                          x="x", y="y",
                          color=sv.color, alpha=sv.alpha, s=sv.s)

        # --- Boundary tick: small notch at every inner right edge ---
        # Drawn just inside the data area (clip=True crops below y=0).
        if i < n - 1:
            c.vlines([length], [0], [(L / 2) * 0.012],
                     color="black", linewidth=0.6)

        # --- Chrom name labels ---
        # Bottom: via xlabel; share_x("col") hides it when per-chrom rows
        # below own the bottom of the share class.
        c.xlabel(cname.replace("chr", ""))
        # Left edge at 45°: matches omicsplot's `chrom_label_side='both'`.
        # The full triangle's left edge is `y = x_linear`; each chrom's
        # midpoint maps to (t_mid/2, t_mid/2) on that edge. That point
        # usually falls in another slice's x range, but `text` is in the
        # foreground layer (not data-clipped) and slices abut via touch(),
        # so pixel positions stay continuous across slices.
        t_mid = Bi0 + length / 2
        offs  = 6 / math.sqrt(2)        # 6 px perpendicular to the edge
        c.annotate(cname.replace("chr", ""),
                   xy=(t_mid / 2 - Bi0, t_mid / 2),
                   ha="center", va="center", rotation=45,
                   dx=-offs, dy=-offs)

        cells.append(c)

    row = cells[0]
    for c in cells[1:]:
        row = row | c
    row.share_y().touch()
    return row


# =============================================================================
# Public entry point
# =============================================================================

def plot_tracks(tracks, gs, *, width=600, track_height=None, gap=8,
                chrom=(), showX=True, chrom_column="chrom",
                style="facecolor", theme=None):
    """Compose a multi-track genome figure.

    Parameters
    ----------
    tracks : list of Track | SVTriangleTrack
    gs : DataFrame with chrom_column + 'length'
    width : total data-area width across all chroms (px)
    track_height : optional uniform per-track height; falls back to each
        Track's own `.height`
    gap : pixels between stacked tracks
    chrom, showX : filter passed to `filter_genome_size`
    style : 'facecolor' (alternating bg bands + diamond banding in SV) or
        'spine' (dotted boundary spines + V-marks in SV)
    theme : pre-registered theme name applied to every leaf chart
    """
    gs = filter_genome_size(gs, chrom, showX, chrom_column)
    lengths = gs["length"].tolist()
    total = sum(lengths)
    panel_widths = [L / total * width for L in lengths]

    # Build each track's h-row (per-chrom panels OR SV slices). SV rows
    # render at the top — they own the chrom labeling, and stacking them
    # above means the chrom labels sit right under the triangle baseline,
    # next to the per-chrom tracks. Every row is an h-layout with N cells,
    # so the outer `share_x("col")` aligns the same chrom column across
    # all rows.
    sv_rows, track_rows = [], []
    for t in tracks:
        if isinstance(t, Track):
            h = track_height if track_height is not None else t.height
            track_rows.append(_build_track_row(
                t, gs, panel_widths,
                height=h, style=style, theme=theme,
                chrom_column=chrom_column,
            ))
        elif isinstance(t, SVTriangleTrack):
            sv_rows.append(_build_sv_row(
                t, gs, panel_widths,
                theme=theme, chrom_column=chrom_column, style=style,
            ))
        else:
            raise TypeError(f"unknown track type: {type(t).__name__}")

    rows = sv_rows + track_rows
    if not rows:
        raise ValueError("no tracks given")

    fig = rows[0]
    for row in rows[1:]:
        fig = fig / row
    if len(rows) > 1:
        fig.share_x("col").gap(gap)
    return fig
