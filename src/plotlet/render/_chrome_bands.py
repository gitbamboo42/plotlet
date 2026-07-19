"""Chrome band geometry — the numbers half of panel chrome.

Pure derivations, no SVG: how far out each chrome layer sits
(`_axis_band_stack`, `radial_tick_chrome_extent`, `axis_label_band`),
where sector spans and walls fall along an axis (`_sector_pixel_spans`,
`sector_walls`), and the per-side margin reservation built from them
(`label_band_sizes`, read by `_resolution._required_margin` and
`emit._render_inner`). The drawing half (`_chrome_emit.py`) and the
circular chrome (`_chrome_circular.py`, `coordinates.py`) import the
same derivations, so what the layout reserves and what the render draws
cannot drift. Visibility flags arrive decided on ``inp.chrome`` — see
`_chrome_visibility.resolve_axis_chrome`.
"""
from __future__ import annotations

from .._spec import SPEC, _FRAME, _FONTSPEC, _PADSPEC
from ..draw import (measure_text, cap_height, descender, tick_band_height,
                    rotated_label_bbox, text_block_height)

_SECTORSPEC = SPEC["sectors"]



# ---------------------------------------------------------------------------
# Band stacking — the ONE derivation of "how far out does each chrome
# layer sit", read by both the margin reservation and the emit pass
# ---------------------------------------------------------------------------

def _outward_mark_extent(pol, ticks):
    """Pixels a tick mark extends outside the data edge — 0 when the
    marks point inward, are suppressed, or there are no ticks. `pol` is
    one axis dict from ``inp.chrome`` (see `resolve_axis_chrome`)."""
    return _FRAME["tick_length"] if (pol["outward_mark"] and ticks) else 0


def _axis_band_stack(*, mark, label_extent=0.0, has_labels=False,
                    sector_extent=0.0, has_sector_labels=False):
    """The inside-out walk through a linear axis chrome band: data edge
    → outward tick mark → tick-label band → sector-label band.

    Callers measure their own extents (rotation-aware band height on x,
    label width on y); this function owns only the stacking rule, so
    the reservation (`_chrome_stack_extents`) and the emit helpers walk
    identical arithmetic — the geometry analog of
    `_chrome_visibility.resolve_axis_chrome` for visibility.

    ``has_labels`` gates the tick-label band and the flush rule: with
    no tick-label band the sector band sits flush at ``tick_pad`` past
    the mark instead of ``label_pad`` past the label band.

    Returns::

        {"label_off":        data edge → tick-label anchor edge,
         "tick_end":         data edge → outer edge of mark + label band,
         "total":            full band including the sector labels,
         "sector_off_spine": spine → sector-label band inner edge,
                             NOT counting the outward mark}

    ``sector_off_spine`` preserves what the sector emitters have always
    drawn: the sector band stacked from the spine, skipping the outward
    mark — ``mark`` px closer to the axis than the reservation
    (``total``) assumes. Known reserve-vs-draw skew; fold the mark in
    (and delete this key) the next time baselines are allowed to move.
    """
    tp = _FRAME["tick_pad"]
    lp = _SECTORSPEC["label_pad"]
    label_band = (tp + label_extent) if has_labels else 0.0
    sector_gap = lp if has_labels else tp
    tick_end = mark + label_band
    total = (tick_end + (sector_gap + sector_extent)
             if has_sector_labels else tick_end)
    return {
        "label_off": mark + tp,
        "tick_end": tick_end,
        "total": total,
        "sector_off_spine": (tp + (label_extent + lp)) if has_labels else tp,
    }


def radial_tick_chrome_extent(*, has_labels, max_label_w, has_marks):
    """Radial pixels past the outer arc consumed by circular tick
    chrome. Read by `_chrome_circular.chrome_pad` (canvas reservation) and the
    `draw_x_sector_chrome` hand-off (sector-label placement) — the two
    must stack identically or ring sector labels drift off their
    reserved band.

    The rule differs from the linear stack on purpose: labels sit at a
    fixed ``tick_length + tick_pad`` radial offset whether or not marks
    are drawn, and marks always point outward regardless of the tick
    direction state (see ``draw_x_chrome``) — hence ``has_marks``, not
    ``outward_mark``."""
    if has_labels:
        return _FRAME["tick_length"] + _FRAME["tick_pad"] + max_label_w
    if has_marks:
        return _FRAME["tick_length"]
    return 0.0



def axis_label_band(state, pol, axis):
    """Outer-label block (xlabel / ylabel) thickness: 2-px gap +
    glyph-block height + pad; 0 when the label is unset or hidden. One
    formula for the reservation (`label_band_sizes`) and the placement
    walk (`_chrome_emit.emit_frame_labels`), so the reserved block and
    the drawn block stay the same size."""
    if not pol["draw_axis_label"]:
        return 0
    return (2 + text_block_height(state[f"{axis}label"], _FONTSPEC["label_size"])
            + _PADSPEC[f"{axis}label"])



def title_band_stack(state):
    """Offsets of the subtitle / title blocks, measured from the outer
    edge of everything below them (top chrome + any top-side xlabel +
    any outside-top legend). One walk for the reservation
    (`label_band_sizes`) and the placement
    (`_chrome_emit.emit_frame_labels`): ``subtitle_off`` / ``title_off``
    are distances to each block's inner edge; ``total`` is the whole
    stack. The subtitle sits between the data area and the title
    (`pad.subtitle` apart when both are set)."""
    off = _PADSPEC["title"]
    subtitle_off = off
    if state["subtitle"]:
        off += text_block_height(state["subtitle"], _FONTSPEC["subtitle_size"])
        if state["title"]:
            off += _PADSPEC["subtitle"]
    title_off = off
    if state["title"]:
        off += text_block_height(state["title"], _FONTSPEC["title_size"])
    return {"subtitle_off": subtitle_off, "title_off": title_off, "total": off}


# ---------------------------------------------------------------------------
# Sector span geometry — positions along a sectored axis. Walls, per-
# sector spine breaks, and ring-arc breaks must all land on identical
# pixels, so every consumer derives them here
# ---------------------------------------------------------------------------

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


def sector_walls(spans, *, cyclic=False):
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



# ---------------------------------------------------------------------------
# Margin reservation — the per-side numbers `_required_margin` and
# `emit._render_inner` read
# ---------------------------------------------------------------------------

def _chrome_stack_extents(state, inp):
    """Inside-out walks through the chrome stack on each side of the
    data area. Returns ``{"top", "bottom", "left", "right"}`` — pixels
    of chrome past the data edge on that side, up to BUT NOT INCLUDING
    the outermost frame label (title / xlabel / ylabel).

    The x-axis band sits on whichever side ``inp.chrome["x"]["side"]``
    names (``"bottom"`` default or ``"top"``); the y-axis band on
    ``inp.chrome["y"]["side"]`` (``"left"`` default or ``"right"``).
    Stack from data edge outward on the axis side: marks → tick band →
    sector band.

    One formula, used by both ``_required_margin`` (to reserve the band)
    and ``_render_inner`` (to position the outermost label past it).
    Keeps the two in lockstep without a DRY violation.
    """
    x_pol, y_pol = inp.chrome["x"], inp.chrome["y"]

    # `inp.chrome` carries the decided flags (see `_chrome_visibility`)
    # and `_axis_band_stack` the stacking rule, so this reservation and
    # `emit_chrome` walk the same booleans and the same arithmetic —
    # only the band measurements are computed here.
    has_xtl = x_pol["draw_labels"] and any(str(l) for l in inp.x_labels)
    x_sec = state["x_sectors"]
    if x_pol["draw_sector_labels"]:
        _sec_x_size = x_sec.fontsize if x_sec.fontsize is not None else _SECTORSPEC["label_size"]
        _sec_x_rot  = x_sec.rotation if x_sec.rotation is not None else 0
        _max_sec_w  = max((measure_text(str(n), _sec_x_size, inp.x_style, inp.x_weight)
                           for n in x_sec.names), default=_sec_x_size)
        _, _sec_h   = rotated_label_bbox(_max_sec_w, _sec_x_size, _sec_x_rot)
    else:
        _sec_h = 0.0
    x_band = _axis_band_stack(
        mark=_outward_mark_extent(x_pol, inp.x_ticks),
        label_extent=(tick_band_height(inp.x_labels, inp.x_size, inp.x_rot,
                                       inp.x_style, inp.x_weight)
                      if has_xtl else 0.0),
        has_labels=has_xtl,
        sector_extent=_sec_h,
        has_sector_labels=x_pol["draw_sector_labels"])["total"]

    has_ytl = y_pol["draw_labels"] and any(str(l) for l in inp.y_labels)
    if has_ytl:
        max_ytl_w = max((measure_text(str(l), inp.y_size, inp.y_style, inp.y_weight)
                         for l in inp.y_labels), default=0.0)
        ytl_bbox_w, _ = rotated_label_bbox(max_ytl_w, inp.y_size, inp.y_rot)
    else:
        ytl_bbox_w = 0.0
    y_sec = state["y_sectors"]
    if y_pol["draw_sector_labels"]:
        _sec_y_size = y_sec.fontsize if y_sec.fontsize is not None else _SECTORSPEC["label_size"]
        sec_lbl_w = max((measure_text(str(n), _sec_y_size, inp.y_style, inp.y_weight)
                         for n in y_sec.names), default=0.0)
    else:
        sec_lbl_w = 0.0
    y_band = _axis_band_stack(
        mark=_outward_mark_extent(y_pol, inp.y_ticks),
        label_extent=ytl_bbox_w,
        has_labels=has_ytl,
        sector_extent=sec_lbl_w,
        has_sector_labels=y_pol["draw_sector_labels"])["total"]

    return {
        "top":    x_band if x_pol["side"] == "top"    else 0,
        "bottom": x_band if x_pol["side"] == "bottom" else 0,
        "left":   y_band if y_pol["side"] == "left"   else 0,
        "right":  y_band if y_pol["side"] == "right"  else 0,
    }


def label_band_sizes(state, inp, dw, dh):
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
    - ``chrome`` — the raw ``_chrome_stack_extents`` dict (no
      label/title blocks). ``_render_inner`` hands it to
      ``emit_frame_labels`` so chrome geometry is computed once per
      render rather than twice.

    Cross-side overhang (centered title wider than ``dw``, rotated
    ylabel taller than ``dh``) is not in the side keys — those would
    displace axis-attached labels and outside legends from their natural
    slots. ``_required_margin`` recomputes the title/xlabel/ylabel
    overhang inline.

    ``inp`` is the derived panel inputs from ``_resolution._derive_panel_inputs``
    — keeps the reservation and render passes walking identical numbers.
    """
    x_pol, y_pol = inp.chrome["x"], inp.chrome["y"]

    # Cross-axis spillover: per-tick label AABB widths/positions used to
    # compute the leftmost/rightmost x-tick label overhang past the data
    # area edges. The chrome stack itself is handled by `_chrome_stack_extents`
    # below; here we just measure the bits `_required_margin` needs for
    # cross-axis reservation.
    has_xtl = x_pol["draw_labels"] and any(str(l) for l in inp.x_labels)
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
    has_ytl = y_pol["draw_labels"] and any(str(l) for l in inp.y_labels)
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

    chrome = _chrome_stack_extents(state, inp)

    # xlabel / ylabel blocks (see `axis_label_band`). Each lives on
    # whichever side its axis band sits; the title is its own block
    # above a top-side xlabel.
    xlabel_band = axis_label_band(state, x_pol, "x")
    ylabel_band = axis_label_band(state, y_pol, "y")

    # Title/subtitle stack (see `title_band_stack`) sits past the top
    # chrome band + any top-side xlabel block. The title renders even on
    # a hidden-top joined edge (`hide_t` drops only the *redundant* axis
    # chrome — a title is the panel's identity, e.g. facet labels on the
    # lower rows of a shared-x grid).
    title_top = (title_band_stack(state)["total"]
                 if state["title"] or state["subtitle"] else 0.0)
    top    = chrome["top"]    + (xlabel_band if x_pol["side"] == "top"    else 0) + title_top
    bottom = chrome["bottom"] + (xlabel_band if x_pol["side"] == "bottom" else 0)
    left   = chrome["left"]   + (ylabel_band if y_pol["side"] == "left"   else 0)
    right  = chrome["right"]  + (ylabel_band if y_pol["side"] == "right"  else 0)

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
    if x_pol["side"] == "top":
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
