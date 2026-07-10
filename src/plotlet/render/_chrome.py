"""Panel chrome emission: spines, ticks, sector chrome, coord-owned frames.

Called from `core._render_inner` once per panel, between the data-layer pass
and the margin-band pass. ``emit_chrome`` returns a list of SVG-fragment
strings; the caller extends its own ``parts`` list with the result. Every
input arrives through the explicit keyword arguments — no module globals,
no implicit state.

Holds the *default* Cartesian chrome. Non-default coordinates own their
chrome in dedicated sibling modules — see ``_chrome_circular.py`` — and
``emit_chrome`` dispatches to them via the coord object's optional
``draw_frame`` / ``draw_x_frame`` hooks.
"""
from __future__ import annotations

import math

from .._spec import SPEC, _FRAME, _FONTSPEC, _PADSPEC
from ..draw import (resolve_color, text_path, segment,
                   measure_text, cap_height, descender, tick_band_height,
                   rotated_label_bbox, text_block_height)
from .. import _regions

_SECTORSPEC = SPEC["sectors"]


def chrome_stack_extents(st, inp):
    """Inside-out walks through the chrome stack on each side of the
    data area. Returns ``{"top", "bottom", "left", "right"}`` — pixels
    of chrome past the data edge on that side, up to BUT NOT INCLUDING
    the outermost frame label (title / xlabel / ylabel).

    The x-axis band sits on whichever side ``inp.x_side`` names
    (``"bottom"`` default or ``"top"``); the y-axis band on
    ``inp.y_side`` (``"left"`` default or ``"right"``). Stack from data
    edge outward on the axis side: marks → tick band → sector band.

    One formula, used by both ``_required_margin`` (to reserve the band)
    and ``_render_inner`` (to position the outermost label past it).
    Keeps the two in lockstep without a DRY violation.
    """
    out_x = (_FRAME["tick_length"]
             if (st["x_marks"] and inp.x_ticks and st["x_direction"] != "in")
             else 0)
    out_y = (_FRAME["tick_length"]
             if (st["y_marks"] and inp.y_ticks and st["y_direction"] != "in")
             else 0)

    hide_x = inp.hide_b if inp.x_side == "bottom" else inp.hide_t
    hide_y = inp.hide_l if inp.y_side == "left"   else inp.hide_r

    x_band = out_x if not hide_x else 0
    has_xtl = (not inp.suppress_xt) and any(str(l) for l in inp.x_labels)
    if has_xtl:
        x_band += _FRAME["tick_pad"] + tick_band_height(inp.x_labels, inp.x_size, inp.x_rot,
                                                        inp.x_style, inp.x_weight)
    x_sec = st["x_sectors"]
    if x_sec is not None and x_sec.label and not hide_x:
        _sec_x_size = x_sec.fontsize if x_sec.fontsize is not None else _SECTORSPEC["label_size"]
        _sec_x_rot  = x_sec.rotation if x_sec.rotation is not None else 0
        _max_sec_w  = max((measure_text(str(n), _sec_x_size, inp.x_style, inp.x_weight)
                           for n in x_sec.names), default=_sec_x_size)
        _, _sec_h   = rotated_label_bbox(_max_sec_w, _sec_x_size, _sec_x_rot)
        top_gap = _SECTORSPEC["label_pad"] if has_xtl else _FRAME["tick_pad"]
        x_band += top_gap + _sec_h

    y_band = out_y if not hide_y else 0
    has_ytl = (not inp.suppress_yt) and any(str(l) for l in inp.y_labels)
    if has_ytl:
        max_ytl_w = max((measure_text(str(l), inp.y_size, inp.y_style, inp.y_weight)
                         for l in inp.y_labels), default=0.0)
        ytl_bbox_w, _ = rotated_label_bbox(max_ytl_w, inp.y_size, inp.y_rot)
        y_band += _FRAME["tick_pad"] + ytl_bbox_w
    y_sec = st["y_sectors"]
    if y_sec is not None and y_sec.label and not hide_y:
        _sec_y_size = y_sec.fontsize if y_sec.fontsize is not None else _SECTORSPEC["label_size"]
        sec_lbl_w = max((measure_text(str(n), _sec_y_size, inp.y_style, inp.y_weight)
                         for n in y_sec.names), default=0.0)
        top_gap = _SECTORSPEC["label_pad"] if has_ytl else _FRAME["tick_pad"]
        y_band += top_gap + sec_lbl_w

    return {
        "top":    x_band if inp.x_side == "top"    else 0,
        "bottom": x_band if inp.x_side == "bottom" else 0,
        "left":   y_band if inp.y_side == "left"   else 0,
        "right":  y_band if inp.y_side == "right"  else 0,
    }


def label_band_sizes(st, inp, dw, dh):
    """Per-side space (float px) for the axis-attached elements only —
    tick marks, tick labels, and the side-anchored label (xlabel /
    ylabel / title). Used by `_render_inner` to position those labels
    and the inline legend just outside the axis band, and by
    `_required_margin` to feed the layout engine.

    Returns ``(bands, chrome)``:

    - ``bands`` — ``{"top","right","bottom","left", *_xtl_overhang,
      *_ytl_overhang}``. The four side keys include axis band +
      xlabel/ylabel/title block; the overhang keys carry cross-side
      tick-label spillover that ``_required_margin`` maxes in.
    - ``chrome`` — the raw ``chrome_stack_extents`` dict (no
      label/title blocks). ``_render_inner`` hands it to
      ``emit_frame_labels`` so chrome geometry is computed once per
      render rather than twice.

    Cross-side overhang (centered title wider than ``dw``, rotated
    ylabel taller than ``dh``) is not in the side keys — those would
    displace axis-attached labels and outside legends from their natural
    slots. ``_required_margin`` recomputes the title/xlabel/ylabel
    overhang inline.

    ``inp`` is the resolved panel inputs from ``core._resolve_panel_inputs``
    — keeps the reservation and render passes walking identical numbers.
    """
    label_size = _FONTSPEC["label_size"]
    title_size = _FONTSPEC["title_size"]

    # Cross-axis spillover: per-tick label AABB widths/positions used to
    # compute the leftmost/rightmost x-tick label overhang past the data
    # area edges. The chrome stack itself is handled by `chrome_stack_extents`
    # below; here we just measure the bits `_required_margin` needs for
    # cross-axis reservation.
    has_xtl = (not inp.suppress_xt) and any(str(l) for l in inp.x_labels)
    if has_xtl:
        n_x = min(len(inp.x_ticks), len(inp.x_labels))
        x_tick_px = [inp.x_scale(t) for t in inp.x_ticks[:n_x]]
        if x_tick_px:
            i_left  = min(range(n_x), key=lambda i: x_tick_px[i])
            i_right = max(range(n_x), key=lambda i: x_tick_px[i])
            left_lbl_w,  _ = rotated_label_bbox(measure_text(str(inp.x_labels[i_left]),  inp.x_size, inp.x_style, inp.x_weight), inp.x_size, inp.x_rot)
            right_lbl_w, _ = rotated_label_bbox(measure_text(str(inp.x_labels[i_right]), inp.x_size, inp.x_style, inp.x_weight), inp.x_size, inp.x_rot)
            left_inset  = x_tick_px[i_left]
            right_inset = dw - x_tick_px[i_right]
        else:
            left_lbl_w = right_lbl_w = 0.0
            left_inset = right_inset = 0.0
    else:
        left_lbl_w = right_lbl_w = 0.0
        left_inset = right_inset = 0.0

    # y-axis cross-axis spillover (asymmetric for rot=0: cap/2 above,
    # cap/2 + descender below — rotated labels use the rotated AABB).
    has_ytl = (not inp.suppress_yt) and any(str(l) for l in inp.y_labels)
    if has_ytl:
        n_y = min(len(inp.y_ticks), len(inp.y_labels))
        y_tick_px = [inp.y_scale(t) for t in inp.y_ticks[:n_y]]
        if y_tick_px:
            i_top = min(range(n_y), key=lambda i: y_tick_px[i])
            i_bot = max(range(n_y), key=lambda i: y_tick_px[i])
            if inp.y_rot == 0:
                top_half_h    = cap_height(inp.y_size) / 2
                bottom_half_h = cap_height(inp.y_size) / 2 + descender(inp.y_size)
            else:
                _, top_h = rotated_label_bbox(measure_text(str(inp.y_labels[i_top]), inp.y_size, inp.y_style, inp.y_weight), inp.y_size, inp.y_rot)
                _, bot_h = rotated_label_bbox(measure_text(str(inp.y_labels[i_bot]), inp.y_size, inp.y_style, inp.y_weight), inp.y_size, inp.y_rot)
                top_half_h    = top_h / 2
                bottom_half_h = bot_h / 2
            top_inset    = y_tick_px[i_top]
            bottom_inset = dh - y_tick_px[i_bot]
        else:
            top_half_h = bottom_half_h = 0.0
            top_inset = bottom_inset = 0.0
    else:
        top_half_h = bottom_half_h = 0.0
        top_inset = bottom_inset = 0.0

    chrome = chrome_stack_extents(st, inp)

    # xlabel block: full glyph-block height (label_size for one line, one
    # line_height more per `\n`) + 2px gap + pad.xlabel. Lives on whichever
    # side x_side names; the title is its own block above the xlabel when
    # they share the top edge.
    xlabel_band = (2 + text_block_height(st["xlabel"], label_size) + _PADSPEC["xlabel"]
                   if st["xlabel"] and not inp.hide_xlabel else 0)
    ylabel_band = (2 + text_block_height(st["ylabel"], label_size) + _PADSPEC["ylabel"]
                   if st["ylabel"] and not inp.hide_ylabel else 0)

    # Title sits past the top chrome band + any top-side xlabel block,
    # then adds `pad.title` + its glyph-block height for its own block —
    # mirrors the inside-out walk in `emit_frame_labels` so reservation
    # matches positioning.
    title_top = (_PADSPEC["title"] + text_block_height(st["title"], title_size)
                 if (st["title"] and not inp.hide_t) else 0)
    top    = chrome["top"]    + (xlabel_band if inp.x_side == "top"    else 0) + title_top
    bottom = chrome["bottom"] + (xlabel_band if inp.x_side == "bottom" else 0)
    left   = chrome["left"]   + (ylabel_band if inp.y_side == "left"   else 0)
    right  = chrome["right"]  + (ylabel_band if inp.y_side == "right"  else 0)

    # Cross-axis tick-label spillover past the data edges. The x-tick labels
    # overhang the LEFT / RIGHT of the panel regardless of which edge they
    # sit on. The share of the rotated AABB that lands past the spine
    # depends on the anchor (see `_tick_label`):
    #   rot == 0  → anchor="middle"  → bbox extends w/2 each side
    #   rot >  0  → anchor="end"     → bbox extends fully LEFT  (0 right)
    #   rot <  0  → anchor="start"   → bbox extends fully RIGHT (0 left)
    # Top-side x ticks reverse end/start, which flips left/right_share.
    if inp.x_rot == 0:
        left_share, right_share = 0.5, 0.5
    elif inp.x_rot > 0:
        left_share, right_share = 1.0, 0.0
    else:
        left_share, right_share = 0.0, 1.0
    if inp.x_side == "top":
        left_share, right_share = right_share, left_share
    left_xtl_overhang  = (0.0 if inp.hide_l
                          else max(0.0, left_lbl_w  * left_share  - left_inset))
    right_xtl_overhang = (0.0 if inp.hide_r
                          else max(0.0, right_lbl_w * right_share - right_inset))

    # Vertical cross-axis spillover from horizontal y-tick labels.
    top_ytl_overhang    = (0.0 if inp.hide_t
                           else max(0.0, top_half_h    - top_inset))
    bottom_ytl_overhang = (0.0 if inp.hide_b
                           else max(0.0, bottom_half_h - bottom_inset))

    bands = {"top": top, "right": right, "bottom": bottom, "left": left,
             "left_xtl_overhang": left_xtl_overhang,
             "right_xtl_overhang": right_xtl_overhang,
             "top_ytl_overhang": top_ytl_overhang,
             "bottom_ytl_overhang": bottom_ytl_overhang}
    return bands, chrome


def emit_frame_labels(st, inp, iw, ih, chrome, *, top_legend_outset=0):
    """Emit xlabel / ylabel / title as SVG fragments. Walks inside-out
    from the data area: past the chrome band on the active side, past
    the label's own (2-px gap + label_size) block, then the title's
    (pad.title + title_size) block above the top-side xlabel (when
    ``inp.x_side == "top"``).

    ``top_legend_outset`` is the extra strip the title must hop over
    when a top-position inline legend sits between title and data
    (``leg_lh + legend_gap``); 0 otherwise.
    """
    label_size = _FONTSPEC["label_size"]
    title_size = _FONTSPEC["title_size"]
    text_color = _FONTSPEC["color"]
    parts = []
    xlabel_band = (2 + text_block_height(st["xlabel"], label_size) + _PADSPEC["xlabel"]
                   if st["xlabel"] and not inp.hide_xlabel else 0)

    # `text_path` anchors multi-line text at the FIRST line's baseline with
    # lines flowing downward. On bottom/right sides the block naturally
    # grows away from the data area, so single-line anchor formulas hold;
    # on top/left the anchor shifts outward by the extra-lines height
    # (`block - size`, zero for one line) so the LAST line lands in the
    # single-line slot and the block grows outward instead of into the axis.

    if st["xlabel"] and not inp.hide_xlabel:
        # Walk past the chrome stack + 2-px gap + full label_size, then back
        # up by descender to land on the baseline. Bottom: y positive past
        # ih. Top: y negative past 0 — same descender adjustment lands the
        # visible glyph bottom at the band's inner edge.
        xlabel_extra = text_block_height(st["xlabel"], label_size) - label_size
        if inp.x_side == "bottom":
            xlabel_baseline = ih + chrome["bottom"] + 2 + label_size - descender(label_size)
        else:
            xlabel_baseline = -(chrome["top"] + 2 + descender(label_size) + xlabel_extra)
        parts.append(text_path(st["xlabel"], iw / 2, xlabel_baseline,
                                label_size, anchor="middle", color=text_color,
                                tag="xlabel"))

    if st["ylabel"] and not inp.hide_ylabel:
        # Walk past the chrome stack + 2-px gap, then half label_size to
        # land on the rotated text's center. Left: cx negative (outside
        # panel on left) — under rotate=90 extra lines flow toward +x
        # (the panel), so the anchor shifts left by the extra-lines
        # height. Right: cx positive past iw, extra lines flow outward.
        ylabel_extra = text_block_height(st["ylabel"], label_size) - label_size
        if inp.y_side == "left":
            ylabel_cx = -(chrome["left"] + 2 + label_size / 2 + ylabel_extra)
        else:
            ylabel_cx = iw + chrome["right"] + 2 + label_size / 2
        parts.append(text_path(st["ylabel"], ylabel_cx, ih / 2,
                                label_size, anchor="middle",
                                color=text_color, rotate=90, tag="ylabel"))

    if st["title"] and not inp.hide_t:
        top_xlabel = xlabel_band if inp.x_side == "top" else 0
        outer = chrome["top"] + top_xlabel + top_legend_outset + _PADSPEC["title"]
        title_extra = text_block_height(st["title"], title_size) - title_size
        title_y = -(outer + descender(title_size) + title_extra)
        parts.append(text_path(st["title"], iw / 2, title_y, title_size,
                                anchor="middle", color=text_color,
                                tag="title"))

    return parts


# ---------------------------------------------------------------------------
# Tick label, minor-tick resolution, sectored spine segmentation
# (moved verbatim from core.py — only the chrome block uses these)
# ---------------------------------------------------------------------------

def _tick_label(s, x, y, size, angle, axis, side,
                fontstyle="normal", fontweight="normal",
                decoration="none", tag=None):
    """Render a single tick label as text-as-paths.

    Called for every tick label on every render — rotation is opt-in via
    `angle`. When `angle=0` (default) routes straight to `text_path` with
    the side-appropriate anchor; when nonzero, emits the glyphs at origin
    and wraps in `<g transform="translate(x,y) rotate(-angle)">`. The
    `angle` argument uses the convention positive = CCW on screen;
    SVG's native rotation is CW, so we negate at emission.

    `side` is the axis edge the label sits on: ``"bottom"|"top"`` for
    axis="x", ``"left"|"right"`` for axis="y". Anchor direction is
    chosen so the rotated text grows AWAY from the data area on every
    side; for the bottom edge, positive rotation (CCW) uses anchor="end"
    (text extends downward), and the other three sides mirror that rule.

    `fontstyle="italic"` / `fontweight="bold"` propagate through
    `text_path`, which resolves the variant face.
    `decoration="underline"|"overline"|"line-through"` adds a stroke line
    at the conventional offset."""
    color = _FONTSPEC["color"]
    if not angle:
        if axis == "x":
            anchor = "middle"
        else:
            anchor = "end" if side == "left" else "start"
        return text_path(s, x, y, size, anchor=anchor, color=color,
                         fontstyle=fontstyle, fontweight=fontweight,
                         decoration=decoration, tag=tag)
    if axis == "x":
        # On bottom: positive angle → anchor=end (text grows down-left
        # from anchor). On top: flipped — positive angle → anchor=start
        # so the text grows up-right, still away from the data area.
        if side == "bottom":
            anchor = "end" if angle > 0 else "start"
        else:
            anchor = "start" if angle > 0 else "end"
    else:
        # Right-side y-tick labels grow rightward; left-side grow left.
        anchor = "end" if side == "left" else "start"
    # Rotate via `text_path(..., rotate=angle)` so its bbox recording
    # captures the post-rotation hull. SVG-wise, rotating around the
    # anchor point (x, y) is equivalent to translating + rotating
    # around the origin; one transform attribute does both.
    # Horizontal centering on the tick: with anchor=end/start the
    # baseline endpoint sits at the anchor, but rotated text's visible
    # bbox is offset by `(cap - descender) / 2 * sin(angle)` away from
    # the anchor in the rotation direction. Shift the anchor x by the
    # opposite to land the label's visible center on the tick. The shift
    # direction inverts on top side because the anchor choice did too.
    if axis == "x" and angle:
        shift_sign = 1 if side == "bottom" else -1
        x = x + shift_sign * (cap_height(size) - descender(size)) / 2 * math.sin(math.radians(angle))
    return text_path(s, x, y, size, anchor=anchor, color=color,
                     fontstyle=fontstyle, fontweight=fontweight,
                     decoration=decoration, rotate=angle, tag=tag)


def _auto_minor_ticks(scale, major_ticks):
    """Default minor-tick positions for `scale`. Linear-shaped scales:
    4 subdivisions between adjacent majors; log: integer multipliers
    (2..9) within each decade."""
    kind = type(scale).__name__
    out = []
    if kind == "_LogScale":
        a = math.floor(scale.l0)
        b = math.ceil(scale.l1)
        for k in range(int(a), int(b) + 1):
            decade = 10 ** k
            for m in range(2, 10):
                v = m * decade
                if scale.d0 <= v <= scale.d1:
                    out.append(v)
        return out
    if len(major_ticks) < 2:
        return []
    nums = [float(t) for t in major_ticks]
    for i in range(len(nums) - 1):
        a, b = nums[i], nums[i + 1]
        step = (b - a) / 5
        for j in range(1, 5):
            out.append(a + step * j)
    return out


def _resolve_minor_ticks(user_minor, scale, major_ticks):
    """Map the user's `minor=` setting to a list of minor positions.
    None/False → none; True → auto from `_auto_minor_ticks`; sequence →
    use as-is."""
    if user_minor is None or user_minor is False:
        return []
    if user_minor is True:
        return _auto_minor_ticks(scale, major_ticks)
    return list(user_minor)


def _sector_pixel_spans(scale, sec):
    """Per-sector pixel spans ``[(lo_px, hi_px), ...]`` along ``sec``'s
    axis. Single source of the span geometry — sector walls, per-sector
    spine breaks, and coord ring-arc breaks must all end at identical
    pixels, so every consumer derives its spans here (a drifted copy is
    how rings bleed through gap whitespace).

    Continuous sectors read the sectored scale's own pixel strips, or
    synthesize spans from data-coord boundaries when the scale carries
    no gap. Categorical sectors span each group's member bands' outer
    edges (band center ± bandwidth/2).
    """
    if sec.kind == "continuous":
        if hasattr(scale, "sector_pixel_ranges"):
            return scale.sector_pixel_ranges()
        bs = sec.boundaries()
        return [(scale(bs[i]), scale(bs[i + 1]))
                for i in range(len(sec.names))]
    bw = scale.bandwidth
    spans = []
    for members in sec.members:
        px = [scale(m) for m in members]
        spans.append((min(px) - bw / 2, max(px) + bw / 2))
    return spans


def _sector_walls(spans, *, cyclic=False):
    """Internal-boundary wall positions for a sectored axis.

    ``spans`` is ``[(lo_0, hi_0), ...]`` — pixel range per sector. For each
    internal boundary we emit the right edge of sector i and the left edge
    of sector i+1 (paired walls bracketing the gap whitespace). At gap=0
    the pair coincides and renders as overlapping strokes; semi-transparent
    walls compensate with a proportionally smaller alpha. ``cyclic=True``
    adds the wrap boundary (last→first) for closed-ring coordinates.
    """
    walls = []
    n = len(spans)
    last = n if cyclic else n - 1
    for i in range(last):
        j = (i + 1) % n
        walls.append(spans[i][1])
        walls.append(spans[j][0])
    return walls


def _spine_segments(side, iw, ih, x_ranges, y_ranges):
    """Yield ``(x1, y1, x2, y2)`` per spine segment for ``side``.

    The spine is the outer envelope. When the parallel-to-spine axis is
    sectored (top/bottom + x-sectors, or left/right + y-sectors), the
    segment breaks per sector so each sector reads as its own bounded
    edge. Internal partitions (verticals when x is sectored, horizontals
    when y is sectored) are emitted separately as sector walls — see
    ``_sector_walls``.
    """
    if side in ("top", "bottom"):
        y_edge = 0 if side == "top" else ih
        if x_ranges is not None:
            for lo, hi in x_ranges:
                yield lo, y_edge, hi, y_edge
        elif y_ranges is not None:
            for lo, hi in y_ranges:
                y = lo if side == "top" else hi
                yield 0, y, iw, y
        else:
            yield 0, y_edge, iw, y_edge
    else:  # left / right
        x_edge = 0 if side == "left" else iw
        if y_ranges is not None:
            for lo, hi in y_ranges:
                yield x_edge, lo, x_edge, hi
        else:
            yield x_edge, 0, x_edge, ih


# ---------------------------------------------------------------------------
# Chrome entry point
# ---------------------------------------------------------------------------

def emit_chrome(*, st, inp, iw, ih,
                coord_object, coord_project,
                has_coord_frame, has_x_frame, has_x_sector_chrome,
                x_sec, y_sec):
    """Emit all panel chrome — spines, ticks, minor ticks, sector chrome,
    and (when present) the coordinate-owned ``draw_frame`` / ``draw_x_frame``
    hooks. Returns a list of SVG-fragment strings; caller extends its own
    ``parts``.

    ``inp`` carries the resolved per-panel axis context (scales, ticks,
    labels, sizes, rotations, suppress / hide flags, side routing);
    everything else here is pure render state pulled from ``st`` or
    the coord descriptor args.
    """
    x_scale, y_scale = inp.x_scale, inp.y_scale
    x_ticks, x_labels = inp.x_ticks, inp.x_labels
    y_ticks, y_labels = inp.y_ticks, inp.y_labels
    x_size, y_size = inp.x_size, inp.y_size
    x_rot, y_rot = inp.x_rot, inp.y_rot
    suppress_xt, suppress_yt = inp.suppress_xt, inp.suppress_yt
    hide_t, hide_b = inp.hide_t, inp.hide_b
    hide_l, hide_r = inp.hide_l, inp.hide_r
    x_style = st.get("x_fontstyle") or "normal"
    y_style = st.get("y_fontstyle") or "normal"
    x_weight = st.get("x_fontweight") or "normal"
    y_weight = st.get("y_fontweight") or "normal"
    x_decor = st.get("x_decoration") or "none"
    y_decor = st.get("y_decoration") or "none"
    x_dir, y_dir = st["x_direction"], st["y_direction"]
    x_marks, y_marks = st["x_marks"], st["y_marks"]

    # Spines — toggleable per side via `c.spines(top=False, right=False, ...)`,
    # restylable via `c.spines(top={"color": "red", "width": 1.5})`.
    # Tick marks on a hidden side are dropped too (an unanchored tick mark
    # reads as a render bug). On a joined share-pair side (hide_*), tick
    # marks AND tick labels are dropped — the panels read as merged, with
    # only the two parallel spines remaining (separated by the per-panel
    # floor on each joined side).
    # Style resolution for any spine target (a side name or "walls"):
    # per-target override > c.spines() base > _FRAME spec.
    def _pick(*candidates):
        for v in candidates:
            if v is not None: return v
        return None

    def _side_stroke(side):
        col = _pick(st[f"spine_{side}_color"], st["spine_base_color"], _FRAME["color"])
        w   = _pick(st[f"spine_{side}_width"], st["spine_base_width"], _FRAME["width"])
        return resolve_color(col), w

    def _side_dash(side):
        return _pick(st[f"spine_{side}_linestyle"], st["spine_base_linestyle"])

    parts = []

    # Panel region — recorded in the sink so layout-debug consumers
    # (`chart.regions()`, layout_diagram detail mode) can ask "did
    # anything overflow this panel?". Panel-local coords: (0, 0)
    # is the inner-margin corner; (iw, ih) is the data-area extent.
    _regions.record("rect", (0, 0, iw, ih), name="panel")

    # Spines — left side handed to the coordinate when draw_frame is present.
    # `_spine_segments` breaks each side into per-sector pieces when a
    # sectored scale is active, so each sector reads as its own bounded
    # subplot. Plain linear / categorical paths yield one full-side segment.
    _x_ranges = (x_scale.sector_pixel_ranges()
                 if hasattr(x_scale, "sector_pixel_ranges") else None)
    _y_ranges = (y_scale.sector_pixel_ranges()
                 if hasattr(y_scale, "sector_pixel_ranges") else None)
    for side in ("top", "bottom", "left", "right"):
        if side in ("left", "top", "right") and has_coord_frame:
            continue
        if side == "bottom" and has_x_frame:
            continue
        if not st[f"spine_{side}"]:
            continue
        col, w = _side_stroke(side)
        dash = _side_dash(side)
        for sx1, sy1, sx2, sy2 in _spine_segments(side, iw, ih,
                                                   _x_ranges, _y_ranges):
            parts.append(segment(sx1, sy1, sx2, sy2,
                                 color=col, width=w, dash=dash, tag="spine"))

    # Tick-mark endpoints relative to the spine. "in" goes inside the data
    # area, "out" goes outside, "inout" spans both sides at full length each.
    bot_in, bot_out = ih - _FRAME["tick_length"], ih + _FRAME["tick_length"]  # bottom spine offsets
    top_in, top_out = _FRAME["tick_length"], -_FRAME["tick_length"]           # top spine offsets
    if x_dir == "in":      x_bot_endpoints, x_top_endpoints = (ih, bot_in),  (0, top_in)
    elif x_dir == "out":   x_bot_endpoints, x_top_endpoints = (ih, bot_out), (0, top_out)
    else:                  x_bot_endpoints, x_top_endpoints = (bot_out, bot_in), (top_out, top_in)
    left_in, left_out  = _FRAME["tick_length"], -_FRAME["tick_length"]        # left spine offsets (x = 0)
    right_in, right_out = iw - _FRAME["tick_length"], iw + _FRAME["tick_length"]
    if y_dir == "in":      y_left_endpoints, y_right_endpoints = (0, left_in),  (iw, right_in)
    elif y_dir == "out":   y_left_endpoints, y_right_endpoints = (0, left_out), (iw, right_out)
    else:                  y_left_endpoints, y_right_endpoints = (left_out, left_in), (right_out, right_in)

    # x-axis — coordinate-aware (bottom spine + ticks + labels via
    # draw_x_frame) or standard Cartesian.
    if has_x_frame:
        # Normalize x tick positions to [0,1] t-space, mirroring draw_frame's
        # y_ticks_r convention. Works for any scale (linear, log, categorical).
        _x_ticks_t = [x_scale(t) / iw for t in x_ticks]
        parts.append(coord_object.draw_x_frame(
            coord_project, iw, ih,
            _x_ticks_t, x_labels,
            {
                "spine_color":   _FRAME["color"],
                "spine_width":   _FRAME["width"],
                "tick_length":   _FRAME["tick_length"],
                "tick_pad":      _FRAME["tick_pad"],
                "x_fontsize":    x_size,
                "font_color":    _FONTSPEC["color"],
                "x_marks":       x_marks,
                "x_show_labels": not suppress_xt,
                "x_fontstyle":   x_style,
                "x_fontweight":  x_weight,
                "x_decoration":  x_decor,
            }
        ))
    else:
        # x-ticks + labels — always Cartesian. Whole block flips wholesale
        # by `x_side`: spine attachment, tick-mark endpoints, label anchor.
        x_side = inp.x_side
        if x_side == "bottom":
            x_spine_side, x_hide_axis = "bottom", hide_b
            x_endpoints = x_bot_endpoints
            y_band_edge_sign = 1   # band grows downward from y=ih
            x_band_y0 = ih
        else:
            x_spine_side, x_hide_axis = "top", hide_t
            x_endpoints = x_top_endpoints
            y_band_edge_sign = -1  # band grows upward from y=0
            x_band_y0 = 0
        x_label_dy = (_FRAME["tick_pad"] if (x_dir == "in" or not x_marks)
                      else _FRAME["tick_length"] + _FRAME["tick_pad"])

        for t, lbl in zip(x_ticks, x_labels):
            x = x_scale(t)
            if x_marks:
                # Hidden sides (joined share-pair) drop tick marks too — marks
                # bleeding into the inter-panel gap read as visual clutter
                # when the two panels are meant to merge.
                if st[f"spine_{x_spine_side}"] and not x_hide_axis:
                    y1, y2 = x_endpoints
                    col, sw = _side_stroke(x_spine_side)
                    parts.append(segment(x, y1, x, y2, color=col, width=sw))
            # Drop only labels redundant with a sharing sibling. A small label
            # overflow into a joined neighbor's collapsed margin is acceptable.
            if not suppress_xt:
                # Visible edge of the label band sits `x_label_dy` past the
                # spine (flush with `tick_pad` past the visible mark, or the
                # spine itself when the mark is inward / suppressed). Anchor
                # offset uses `cap*cos` past that on bottom (rotating the
                # rect around the anchor pulls the top corner up by cap*cos),
                # and `-descender*cos` on top — mirror symmetry. Covers
                # rot=0 (full offset), rot=±90 (0), and intermediate angles.
                if x_side == "bottom":
                    y_lbl = ih + x_label_dy + cap_height(x_size) * math.cos(math.radians(x_rot))
                else:
                    y_lbl = -x_label_dy - descender(x_size) * math.cos(math.radians(x_rot))
                parts.append(_tick_label(str(lbl), x, y_lbl,
                                         x_size, x_rot, axis="x", side=x_side,
                                         fontstyle=x_style, fontweight=x_weight,
                                         decoration=x_decor,
                                         tag="tick-x"))

        # Minor ticks — shorter than majors (frame.minor_tick_ratio), no
        # labels. Emit only when the user opted in via xticks(minor=True) or
        # xticks(minor=[...]).
        x_minor = _resolve_minor_ticks(st["x_minor"], x_scale, x_ticks)
        if x_minor and x_marks and st[f"spine_{x_spine_side}"] and not x_hide_axis:
            minor_len = _FRAME["tick_length"] * _FRAME["minor_tick_ratio"]
            col, sw = _side_stroke(x_spine_side)
            for t in x_minor:
                x = x_scale(t)
                if not math.isfinite(x):
                    continue
                # Endpoint pair on the active spine, signed by side: minor
                # tick lengths fan inside/outside the same way as majors.
                if x_dir == "in":
                    y1, y2 = x_band_y0, x_band_y0 - y_band_edge_sign * minor_len
                elif x_dir == "out":
                    y1, y2 = x_band_y0, x_band_y0 + y_band_edge_sign * minor_len
                else:
                    y1, y2 = x_band_y0 + y_band_edge_sign * minor_len, x_band_y0 - y_band_edge_sign * minor_len
                parts.append(segment(x, y1, x, y2, color=col, width=sw))

    # Sector chrome — internal walls + sector-name labels along the sectored
    # axis. Walls are conceptually side spines, so style resolves through
    # the same _side_stroke/_side_dash with "walls" as the target. The
    # c.spines(walls=False) toggle suppresses walls regardless of
    # `Sectors.divider`. Artists that span sectors (chord_links, ribbons)
    # also suppress walls via `ArtistSpec.crosses_sectors` — walls cutting
    # through cross-sector curves read as a layering bug.
    from ..registry import get_artist as _get_artist
    _crossers = any(
        (_spec := _get_artist(a["type"])) is not None and _spec.crosses_sectors
        for a in st["artists"]
    )
    if x_sec is not None and (x_sec.divider or x_sec.label):
        sec_col, sec_w = _side_stroke("walls")
        sec_dash = _side_dash("walls")
        sec_pad  = _SECTORSPEC["label_pad"]
        sec = x_sec
        spans = _sector_pixel_spans(x_scale, sec)
        if sec.kind == "continuous":
            label_xs = [x_scale(sec.center(n)) for n in sec.names]
        else:
            label_xs = [(lo + hi) / 2 for lo, hi in spans]
        divider_xs = _sector_walls(spans)
        if has_x_sector_chrome:
            # Coordinate owns x-sector chrome (e.g. ring → side walls per
            # sector bracketing the gap whitespace, computed via the same
            # `_sector_walls` helper but on cyclic t-space). Hand the coord
            # the normalized sector spans so it can build its own walls.
            #
            # x_chrome_extent: radial pixels past the outer arc already
            # consumed by tick marks + labels (drawn by draw_x_frame).
            # Mirrors the linear stacking rule (tick marks → tick labels →
            # sector labels, from spine outward) so sector labels clear tick
            # chrome without overlap. When zero (no ticks on this ring),
            # sector labels fall back to the plain tick_pad gap.
            _tl = _FRAME["tick_length"]
            _tp = _FRAME["tick_pad"]
            _has_x_labels = any(str(l) for l in x_labels) and not suppress_xt
            if _has_x_labels:
                # Tick labels are radial: inner edge at R+tl+tp, center at
                # R+tl+tp+w/2 (per label), outer edge at R+tl+tp+w. Use the
                # widest label as the conservative bound for stacking.
                _max_w = max((measure_text(str(l), x_size, x_style, x_weight)
                              for l in x_labels), default=0.0)
                x_chrome_extent = _tl + _tp + _max_w
            elif x_marks and x_ticks:
                x_chrome_extent = _tl
            else:
                x_chrome_extent = 0.0
            parts.append(coord_object.draw_x_sector_chrome(
                coord_project, iw, ih,
                [(lo / iw, hi / iw) for lo, hi in spans],
                [x / iw for x in label_xs],
                list(sec.names),
                {
                    "divider_color":     sec_col,
                    "divider_width":     sec_w,
                    "divider_dash":      sec_dash,
                    "tick_pad":          _tp,
                    "label_pad":         sec_pad,
                    "x_chrome_extent":   x_chrome_extent,
                    "label_fontsize":    sec.fontsize if sec.fontsize is not None else _SECTORSPEC["label_size"],
                    "label_fontcolor":   _FONTSPEC["color"],
                    "label_fontstyle":   x_style,
                    "label_fontweight":  x_weight,
                    "label_decoration":  x_decor,
                    "draw_dividers":     bool(sec.divider) and st["spine_walls"] and not _crossers,
                    "draw_labels":       bool(sec.label) and not suppress_xt,
                },
            ))
        else:
            if sec.divider and st["spine_walls"] and not _crossers:
                for x in divider_xs:
                    parts.append(segment(x, 0, x, ih,
                                         color=sec_col, width=sec_w, dash=sec_dash,
                                         tag="sector-divider"))
            if sec.label and not suppress_xt and not hide_b:
                # Sector label band sits flush against the spine when no
                # tick band is above it (continuous-no-user-ticks case);
                # otherwise it stacks below the tick band. Same rule for
                # categorical (always has cat labels above) and continuous
                # (has labels only when user supplied xticks). Uses the
                # rotation-aware tick band height — must match the
                # reservation in `_required_margin`.
                _sec_x_size = sec.fontsize if sec.fontsize is not None else _SECTORSPEC["label_size"]
                _sec_x_rot  = sec.rotation if sec.rotation is not None else 0
                has_xtl = any(str(l) for l in x_labels)
                # sec_baseline mirrors the _tick_label y_lbl formula:
                # cap_height * cos(rot) gives the y-offset from the band top to
                # the anchor — 0 at 90° (anchor is at the top, text hangs down),
                # cap_height at 0° (baseline sits one cap below the band top).
                _sec_cap_offset = cap_height(_sec_x_size) * math.cos(math.radians(_sec_x_rot))
                if has_xtl:
                    sec_baseline = (ih + _FRAME["tick_pad"]
                                    + tick_band_height(x_labels, x_size, x_rot,
                                                       x_style, x_weight)
                                    + sec_pad + _sec_cap_offset)
                else:
                    sec_baseline = ih + _FRAME["tick_pad"] + _sec_cap_offset
                for name, cx in zip(sec.names, label_xs):
                    parts.append(_tick_label(str(name), cx, sec_baseline,
                                             _sec_x_size, _sec_x_rot, axis="x",
                                             side="bottom",
                                             fontstyle=x_style, fontweight=x_weight,
                                             decoration=x_decor,
                                             tag="sector-label"))
    if y_sec is not None and (y_sec.divider or y_sec.label):
        sec_col, sec_w = _side_stroke("walls")
        sec_dash = _side_dash("walls")
        sec_pad  = _SECTORSPEC["label_pad"]
        sec = y_sec
        spans = _sector_pixel_spans(y_scale, sec)
        if sec.kind == "continuous":
            label_ys = [y_scale(sec.center(n)) for n in sec.names]
        else:
            label_ys = [(lo + hi) / 2 for lo, hi in spans]
        divider_ys = _sector_walls(spans)
        if sec.divider and st["spine_walls"]:
            for y in divider_ys:
                parts.append(segment(0, y, iw, y,
                                     color=sec_col, width=sec_w, dash=sec_dash,
                                     tag="sector-divider"))
        if sec.label and not suppress_yt and not hide_l:
            # Sector label column sits flush against the spine when no
            # tick label column exists to its inside; otherwise it stacks
            # past the tick labels. Same rule for categorical (always has
            # cat labels) and continuous (has labels only when user
            # supplied yticks).
            _sec_y_size = sec.fontsize if sec.fontsize is not None else _SECTORSPEC["label_size"]
            has_ytl = any(str(l) for l in y_labels)
            if has_ytl:
                ytl_w = max((measure_text(str(l), y_size, y_style, y_weight)
                             for l in y_labels), default=0.0)
                y_label_x = -(_FRAME["tick_pad"] + ytl_w + sec_pad)
            else:
                y_label_x = -_FRAME["tick_pad"]
            for name, cy in zip(sec.names, label_ys):
                parts.append(_tick_label(str(name), y_label_x,
                                         cy + cap_height(_sec_y_size) / 2,
                                         _sec_y_size, 0, axis="y",
                                         side="left",
                                         fontstyle=y_style, fontweight=y_weight,
                                         decoration=y_decor,
                                         tag="sector-label"))

    # y-axis — coordinate-aware (left spine + ticks + labels via draw_frame)
    # or standard Cartesian.
    if has_coord_frame:
        # Normalize y tick positions to [0,1] r-space so draw_frame works for
        # any scale (numeric, log, categorical) without knowing the scale type.
        _y_ticks_r = [(ih - y_scale(t)) / ih for t in y_ticks]
        # When the coord also owns the x-sector chrome, hand the y-axis the
        # same sector_ts so it can break its spines at gap boundaries
        # (each sector is a bounded arc, so the rings don't bleed
        # through gap whitespace). Cartesian / non-sector renders ignore it.
        _y_sector_ts = None
        if has_x_sector_chrome and x_sec is not None:
            _y_sector_ts = [(lo / iw, hi / iw)
                            for lo, hi in _sector_pixel_spans(x_scale, x_sec)]
        parts.append(coord_object.draw_frame(
            coord_project, iw, ih,
            _y_ticks_r, y_labels,
            {
                "spine_color":   _FRAME["color"],
                "spine_width":   _FRAME["width"],
                "tick_length":   _FRAME["tick_length"],
                "tick_pad":      _FRAME["tick_pad"],
                "y_fontsize":    y_size,
                "font_color":    _FONTSPEC["color"],
                "y_marks":       y_marks,
                "y_show_labels": not suppress_yt,
                "y_fontstyle":   y_style,
                "y_fontweight":  y_weight,
                "y_decoration":  y_decor,
                "y_side":        inp.y_side,
                "sector_ts":     _y_sector_ts,
                "spine_top":     st["spine_top"],
                "spine_bottom":  st["spine_bottom"],
            }
        ))
    else:
        # y-ticks + labels — Cartesian. Like the x-block above, flip wholesale
        # by `y_side`: spine attachment, tick-mark endpoints, label anchor.
        y_side = inp.y_side
        y_label_dx = (_FRAME["tick_pad"] if (y_dir == "in" or not y_marks)
                      else _FRAME["tick_length"] + _FRAME["tick_pad"])
        if y_side == "left":
            y_spine_side, y_hide_axis = "left", hide_l
            y_endpoints = y_left_endpoints
            x_band_edge_sign = -1  # band grows leftward from x=0
            y_band_x0 = 0
            y_label_x = -y_label_dx
        else:
            y_spine_side, y_hide_axis = "right", hide_r
            y_endpoints = y_right_endpoints
            x_band_edge_sign = 1   # band grows rightward from x=iw
            y_band_x0 = iw
            y_label_x = iw + y_label_dx

        for t, lbl in zip(y_ticks, y_labels):
            y = y_scale(t)
            if y_marks:
                if st[f"spine_{y_spine_side}"] and not y_hide_axis:
                    x1, x2 = y_endpoints
                    col, sw = _side_stroke(y_spine_side)
                    parts.append(segment(x1, y, x2, y, color=col, width=sw))
            if not suppress_yt:
                # `y + cap_height/2` places the baseline so the cap is vertically
                # centered on the tick line (cap top at y - cap/2, cap bottom at y + cap/2).
                parts.append(_tick_label(str(lbl), y_label_x, y + cap_height(y_size) / 2,
                                         y_size, y_rot, axis="y", side=y_side,
                                         fontstyle=y_style, fontweight=y_weight,
                                         decoration=y_decor,
                                         tag="tick-y"))

        y_minor = _resolve_minor_ticks(st["y_minor"], y_scale, y_ticks)
        if y_minor and y_marks and st[f"spine_{y_spine_side}"] and not y_hide_axis:
            minor_len = _FRAME["tick_length"] * _FRAME["minor_tick_ratio"]
            col, sw = _side_stroke(y_spine_side)
            for t in y_minor:
                y = y_scale(t)
                if not math.isfinite(y):
                    continue
                if y_dir == "in":
                    x1, x2 = y_band_x0, y_band_x0 - x_band_edge_sign * minor_len
                elif y_dir == "out":
                    x1, x2 = y_band_x0, y_band_x0 + x_band_edge_sign * minor_len
                else:
                    x1, x2 = y_band_x0 + x_band_edge_sign * minor_len, y_band_x0 - x_band_edge_sign * minor_len
                parts.append(segment(x1, y, x2, y, color=col, width=sw))

    return parts
