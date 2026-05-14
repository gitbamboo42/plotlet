"""Custom artist: parallel coordinates.

n vertical axes (one per variable), evenly spaced on the x axis. Each
row of data becomes a polyline that connects its values across all
axes. Each axis is independently scaled to [0, 1] so variables on
different scales coexist.

Used everywhere EDA touches more than three numeric columns. ggplot2
doesn't ship it natively; pandas does (`pandas.plotting.parallel_coordinates`).

API:
    c.parallel_coords(rows, var_names, hue=None, alpha=0.6)

`rows`     -> list of rows, each a list of values aligned with `var_names`.
`var_names` -> ordered list of column names.
`hue`      -> optional per-row category vector; same length as `rows`.
              Each unique value gets its own color via the cycle.

Pass `hue` to highlight class membership (the most common use case).
"""

SUMMARY = "Multivariate EDA: vertical axes per variable, one polyline per row, normalized scales."

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import text_path


def parallel_coords_record(args, kw):
    rows = [list(to_list(r)) for r in args[0]]
    var_names = list(args[1])
    return {"type": "parallel_coords", "rows": rows, "var_names": var_names,
            "opts": kw}


def parallel_coords_xdomain(a):
    return [0, len(a["var_names"]) - 1] if a["var_names"] else [0, 1]


def parallel_coords_ydomain(a):
    return [0, 1]


def parallel_coords_draw(a, ctx):
    rows = a["rows"]
    var_names = a["var_names"]
    n_vars = len(var_names)
    if n_vars == 0 or not rows:
        return ""
    # Per-variable min/max for normalization.
    col_lo = [min(row[i] for row in rows) for i in range(n_vars)]
    col_hi = [max(row[i] for row in rows) for i in range(n_vars)]
    span = [h - l if h > l else 1 for l, h in zip(col_lo, col_hi)]
    hue = a["opts"].get("hue")
    alpha = a["opts"].get("alpha", 0.6)
    lw = a["opts"].get("linewidth", 1.0)
    # Color per row.
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
               "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    if hue is not None:
        cats = []
        for h in hue:
            if h not in cats:
                cats.append(h)
        row_colors = [palette[cats.index(h) % len(palette)] for h in hue]
    else:
        row_colors = [ctx.color or palette[0]] * len(rows)
    out = []
    # Polylines.
    for row, rc in zip(rows, row_colors):
        pts = []
        for i, v in enumerate(row):
            frac = (v - col_lo[i]) / span[i]
            pts.append((ctx.x_scale(i), ctx.y_scale(frac)))
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        out.append(
            f'<path d="{d}" fill="none" stroke="{rc}" stroke-width="{lw}" '
            f'opacity="{alpha}"/>'
        )
    # Axes: a thin vertical line at each variable's x, with the variable
    # name at the top and lo/hi labels at the bottom and top.
    y_top = ctx.y_scale(1); y_bot = ctx.y_scale(0)
    for i, name in enumerate(var_names):
        x = ctx.x_scale(i)
        out.append(
            f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y_top:.2f}" y2="{y_bot:.2f}" '
            f'stroke="#888" stroke-width="0.8"/>'
        )
        out.append(text_path(name, x, y_bot + 14, 10, anchor="middle"))
        out.append(text_path(f"{col_hi[i]:.2g}", x + 3, y_top + 4, 8, anchor="start"))
        out.append(text_path(f"{col_lo[i]:.2g}", x + 3, y_bot - 1, 8, anchor="start"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="parallel_coords",
    record=parallel_coords_record,
    xdomain=parallel_coords_xdomain,
    ydomain=parallel_coords_ydomain,
    draw=parallel_coords_draw,
    uses_color_cycle=False,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    var_names = ["sepal_len", "sepal_wid", "petal_len", "petal_wid"]
    rows = []; hue = []
    for cls, base, base_w in [("A", 5.0, 1.4), ("B", 6.0, 4.0), ("C", 6.8, 5.5)]:
        for _ in range(35):
            rows.append([
                base + random.gauss(0, 0.4),
                random.gauss(3, 0.4),
                base_w + random.gauss(0, 0.5),
                base_w * 0.4 + random.gauss(0, 0.2),
            ])
            hue.append(cls)
    c = pt.chart(data_width=520, data_height=260)
    c.parallel_coords(rows, var_names, hue=hue)
    c.xticks([]); c.yticks([])  # labels are drawn inside the artist
    c.title("Parallel coordinates")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
