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
from plotlet.draw import text_path


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
    # Use column indices as x (categorical-numeric).
    return [-0.5, max(0, len(a["_inter"]) - 0.5)]


def upset_ydomain(a):
    # Bars sit at y > 0; dot matrix sits at y < 0.
    max_size = max((s for _, s in a["_inter"]), default=1)
    n_sets = len(a["_names"])
    return [-n_sets - 0.5, max_size * 1.1]


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
        out.append(
            f'<rect x="{x0:.2f}" y="{y_top:.2f}" width="{w:.2f}" '
            f'height="{abs(y0 - y_top):.2f}" fill="{bar_color}"/>'
        )
        out.append(text_path(str(size), cx, y_top - 4, 9, anchor="middle"))
    # Divider between bars and matrix.
    out.append(
        f'<line x1="{ctx.x_scale(-0.5):.2f}" x2="{ctx.x_scale(n_inter - 0.5):.2f}" '
        f'y1="{y0:.2f}" y2="{y0:.2f}" stroke="#bbb" stroke-width="0.8"/>'
    )
    # Dot matrix: rows at y = -1, -2, ... -n_sets.
    for j, name in enumerate(a["_names"]):
        y_data = -(j + 1)
        py = ctx.y_scale(y_data)
        # Row label on the left.
        out.append(text_path(name, ctx.x_scale(-0.5) - 6, py + 3,
                              10, anchor="end"))
        for i, (combo, _) in enumerate(a["_inter"]):
            cx = ctx.x_scale(i)
            fill = on_color if name in combo else off_color
            out.append(
                f'<circle cx="{cx:.2f}" cy="{py:.2f}" r="4" fill="{fill}"/>'
            )
    # Connector lines through contiguous "on" dots in each column.
    for i, (combo, _) in enumerate(a["_inter"]):
        rows_on = [j for j, name in enumerate(a["_names"]) if name in combo]
        if len(rows_on) > 1:
            cx = ctx.x_scale(i)
            y_top = ctx.y_scale(-(min(rows_on) + 1))
            y_bot = ctx.y_scale(-(max(rows_on) + 1))
            out.append(
                f'<line x1="{cx:.2f}" x2="{cx:.2f}" y1="{y_top:.2f}" y2="{y_bot:.2f}" '
                f'stroke="{on_color}" stroke-width="1.4"/>'
            )
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="upset",
    record=upset_record,
    xdomain=upset_xdomain,
    ydomain=upset_ydomain,
    draw=upset_draw,
    uses_color_cycle=False,
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
    c.title("UpSet — hits per assay combination").ylabel("intersection size")
    c.xticks([])
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
