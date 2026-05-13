"""Custom artist: hexbin density.

For dense 2-D scatter, hex binning beats overplotting. Each hexagonal cell
counts the points that fall in it; cells are colored by count via a
sequential colormap. Used everywhere a `c.scatter()` would devolve into
a black blob — millions-of-stars Hertzsprung-Russell, single-cell UMAPs,
flow cytometry.

API: c.hexbin(xs, ys, gridsize=30, cmap="viridis").
The gridsize is the number of hex columns across the x range.
"""

SUMMARY = 'Hexagonal density binning for crowded scatter; cells colored by point count.'
import math
from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist
from plotlet.colormaps import colormap, _ContinuousNorm
from plotlet._spec import _D


def hexbin_record(args, kw):
    xs = _to_pylist(args[0]); ys = _to_pylist(args[1])
    gridsize = kw.get("gridsize", 30)
    # Hex grid math: offset every other row by half a hex width. We bin
    # into the *axial* coordinate that minimizes data-point→hex-center
    # distance; the simple "two candidate hex centers per point" trick is
    # standard for hexagonal binning.
    if not xs:
        return {"type": "hexbin", "xs": xs, "ys": ys, "_bins": {}, "opts": kw}
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    dx = (x_hi - x_lo) / gridsize or 1.0
    # Hex aspect ratio: height/width = 2/√3 for pointy-top, √3/2 for flat-top.
    # Plotlet pixels are square in data space (after scale), so we choose
    # flat-top with vertical step = dx * √3 / 2 so cells look reasonably
    # regular when x and y data scales aren't equal.
    dy = dx * math.sqrt(3) / 2
    bins = {}
    for x, y in zip(xs, ys):
        # Two candidate hex centers; pick the closer.
        col = round((x - x_lo) / dx)
        row = round((y - y_lo) / dy)
        # In flat-top hex, every other column is offset by dy/2.
        cx_a = x_lo + col * dx
        cy_a = y_lo + (row + (0.5 if col % 2 else 0)) * dy
        cx_b = x_lo + col * dx
        cy_b = y_lo + (row + 1 + (0.5 if col % 2 else -0.5)) * dy
        # Use the candidate with smaller distance.
        da = (x - cx_a) ** 2 + (y - cy_a) ** 2
        db = (x - cx_b) ** 2 + (y - cy_b) ** 2
        if db < da:
            cx, cy = cx_b, cy_b
        else:
            cx, cy = cx_a, cy_a
        key = (round(cx, 6), round(cy, 6))
        bins[key] = bins.get(key, 0) + 1
    return {"type": "hexbin", "xs": xs, "ys": ys, "_bins": bins,
            "_dx": dx, "_dy": dy, "opts": kw}


def hexbin_xdomain(a): return a["xs"]
def hexbin_ydomain(a): return a["ys"]


def hexbin_draw(a, ctx):
    if not a["_bins"]:
        return ""
    cmap = colormap(a["opts"].get("cmap", _D["default_cmap"]))
    counts = list(a["_bins"].values())
    vmin = a["opts"].get("vmin", 0)
    vmax = a["opts"].get("vmax", max(counts))
    norm = _ContinuousNorm(vmin or 1e-9, vmax or 1.0, "linear")
    out = []
    # Hex vertices for a flat-top hex centered at (0,0) with "radius" r:
    # x-radius = dx/2 + small fudge; y-radius = dy / √3 * something.
    # Simpler: use a regular hexagon inscribed in a circle of radius rx.
    # rx is half the x-step of adjacent same-row hexes (which is dx).
    rx_data = a["_dx"]  # x distance from center to next same-row hex center
    ry_data = a["_dy"] * 2 / 3  # vertical radius (to top/bottom vertex)
    for (cx, cy), n in a["_bins"].items():
        r, g, b = cmap(norm.to_unit(n))
        fill = f"rgb({r},{g},{b})"
        # Compute pixel hex vertices.
        center_px_x = ctx.x_scale(cx)
        center_px_y = ctx.y_scale(cy)
        # x scale per data unit
        sx = abs(ctx.x_scale(cx + 1) - ctx.x_scale(cx))
        sy = abs(ctx.y_scale(cy + 1) - ctx.y_scale(cy))
        # Flat-top hex: vertices at angles 0, 60, 120, 180, 240, 300.
        verts = []
        for k in range(6):
            angle = math.pi / 3 * k
            vx = center_px_x + math.cos(angle) * (rx_data / 2 * sx)
            vy = center_px_y + math.sin(angle) * (ry_data * sy)
            verts.append((vx, vy))
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in verts) + " Z"
        out.append(f'<path d="{d}" fill="{fill}"/>')
    return "".join(out)


def hexbin_legend_gradient(a):
    counts = list(a["_bins"].values()) if a["_bins"] else [0, 1]
    return {"kind": "continuous",
            "cmap": a["opts"].get("cmap", _D["default_cmap"]),
            "vmin": a["opts"].get("vmin", 0),
            "vmax": a["opts"].get("vmax", max(counts) if counts else 1),
            "norm": "linear", "label": "count"}


pt.add_artist(pt.ArtistSpec(
    name="hexbin",
    record=hexbin_record,
    xdomain=hexbin_xdomain,
    ydomain=hexbin_ydomain,
    draw=hexbin_draw,
    uses_color_cycle=False,
    legend_gradient=hexbin_legend_gradient,
))


if __name__ == "__main__":
    import random
    random.seed(3)
    n = 5000
    xs = [random.gauss(0, 1) + random.gauss(0, 0.4) for _ in range(n)]
    ys = [x + random.gauss(0, 1) for x in xs]
    c = pt.chart()
    c.hexbin(xs, ys, gridsize=28)
    c.title("Hexbin density").xlabel("x").ylabel("y")
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
