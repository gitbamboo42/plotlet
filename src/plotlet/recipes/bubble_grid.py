"""Custom artist: bubble grid (dot matrix).

Categorical x × categorical y grid of dots, where each dot's *size* and
*color* encode two values for that cell. Used heavily in genomics (gene
expression heatmaps with significance encoded as size) and survey
results (proportion + count).

API: c.bubble_grid(x_cats, y_cats, size_matrix, color_matrix=None,
                   cmap="viridis", smax=12).
- `size_matrix[i][j]`  -> size value for x_cats[j], y_cats[i].
- `color_matrix[i][j]` -> color value (same shape). Defaults to size.
- `smax`               -> max dot radius in pixels.
"""

SUMMARY = 'Categorical dot matrix encoding two values per cell (size + color).'
from pathlib import Path

import plotlet as pt
from plotlet.draw import circle
from plotlet.utils import to_list, to_list_2d
from plotlet.draw.colormaps import colormap, _ContinuousNorm
from plotlet._spec import _D


def bubble_record(args, kw):
    x_cats = to_list(args[0])
    y_cats = to_list(args[1])
    size_m = to_list_2d(args[2])
    color_m = to_list_2d(args[3]) if len(args) > 3 and args[3] is not None else size_m
    return {"type": "bubble_grid", "x_cats": x_cats, "y_cats": y_cats,
            "size_m": size_m, "color_m": color_m, "opts": kw}


def bubble_xdomain(a): return a["x_cats"]
def bubble_ydomain(a): return a["y_cats"]


def bubble_draw(a, ctx):
    cmap = colormap(a["opts"].get("cmap", _D["default_cmap"]))
    smax = a["opts"].get("smax", 12)
    flat_s = [v for row in a["size_m"] for v in row if v == v]
    flat_c = [v for row in a["color_m"] for v in row if v == v]
    s_lo = min(flat_s) if flat_s else 0
    s_hi = max(flat_s) if flat_s else 1
    c_lo = a["opts"].get("vmin", min(flat_c) if flat_c else 0.0)
    c_hi = a["opts"].get("vmax", max(flat_c) if flat_c else 1.0)
    cnorm = _ContinuousNorm(c_lo, c_hi, "linear")
    out = []
    for i, y in enumerate(a["y_cats"]):
        for j, x in enumerate(a["x_cats"]):
            sv = a["size_m"][i][j]
            cv = a["color_m"][i][j]
            if sv != sv or cv != cv:
                continue
            r_frac = 0 if s_hi == s_lo else (sv - s_lo) / (s_hi - s_lo)
            r = max(1.0, r_frac * smax)
            rgb = cmap(cnorm.to_unit(cv))
            fill = f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
            cx = ctx.x_scale(x); cy = ctx.y_scale(y)
            out.append(circle(cx, cy, r, fill=fill))
    return "".join(out)


def bubble_legend_gradient(a):
    flat = [v for row in a["color_m"] for v in row if v == v]
    return {"kind": "continuous",
            "cmap": a["opts"].get("cmap", _D["default_cmap"]),
            "vmin": a["opts"].get("vmin", min(flat) if flat else 0.0),
            "vmax": a["opts"].get("vmax", max(flat) if flat else 1.0),
            "norm": "linear"}


pt.add_artist(pt.ArtistSpec(
    name="bubble_grid",
    record=bubble_record,
    xdomain=bubble_xdomain,
    ydomain=bubble_ydomain,
    draw=bubble_draw,
    uses_color_cycle=False,
    legend_gradient=bubble_legend_gradient,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import math
    genes = ["GAPDH", "ACTB", "TP53", "BRCA1", "MYC", "EGFR"]
    samples = ["control", "drug A", "drug B", "drug C"]
    size_m = [[abs(math.sin(i * 0.7 + j)) * 10 + 1 for j in range(len(samples))]
              for i in range(len(genes))]
    color_m = [[math.cos(i + j * 0.5) for j in range(len(samples))]
               for i in range(len(genes))]
    c = pt.chart(data_width=240, data_height=300)
    c.xscale("category", order=samples)
    c.yscale("category", order=genes)
    c.bubble_grid(samples, genes, size_m, color_m, cmap="RdBu_r", vmin=-1, vmax=1)
    c.title("Expression × significance")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
