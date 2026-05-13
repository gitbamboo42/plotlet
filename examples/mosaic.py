"""Custom artist: mosaic plot.

For a 2-D contingency table over two categorical variables. The plot
area is split vertically by the marginal proportions of the row
variable; each row-strip is then split horizontally by the *conditional*
proportions of the column variable given that row. Cell area = joint
count, cell width = conditional column proportion, cell height = marginal
row proportion. Standing in for what `mosaicplot` does in R.

Useful for spotting deviation from independence at a glance: under
independence, all rows have the same horizontal split.

API:
    c.mosaic(table, row_names, col_names, cmap=None,
             color_by="row")

`table[i][j]` is the count of (row_i, col_j). `color_by="row"` colors
strips by row; `"col"` re-colors per cell by column.
"""

SUMMARY = "Contingency-table proportional rectangles: row × col area = joint count, splits show conditional rates."

from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_2d_pylist
from plotlet.font import _text_path


_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


def mosaic_record(args, kw):
    table = _to_2d_pylist(args[0])
    row_names = list(args[1])
    col_names = list(args[2])
    return {"type": "mosaic", "table": table,
            "row_names": row_names, "col_names": col_names, "opts": kw}


def mosaic_xdomain(a): return [0, 1]
def mosaic_ydomain(a): return [0, 1]


def mosaic_draw(a, ctx):
    table = a["table"]
    nr = len(table); nc = len(table[0]) if table else 0
    if nr == 0 or nc == 0:
        return ""
    color_by = a["opts"].get("color_by", "row")
    pad = a["opts"].get("pad", 0.005)
    row_totals = [sum(row) for row in table]
    total = sum(row_totals) or 1
    out = []
    # Walk rows top-to-bottom.
    y = 0.0
    for i in range(nr):
        rh = row_totals[i] / total
        x = 0.0
        for j in range(nc):
            cw = (table[i][j] / row_totals[i]) if row_totals[i] else 0
            col_idx = i if color_by == "row" else j
            fill = _PALETTE[col_idx % len(_PALETTE)]
            x0 = ctx.x_scale(x + pad / 2)
            y0 = ctx.y_scale(1 - (y + rh) + pad / 2)
            x1 = ctx.x_scale(x + cw - pad / 2)
            y1 = ctx.y_scale(1 - y - pad / 2)
            out.append(
                f'<rect x="{x0:.2f}" y="{y0:.2f}" '
                f'width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" '
                f'fill="{fill}" fill-opacity="0.65" stroke="white" stroke-width="0.6"/>'
            )
            # Annotate cell with count if it's big enough to fit.
            if (x1 - x0) > 30 and (y1 - y0) > 14:
                out.append(_text_path(str(table[i][j]),
                                       (x0 + x1) / 2, (y0 + y1) / 2 + 3,
                                       10, anchor="middle", color="#222"))
            x += cw
        y += rh
    # Row labels on the left, column labels along the top.
    y = 0.0
    for i, name in enumerate(a["row_names"]):
        rh = row_totals[i] / total
        py = ctx.y_scale(1 - y - rh / 2) + 3
        out.append(_text_path(name, ctx.x_scale(0) - 4, py, 10, anchor="end"))
        y += rh
    # Column labels — placed above the first row, anchored at conditional
    # midpoint within that row.
    if row_totals[0]:
        x = 0.0
        py = ctx.y_scale(1.0) - 6
        for j, name in enumerate(a["col_names"]):
            cw = table[0][j] / row_totals[0]
            px = ctx.x_scale(x + cw / 2)
            out.append(_text_path(name, px, py, 10, anchor="middle"))
            x += cw
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="mosaic",
    record=mosaic_record,
    xdomain=mosaic_xdomain,
    ydomain=mosaic_ydomain,
    draw=mosaic_draw,
    uses_color_cycle=False,
    tight_domain=True,
))


if __name__ == "__main__":
    # Titanic-style: survived vs class.
    classes = ["1st", "2nd", "3rd", "crew"]
    outcomes = ["survived", "died"]
    table = [
        [203, 122],   # 1st: surv, died
        [118, 167],   # 2nd
        [178, 528],   # 3rd
        [212, 673],   # crew
    ]
    c = pt.chart(data_width=440, data_height=300)
    c.mosaic(table, classes, outcomes, color_by="col")
    c.xticks([]); c.yticks([])
    c.title("Titanic survival × class")
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
