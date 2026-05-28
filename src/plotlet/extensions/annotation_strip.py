"""Custom artist: categorical annotation strip.

A row or column of colored cells encoding a category per position. The
default is horizontal (positions along the x axis), designed to align
with a host panel above or below via `share_x` — sample-group bars on
top of a heatmap, regime tags above a time series, cluster labels
alongside a dendrogram, etc. Pass `orient="y"` for a vertical column
that aligns with a host panel via `share_y` (per-row group labels next
to a heatmap, marsilea-style chunk strips).

Two scale kinds supported on the position axis:

- **Categorical** (heatmap-style): pass `positions` as category names
  (e.g. sample IDs). Cell size on that axis comes from `bandwidth`.
- **Numeric** (time-series-style): pass `positions` as numbers and set
  `width=` in data units of the position axis.

API:

    c.annotation_strip(positions, values, palette={...}, name="Group")
    c.annotation_strip(positions, values, orient="y", ...)  # vertical

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
    orient = kw.get("orient", "x")
    if orient not in ("x", "y"):
        raise ValueError(
            f"annotation_strip: orient= must be 'x' or 'y'; got {orient!r}."
        )
    return {
        "type": "annotation_strip",
        "positions": positions,
        "values": values,
        "_orient": orient,
        "opts": kw,
    }


def annotation_strip_xdomain(a):
    # Position axis carries the categories/numeric ticks; the orthogonal
    # axis spans [0, 1] (the cell's extent on its decorative side).
    if a.get("_orient") == "y":
        return [0, 1]
    return list(a["positions"])


def annotation_strip_ydomain(a):
    if a.get("_orient") == "y":
        return list(a["positions"])
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
    cat_pad = opts.get("x_padding", 0.0)   # padding along the position axis
    orth_pad = opts.get("y_padding", 0.0)  # padding along the orthogonal axis
    absent_fill = opts.get("absent_fill")
    width = opts.get("width")
    fallback = ctx.color
    orient = a.get("_orient", "x")
    cat_scale  = ctx.y_scale if orient == "y" else ctx.x_scale
    orth_scale = ctx.x_scale if orient == "y" else ctx.y_scale

    # Cell extent on the orthogonal axis (which spans [0, 1] by ydomain).
    o0 = orth_scale(0); o1 = orth_scale(1)
    o_lo, o_hi = min(o0, o1), max(o0, o1)
    h_orth = o_hi - o_lo
    o_inner = o_lo + h_orth * orth_pad
    h_inner_orth = h_orth * (1 - 2 * orth_pad)

    # Cell extent on the position axis: bandwidth for category scale,
    # user-supplied width for numeric.
    bw_attr = getattr(cat_scale, "bandwidth", None)
    if bw_attr is not None:
        bw = bw_attr
    elif width is not None:
        bw = abs(cat_scale(width) - cat_scale(0))
    else:
        raise ValueError(
            f"annotation_strip on a non-categorical {orient} scale needs "
            f"`width=<data-units>` (e.g. `width=1.0` for unit-spaced "
            f"integer positions)."
        )

    out = []
    for pos, v in zip(a["positions"], a["values"]):
        cp = cat_scale(pos)
        c_lo = cp - bw / 2
        c_inner = c_lo + bw * cat_pad
        c_inner_w = bw * (1 - 2 * cat_pad)

        # Map (cat-axis, orth-axis) → (x, y) based on orientation.
        if orient == "y":
            x0, y0, w, h = o_inner, c_inner, h_inner_orth, c_inner_w
        else:
            x0, y0, w, h = c_inner, o_inner, c_inner_w, h_inner_orth

        if absent_fill is not None:
            out.append(rect(x0, y0, w, h, fill=absent_fill))
        if v is None or v == "":
            continue
        fill = palette.get(v, fallback)
        out.append(rect(x0, y0, w, h, fill=fill))
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
    """Decorative strip: hide spines + the position-axis tick marks. If
    `name=` is given, use it as a single tick label on the ORTHOGONAL
    axis (at the band center); otherwise hide that axis entirely. The
    caller can override any of this with their own `xticks(...)` /
    `yticks(...)` after the artist call (e.g. to surface sample labels
    under the bottom row of a stack)."""
    orient = kw.get("orient", "x")
    name = kw.get("name")
    out = [("spines", [], {"top": False, "right": False,
                           "bottom": False, "left": False})]
    # Position axis: keep auto category labels but drop tick marks.
    # Orthogonal axis: collapse to a single `name=` label or hide.
    pos_ticks  = "yticks" if orient == "y" else "xticks"
    orth_ticks = "xticks" if orient == "y" else "yticks"
    out.append((pos_ticks, [None], {"marks": False}))
    if name is not None:
        out.append((orth_ticks, [[0.5], [name]], {"marks": False}))
    else:
        out.append((orth_ticks, [[]], {}))
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
