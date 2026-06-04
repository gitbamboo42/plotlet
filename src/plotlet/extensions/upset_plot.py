"""Custom artist: UpSet plot.

For visualizing 4+ overlapping sets where Venn diagrams give up. The
layout is a composite:
  - top:    a bar chart of intersection sizes
  - bottom: a dot matrix where each column is one intersection and rows
            are the sets; a filled dot means "set is included in this
            intersection". Connected dots have a vertical line through them.

UpSet's original layout puts a "set size" panel on the left, too — left
out here to keep the artist focused. The result reads top-to-bottom:
"which intersection?" → "how big?".

API:
    c.upset(set_names, sets, n_top=None)

`sets` is a dict-like `{name: set_of_members}`. The artist computes the
2ⁿ intersections, sorts descending by size, optionally keeps the top
`n_top`, and lays them out as a single composite.
"""

SUMMARY = 'Intersection-size bars over a dot matrix (Venn replacement for 4+ sets).'
from itertools import combinations
from pathlib import Path

import plotlet as pt
from plotlet.draw import text_path, rect, segment, circle


def upset_record(args, kw):
    names = list(args[0])
    sets = {n: set(args[1][n]) for n in names}
    universe = set().union(*sets.values()) if sets else set()
    # Compute intersection sizes: for every non-empty subset of names.
    intersections = []
    for k in range(1, len(names) + 1):
        for combo in combinations(names, k):
            inc = set.intersection(*[sets[n] for n in combo])
            excl = set.union(*[sets[n] for n in names if n not in combo]) if (
                len(combo) < len(names)) else set()
            members = inc - excl
            if members:
                intersections.append((set(combo), len(members)))
    intersections.sort(key=lambda x: -x[1])
    n_top = kw.get("n_top")
    if n_top:
        intersections = intersections[:n_top]
    return {"type": "upset", "_names": names, "_inter": intersections,
            "opts": kw}


def upset_xdomain(a):
    # Use column indices as x; left pad reserves room for set-name labels
    # so they don't get clipped by the data-area overflow:hidden.
    return [-0.5 - _LABEL_PAD, max(0, len(a["_inter"]) - 0.5)]


_LABEL_PAD = 2.5  # in data-unit columns; ~90 px for typical bar widths


# Matrix region's share of vertical space. Fixed (not n_sets-dependent) so
# row spacing stays scale-invariant: when bars are tall, the matrix doesn't
# get squashed into a few pixels and dots stop overlapping.
_MATRIX_FRACTION = 0.42


def _matrix_data_height(a):
    # Data-unit height of the dot-matrix region, sized so it occupies
    # _MATRIX_FRACTION of the total y-domain.
    max_size = max((s for _, s in a["_inter"]), default=1)
    return max_size * 1.1 * _MATRIX_FRACTION / (1 - _MATRIX_FRACTION)


def _row_y(a, j):
    # Y-data position of dot row j (0-indexed), evenly spaced within matrix region.
    return -_matrix_data_height(a) * (j + 1) / (len(a["_names"]) + 1)


def upset_ydomain(a):
    # Bars sit at y > 0; dot matrix sits at y < 0.
    max_size = max((s for _, s in a["_inter"]), default=1)
    return [-_matrix_data_height(a), max_size * 1.1]


def upset_draw(a, ctx):
    n_sets = len(a["_names"])
    n_inter = len(a["_inter"])
    bar_w = a["opts"].get("bar_width", 0.7)
    bar_color = a["opts"].get("color", "#333333")
    on_color = a["opts"].get("on_color", "#333333")
    off_color = a["opts"].get("off_color", "#dddddd")
    out = []
    # Bars on top.
    y0 = ctx.y_scale(0)
    for i, (combo, size) in enumerate(a["_inter"]):
        cx = ctx.x_scale(i)
        x0 = cx - bar_w / 2 * (ctx.x_scale(1) - ctx.x_scale(0))
        w = bar_w * (ctx.x_scale(1) - ctx.x_scale(0))
        y_top = ctx.y_scale(size)
        out.append(rect(x0, y_top, w, abs(y0 - y_top), fill=bar_color))
        out.append(text_path(str(size), cx, y_top - 4, 9, anchor="middle"))
    # Divider between bars and matrix.
    out.append(segment(ctx.x_scale(-0.5), y0, ctx.x_scale(n_inter - 0.5), y0,
                       color="#bbb", width=0.8))
    # Dot matrix: rows evenly spaced within the matrix region.
    for j, name in enumerate(a["_names"]):
        py = ctx.y_scale(_row_y(a, j))
        # Row label on the left.
        out.append(text_path(name, ctx.x_scale(-0.5) - 6, py + 3,
                              10, anchor="end"))
        for i, (combo, _) in enumerate(a["_inter"]):
            cx = ctx.x_scale(i)
            fill = on_color if name in combo else off_color
            out.append(circle(cx, py, 4, fill=fill))
    # Connector lines through contiguous "on" dots in each column.
    for i, (combo, _) in enumerate(a["_inter"]):
        rows_on = [j for j, name in enumerate(a["_names"]) if name in combo]
        if len(rows_on) > 1:
            cx = ctx.x_scale(i)
            y_top = ctx.y_scale(_row_y(a, min(rows_on)))
            y_bot = ctx.y_scale(_row_y(a, max(rows_on)))
            out.append(segment(cx, y_top, cx, y_bot, color=on_color, width=1.4))
    return "".join(out)


def upset_frame_defaults(args, kw):
    # Bare frame matches canonical UpSet aesthetic: bars + dot matrix only.
    return [("spines", [], {"top": False, "right": False,
                            "bottom": False, "left": False}),
            ("yticks", [[]], {})]


def upset_legend_entries(a):
    opts = a["opts"]
    return [
        {"label": opts.get("on_label", "in set"),
         "color": opts.get("on_color", "#333333")},
        {"label": opts.get("off_label", "not in set"),
         "color": opts.get("off_color", "#dddddd")},
    ]


pt.add_artist(pt.ArtistSpec(
    name="upset",
    record=upset_record,
    xdomain=upset_xdomain,
    ydomain=upset_ydomain,
    draw=upset_draw,
    uses_color_cycle=False,
    legend_entries=upset_legend_entries,
    frame_defaults=upset_frame_defaults,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(8)
    universe = list(range(500))
    def sample(p): return set(x for x in universe if random.random() < p)
    sets = {
        "RNA-seq":    sample(0.30),
        "ChIP-seq":   sample(0.25),
        "ATAC-seq":   sample(0.20),
        "Proteomics": sample(0.18),
        "Methylome":  sample(0.15),
    }
    c = pt.chart(data_width=520, data_height=300)
    c.upset(list(sets), sets, n_top=12)
    c.legend(True)
    c.xticks([])
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
