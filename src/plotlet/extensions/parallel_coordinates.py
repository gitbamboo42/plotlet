"""Custom artist: parallel coordinates.

n vertical axes (one per variable), evenly spaced on the x axis. Each
row of data becomes a polyline that connects its values across all
axes. Each axis is independently scaled to [0, 1] so variables on
different scales coexist.

Used everywhere EDA touches more than three numeric columns.

API:
    c.parallel_coords(data=df, vars=["col1", "col2", ...],
                       group="category_col", alpha=0.6)

`vars=`  -> ordered list of column names; each becomes one vertical axis.
`group=` -> optional column of per-row category. Each unique value
            gets its own color via the cycle.

Pass `group` to highlight class membership (the most common use case).
"""

SUMMARY = "Multivariate EDA: vertical axes per variable, one polyline per row, normalized scales."

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import polyline, segment, text_path


def parallel_coords_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "parallel_coords requires long-form input: "
            "c.parallel_coords(data=df, vars=['col1','col2',...], group='col')."
        )
    data = kw.pop("data", None)
    var_names = kw.pop("vars", None)
    if data is None or not var_names:
        raise TypeError("parallel_coords requires data=, vars=[...].")
    var_names = list(var_names)
    cols = [to_list(data[v]) for v in var_names]
    n_rows = len(cols[0]) if cols else 0
    rows = [[cols[c][r] for c in range(len(var_names))] for r in range(n_rows)]
    group_col = kw.pop("group", None)
    if group_col is not None:
        kw["group"] = to_list(data[group_col])
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
    group = a["opts"].get("group")
    alpha = a["opts"].get("alpha", 0.6)
    lw = a["opts"].get("linewidth", 1.0)
    # Color per row.
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
               "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    if group is not None:
        cats = []
        for h in group:
            if h not in cats:
                cats.append(h)
        row_colors = [palette[cats.index(h) % len(palette)] for h in group]
    else:
        row_colors = [ctx.color or palette[0]] * len(rows)
    out = []
    # Polylines.
    for row, rc in zip(rows, row_colors):
        pts = []
        for i, v in enumerate(row):
            frac = (v - col_lo[i]) / span[i]
            pts.append((ctx.x_scale(i), ctx.y_scale(frac)))
        out.append(polyline(pts, color=rc, width=lw, alpha=alpha))
    # Axes: a thin vertical line at each variable's x, with the variable
    # name at the top and lo/hi labels at the bottom and top.
    y_top = ctx.y_scale(1); y_bot = ctx.y_scale(0)
    for i, name in enumerate(var_names):
        x = ctx.x_scale(i)
        out.append(segment(x, y_top, x, y_bot, color="#888", width=0.8))
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
    rows = []
    for cls, base, base_w in [("A", 5.0, 1.4), ("B", 6.0, 4.0), ("C", 6.8, 5.5)]:
        for _ in range(35):
            rows.append({
                "sepal_len": base + random.gauss(0, 0.4),
                "sepal_wid": random.gauss(3, 0.4),
                "petal_len": base_w + random.gauss(0, 0.5),
                "petal_wid": base_w * 0.4 + random.gauss(0, 0.2),
                "class": cls,
            })
    df = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=520, data_height=260)
    c.parallel_coords(df, vars=var_names, group="class")
    c.xticks([]); c.yticks([])  # labels are drawn inside the artist
    c.title("Parallel coordinates")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
