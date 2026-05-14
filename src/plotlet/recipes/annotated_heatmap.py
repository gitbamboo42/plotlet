"""Custom artist: annotated heatmap.

A heatmap with per-cell text labels — the staple of correlation matrices,
confusion matrices, and ComplexHeatmap-style annotated grids. The cells
themselves are emitted via plotlet's built-in `imshow`; this recipe adds
just the per-cell text overlay, registered as its own artist so call
order is "imshow first, annotations on top".

API:
    c.imshow(matrix, cmap="RdBu_r")
    c.cell_text(matrix, fmt="{:.2f}", color="auto")

`color="auto"` picks white text on dark cells, black on light, using the
cell's luminance after the colormap is applied.
"""

SUMMARY = 'Per-cell text overlay on imshow; auto-picks black/white text by luminance.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list_2d
from plotlet.draw.colormaps import colormap, _ContinuousNorm
from plotlet._spec import _D
from plotlet.draw import text_path


def cell_text_record(args, kw):
    d = to_list_2d(args[0])
    return {"type": "cell_text", "data": d, "opts": kw}


def cell_text_xdomain(a):  # piggyback on imshow's own domain
    return None


def cell_text_ydomain(a):
    return None


def _luminance(rgb):
    r, g, b = rgb
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def cell_text_draw(a, ctx):
    d = a["data"]
    nrows = len(d); ncols = len(d[0]) if d else 0
    if not nrows:
        return ""
    fmt = a["opts"].get("fmt", "{:.2f}")
    color_opt = a["opts"].get("color", "auto")
    fontsize = a["opts"].get("fontsize", 10)
    cmap_name = a["opts"].get("cmap", _D["default_cmap"])
    cmap = colormap(cmap_name)
    flat = [v for row in d for v in row if v == v]
    vmin = a["opts"].get("vmin", min(flat) if flat else 0.0)
    vmax = a["opts"].get("vmax", max(flat) if flat else 1.0)
    norm = _ContinuousNorm(vmin, vmax, "linear")
    # imshow's coordinate system: cell (r, c) spans data x∈[c, c+1],
    # y∈[r, r+1] (origin="lower" default — row 0 at the bottom).
    out = []
    for r in range(nrows):
        for c in range(ncols):
            v = d[r][c]
            cx = ctx.x_scale(c + 0.5)
            cy = ctx.y_scale(r + 0.5)
            if color_opt == "auto":
                rgb = cmap(norm.to_unit(v))
                txt_col = "#ffffff" if _luminance(rgb) < 0.55 else "#000000"
            else:
                txt_col = color_opt
            out.append(text_path(fmt.format(v), cx, cy + fontsize / 3,
                                  fontsize, anchor="middle", color=txt_col))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="cell_text",
    record=cell_text_record,
    xdomain=cell_text_xdomain,
    ydomain=cell_text_ydomain,
    draw=cell_text_draw,
    layer="foreground",
    uses_color_cycle=False,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import math
    n = 6
    # Build a symmetric correlation-like matrix.
    matrix = [[math.cos((i - j) * 0.4) for j in range(n)] for i in range(n)]
    c = pt.chart(data_width=300, data_height=300)
    c.imshow(matrix, cmap="RdBu_r", vmin=-1, vmax=1)
    c.cell_text(matrix, fmt="{:+.2f}", cmap="RdBu_r", vmin=-1, vmax=1)
    c.title("Correlation matrix")
    c.xticks([i + 0.5 for i in range(n)], [f"v{i}" for i in range(n)])
    c.yticks([i + 0.5 for i in range(n)], [f"v{i}" for i in range(n)])
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
