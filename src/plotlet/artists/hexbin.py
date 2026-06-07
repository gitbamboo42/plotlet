"""Hexagonal density binning for crowded scatter; cells colored by point count.

For dense 2-D scatter, hex binning beats overplotting. Each hexagonal cell
counts the points that fall in it; cells are colored by count via a sequential
colormap. Used wherever a c.scatter() would devolve into a black blob.

Hexagons are sized and binned in pixel space so they always appear as regular
hexagons that tile without gaps regardless of the canvas aspect ratio.

API: c.hexbin(xs, ys)

Styling kwargs:
  gridsize=30    number of hex columns across the canvas width
  cmap='viridis' colormap name for coloring cells by count
  vmin=0         colormap domain lower bound
  vmax=None      colormap domain upper bound (defaults to max count)
"""
from __future__ import annotations

import math

from ..registry import ArtistSpec, add_artist
from ..draw import polygon
from ..draw import colormap, ContinuousNorm
from ..utils import to_list
from .._spec import _D


def _hexbin_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "hexbin requires long-form input: "
            "c.hexbin(data=df, x='col', y='col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    if data is None or x_col is None or y_col is None:
        raise TypeError("hexbin requires data=, x=, y=.")
    xs = to_list(data[x_col])
    ys = to_list(data[y_col])
    # Rough max-count estimate for the legend gradient (4× avg per cell).
    gridsize = kw.get("gridsize", 30)
    n = len(xs)
    rough_max = max(1, n // max(1, gridsize * gridsize // 4))
    return {"type": "hexbin", "xs": xs, "ys": ys,
            "_rough_max": rough_max, "opts": kw}


def _hexbin_xdomain(a): return a["xs"]
def _hexbin_ydomain(a): return a["ys"]


def _hexbin_draw(a, ctx):
    xs = a["xs"]
    ys = a["ys"]
    if not xs:
        return ""

    gridsize = a["opts"].get("gridsize", 30)

    # Flat-top hexagon radius in pixels: gridsize columns → canvas width.
    # Column center-to-center spacing = 3/2 * r, so r = iw / (gridsize * 1.5).
    r_px = ctx.iw / (gridsize * 1.5)
    dx_px = 1.5 * r_px              # horizontal column spacing
    dy_px = r_px * math.sqrt(3)     # vertical row spacing (same column)
    dy_half = dy_px / 2             # alternating-column vertical offset

    # Bin each point into the nearest hex center in pixel space.
    bins: dict[tuple[int, int], int] = {}
    for x, y in zip(xs, ys):
        px = ctx.x_scale(x)
        py = ctx.y_scale(y)
        col0 = round(px / dx_px)
        # Check a 3×3 neighbourhood of candidate columns to find the nearest center.
        best_key = (col0, 0)
        best_d2 = float("inf")
        for cc in range(col0 - 1, col0 + 2):
            off = dy_half if cc % 2 else 0.0
            row0 = round((py - off) / dy_px)
            for rr in range(row0 - 1, row0 + 2):
                hx = cc * dx_px
                hy = off + rr * dy_px
                d2 = (px - hx) ** 2 + (py - hy) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    best_key = (cc, rr)
        bins[best_key] = bins.get(best_key, 0) + 1

    cm = colormap(a["opts"].get("cmap", _D["default_cmap"]))
    counts = list(bins.values())
    vmin = a["opts"].get("vmin", 0)
    vmax = a["opts"].get("vmax", max(counts))
    norm = ContinuousNorm(vmin or 1e-9, vmax or 1.0, "linear")

    out = []
    for (cc, rr), n in bins.items():
        rv, gv, bv = cm(norm.to_unit(n))
        fill = f"rgb({rv},{gv},{bv})"
        off = dy_half if cc % 2 else 0.0
        hx = cc * dx_px
        hy = off + rr * dy_px
        verts = [(hx + math.cos(math.pi / 3 * k) * r_px,
                  hy + math.sin(math.pi / 3 * k) * r_px)
                 for k in range(6)]
        out.append(polygon(verts, fill=fill))
    return "".join(out)


def _hexbin_legend_gradient(a):
    return {"kind": "continuous",
            "cmap": a["opts"].get("cmap", _D["default_cmap"]),
            "vmin": a["opts"].get("vmin", 0),
            "vmax": a["opts"].get("vmax", a["_rough_max"]),
            "norm": "linear", "label": "count"}


add_artist(ArtistSpec(
    name="hexbin",
    accepts_data_positional=True,
    record=_hexbin_record,
    xdomain=_hexbin_xdomain,
    ydomain=_hexbin_ydomain,
    draw=_hexbin_draw,
    uses_color_cycle=False,
    legend_gradient=_hexbin_legend_gradient,
))
