"""Stacked, length-weighted genome figure built on `c.sectors()`.

Each ``Track`` is a single chart spanning the full genome;
``c.sectors(...)`` declares the per-chrom partition so any artist that
carries the ``chrom`` column gets its x values auto-remapped into global
genome coords. Tracks stack vertically with ``/``, ``share_x()`` aligns
their x-domains, ``.gap(...)`` controls inter-track spacing.

This is a cookbook recipe — patterns to copy, not a configurable product.
Most styling decisions (highlights, palettes, fancy chrome) belong in the
paint callback. The few framework-level features here are things that
*can't* live in a paint callback:

- **chrom / showX filtering** — operates on ``gs`` before sectors get
  built.
- **facecolor / spine / gap banding** — per-sector backgrounds
  (facecolor), per-sector divider styling (spine), or empty pixel pad
  between sectors (gap), set at chart construction time outside the
  paint.
- **yscale** — chart-level state set before any artist call.

Style — only differs in per-sector decoration on the track rows:

- **facecolor**: alternating axvspan bands on each track.
- **spine**: dotted sector dividers via the ``divider={"linestyle":
  "dotted", ...}`` chrome.
- **gap**: empty pixel pad between sectors — the gap *is* the separator,
  no dividers / banding. ``c.sectors(..., gap=N)`` (px) routes through
  the new ``_SectoredLinearScale``, same unit as the categorical heatmap
  path so gaps align visually across mixed-scale tracks.
- **boxed**: gap mode with all four spines on per sector — each chrom
  reads as a fully-bounded mini-subplot. Per-sector spines are automatic
  whenever a sectored scale is active; "boxed" just keeps top + right
  enabled (gap drops them L-frame style).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

import plotlet as pt


# =============================================================================
# Genome-size filter
# =============================================================================

def filter_genome_size(gs, chrom=(), showX=True, chrom_column="chrom"):
    """Filter ``gs`` by chromosome selection. Empty ``chrom`` keeps all
    autosomes + chrX (if ``showX``); chrY is always dropped unless asked
    for explicitly via ``chrom``."""
    if chrom:
        return gs[gs[chrom_column].isin(list(chrom))].reset_index(drop=True)
    drop = {"chrY"} if showX else {"chrX", "chrY"}
    return gs[~gs[chrom_column].isin(drop)].reset_index(drop=True)


# =============================================================================
# Tracks
# =============================================================================

@dataclass
class Track:
    """A genome-wide track.

    ``paint(chart, df, offsets) -> None`` draws into the chart with the
    full DataFrame. For ``data=`` artists the ``chrom`` column drives the
    sector remap automatically; for positional artists (``hlines``,
    ``axvspan``) the painter precomputes global coords from ``offsets``.
    """
    data: Any
    paint: Callable
    ylabel: str | None = None
    ylim: tuple | None = None
    yscale: str = "linear"
    height: int = 60
    highlight_df: Any | None = None
    highlight_color: str = "pink"
    highlight_alpha: float = 0.3


# =============================================================================
# Constants
# =============================================================================

# Alternating per-chrom band colors — matches omicsplot's "alternating
# columns" look without fighting the data. The odd band sits at ~20%
# darker than white — solidly visible without competing with the data.
_FACECOLOR_EVEN = "white"
_FACECOLOR_ODD  = "#cccccc"

# Spine-mode divider: dotted grey at standard frame width. "3,1" gives
# 3 px on / 1 px off — reads as a near-solid line with subtle breaks,
# visible at thin strokes. The default ":" linestyle (1,3) is too sparse
# to see at width 1.
_SPINE_DIVIDER = {"dasharray": "3,1", "color": "#000000", "linewidth": 1.0}


# =============================================================================
# Sector helpers
# =============================================================================

def _genome_dict(gs, chrom_column):
    """``{chrom: length}`` mapping in row order — feeds ``c.sectors(...)``."""
    return dict(zip(gs[chrom_column], gs["length"].astype(float)))


def _genome_offsets(gs, chrom_column):
    """``{chrom: offset}`` + total length, in **data coords** (no gap).

    Sector chrome and gaps are scale-level — the linear x_scale knows
    about ``sector_gap_px`` and inserts pixels between sectors. Painter
    offsets stay in the no-gap data domain so positional artists
    (``hlines``, ``axvspan`` for highlights) work the same as the
    sectors auto-remap."""
    lengths = gs["length"].astype(float).to_numpy()
    cum = np.concatenate([[0.0], np.cumsum(lengths)])
    return dict(zip(gs[chrom_column], cum[:-1])), float(cum[-1])


# =============================================================================
# Per-chrom track chart
# =============================================================================

def _build_track_chart(track, gs, *, total_width, height, style, theme,
                       chrom_column, gap_size):
    """Build one Track as a single genome-wide chart.

    Sectors declare the chrom partition; the paint callback writes
    artists with the full DataFrame and the chrom column rides along for
    ``_sector_remap_data``. Background banding (facecolor mode) draws
    axvspans per sector before the paint runs."""
    spec = _genome_dict(gs, chrom_column)
    offsets, _ = _genome_offsets(gs, chrom_column)
    chroms  = gs[chrom_column].tolist()
    lengths = gs["length"].astype(float).tolist()

    c = pt.chart(data_width=total_width, data_height=height)
    if theme is not None:
        c.theme(theme)
    # `boxed` style enables all four spines so each sector reads as a
    # fully-bounded mini-subplot (overrides the L-frame default the demo
    # theme sets via `frame.spine_top` / `frame.spine_right`). Other
    # styles enforce the L-frame regardless of theme.
    if style == "boxed":
        c.spines(top=True, right=True, bottom=True, left=True)
    else:
        c.spines(top=False, right=False)
    if track.ylim is not None:
        c.ylim(*track.ylim)
    if track.yscale != "linear":
        c.yscale(track.yscale)
    if track.ylabel is not None:
        c.ylabel(track.ylabel)
    # Tick marks off; sector labels (chrom names) own the x chrome.
    c.xticks([])

    # Divider chrome: dotted in spine mode, off otherwise. Sector labels
    # stay on — `share_x()` auto-hides them on non-bottom rows.
    divider = _SPINE_DIVIDER if style == "spine" else False
    sector_kw = {"column": chrom_column, "divider": divider}
    if style in ("gap", "boxed"):
        sector_kw["gap"] = gap_size  # pixels
    c.sectors(spec, **sector_kw)

    # facecolor banding via per-sector axvspans (background layer); spine
    # and gap modes skip this. alpha=0.5 overrides axvspan's default 0.2
    # so the bands are clearly readable while still sitting behind the
    # data marks (not competing with them).
    if style == "facecolor":
        for i, (cname, L_i) in enumerate(zip(chroms, lengths)):
            color = _FACECOLOR_EVEN if i % 2 == 0 else _FACECOLOR_ODD
            x0 = offsets[cname]
            c.axvspan(x0, x0 + L_i, color=color, alpha=0.5,
                      edgecolor="none")

    # Highlights: convert per-chrom positions to global data coords. The
    # sectored linear scale handles any inter-sector px gaps visually.
    if track.highlight_df is not None:
        for _, h in track.highlight_df.iterrows():
            if h[chrom_column] not in offsets:
                continue
            off = offsets[h[chrom_column]]
            c.axvspan(off + h["start"], off + h["end"],
                      color=track.highlight_color, alpha=track.highlight_alpha,
                      edgecolor="none")

    # Drop rows whose chrom isn't in the active sector set so the sector
    # remap doesn't choke on filtered-out chroms (chrY when ``showX=True``,
    # custom chrom= subsets, etc.).
    df = track.data
    if chrom_column in df:
        df = df[df[chrom_column].isin(offsets.keys())]
    track.paint(c, df, offsets)
    return c


# =============================================================================
# Public entry point
# =============================================================================

def plot_tracks(tracks, gs, *, width=600, track_height=None, gap=8,
                chrom=(), showX=True, chrom_column="chrom",
                style="facecolor", theme=None, gap_size=None):
    """Compose a multi-track genome figure.

    Parameters
    ----------
    tracks : list of Track
    gs : DataFrame with ``chrom_column`` + 'length'
    width : data-area width across the whole genome (px)
    track_height : optional uniform per-track height; falls back to each
        Track's own ``.height``
    gap : pixels between stacked tracks
    chrom, showX : filter passed to ``filter_genome_size``
    style : 'facecolor' (alternating bg bands), 'spine' (dotted divider
        lines), 'gap' (empty pixel pad, L-frame per sector), or 'boxed'
        (gap pad + all four spines on per sector = mini-subplot look).
    theme : pre-registered theme name applied to every leaf chart
    gap_size : inter-sector pad in **pixels** for ``style`` in
        ``("gap", "boxed")`` — matches the categorical
        ``c.sectors(..., gap=...)`` unit so gaps align visually across
        mixed-scale tracks in the same figure. Defaults to 8 px.
        Ignored for the other styles.
    """
    gs = filter_genome_size(gs, chrom, showX, chrom_column)
    if gap_size is None and style in ("gap", "boxed"):
        gap_size = 8.0

    rows = []
    for t in tracks:
        if not isinstance(t, Track):
            raise TypeError(f"unknown track type: {type(t).__name__}")
        h = track_height if track_height is not None else t.height
        rows.append(_build_track_chart(
            t, gs, total_width=width, height=h, style=style,
            theme=theme, chrom_column=chrom_column,
            gap_size=gap_size or 0.0,
        ))

    if not rows:
        raise ValueError("no tracks given")

    fig = rows[0]
    for row in rows[1:]:
        fig = fig / row
    if len(rows) > 1:
        fig.share_x().gap(gap)
    return fig
