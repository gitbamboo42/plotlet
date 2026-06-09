"""Custom artist: annotation strip.

A row or column of cells encoding one value per position (band mode) or
per contiguous run of equal values (block mode). The default is
horizontal (positions along the x axis), designed to align with a host
panel above or below via `share_x` — sample-group bars on top of a
heatmap, regime tags above a time series, cluster labels alongside a
dendrogram, score tracks aligned with a coverage plot, group titles
above a split heatmap, etc. Pass `orient="y"` for a vertical column.

Each cell can carry any combination of fill, text, and border:

- **Fill** (categorical via `palette={...}` or continuous via
  `cmap=...`). cmap is band-mode only — per-block cmap aggregates
  would mask within-block variation.
- **Text** (`text=True` shows the value; `text="other_col"` pulls
  display text from a different column). Position+rotation controlled
  by `side=`, `rotation=`, `fontsize=`, `text_color=`, `text_pad=`.
- **Border** (`cell_border="#999"` or `{"color":..., "width":...}`).
  In block mode with text only, the border outlines each block.

Two scale kinds on the position axis:

- **Categorical** (heatmap-style): pass `positions` as category names.
- **Numeric** (time-series-style): pass `positions` as numbers and set
  `width=` in data units of the position axis.

API examples:

    # categorical color bar
    c.annotation_strip(df, position="col", value="col",
                       palette={...}, name="Group")
    # continuous score bar (band mode only)
    c.annotation_strip(df, position="col", value="col",
                       cmap="viridis", name="Score")
    # per-position text labels
    c.annotation_strip(df, position="col", value="col",
                       text=True, side="bottom", rotation=90)
    # per-block group titles with fill + text + border
    c.annotation_strip(df, position="col", value="group",
                       mode="block", palette={...}, text=True,
                       cell_border="#000", text_color="white")
    # per-block group titles, text only (no fill, no border)
    c.annotation_strip(df, position="col", value="group",
                       mode="block", text=True)

`None` / `""` (or NaN in cmap mode) means missing data — drawn as
`absent_fill` if set, otherwise transparent.

In block mode, runs are computed per-contiguous-value (not per unique
value): `[A, B, A, B]` produces four blocks, each rendered with its own
label/fill. Pair with `column_split=`/`row_split=` on the host heatmap
so the cluster machinery groups equal values into single runs.
"""

SUMMARY = 'Annotation strip — categorical/continuous fill, optional per-cell text, optional border. Band mode (per position) or block mode (per contiguous run of equal values) for group titles.'
from pathlib import Path

import plotlet as pt
from plotlet.draw import rect, resolve_color
from plotlet.draw import colormap, ContinuousNorm
from plotlet.draw import text_path, cap_height, descender
from plotlet.utils import to_list
from plotlet._splits import block_bbox_1d


_VALID_SIDES = {"x": {"bottom", "top"}, "y": {"left", "right"}}
_DEFAULT_SIDE = {"x": "bottom", "y": "right"}


def annotation_strip_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "annotation_strip requires long-form input: "
            "c.annotation_strip(data=df, position='col', value='col')."
        )
    data = kw.pop("data", None)
    position_col = kw.pop("position", None)
    value_col = kw.pop("value", None)
    if data is None or position_col is None or value_col is None:
        raise TypeError("annotation_strip requires data=, position=, value=.")
    positions = to_list(data[position_col])
    values = to_list(data[value_col])
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
    if kw.get("palette"):
        kw = dict(kw)
        kw["palette"] = {k: resolve_color(v) for k, v in kw["palette"].items()}
    # mode=: "band" (default) one cell per position; "block" one cell per
    # contiguous run of equal values (per-run, not per-unique-value — see
    # `_splits.group_order` for the permuting variant).
    mode = kw.get("mode", "band")
    if mode not in ("band", "block"):
        raise ValueError(
            f"annotation_strip: mode= must be 'band' or 'block'; got {mode!r}."
        )
    if mode == "block" and kw.get("cmap") is not None:
        raise ValueError(
            "annotation_strip: mode='block' does not support cmap= "
            "(per-block aggregate would mask within-block variation). "
            "Use mode='band' for cmap fills."
        )
    # text=: None/False → no per-cell text; True → use `value` column as
    # text; str → name of a separate column to read text from.
    text_spec = kw.get("text")
    text_values = None
    side = None
    if text_spec not in (None, False):
        if text_spec is True:
            text_values = [None if v is None or (isinstance(v, float) and v != v)
                           else str(v) for v in values]
        elif isinstance(text_spec, str):
            if text_spec not in data:
                raise ValueError(
                    f"annotation_strip: text={text_spec!r} is not a column in data."
                )
            raw = to_list(data[text_spec])
            if len(raw) != len(positions):
                raise ValueError(
                    f"annotation_strip: text column {text_spec!r} length "
                    f"({len(raw)}) doesn't match positions ({len(positions)})."
                )
            text_values = [None if v is None or v == ""
                           else str(v) for v in raw]
        else:
            raise ValueError(
                f"annotation_strip: text= must be True, False, None, or a "
                f"column name; got {type(text_spec).__name__}."
            )
        side = kw.get("side") or _DEFAULT_SIDE[orient]
        if side not in _VALID_SIDES[orient]:
            raise ValueError(
                f"annotation_strip: side={side!r} invalid for orient={orient!r}; "
                f"expected one of {sorted(_VALID_SIDES[orient])}."
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
    # In block mode, find boundaries where consecutive values differ.
    # `block_bbox_1d` consumes this list to yield per-block pixel extents.
    run_bounds = None
    if mode == "block":
        if not kw.get("palette") and text_values is None:
            raise ValueError(
                "annotation_strip: mode='block' needs at least one of "
                "palette= or text= (otherwise the strip has no content)."
            )
        run_bounds = [i for i in range(1, len(values))
                      if values[i] != values[i-1]]
    return {
        "type": "annotation_strip",
        "positions": positions,
        "values": values,
        "_orient": orient,
        "_vmin": vmin,
        "_vmax": vmax,
        "_text_values": text_values,
        "_side": side,
        "_mode": mode,
        "_run_bounds": run_bounds,
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


def _resolve_cell_border(spec):
    """Normalize `cell_border=` kwarg to `(color, width)` or `None`.

    Accepts a color spec (string → width 1) or a `{color, width}` dict.
    """
    if spec in (None, False):
        return None
    if isinstance(spec, dict):
        return (resolve_color(spec.get("color", "#222")),
                float(spec.get("width", 1.0)))
    return (resolve_color(spec), 1.0)


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
        norm = ContinuousNorm(a["_vmin"], a["_vmax"],
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

    border = _resolve_cell_border(opts.get("cell_border"))
    stroke_kw = ({"stroke": border[0], "stroke_width": border[1]}
                 if border else {})

    out = []
    mode = a.get("_mode", "band")
    text_values = a.get("_text_values")

    if mode == "block":
        # Per-block iteration: one rect (palette only — cmap forbidden) +
        # optional centered text per contiguous run. `block_bbox_1d`
        # already accounts for split-gap pixels via `cat_scale(cats[i])`.
        run_bounds = a.get("_run_bounds") or []
        fontsize = opts.get("fontsize", 11)
        text_color = opts.get("text_color", "#222")
        rotation = float(opts.get("rotation", 0))
        cap = cap_height(fontsize)
        desc = descender(fontsize)
        omid = (o_lo + o_hi) / 2
        for i0, i1, c_lo_raw, c_hi_raw in block_bbox_1d(
                cat_scale, a["positions"], bw, run_bounds):
            v = a["values"][i0]
            missing = v is None or v == ""
            c_lo = c_lo_raw + bw * cat_pad
            c_hi = c_hi_raw - bw * cat_pad
            c_w = c_hi - c_lo
            if orient == "y":
                x0, y0, w, h = o_inner, c_lo, h_inner_orth, c_w
            else:
                x0, y0, w, h = c_lo, o_inner, c_w, h_inner_orth
            if absent_fill is not None:
                out.append(rect(x0, y0, w, h, fill=absent_fill, **stroke_kw))
            if palette and not missing:
                fill = palette.get(v, fallback)
                out.append(rect(x0, y0, w, h, fill=fill, **stroke_kw))
            elif border and not missing and absent_fill is None:
                # Text-only block with cell_border= → outline the block.
                out.append(rect(x0, y0, w, h, **stroke_kw))
            if text_values is not None:
                label = text_values[i0]
                if label is None or label == "":
                    continue
                cmid = (c_lo + c_hi) / 2
                if orient == "y":
                    tx, ty = omid, cmid + (cap - desc) / 2
                else:
                    tx, ty = cmid, omid + (cap - desc) / 2
                out.append(text_path(label, tx, ty, fontsize,
                                     anchor="middle", color=text_color,
                                     rotate=rotation))
        return "".join(out)

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
            out.append(rect(x0, y0, w, h, fill=absent_fill, **stroke_kw))
        missing = v is None or v == "" or (cmap_fn is not None and v != v)
        if missing:
            continue
        if cmap_fn is not None:
            r, g, b = cmap_fn(norm.to_unit(v))
            fill = f"rgb({r},{g},{b})"
        else:
            fill = palette.get(v, fallback)
        out.append(rect(x0, y0, w, h, fill=fill, **stroke_kw))

    # Optional per-cell text overlay. Centered along the position axis
    # with side= picking which orthogonal edge to anchor against.
    # Unrotated text uses cap-height padding from the inner edge;
    # rotated text switches to an end-anchored placement so the rotated
    # body sits inside the strip.
    if text_values is not None:
        side = a["_side"]
        fontsize = opts.get("fontsize", 11)
        text_color = opts.get("text_color", "#222")
        rotation = float(opts.get("rotation", 0))
        text_pad = float(opts.get("text_pad", 3))
        cap = cap_height(fontsize)
        desc = descender(fontsize)
        for pos, label in zip(a["positions"], text_values):
            if label is None or label == "":
                continue
            cp = cat_scale(pos)
            if orient == "x":
                x = cp
                if side == "bottom":
                    if rotation == 0:
                        anchor, y = "middle", o_hi - desc - text_pad
                    else:
                        anchor, y = "start", o_hi - text_pad
                else:  # "top"
                    if rotation == 0:
                        anchor, y = "middle", o_lo + cap + text_pad
                    else:
                        anchor, y = "end", o_lo + text_pad
            else:  # orient == "y"
                if side == "right":
                    anchor, x = "end", o_hi - text_pad
                else:  # "left"
                    anchor, x = "start", o_lo + text_pad
                y = cp + (cap - desc) / 2
            out.append(text_path(label, x, y, fontsize, anchor=anchor,
                                 color=text_color, rotate=rotation))
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

    Three stacked strips on the same sample axis:

    1. Block-mode group titles with palette fill + text + border.
    2. Band-mode categorical strip (one cell per sample, palette fill).
    3. Band-mode continuous strip with cmap and a gradient legend.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import math
    samples = [f"S{i+1:02d}" for i in range(12)]
    groups = (["ctrl"] * 4) + (["treat"] * 5) + (["resist"] * 3)
    palette = {"ctrl": pt.TAB10[0], "treat": pt.TAB10[1], "resist": pt.TAB10[2]}
    scores = [math.sin(i * 0.6) for i in range(12)]

    df = {"sample": samples, "group": groups, "score": scores}

    blocks = pt.chart(data_width=420, data_height=22)
    blocks.annotation_strip(df, position="sample", value="group",
                            mode="block", palette=palette, text=True,
                            text_color="white", cell_border="#222",
                            name="Cohort")
    blocks.xticks([])

    cat = pt.chart(data_width=420, data_height=24)
    cat.annotation_strip(df, position="sample", value="group",
                         palette=palette, name="Treatment")
    cat.xticks([])

    cont = pt.chart(data_width=420, data_height=24)
    cont.annotation_strip(df, position="sample", value="score",
                          cmap="RdBu_r", vmin=-1, vmax=1, name="Score")
    cont.xticks(rotation=45)

    return pt.grid([[blocks], [cat], [cont]]).share_x(True) | pt.legend()


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
