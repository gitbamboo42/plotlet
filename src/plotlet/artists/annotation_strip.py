"""Custom artist: annotation strip.

A row or column of cells encoding one value per position (band mode) or
per contiguous run of equal values (block mode). The default is
horizontal (positions along the x axis), designed to align with a host
panel above or below via `share_x` — sample-group bars on top of a
heatmap, regime tags above a time series, cluster labels alongside a
dendrogram, score tracks aligned with a coverage plot, group titles
above a split heatmap, etc. Pass `orientation="y"` for a vertical column.

Each cell can carry any combination of fill, text, and border:

- **Fill** (categorical via `palette={...}` or continuous via
  `cmap=...`). cmap is band-mode only — per-block cmap aggregates
  would mask within-block variation.
- **Text** (`text=True` shows the value; `text="other_col"` pulls
  display text from a different column). Position+rotation controlled
  by `side=`, `rotation=`, `fontsize=`, `text_color=`, `text_pad=`.
- **Border** (`cell_border="#999"` or `{"color":..., "width":...}`).
  In block mode with text only, the border outlines each block.

Three input shapes for the position axis:

- **Categorical** (heatmap-style): pass `position=` as a column of
  category names; cell width comes from the category scale's bandwidth.
- **Numeric uniform** (time-series-style): pass `position=` as numbers
  and set `width=` (scalar) in data units of the position axis.
- **Numeric interval** (cytoband / sector / gene-track style): pass
  `x1=`, `x2=` instead of `position=`. Each row's cell spans
  ``[x1, x2]`` — variable widths.

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
    # variable-width interval strip (cytobands, sector bars, gene tracks)
    c.annotation_strip(df, x1="start", x2="end", value="stain",
                       palette={...}, text=True)

`None` / `""` (or NaN in cmap mode) means missing data — drawn as
`absent_fill` if set, otherwise transparent.

In block mode, runs are computed per-contiguous-value (not per unique
value): `[A, B, A, B]` produces four blocks, each rendered with its own
label/fill. Pair with `c.sectors({cluster: [members]}, axis=...)` on the
host heatmap so the cluster machinery groups equal values into single
runs.
"""

import math

from ..registry import ArtistSpec, add_artist, declare_coord_support
from ..utils import pack_opts, to_list
from ..draw import rect, resolve_color
from ..draw import colormap, ContinuousNorm
from ..draw import text_path, cap_height, descender
from .._splits import block_bbox_1d, blocks as _blocks


_VALID_SIDES = {"x": {"bottom", "top"}, "y": {"left", "right"}}
_DEFAULT_SIDE = {"x": "bottom", "y": "right"}


def annotation_strip_record(data=None,
                            # input columns — consumed here at record
                            position=None, x1=None, x2=None, value=None,
                            # layout/mode switches — consumed at record
                            orientation="x", mode="band", text=None,
                            side=None, vmin=None, vmax=None,
                            # style — packed into opts for draw/legend
                            palette=None, cmap=None, norm=None, center=None,
                            width=None, x_padding=None, y_padding=None,
                            absent_fill=None, cell_border=None,
                            fontsize=None, text_color=None, rotation=None,
                            text_pad=None, name=None, label=None,
                            legend=None):
    position_col = position
    x1_col       = x1
    x2_col       = x2
    value_col    = value
    if data is None or value_col is None:
        raise TypeError("annotation_strip requires data= and value=.")
    interval_mode = x1_col is not None or x2_col is not None
    if interval_mode:
        if position_col is not None:
            raise TypeError(
                "annotation_strip: pass either position= (point + width) "
                "or x1=/x2= (interval), not both."
            )
        if x1_col is None or x2_col is None:
            raise TypeError(
                "annotation_strip interval mode requires both x1= and x2=."
            )
        xs1 = to_list(data[x1_col])
        xs2 = to_list(data[x2_col])
        if len(xs1) != len(xs2):
            raise ValueError(
                f"annotation_strip: x1 ({len(xs1)}) and x2 ({len(xs2)}) "
                f"must be the same length."
            )
        # Keep xs1 / xs2 untouched (preserves SectoredValue tags so the
        # scale projects each edge unambiguously). `positions` carries
        # the float midpoint for text anchoring (interior point — no
        # sector boundary to worry about), `widths` is just a presence
        # signal for the draw branch.
        positions = [(float(a) + float(b)) / 2 for a, b in zip(xs1, xs2)]
        widths    = [(float(b) - float(a))     for a, b in zip(xs1, xs2)]
    else:
        if position_col is None:
            raise TypeError(
                "annotation_strip requires position= (or x1=/x2= for "
                "variable-width intervals)."
            )
        positions = to_list(data[position_col])
        widths    = None
    values = to_list(data[value_col])
    if len(positions) != len(values):
        raise ValueError(
            f"annotation_strip: positions ({len(positions)}) and "
            f"values ({len(values)}) must be the same length."
        )
    orient = orientation
    if orient not in ("x", "y"):
        raise ValueError(
            f"annotation_strip: orientation= must be 'x' or 'y'; got {orient!r}."
        )
    if palette is not None and cmap is not None:
        raise ValueError(
            "annotation_strip: pass either palette= (categorical mode) "
            "or cmap= (continuous mode), not both."
        )
    if palette:
        palette = {k: resolve_color(v) for k, v in palette.items()}
    # mode=: "band" (default) one cell per position; "block" one cell per
    # contiguous run of equal values (per-run, not per-unique-value — see
    # `_splits.group_order` for the permuting variant).
    if mode not in ("band", "block"):
        raise ValueError(
            f"annotation_strip: mode= must be 'band' or 'block'; got {mode!r}."
        )
    if mode == "block" and cmap is not None:
        raise ValueError(
            "annotation_strip: mode='block' does not support cmap= "
            "(per-block aggregate would mask within-block variation). "
            "Use mode='band' for cmap fills."
        )
    # text=: None/False → no per-cell text; True → use `value` column as
    # text; str → name of a separate column to read text from.
    text_spec = text
    text_values = None
    text_side = None
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
        # side= default depends on orientation — resolve here.
        text_side = side or _DEFAULT_SIDE[orient]
        if text_side not in _VALID_SIDES[orient]:
            raise ValueError(
                f"annotation_strip: side={text_side!r} invalid for orientation={orient!r}; "
                f"expected one of {sorted(_VALID_SIDES[orient])}."
            )
    # Precompute vmin/vmax for cmap mode so the legend gradient and the
    # draw step agree on the range without recomputing.
    res_vmin = res_vmax = None
    if cmap is not None:
        if norm == "log":
            flat = [v for v in values if isinstance(v, (int, float)) and v == v and v > 0]
        else:
            flat = [v for v in values if isinstance(v, (int, float)) and v == v]
        if flat:
            res_vmin = vmin if vmin is not None else min(flat)
            res_vmax = vmax if vmax is not None else max(flat)
        else:
            res_vmin = vmin if vmin is not None else (1.0 if norm == "log" else 0.0)
            res_vmax = vmax if vmax is not None else (10.0 if norm == "log" else 1.0)
    # In block mode, find boundaries where consecutive values differ.
    # `block_bbox_1d` consumes this list to yield per-block pixel extents.
    run_bounds = None
    if mode == "block":
        if not palette and text_values is None:
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
        "_vmin": res_vmin,
        "_vmax": res_vmax,
        "_text_values": text_values,
        "_side": text_side,
        "_mode": mode,
        "_run_bounds": run_bounds,
        "_widths": widths,
        "_xs1": xs1 if interval_mode else None,
        "_xs2": xs2 if interval_mode else None,
        "opts": pack_opts(palette=palette, cmap=cmap, norm=norm,
                          center=center, width=width,
                          x_padding=x_padding, y_padding=y_padding,
                          absent_fill=absent_fill, cell_border=cell_border,
                          fontsize=fontsize, text_color=text_color,
                          rotation=rotation, text_pad=text_pad,
                          name=name, label=label, legend=legend),
    }


def _position_domain(a):
    """Position-axis domain: midpoints in uniform mode; outer cell
    edges in interval mode so autoscale fits the actual extents."""
    widths = a.get("_widths")
    if widths is None:
        return list(a["positions"])
    edges = []
    for p, w in zip(a["positions"], widths):
        edges.append(p - w / 2)
        edges.append(p + w / 2)
    return edges


def annotation_strip_xdomain(a):
    # Position axis carries the categories/numeric ticks; the orthogonal
    # axis spans [0, 1] (the cell's extent on its decorative side).
    if a.get("_orient") == "y":
        return [0, 1]
    return _position_domain(a)


def annotation_strip_ydomain(a):
    if a.get("_orient") == "y":
        return _position_domain(a)
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

    # Cell extent on the position axis: per-row in interval mode,
    # otherwise bandwidth (categorical) or scalar `width=` (numeric).
    widths = a.get("_widths")
    bw = None
    if widths is None:
        bw_attr = getattr(cat_scale, "bandwidth", None)
        if bw_attr is not None:
            bw = bw_attr
        elif width is not None:
            bw = abs(cat_scale(width) - cat_scale(0))
        else:
            raise ValueError(
                f"annotation_strip on a non-categorical {orient} scale needs "
                f"`width=<data-units>` (e.g. `width=1.0` for unit-spaced "
                f"integer positions) or x1=/x2= for variable-width intervals."
            )

    xs1 = a.get("_xs1")
    xs2 = a.get("_xs2")

    def _cell_extent_px(i, pos):
        """Pixel [c_lo, c_hi] for cell `i` on the position axis."""
        if widths is not None:
            a_px = cat_scale(xs1[i])    # SectoredValue → unambiguous
            b_px = cat_scale(xs2[i])
            return min(a_px, b_px), max(a_px, b_px)
        cp = cat_scale(pos)
        return cp - bw / 2, cp + bw / 2

    border = _resolve_cell_border(opts.get("cell_border"))
    stroke_kw = ({"stroke": border[0], "stroke_width": border[1]}
                 if border else {})
    # Coord-native pass-through: under a non-affine coord (e.g.
    # CircularCoordinate), rects subdivide-and-project so each band
    # follows the disc curve; text anchors project manually below so
    # the glyph sits at the right pixel (glyphs themselves don't warp).
    rect_kw = {"project": ctx.warp} if ctx.warp is not None else {}
    # Canvas center for tangent-rotation lookup in circular coord.
    # `ctx.warp(iw/2, ih)` only lands at the canvas center for an
    # `r_inner=0` sub-coord (e.g. chord_ribbon's inner disc). On a
    # ring sub-coord (r_inner > 0) it lands on the inner edge of the
    # band at t=0.5. To get the real center, take two points at t=0.25
    # and t=0.75 — always 180° apart regardless of wrap_gap_rad — and
    # average. None signals "no circular tangent" (linear / no coord).
    if ctx.warp is not None:
        _a = ctx.warp(0.25 * ctx.iw, ctx.ih)
        _b = ctx.warp(0.75 * ctx.iw, ctx.ih)
        _cx_px = (_a[0] + _b[0]) / 2
        _cy_px = (_a[1] + _b[1]) / 2
    else:
        _cx_px = _cy_px = None

    def _text_anchor(x, y):
        if ctx.warp is None:
            return (x, y), 0.0
        tx, ty = ctx.warp(x, y)
        # Recover the polar angle at the projected pixel and convert to
        # the tangent rotation, then upright-clamp into [-90, 90] so the
        # bottom-half of the ring reads naturally rather than upside down.
        # Mirrors `draw_x_sector_chrome` in _chrome_circular.py.
        ang = math.atan2(_cy_px - ty, tx - _cx_px)
        rot = math.degrees(ang) - 90.0
        rot = ((rot + 180.0) % 360.0) - 180.0
        if rot > 90.0:  rot -= 180.0
        if rot < -90.0: rot += 180.0
        return (tx, ty), rot

    out = []
    mode = a.get("_mode", "band")
    text_values = a.get("_text_values")

    if mode == "block":
        # Per-block iteration: one rect (palette only — cmap forbidden) +
        # optional centered text per contiguous run. In uniform mode the
        # block's pixel extent runs from `scale(positions[i0]) - bw/2`
        # to `scale(positions[i1-1]) + bw/2`; in interval mode it runs
        # from the first cell's left edge to the last cell's right
        # edge (per-row widths, so no shared `bw`).
        run_bounds = a.get("_run_bounds") or []
        fontsize = opts.get("fontsize", 11)
        text_color = opts.get("text_color", "#222")
        rotation = float(opts.get("rotation", 0))
        cap = cap_height(fontsize)
        desc = descender(fontsize)
        omid = (o_lo + o_hi) / 2
        if widths is None:
            block_iter = block_bbox_1d(
                cat_scale, a["positions"], bw, run_bounds)
        else:
            def _interval_blocks():
                for i0, i1 in _blocks(len(a["positions"]), run_bounds):
                    lo0, hi0 = _cell_extent_px(i0,     a["positions"][i0])
                    lo1, hi1 = _cell_extent_px(i1 - 1, a["positions"][i1 - 1])
                    yield i0, i1, min(lo0, lo1, hi0, hi1), max(lo0, lo1, hi0, hi1)
            block_iter = _interval_blocks()
        for i0, i1, c_lo_raw, c_hi_raw in block_iter:
            v = a["values"][i0]
            missing = v is None or v == ""
            block_w_raw = c_hi_raw - c_lo_raw
            c_lo = c_lo_raw + block_w_raw * cat_pad
            c_hi = c_hi_raw - block_w_raw * cat_pad
            c_w = c_hi - c_lo
            if orient == "y":
                x0, y0, w, h = o_inner, c_lo, h_inner_orth, c_w
            else:
                x0, y0, w, h = c_lo, o_inner, c_w, h_inner_orth
            if absent_fill is not None:
                out.append(rect(x0, y0, w, h, fill=absent_fill,
                                **stroke_kw, **rect_kw))
            if palette and not missing:
                fill = palette.get(v, fallback)
                out.append(rect(x0, y0, w, h, fill=fill,
                                **stroke_kw, **rect_kw))
            elif border and not missing and absent_fill is None:
                # Text-only block with cell_border= → outline the block.
                out.append(rect(x0, y0, w, h, **stroke_kw, **rect_kw))
            if text_values is not None:
                label = text_values[i0]
                if label is None or label == "":
                    continue
                cmid = (c_lo + c_hi) / 2
                if orient == "y":
                    tx, ty = omid, cmid + (cap - desc) / 2
                else:
                    tx, ty = cmid, omid + (cap - desc) / 2
                (tx, ty), tangent_rot = _text_anchor(tx, ty)
                out.append(text_path(label, tx, ty, fontsize,
                                     anchor="middle", color=text_color,
                                     rotate=rotation + tangent_rot))
        return "".join(out)

    for i, (pos, v) in enumerate(zip(a["positions"], a["values"])):
        c_lo_raw, c_hi_raw = _cell_extent_px(i, pos)
        cell_w_raw = c_hi_raw - c_lo_raw
        c_inner   = c_lo_raw + cell_w_raw * cat_pad
        c_inner_w = cell_w_raw * (1 - 2 * cat_pad)

        # Map (cat-axis, orth-axis) → (x, y) based on orientation.
        if orient == "y":
            x0, y0, w, h = o_inner, c_inner, h_inner_orth, c_inner_w
        else:
            x0, y0, w, h = c_inner, o_inner, c_inner_w, h_inner_orth

        if absent_fill is not None:
            out.append(rect(x0, y0, w, h, fill=absent_fill,
                            **stroke_kw, **rect_kw))
        missing = v is None or v == "" or (cmap_fn is not None and v != v)
        if missing:
            continue
        if cmap_fn is not None:
            r, g, b = cmap_fn(norm.to_unit(v))
            fill = f"rgb({r},{g},{b})"
        else:
            fill = palette.get(v, fallback)
        out.append(rect(x0, y0, w, h, fill=fill,
                        **stroke_kw, **rect_kw))

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
        # Interval mode (variable widths) centers text inside each cell
        # — sector / cytoband / gene tracks read better that way. Uniform
        # mode pins text to `side=` (default bottom/right for x/y) since
        # cells are typically too narrow to fit centered text.
        omid = (o_lo + o_hi) / 2
        center_text = widths is not None
        for pos, label in zip(a["positions"], text_values):
            if label is None or label == "":
                continue
            cp = cat_scale(pos)
            if center_text:
                if orient == "y":
                    x, y, anchor = omid, cp + (cap - desc) / 2, "middle"
                else:
                    x, y, anchor = cp, omid + (cap - desc) / 2, "middle"
            elif orient == "x":
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
            (x, y), tangent_rot = _text_anchor(x, y)
            out.append(text_path(label, x, y, fontsize, anchor=anchor,
                                 color=text_color,
                                 rotate=rotation + tangent_rot))
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
    """Decorative strip: hide the position-axis tick marks + collapse the
    orthogonal axis. If `name=` is given, use it as a single tick label
    on the orthogonal axis (at the band center); otherwise hide that
    axis entirely. The caller can override any of this with their own
    `xticks(...)` / `yticks(...)` after the artist call.

    Spines: hidden in point/categorical mode (decorative track —
    spines would add visual weight no one wants on a 1-pixel-tall
    column annotation). In interval mode (x1=/x2= variable widths —
    cytobands, sectors, gene tracks) the strip is the framing element,
    so spines stay on by default."""
    orient = kw.get("orientation", "x")
    name = kw.get("name")
    interval_mode = ("x1" in kw) or ("x2" in kw)
    out = []
    if not interval_mode:
        out.append(("spines", [], {"top": False, "right": False,
                                   "bottom": False, "left": False}))
    # Position axis defaults:
    # - Point / categorical mode: keep category labels (heatmap sample
    #   names etc.), just drop tick marks.
    # - Interval mode: the strip text labels each cell, so the position
    #   axis numeric labels are redundant — and on a CircularCoordinate
    #   they bloat the outer chrome (radial space reserved for tick
    #   text). Drop both marks and labels; users who want them back can
    #   call `c.xticks(...)` explicitly.
    pos_ticks  = "yticks" if orient == "y" else "xticks"
    orth_ticks = "xticks" if orient == "y" else "yticks"
    if interval_mode:
        out.append((pos_ticks, [[]], {}))
    else:
        out.append((pos_ticks, [None], {"marks": False}))
    if name is not None:
        out.append((orth_ticks, [[0.5], [name]], {"marks": False}))
    else:
        out.append((orth_ticks, [[]], {}))
    return out


add_artist(ArtistSpec(
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
declare_coord_support("Circular", ["annotation_strip"])
