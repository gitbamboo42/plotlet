"""Custom artist: chord_ribbon — filled ribbons between two x-ranges.

Sibling of ``chord_links``: where ``chord_links`` draws a thin line
between two x positions (chords carry no width), ``chord_ribbon`` draws
a filled shape between two x **ranges**. That's the visual a matrix
chord diagram demands — each non-zero matrix entry M[i, j] becomes a
ribbon whose width on the i side and the j side is proportional to
M[i, j].

Inside a ``CircularCoordinate`` inner disc each ribbon edge is a
cubic Bezier whose two control points sit on the endpoint→center
radius at fraction ``tension`` (default 0.5) of the way to the
center. That recipe matches d3's chord-ribbon convention and handles
both extremes cleanly: opposite-arc chords curve through the center;
self-loops bulge inward as short petals without a center pinch. The
boundary caps between same-side corners are short polylines along the
disc boundary.

In flat (no-coord) panels the artist falls back to a linear-bow
shape: an outer half-bow arc spanning the outer pair of corners and
an inner half-bow arc spanning the inner pair, joined by short
baseline caps at each end. That's the linear unroll of the circular
ribbon and matches the linear-strip idiom used in the hg38 chord
cookbook.

API mirrors ``chord_links`` for the sector tags and color resolution:

    c.chord_ribbon(x1_start="x1a", x1_end="x1b",
                   x2_start="x2a", x2_end="x2b",
                   x1_sector="src", x2_sector="dst",
                   color="src", palette={...},
                   alpha=0.6, edge_color="#000", edge_width=0.5)

Each row contributes one ribbon. Positions are in the **data**
coordinate system — when the panel has continuous sectors, the standard
sector remap offsets them into the global span automatically. With no
sectors, positions are global from the start.

Self-loops (where both endpoints land on the same sector) render as a
through-center curve like any other ribbon. They read OK for thin
sectors and get visually busy for thick ones; if that matters, drop
the diagonal before passing the matrix in.
"""

SUMMARY = "Filled ribbons between two x ranges inside a CircularCoordinate inner disc — the matrix-chord-diagram visual."

import math
from pathlib import Path

import plotlet as pt
from plotlet.draw import path as draw_path, polygon, TAB10
from plotlet.utils import to_list, resolve_aes, palette_color
from ..draw import coord


_ARC_STEPS = 12     # polyline segments per disc-boundary cap
_DEFAULT_TENSION = 1.0   # cubic-control fraction along endpoint→center radius
                         # 1.0 = control AT canvas center (pycirclize default,
                         # narrow waist); lower values keep the controls
                         # partway in, which spares self-loops the center pinch
                         # at the cost of a less pronounced waist on regular chords.


def _chord_ribbon_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "chord_ribbon requires long-form input: "
            "c.chord_ribbon(data=df, x1_start=..., x1_end=..., "
            "x2_start=..., x2_end=...)."
        )
    data = kw.pop("data", None)
    x1a = kw.pop("x1_start", None)
    x1b = kw.pop("x1_end",   None)
    x2a = kw.pop("x2_start", None)
    x2b = kw.pop("x2_end",   None)
    if data is None or None in (x1a, x1b, x2a, x2b):
        raise TypeError(
            "chord_ribbon requires data=, x1_start=, x1_end=, "
            "x2_start=, x2_end=."
        )
    color   = kw.pop("color",   None)
    palette = kw.pop("palette", None)

    xs1a = to_list(data[x1a]); xs1b = to_list(data[x1b])
    xs2a = to_list(data[x2a]); xs2b = to_list(data[x2b])

    color_kind, color_value = resolve_aes(data, color)
    if color_kind != "column":
        opts = dict(kw)
        if color_value is not None:
            opts["color"] = color_value
        return {
            "type": "chord_ribbon",
            "xs1a": xs1a, "xs1b": xs1b, "xs2a": xs2a, "xs2b": xs2b,
            "opts": opts,
        }

    # One record per color level — keeps the standard color-cycle and
    # legend hooks happy without a continuous-color branch (link artists
    # rarely want one).
    color_vec = list(color_value)
    levels = list(dict.fromkeys(color_vec))
    records = []
    labeled: set = set()
    for ck in levels:
        idxs = [i for i, v in enumerate(color_vec) if v == ck]
        opts = dict(kw)
        idx = levels.index(ck)
        opts["color"] = palette_color(palette, ck, idx) or TAB10[idx % 10]
        if ck not in labeled:
            opts["label"] = str(ck)
            labeled.add(ck)
        records.append({
            "type":  "chord_ribbon",
            "xs1a":  [xs1a[i] for i in idxs],
            "xs1b":  [xs1b[i] for i in idxs],
            "xs2a":  [xs2a[i] for i in idxs],
            "xs2b":  [xs2b[i] for i in idxs],
            "opts":  opts,
        })
    return records


def _chord_ribbon_xdomain(a):
    return (list(a["xs1a"]) + list(a["xs1b"])
            + list(a["xs2a"]) + list(a["xs2b"]))


def _chord_ribbon_ydomain(a):
    return [0, 1]


def _chord_ribbon_draw(a, ctx):
    opts  = a["opts"]
    fill  = ctx.color
    alpha = float(opts.get("alpha", 0.6))
    edge_color = opts.get("edge_color")
    edge_width = float(opts.get("edge_width", 0.0))
    stroke_kw = dict(
        stroke=edge_color if edge_width > 0 else None,
        stroke_width=edge_width if edge_width > 0 else 1,
    )

    if ctx.warp is None:
        return _draw_linear(a, ctx, fill, alpha, stroke_kw, opts)
    return _draw_circular(a, ctx, fill, alpha, stroke_kw, opts)


def _draw_circular(a, ctx, fill, alpha, stroke_kw, opts):
    cx_px, cy_px = ctx.warp(ctx.iw / 2, ctx.ih)   # canvas center
    tension = float(opts.get("tension", _DEFAULT_TENSION))

    def boundary(x):
        # x is in data coords (post-sector-remap); land on the disc edge.
        return ctx.warp(ctx.x_scale(x), 0.0)

    def boundary_arc(x_from, x_to):
        # Sample N points along the disc boundary between two data-x
        # positions. The CircularCoordinate maps x linearly to angle, so
        # uniform x steps give uniform angular steps.
        pts = []
        for k in range(1, _ARC_STEPS):
            t = k / _ARC_STEPS
            x = x_from + (x_to - x_from) * t
            pts.append(boundary(x))
        return pts

    def ctl(pt):
        # Cubic-Bezier control along the endpoint→center radius. Tension
        # 1.0 = at center (legacy through-center pinch); 0.5 = halfway
        # in (default — wide chords still flow through center, self-loops
        # bulge as a short petal).
        return (pt[0] + (cx_px - pt[0]) * tension,
                pt[1] + (cy_px - pt[1]) * tension)

    # `allow_twist=False` (default) — when both arcs share a winding
    # direction the literal start↔start / end↔end ribbon would knot up
    # in an X at the center; swapping start2/end2 keeps the edges
    # parallel along the natural sweep. Same kwarg as pycirclize.
    allow_twist = bool(opts.get("allow_twist", False))

    out = []
    for x1a, x1b, x2a, x2b in zip(a["xs1a"], a["xs1b"],
                                   a["xs2a"], a["xs2b"]):
        if (not allow_twist
                and (float(x1b) - float(x1a)) * (float(x2b) - float(x2a)) > 0):
            x2a, x2b = x2b, x2a
        c1a = boundary(x1a); c1b = boundary(x1b)
        c2a = boundary(x2a); c2b = boundary(x2b)
        k1a = ctl(c1a); k1b = ctl(c1b)
        k2a = ctl(c2a); k2b = ctl(c2b)

        seg_2 = boundary_arc(x2a, x2b)
        seg_1 = boundary_arc(x1b, x1a)
        d = [f"M {coord(c1a[0])},{coord(c1a[1])}"]
        # Top edge: cubic c1a -> c2a, controls toward center
        d.append(f"C {coord(k1a[0])},{coord(k1a[1])} "
                 f"{coord(k2a[0])},{coord(k2a[1])} "
                 f"{coord(c2a[0])},{coord(c2a[1])}")
        for px, py in seg_2:
            d.append(f"L {coord(px)},{coord(py)}")
        d.append(f"L {coord(c2b[0])},{coord(c2b[1])}")
        # Bottom edge: cubic c2b -> c1b, controls toward center
        d.append(f"C {coord(k2b[0])},{coord(k2b[1])} "
                 f"{coord(k1b[0])},{coord(k1b[1])} "
                 f"{coord(c1b[0])},{coord(c1b[1])}")
        for px, py in seg_1:
            d.append(f"L {coord(px)},{coord(py)}")
        d.append(f"L {coord(c1a[0])},{coord(c1a[1])}")
        d.append("Z")
        out.append(draw_path(" ".join(d), fill=fill, alpha=alpha, **stroke_kw))
    return "".join(out)


def _draw_linear(a, ctx, fill, alpha, stroke_kw, opts):
    # Linear unroll: both endpoints sit on the baseline at y = 0 and bows
    # arc upward. Match chord_links — the layering convention (arc panel
    # ABOVE the strip via `attach_above`) puts arc roots at the panel
    # bottom, naturally facing the strip below, so the artist needs no
    # direction kwarg.
    y0 = ctx.y_scale(0)
    h_px = float(opts.get("height", ctx.ih * 0.7))
    y_peak_outer = y0 - 2 * h_px

    out = []
    for x1a, x1b, x2a, x2b in zip(a["xs1a"], a["xs1b"],
                                   a["xs2a"], a["xs2b"]):
        p_1a = ctx.x_scale(x1a); p_1b = ctx.x_scale(x1b)
        p_2a = ctx.x_scale(x2a); p_2b = ctx.x_scale(x2b)
        # Outer pair = the two corners furthest apart in pixel space;
        # inner pair = the two closest. This handles both directions
        # (x2 > x1 and x2 < x1) without special casing.
        side_1 = sorted([p_1a, p_1b])
        side_2 = sorted([p_2a, p_2b])
        if side_1[0] <= side_2[0]:
            outer_l, outer_r = side_1[0], side_2[1]
            inner_l, inner_r = side_1[1], side_2[0]
        else:
            outer_l, outer_r = side_2[0], side_1[1]
            inner_l, inner_r = side_2[1], side_1[0]

        outer_w = outer_r - outer_l
        inner_w = inner_r - inner_l
        ratio = max(inner_w, 0.0) / outer_w if outer_w > 0 else 0.0
        y_peak_inner = y0 - 2 * h_px * ratio
        xc_outer = (outer_l + outer_r) / 2
        xc_inner = (inner_l + inner_r) / 2

        d = (f"M {coord(outer_l)},{coord(y0)} "
             f"Q {coord(xc_outer)},{coord(y_peak_outer)} "
             f"{coord(outer_r)},{coord(y0)} "
             f"L {coord(inner_r)},{coord(y0)} "
             f"Q {coord(xc_inner)},{coord(y_peak_inner)} "
             f"{coord(inner_l)},{coord(y0)} "
             f"Z")
        out.append(draw_path(d, fill=fill, alpha=alpha, **stroke_kw))
    return "".join(out)


def _chord_ribbon_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    return [{"label": label, "color": a.get("_color")}]


def _chord_ribbon_frame_defaults(args, kw):
    # Same frame defaults as chord_links: no axes — the inner disc has no
    # axis lines, and ticks/labels would be illegible at the disc center
    # anyway. The rings own the t-axis chrome.
    return [
        ("spines", [], {"top": False, "right": False,
                        "bottom": False, "left": False}),
        ("xticks", [[]], {}),
        ("yticks", [[]], {}),
        ("ylabel", [""], {}),
    ]


pt.add_artist(pt.ArtistSpec(
    name="chord_ribbon",
    record=_chord_ribbon_record,
    xdomain=_chord_ribbon_xdomain,
    ydomain=_chord_ribbon_ydomain,
    draw=_chord_ribbon_draw,
    legend_entries=_chord_ribbon_legend_entries,
    frame_defaults=_chord_ribbon_frame_defaults,
    coord_native=True,
    crosses_sectors=True,
    tight_domain=True,
))


def demo():
    """Tiny 3-sector demo with three ribbons of varying width."""
    import pandas as pd
    sectors = pt.Sectors(names=["A", "B", "C"], lengths=[30, 25, 20], gap=4)
    XL = (0, sectors.total())
    df = pd.DataFrame({
        "src":  ["A", "A", "B"],
        "dst":  ["B", "C", "C"],
        "x1a":  [0,  18,  0],
        "x1b":  [10, 28, 15],
        "x2a":  [0,  0,  0],
        "x2b":  [10, 8, 12],
    })
    arcs = pt.chart(df, xlim=XL, data_width=400, data_height=400)
    arcs.sectors(sectors, column="src", label=False)
    arcs.chord_ribbon(x1_start="x1a", x1_end="x1b",
                      x2_start="x2a", x2_end="x2b",
                      x1_sector="src", x2_sector="dst",
                      color="src", alpha=0.6)

    ring = pt.chart(xlim=XL, ylim=(0, 1), data_width=400, data_height=400)
    ring.sectors(sectors, column="x")
    return pt.grid([[ring]]).coordinate(
        pt.CircularCoordinate(r_inner=0.85, inner=arcs)
    )


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
