"""Custom artist: alluvial diagram.

Visualizes categorical-state transitions over a sequence of layers. Each
layer holds the same (or different) category set; ribbons connect each
adjacent pair of layers, sized by the flow count of "subjects in
category A at layer i → category B at layer i+1".

Sankey-shaped, but with the added constraint that nodes are grouped by
layer in the user-supplied order (no longest-path inference), and
ribbons only connect adjacent layers.

API:
    c.alluvial(layers, transitions)

`layers` is a list of *(layer_name, [categories_in_order])* tuples.
`transitions` is a dict keyed by adjacent-layer-index `(i, i+1)`:
    transitions[(i, i+1)] = {(cat_a, cat_b): count, ...}
"""

SUMMARY = "Categorical-state transitions over time: adjacent-layer flow ribbons (sankey for time series)."

from pathlib import Path

import plotlet as pt
from plotlet.draw import path, rect, text_path
from ..draw import coord



_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


def alluvial_record(args, kw):
    layers = [(str(name), list(cats)) for name, cats in args[0]]
    transitions = {tuple(k): dict(v) for k, v in dict(args[1]).items()}
    return {"type": "alluvial", "layers": layers, "trans": transitions,
            "opts": kw}


def alluvial_xdomain(a): return [0, 1]
def alluvial_ydomain(a): return [0, 1]


def alluvial_draw(a, ctx):
    layers = a["layers"]
    trans = a["trans"]
    n_layers = len(layers)
    if n_layers < 2:
        return ""
    node_w = a["opts"].get("node_w", 0.025)
    node_pad = a["opts"].get("node_pad", 0.015)
    ribbon_alpha = a["opts"].get("ribbon_alpha", 0.45)
    # Compute per-node weight: sum of outgoing (for non-final layers) or
    # incoming (for the final layer).
    weights = []  # list of {cat: weight}
    for i, (_, cats) in enumerate(layers):
        w = {c: 0 for c in cats}
        if i < n_layers - 1:
            for (a_, b), v in trans.get((i, i + 1), {}).items():
                if a_ in w: w[a_] += v
        else:
            for (a_, b), v in trans.get((i - 1, i), {}).items():
                if b in w: w[b] += v
        weights.append(w)
    layer_totals = [sum(w.values()) for w in weights]
    plot_max = max(layer_totals) or 1.0
    # Vertical position of each (layer, cat): top-down, with node_pad gaps.
    pos = []  # pos[i][cat] = (y_top, y_bot)
    for i, (_, cats) in enumerate(layers):
        avail = 1.0 - node_pad * max(len(cats) - 1, 0)
        scale = avail / plot_max
        y = (1.0 - layer_totals[i] * scale - node_pad * max(len(cats) - 1, 0)) / 2
        layer_pos = {}
        for c in cats:
            h = weights[i][c] * scale
            layer_pos[c] = (y, y + h)
            y += h + node_pad
        pos.append(layer_pos)
    # Layer x positions evenly spread.
    if n_layers == 1:
        x_left = {0: 0.5 - node_w / 2}
    else:
        x_left = {i: i * (1.0 - node_w) / (n_layers - 1) for i in range(n_layers)}

    def fx(x): return ctx.x_scale(x)

    def fy(y): return ctx.y_scale(1 - y)
    out = []
    # Ribbons between adjacent layers.
    for i in range(n_layers - 1):
        link_total = layer_totals[i] or 1.0
        cats_a = layers[i][1]; cats_b = layers[i + 1][1]
        # Track cumulative offset on the right of layer i and left of layer i+1.
        out_cum = {c: 0.0 for c in cats_a}
        in_cum = {c: 0.0 for c in cats_b}
        # Flow ordering: sort flows by source category appearance, then target.
        flows = sorted(trans.get((i, i + 1), {}).items(),
                       key=lambda kv: (cats_a.index(kv[0][0]) if kv[0][0] in cats_a else 999,
                                       cats_b.index(kv[0][1]) if kv[0][1] in cats_b else 999))
        for (a_, b), v in flows:
            if a_ not in pos[i] or b not in pos[i + 1]:
                continue
            a_top, a_bot = pos[i][a_]
            b_top, b_bot = pos[i + 1][b]
            src_top = a_top + out_cum[a_] / (weights[i][a_] or 1) * (a_bot - a_top)
            src_bot = a_top + (out_cum[a_] + v) / (weights[i][a_] or 1) * (a_bot - a_top)
            tgt_top = b_top + in_cum[b] / (weights[i + 1][b] or 1) * (b_bot - b_top)
            tgt_bot = b_top + (in_cum[b] + v) / (weights[i + 1][b] or 1) * (b_bot - b_top)
            x_src = x_left[i] + node_w; x_tgt = x_left[i + 1]
            cx1 = (x_src + x_tgt) / 2; cx2 = cx1
            d = (f"M{coord(fx(x_src))},{coord(fy(src_top))} "
                 f"C{coord(fx(cx1))},{coord(fy(src_top))} "
                 f"{coord(fx(cx2))},{coord(fy(tgt_top))} "
                 f"{coord(fx(x_tgt))},{coord(fy(tgt_top))} "
                 f"L{coord(fx(x_tgt))},{coord(fy(tgt_bot))} "
                 f"C{coord(fx(cx2))},{coord(fy(tgt_bot))} "
                 f"{coord(fx(cx1))},{coord(fy(src_bot))} "
                 f"{coord(fx(x_src))},{coord(fy(src_bot))} Z")
            cat_idx = cats_a.index(a_) if a_ in cats_a else 0
            col = _PALETTE[cat_idx % len(_PALETTE)]
            out.append(path(d, fill=col, alpha=ribbon_alpha))
            out_cum[a_] += v
            in_cum[b] += v
    # Node bars on top.
    for i, (layer_name, cats) in enumerate(layers):
        for j, c in enumerate(cats):
            y_t, y_b = pos[i][c]
            col = _PALETTE[j % len(_PALETTE)]
            out.append(rect(fx(x_left[i]), fy(y_b),
                            fx(x_left[i] + node_w) - fx(x_left[i]),
                            fy(y_t) - fy(y_b), fill=col))
            # Label: left of first layer, right elsewhere.
            cy = fy((y_t + y_b) / 2) + 4
            if i == 0:
                out.append(text_path(c, fx(x_left[i]) - 4, cy,
                                       10, anchor="end"))
            else:
                out.append(text_path(c, fx(x_left[i] + node_w) + 4, cy,
                                       10, anchor="start"))
        # Layer name above the column.
        out.append(text_path(layer_name, fx(x_left[i] + node_w / 2),
                              fy(1.0) - 8, 11, anchor="middle"))
    return "".join(out)


def alluvial_legend_entries(a):
    # Categories are colored by their position within each layer (palette index
    # = j). Enumerate unique categories in first-seen order, assigning each
    # the color of its first appearance.
    entries = []
    seen = set()
    for _, cats in a["layers"]:
        for j, c in enumerate(cats):
            if c in seen:
                continue
            seen.add(c)
            entries.append({"label": str(c),
                            "color": _PALETTE[j % len(_PALETTE)]})
    return entries


pt.add_artist(pt.ArtistSpec(
    name="alluvial",
    record=alluvial_record,
    xdomain=alluvial_xdomain,
    ydomain=alluvial_ydomain,
    draw=alluvial_draw,
    uses_color_cycle=False,
    tight_domain=True,
    legend_entries=alluvial_legend_entries,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    layers = [
        ("Year 1", ["A", "B", "C"]),
        ("Year 2", ["A", "B", "C"]),
        ("Year 3", ["A", "B", "C"]),
    ]
    transitions = {
        (0, 1): {("A", "A"): 30, ("A", "B"): 8,  ("A", "C"): 2,
                 ("B", "A"): 5,  ("B", "B"): 20, ("B", "C"): 5,
                 ("C", "A"): 2,  ("C", "B"): 4,  ("C", "C"): 14},
        (1, 2): {("A", "A"): 28, ("A", "B"): 7,  ("A", "C"): 2,
                 ("B", "A"): 6,  ("B", "B"): 20, ("B", "C"): 6,
                 ("C", "A"): 3,  ("C", "B"): 5,  ("C", "C"): 13},
    }
    c = pt.chart(data_width=560, data_height=320)
    c.alluvial(layers, transitions)
    c.xticks([]); c.yticks([])
    c.title("Customer-segment migration").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
