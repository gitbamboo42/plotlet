"""Custom artist: annotation strip.

A row or column of colored cells encoding one value per position. The
default is horizontal (positions along the x axis), designed to align
with a host panel above or below via `share_x` — sample-group bars on
top of a heatmap, regime tags above a time series, cluster labels
alongside a dendrogram, score tracks aligned with a coverage plot, etc.
Pass `orient="y"` for a vertical column that aligns with a host panel
via `share_y` (per-row group labels next to a heatmap, marsilea-style
chunk strips).

Two color modes — same artist, the color spec chooses:

- **Categorical** (`palette={...}`): each unique value gets a discrete
  color via a label→color dict. Legend renders as swatches.
- **Continuous** (`cmap=...`): numeric values are mapped through a
  colormap with optional `vmin`/`vmax`/`norm`. Legend renders as a
  gradient strip (same shape as `heatmap` / `bubble_grid`).

Two scale kinds on the position axis:

- **Categorical** (heatmap-style): pass `positions` as category names.
  Cell size on that axis comes from `bandwidth`.
- **Numeric** (time-series-style): pass `positions` as numbers and set
  `width=` in data units of the position axis.

API:

    c.annotation_strip(positions, values, palette={...}, name="Group")
    c.annotation_strip(positions, values, cmap="viridis", name="Score")
    c.annotation_strip(positions, values, orient="y", ...)  # vertical

`None` / `""` (or NaN in cmap mode) means missing data — drawn as
`absent_fill` if set, otherwise transparent.
"""

SUMMARY = 'One-cell-per-position color strip (categorical palette or continuous cmap) for annotation tracks aligned to a host panel.'
from pathlib import Path

import plotlet as pt
from plotlet.draw import rect
from plotlet.draw.colormaps import colormap, _ContinuousNorm
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
    if kw.get("palette") is not None and kw.get("cmap") is not None:
        raise ValueError(
            "annotation_strip: pass either palette= (categorical mode) "
            "or cmap= (continuous mode), not both."
        )
    # Precompute vmin/vmax for cmap mode so the legend gradient and the
    # draw step agree on the range without recomputing.
    vmin = vmax = None
    if kw.get("cmap") is not None:
        norm = kw.get("norm", "linear")
        if norm == "log":
            flat = [v for v in values if isinstance(v, (int, float)) and v == v and v > 0]
        else:
            flat = [v for v in values if isinstance(v, (int, float)) and v == v]
        user_vmin = kw.get("vmin"); user_vmax = kw.get("vmax")
        if flat:
            vmin = user_vmin if user_vmin is not None else min(flat)
            vmax = user_vmax if user_vmax is not None else max(flat)
        else:
            vmin = user_vmin if user_vmin is not None else (1.0 if norm == "log" else 0.0)
            vmax = user_vmax if user_vmax is not None else (10.0 if norm == "log" else 1.0)
    return {
        "type": "annotation_strip",
        "positions": positions,
        "values": values,
        "_orient": orient,
        "_vmin": vmin,
        "_vmax": vmax,
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
    cmap_name = opts.get("cmap")
    cat_pad = opts.get("x_padding", 0.0)   # padding along the position axis
    orth_pad = opts.get("y_padding", 0.0)  # padding along the orthogonal axis
    absent_fill = opts.get("absent_fill")
    width = opts.get("width")
    fallback = ctx.color
    orient = a.get("_orient", "x")
    cat_scale  = ctx.y_scale if orient == "y" else ctx.x_scale
    orth_scale = ctx.x_scale if orient == "y" else ctx.y_scale

    # cmap-mode setup: precomputed range from record(); norm + LUT here.
    cmap_fn = norm = None
    if cmap_name is not None:
        cmap_fn = colormap(cmap_name)
        norm = _ContinuousNorm(a["_vmin"], a["_vmax"],
                               kind=opts.get("norm", "linear"),
                               center=opts.get("center"))

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
        missing = v is None or v == "" or (cmap_fn is not None and v != v)
        if missing:
            continue
        if cmap_fn is not None:
            r, g, b = cmap_fn(norm.to_unit(v))
            fill = f"rgb({r},{g},{b})"
        else:
            fill = palette.get(v, fallback)
        out.append(rect(x0, y0, w, h, fill=fill))
    return "".join(out)


def annotation_strip_legend_entries(a):
    opts = a["opts"]
    # cmap mode emits its own gradient via legend_gradient.
    if opts.get("cmap") is not None:
        return []
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


def annotation_strip_legend_gradient(a):
    opts = a["opts"]
    if opts.get("cmap") is None:
        return None
    legend_opts = opts.get("legend") or {}
    return {
        "kind": "continuous",
        "cmap": opts["cmap"],
        "vmin": a["_vmin"],
        "vmax": a["_vmax"],
        "norm": opts.get("norm", "linear"),
        "center": opts.get("center"),
        "label": legend_opts.get("label") or opts.get("name"),
        "ticks": legend_opts.get("ticks"),
    }


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
    legend_gradient=annotation_strip_legend_gradient,
    frame_defaults=annotation_strip_frame_defaults,
    uses_color_cycle=False,
    tight_domain=True,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Two stacked strips on the same sample axis: a categorical group track
    (palette) above a continuous score track (cmap). The cmap-mode strip
    pulls a gradient legend on the right via `pt.legend()`.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import math
    samples = [f"S{i+1:02d}" for i in range(12)]
    groups = (["ctrl"] * 4) + (["treat"] * 5) + (["resist"] * 3)
    palette = {"ctrl": pt.TAB10[0], "treat": pt.TAB10[1], "resist": pt.TAB10[2]}
    scores = [math.sin(i * 0.6) for i in range(12)]

    cat = pt.chart(data_width=420, data_height=24)
    cat.annotation_strip(samples, groups, palette=palette, name="Treatment")
    cat.xticks([])

    cont = pt.chart(data_width=420, data_height=24)
    cont.annotation_strip(samples, scores, cmap="RdBu_r",
                          vmin=-1, vmax=1, name="Score")
    cont.xticks(rotation=45)

    return pt.grid([[cat], [cont]]).share_x(True) | pt.legend()


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
