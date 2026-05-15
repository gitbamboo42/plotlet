"""Custom artist: Sankey diagram.

Flows between sets of nodes, sized proportionally and connected by
ribbons. Stages (left-to-right columns) are inferred from the flow
graph via longest-path layering. Node order within a stage uses input
order — no crossing-minimization step, so it's the user's job to pass
node names in a sensible order if crossings matter.

The whole diagram is one artist on a "blank" panel (x and y don't carry
data meaning; xlim and ylim become [0, 1]). Pair with `c.xticks([])`
and `c.yticks([])` for the clean Sankey look.

API:
    c.sankey(nodes, flows,
             node_pad=0.02,    # vertical gap between stacked nodes (fraction of plot height)
             node_w=0.03,      # node bar width (fraction of plot width)
             ribbon_alpha=0.4,
             node_colors=None) # dict mapping node name -> color

`nodes` -> list of node names (strings) in their preferred display order.
`flows` -> list of `(source, target, value)` triples; `source` and
           `target` reference `nodes` by name or by index.

The recipe is ~150 lines including the layout solver; the heavy bit is
the cubic-bezier ribbon path. See marsilea and d3-sankey for the
production-quality versions of this idea.
"""

SUMMARY = "Flows between nodes drawn as cubic-bezier ribbons; layers inferred via longest-path layering."

from collections import deque
from pathlib import Path

import plotlet as pt
from plotlet.draw import path, rect, text_path


_DEFAULT_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


def _layer_assignment(n_nodes, edges):
    """layer[i] = longest path from any source node (in_degree=0) to i."""
    layer = [0] * n_nodes
    in_deg = [0] * n_nodes
    succ = [[] for _ in range(n_nodes)]
    for s, t, _ in edges:
        in_deg[t] += 1
        succ[s].append(t)
    # Kahn-style topological pass.
    rem_in = list(in_deg)
    q = deque(i for i in range(n_nodes) if rem_in[i] == 0)
    while q:
        u = q.popleft()
        for v in succ[u]:
            layer[v] = max(layer[v], layer[u] + 1)
            rem_in[v] -= 1
            if rem_in[v] == 0:
                q.append(v)
    return layer


def sankey_record(args, kw):
    nodes = list(args[0])
    flows_in = list(args[1])
    idx = {n: i for i, n in enumerate(nodes)}
    flows = []
    for s, t, v in flows_in:
        si = idx[s] if isinstance(s, str) else s
        ti = idx[t] if isinstance(t, str) else t
        flows.append((si, ti, float(v)))
    return {"type": "sankey", "_nodes": nodes, "_flows": flows, "opts": kw}


def sankey_xdomain(a): return [0, 1]
def sankey_ydomain(a): return [0, 1]


def sankey_draw(a, ctx):
    nodes = a["_nodes"]
    flows = a["_flows"]
    n = len(nodes)
    if not n or not flows:
        return ""
    node_pad = a["opts"].get("node_pad", 0.02)
    node_w = a["opts"].get("node_w", 0.03)
    ribbon_alpha = a["opts"].get("ribbon_alpha", 0.4)
    node_colors = a["opts"].get("node_colors") or {}
    # Per-node total flow (max of in / out).
    in_sum = [0.0] * n; out_sum = [0.0] * n
    for s, t, v in flows:
        out_sum[s] += v
        in_sum[t] += v
    weight = [max(in_sum[i], out_sum[i]) for i in range(n)]
    # Layer assignment.
    layer = _layer_assignment(n, flows)
    n_layers = max(layer) + 1
    # Nodes grouped by layer, preserving input order.
    layer_nodes = [[] for _ in range(n_layers)]
    for i in range(n):
        layer_nodes[layer[i]].append(i)
    # Total weight per layer for vertical normalization.
    layer_total = [sum(weight[i] for i in layer_nodes[L]) for L in range(n_layers)]
    plot_unit = max(layer_total) or 1.0
    # Each layer fills [pad, 1 - pad] vertically; nodes stack from the top.
    # Scale: 1 weight unit = (1 - 2*v_pad) / plot_unit  vertical fraction.
    v_pad_total = node_pad * (max(len(ln) for ln in layer_nodes) - 1)
    avail = 1.0 - v_pad_total
    # node_y[i] = (y_top, y_bot) in [0, 1] data coords (0 at top — note that
    # plotlet's y axis is normal-orientation, so we'll invert later).
    node_y = [None] * n
    for L in range(n_layers):
        # Vertical scale specific to this layer so nodes fit even if
        # this layer's total < plot_unit (typical at the right side).
        L_total = layer_total[L] or 1.0
        L_pad_total = node_pad * (len(layer_nodes[L]) - 1) if len(layer_nodes[L]) > 1 else 0
        L_avail = 1.0 - L_pad_total
        y = (1.0 - L_avail * L_total / plot_unit - L_pad_total) / 2  # vertical center
        for ni in layer_nodes[L]:
            h = L_avail * weight[ni] / plot_unit
            node_y[ni] = (y, y + h)
            y += h + node_pad
    # Per-node x position: evenly distribute layer left-edges so leftmost
    # is at 0 and rightmost is at 1 - node_w.
    node_x = {}
    if n_layers == 1:
        for i in range(n):
            node_x[i] = 0.5 - node_w / 2
    else:
        for L in range(n_layers):
            x_left = L * (1.0 - node_w) / (n_layers - 1)
            for ni in layer_nodes[L]:
                node_x[ni] = x_left
    # For each node, decide ribbon attach offsets on its right (outgoing)
    # and left (incoming) sides. Each side splits the node's height in
    # the order that flows appear.
    out_offsets = {i: [] for i in range(n)}
    in_offsets = {i: [] for i in range(n)}
    # We need to remember, for each flow, its source-side cumulative offset
    # and target-side cumulative offset (both within the node's height).
    src_cum = [0.0] * n
    tgt_cum = [0.0] * n
    flow_geom = []  # (src, tgt, value, src_y_top, src_y_bot, tgt_y_top, tgt_y_bot)
    # Process flows in input order — that's the user's implicit ribbon ordering.
    for s, t, v in flows:
        src_top = node_y[s][0] + src_cum[s] / weight[s] * (node_y[s][1] - node_y[s][0])
        src_bot = node_y[s][0] + (src_cum[s] + v) / weight[s] * (node_y[s][1] - node_y[s][0])
        tgt_top = node_y[t][0] + tgt_cum[t] / weight[t] * (node_y[t][1] - node_y[t][0])
        tgt_bot = node_y[t][0] + (tgt_cum[t] + v) / weight[t] * (node_y[t][1] - node_y[t][0])
        flow_geom.append((s, t, v, src_top, src_bot, tgt_top, tgt_bot))
        src_cum[s] += v
        tgt_cum[t] += v
    # Pixel helpers: data y is 0=top -> we feed (1 - y) into y_scale so the
    # diagram reads top-to-bottom in the SVG.
    def fx(x): return ctx.x_scale(x)
    def fy(y): return ctx.y_scale(1 - y)
    out = []
    # Ribbons first (background).
    for s, t, v, st_, sb_, tt_, tb_ in flow_geom:
        x_src = node_x[s] + node_w; x_tgt = node_x[t]
        col = node_colors.get(nodes[s], _DEFAULT_PALETTE[s % len(_DEFAULT_PALETTE)])
        # Cubic bezier control points at the midpoint of the layer gap.
        cx1 = (x_src + x_tgt) / 2
        cx2 = (x_src + x_tgt) / 2
        # Top edge: src_top -> tgt_top
        d = (f"M{fx(x_src):.2f},{fy(st_):.2f} "
             f"C{fx(cx1):.2f},{fy(st_):.2f} "
             f"{fx(cx2):.2f},{fy(tt_):.2f} "
             f"{fx(x_tgt):.2f},{fy(tt_):.2f} "
             # Down the tgt-side band
             f"L{fx(x_tgt):.2f},{fy(tb_):.2f} "
             # Bottom edge: tgt_bot -> src_bot (reverse direction)
             f"C{fx(cx2):.2f},{fy(tb_):.2f} "
             f"{fx(cx1):.2f},{fy(sb_):.2f} "
             f"{fx(x_src):.2f},{fy(sb_):.2f} "
             f"Z")
        out.append(path(d, fill=col, alpha=ribbon_alpha))
    # Node bars + labels on top.
    for i, name in enumerate(nodes):
        y_t, y_b = node_y[i]
        x_l = node_x[i]; x_r = x_l + node_w
        col = node_colors.get(name, _DEFAULT_PALETTE[i % len(_DEFAULT_PALETTE)])
        # fy(y_t) is the smaller SVG y (top of the bar); fy(y_b) the larger.
        out.append(rect(fx(x_l), fy(y_t), fx(x_r) - fx(x_l), fy(y_b) - fy(y_t),
                        fill=col))
        # Label: left of leftmost-layer nodes (anchor end), right of others (anchor start).
        cy_px = fy((y_t + y_b) / 2) + 4
        if layer[i] == 0:
            out.append(text_path(name, fx(x_r) + 4, cy_px, 10, anchor="start"))
        else:
            out.append(text_path(name, fx(x_l) - 4, cy_px, 10, anchor="end"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="sankey",
    record=sankey_record,
    xdomain=sankey_xdomain,
    ydomain=sankey_ydomain,
    draw=sankey_draw,
    uses_color_cycle=False,
    tight_domain=True,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    # 3-stage energy flow: source → conversion → end-use.
    nodes = [
        "Coal", "Gas", "Solar", "Wind", "Nuclear",        # stage 0
        "Electricity", "Heat",                            # stage 1
        "Industry", "Residential", "Transport", "Losses", # stage 2
    ]
    flows = [
        ("Coal", "Electricity", 25),
        ("Coal", "Heat",         8),
        ("Gas",  "Electricity", 20),
        ("Gas",  "Heat",        15),
        ("Solar","Electricity",  8),
        ("Wind", "Electricity", 12),
        ("Nuclear","Electricity",18),
        ("Electricity","Industry",   30),
        ("Electricity","Residential",25),
        ("Electricity","Transport",  10),
        ("Electricity","Losses",     18),
        ("Heat","Industry",     10),
        ("Heat","Residential",  10),
        ("Heat","Losses",        3),
    ]
    c = pt.chart(data_width=600, data_height=360)
    c.sankey(nodes, flows)
    c.xticks([]); c.yticks([])
    c.title("Energy flow (TWh)")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
