"""Custom artist: chord_links — pairwise arcs between two x-positions.

Same call works in two coordinate setups:

- In Cartesian (no coord, or any affine coord) the artist emits half-ellipse
  arcs above ``y=0`` from ``x1`` to ``x2`` — a classic arc diagram. The
  bulge defaults to a semicircle (height = ``|x2 − x1| / 2``), so the
  chart's ``ylim`` autoscales to fit. Pair with ``c.yticks([])`` for the
  clean arc-diagram look.

- Attached to a ``CircularCoordinate`` via its ``inner=`` slot, the same
  artist draws Bezier chords through the central disc — the Circos-style
  link visual. The disc sub-coord ignores y data; chord endpoints land at
  the disc boundary (``r = 1`` of the sub-coord = ``r_inner`` of the rings)
  and curve through the canvas center.

Color follows the standard convention: ``aes(color="col")`` maps a
column (categorical → palette); a bare ``color="#hex"`` is a literal.

Sector handling:

- **Intra-sector** links (both endpoints in the same sector): pass the
  sector tag once on the layout via ``c.sectors(spec, column="chrom")``;
  ``x1`` and ``x2`` both pick it up.
- **Cross-sector** links: map per-endpoint sector-tag columns
  ``aes(x1_sector="src_chrom", x2_sector="dst_chrom")`` on the call. The
  layout-level ``column=`` is then optional. ``x1_sector`` /
  ``x2_sector`` are consumed by the sector remap and never reach the
  artist.

The chrome renderer auto-suppresses inter-sector divider walls when
this artist is active (via ``crosses_sectors=True``) — walls cutting
through a cross-sector curve read as a layering bug. Sector *labels*
still render.
"""

from ..registry import ArtistSpec, add_artist, declare_coord_support
from ..utils import pack_opts, to_list, resolve_aes, palette_color
from ..draw import path as draw_path, segment, TAB10
from ..draw import coord



def _chord_links_record(data=None,
                        # input columns & color grouping — consumed at record
                        x1=None, x2=None, color=None, palette=None,
                        # style — packed into opts for the draw/legend side
                        width=None, alpha=None, height=None,
                        label=None, legend=None):
    if data is None or x1 is None or x2 is None:
        raise TypeError("chord_links requires data=, x1=, x2=.")
    xs1 = to_list(data[x1])
    xs2 = to_list(data[x2])
    base_opts = pack_opts(width=width, alpha=alpha, height=height,
                          label=label, legend=legend)

    color_kind, color_value = resolve_aes(data, color)
    if color_kind != "column":
        opts = dict(base_opts)
        if color_value is not None:
            opts["color"] = color_value
        return {"type": "chord_links", "xs1": xs1, "xs2": xs2, "opts": opts}

    # Categorical color: one record per level so the standard color cycle
    # and legend dispatch apply. No continuous-color path (not common for
    # link artists; add later if needed).
    color_vec = list(color_value)
    levels = list(dict.fromkeys(color_vec))
    records = []
    labeled: set = set()
    for ck in levels:
        idxs = [i for i, v in enumerate(color_vec) if v == ck]
        opts = dict(base_opts)
        idx = levels.index(ck)
        opts["color"] = palette_color(palette, ck, idx) or TAB10[idx % 10]
        if ck not in labeled:
            opts["label"] = str(ck)
            labeled.add(ck)
        records.append({
            "type": "chord_links",
            "xs1": [xs1[i] for i in idxs],
            "xs2": [xs2[i] for i in idxs],
            "opts": opts,
        })
    return records


def _chord_links_xdomain(a):
    return list(a["xs1"]) + list(a["xs2"])


def _chord_links_ydomain(a):
    # Arc diagrams have no y-data — the y-axis is just space for the
    # bulge to live in. Return [0, 1] for a degenerate-safe autoscale;
    # `height=` (pixels) controls the actual bulge.
    return [0, 1]


def _chord_links_draw(a, ctx):
    opts = a["opts"]
    col = ctx.color
    alpha = opts.get("alpha", 0.6)
    width = opts.get("width", 1.0)
    out = []

    if ctx.warp is None:
        # Cartesian: quadratic Bezier bells above y=0. All chords peak at
        # the same height regardless of chord length — short chords get
        # narrow bells, long chords get wide bells, both at the same y.
        # (A half-ellipse default would give short chords a degenerate
        # hairpin shape; same peak height, but visually reads as a
        # vertical line.) `height=N` overrides the peak height in pixels.
        y0 = ctx.y_scale(0)
        h_px = float(opts.get("height", ctx.ih * 0.7))
        # Quadratic Bezier peaks at y = 0.5 * (y0 + y_ctrl), so for the
        # peak to land h_px above y0, control y must be y0 - 2*h_px.
        y_ctrl = y0 - 2 * h_px
        for x1, x2 in zip(a["xs1"], a["xs2"]):
            x1_px = ctx.x_scale(x1)
            x2_px = ctx.x_scale(x2)
            xc = (x1_px + x2_px) / 2
            d = (f"M {coord(x1_px)},{coord(y0)} "
                 f"Q {coord(xc)},{coord(y_ctrl)} {coord(x2_px)},{coord(y0)}")
            out.append(draw_path(d, stroke=col, stroke_width=width, alpha=alpha))
        return "".join(out)

    # Disc sub-coord (non-affine): quadratic Bezier through the canvas
    # center. Endpoint t-positions come from x_scale; r is fixed at the
    # disc boundary (r = 1 of the sub-coord). In pre-warp Cartesian
    # pixels, r=1 ↔ y_px = 0 (top edge) and r=0 ↔ y_px = ih (bottom,
    # but the warp collapses every column to the canvas center).
    cx_px, cy_px = ctx.warp(ctx.iw / 2, ctx.ih)
    for x1, x2 in zip(a["xs1"], a["xs2"]):
        p1x, p1y = ctx.warp(ctx.x_scale(x1), 0.0)
        p2x, p2y = ctx.warp(ctx.x_scale(x2), 0.0)
        d = (f"M {coord(p1x)},{coord(p1y)} "
             f"Q {coord(cx_px)},{coord(cy_px)} {coord(p2x)},{coord(p2y)}")
        out.append(draw_path(d, stroke=col, stroke_width=width, alpha=alpha))
    return "".join(out)


def _chord_links_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        col = a["_color"]
        opts = a["opts"]
        return segment(x0, y_mid, x0 + 22, y_mid, color=col,
                       width=opts.get("width", 1.0),
                       alpha=opts.get("alpha", 0.6))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


def _chord_links_frame_defaults(args, kw):
    # No data lives on the y-axis (it's just space for the bulge), and
    # the strip looks cleanest free of spines — pairs naturally with
    # `attach_above` / `attach_below` on a host panel that owns the
    # x-axis. Same idiom as `dendrogram`. Inside a Circular inner disc
    # the rings own t-axis labels, so suppress x-ticks by default too;
    # users can opt in with an explicit `.xticks(...)`.
    return [
        ("spines", [], {"top": False, "right": False,
                        "bottom": False, "left": False}),
        ("xticks", [[]], {}),
        ("yticks", [[]], {}),
        ("ylabel", [""], {}),
    ]


add_artist(ArtistSpec(
    name="chord_links",
    record=_chord_links_record,
    xdomain=_chord_links_xdomain,
    ydomain=_chord_links_ydomain,
    draw=_chord_links_draw,
    legend_entries=_chord_links_legend_entries,
    frame_defaults=_chord_links_frame_defaults,
    crosses_sectors=True,
    tight_domain=True,
))
declare_coord_support("Circular", ["chord_links"])
