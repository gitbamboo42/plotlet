"""Stacked, length-weighted facet — coordination layer for plot_tracks.

Lay out per-chrom track panels with widths proportional to `gs.length`,
stacked vertically. Each Track is a (data, paint) pair plus a few
panel fields; the paint callback `(chart, sub_df) -> None` decides
what gets drawn.

This is a cookbook recipe — patterns to copy and modify, not a
configurable product. Things you might want (facecolor banding,
highlights, font customization, chrom filtering) belong in the caller:
in the paint callback, or in pre-processing of `gs` / data, or in a
pre-registered theme. See [genomic_tracks.py](genomic_tracks.py) for
the patterns.

Layout: each track is built as `(c1 | c2 | ... | cN).share_y().touch()`
— chroms within a track share y, inner spines collapse, and the panels
read as one continuous frame. The tracks then stack vertically with `/`,
and the outer composition gets `.share_x("col")` so the same chrom
column shares x across all tracks (xticks suppress on non-bottom rows,
so only the bottom edge of the figure shows them). The outer `.gap(N)`
controls the visual separation between tracks — kept positive on
purpose: tracks are independent measurements, just position-aligned.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Optional

import plotlet as pt


@dataclass
class Track:
    data: Any                              # DataFrame with a chrom column
    paint: Callable                        # (chart, sub_df) -> None
    ylabel: Optional[str] = None
    ylim: Optional[tuple] = None
    height: int = 60


def plot_tracks(tracks, gs, *, width=600, track_height=None,
                gap=8, chrom_column="chrom", theme=None):
    chroms = gs[chrom_column].tolist()
    lengths = gs["length"].tolist()
    total = sum(lengths)
    panel_widths = [L / total * width for L in lengths]

    rows = []
    for track in tracks:
        h = track_height if track_height is not None else track.height
        per_chrom = {k: sub for k, sub in track.data.groupby(chrom_column)}

        cells = []
        for cname, w, length in zip(chroms, panel_widths, lengths):
            c = pt.chart(data_width=w, data_height=h)
            if theme is not None:
                c.theme(theme)
            c.spines(top=False, right=False)
            c.xlim(0, length)
            if track.ylim is not None:
                c.ylim(*track.ylim)
            if track.ylabel is not None:
                c.ylabel(track.ylabel)             # share_y suppresses non-anchor
            c.xlabel(cname.replace("chr", ""))     # share_x("col") suppresses non-bottom rows
            sub = per_chrom.get(cname, track.data.iloc[0:0])
            if not sub.empty:
                track.paint(c, sub)
            cells.append(c)

        # Build the per-track row left-to-right; share_y + touch collapse
        # the inner spines so chroms in the same track read as one frame.
        row = cells[0]
        for c in cells[1:]:
            row = row | c
        row.share_y().touch()
        rows.append(row)

    # Stack the tracks vertically; cross-row column-wise x-sharing aligns
    # the same chrom across all tracks. `.gap(gap)` only applies to this
    # outer layout's children (the rows), so it doesn't fight `.touch()`
    # inside each row.
    fig = rows[0]
    for row in rows[1:]:
        fig = fig / row
    fig.share_x("col").gap(gap)
    return fig
