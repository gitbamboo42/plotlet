"""Custom artist: categorical annotation strip.

A horizontal row of colored cells encoding a category per position along
the x axis. Designed to align with a host panel above or below via
`share_x` — sample-group bars on top of a heatmap, regime tags above a
time series, cluster labels alongside a dendrogram, etc.

Two scale kinds supported:

- **Categorical x** (heatmap-style): pass `positions` as category names
  (e.g. sample IDs). Cell width comes from `ctx.x_scale.bandwidth`.
- **Numeric x** (time-series-style): pass `positions` as numbers and set
  `width=` in data units.

API:

    c.annotation_strip(positions, values, palette={...}, name="Group")

`palette` maps each unique `value` to a color. Unmapped values fall back
to `ctx.color`. `None` / `""` in `values` means missing data (drawn as
`absent_fill` if set, otherwise transparent).
"""

SUMMARY = 'Categorical color strip — one cell per position, for annotation tracks aligned to a host panel.'
from pathlib import Path

import plotlet as pt
from plotlet.draw import rect
from plotlet.utils import to_list


def annotation_strip_record(args, kw):
    if len(args) < 2:
        raise TypeError(
            "annotation_strip requires (positions, values); "
            "got %d positional arg(s)." % len(args)
        )
    positions = to_list(args[0])
    values = to_list(args[1])
    if len(positions) != len(values):
        raise ValueError(
            f"annotation_strip: positions ({len(positions)}) and "
            f"values ({len(values)}) must be the same length."
        )
    return {
        "type": "annotation_strip",
        "positions": positions,
        "values": values,
        "opts": kw,
    }


def annotation_strip_xdomain(a):
    # Mirror what the host panel uses. If positions are strings we hand
    # them to the category scale; if numeric, the linear scale.
    return list(a["positions"])


def annotation_strip_ydomain(a):
    return [0, 1]


def _ordered_values(values, palette):
    """Legend / draw order: palette declaration order first, then any
    values not in the palette in first-appearance order."""
    seen_in_data = []
    for v in values:
        if v is None or v == "":
            continue
        if v not in seen_in_data:
            seen_in_data.append(v)
    if not palette:
        return seen_in_data
    in_palette = [v for v in palette if v in seen_in_data]
    extras = [v for v in seen_in_data if v not in palette]
    return in_palette + extras


def annotation_strip_draw(a, ctx):
    opts = a["opts"]
    palette = opts.get("palette") or {}
    x_pad = opts.get("x_padding", 0.0)
    y_pad = opts.get("y_padding", 0.0)
    absent_fill = opts.get("absent_fill")
    width = opts.get("width")
    fallback = ctx.color

    # Cell height from y data range [0, 1].
    y0 = ctx.y_scale(0); y1 = ctx.y_scale(1)
    yt, yb = min(y0, y1), max(y0, y1)
    h = yb - yt
    y_inner = yt + h * y_pad
    h_inner = h * (1 - 2 * y_pad)

    # Cell width: bandwidth for category scale, user-supplied for numeric.
    bw_attr = getattr(ctx.x_scale, "bandwidth", None)
    if bw_attr is not None:
        bw = bw_attr
    elif width is not None:
        # Convert data-unit width to pixels via scale.
        bw = abs(ctx.x_scale(width) - ctx.x_scale(0))
    else:
        raise ValueError(
            "annotation_strip on a non-categorical x scale needs "
            "`width=<data-units>` (e.g. `width=1.0` for unit-spaced "
            "integer positions)."
        )

    out = []
    for pos, v in zip(a["positions"], a["values"]):
        cx = ctx.x_scale(pos)
        x0 = cx - bw / 2
        w = bw
        x_inner = x0 + w * x_pad
        w_inner = w * (1 - 2 * x_pad)

        if absent_fill is not None:
            out.append(rect(x_inner, y_inner, w_inner, h_inner,
                            fill=absent_fill))
        if v is None or v == "":
            continue
        fill = palette.get(v, fallback)
        out.append(rect(x_inner, y_inner, w_inner, h_inner, fill=fill))
    return "".join(out)


def annotation_strip_legend_entries(a):
    opts = a["opts"]
    palette = opts.get("palette") or {}
    order = _ordered_values(a["values"], palette)
    if not order:
        return []
    # If no palette was given and there's a single fallback color, surface
    # one entry with the optional `label=` kwarg (decorative single-color
    # strip case). Otherwise emit one entry per value.
    if not palette:
        label = opts.get("label")
        if not label:
            return []
        return [{"label": label, "color": a.get("_color")}]
    entries = []
    for v in order:
        col = palette.get(v, a.get("_color"))
        entries.append({"label": str(v), "color": col})
    return entries


def annotation_strip_frame_defaults(args, kw):
    """Decorative row: hide spines + x-tick marks. If `name=` is given,
    use it as a single y-tick label at the band center; otherwise hide
    the y axis entirely. The caller can override any of this with their
    own `xticks(...)` / `yticks(...)` after the artist call (e.g. to
    surface sample labels under the bottom row of a stack)."""
    name = kw.get("name")
    out = [("spines", [], {"top": False, "right": False,
                           "bottom": False, "left": False})]
    out.append(("xticks", [None], {"marks": False}))
    if name is not None:
        out.append(("yticks", [[0.5], [name]], {"marks": False}))
    else:
        out.append(("yticks", [[]], {}))
    return out


pt.add_artist(pt.ArtistSpec(
    name="annotation_strip",
    record=annotation_strip_record,
    xdomain=annotation_strip_xdomain,
    ydomain=annotation_strip_ydomain,
    draw=annotation_strip_draw,
    legend_entries=annotation_strip_legend_entries,
    frame_defaults=annotation_strip_frame_defaults,
    uses_color_cycle=False,
    tight_domain=True,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    samples = [f"S{i+1:02d}" for i in range(12)]
    groups = (["ctrl"] * 4) + (["treat"] * 5) + (["resist"] * 3)
    palette = {"ctrl": pt.TAB10[0], "treat": pt.TAB10[1], "resist": pt.TAB10[2]}
    c = pt.chart(data_width=420, data_height=24)
    c.annotation_strip(samples, groups, palette=palette, name="Treatment")
    c.xticks(rotation=45)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
