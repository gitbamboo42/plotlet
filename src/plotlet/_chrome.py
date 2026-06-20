"""Panel chrome emission: spines, ticks, sector chrome, coord-owned frames.

Called from `core._render_inner` once per panel, between the data-layer pass
and the margin-band pass. ``emit_chrome`` returns a list of SVG-fragment
strings; the caller extends its own ``parts`` list with the result. Every
input arrives through the explicit keyword arguments — no module globals,
no implicit state.

Holds the *default* Cartesian chrome. Non-default coordinates own their
chrome in dedicated sibling modules — see ``_chrome_linear.py``,
``_chrome_circular.py`` — and ``emit_chrome`` dispatches to them via the
coord object's optional ``draw_frame`` / ``draw_x_frame`` hooks.
"""
from __future__ import annotations

import math

from ._spec import SPEC, _FRAME, _FONTSPEC
from .draw import (resolve_color, text_path, segment,
                   measure_text, cap_height, descender, tick_band_height,
                   rotated_label_bbox)
from . import _regions

_SECTORSPEC = SPEC["sectors"]


def chrome_stack_extents(st, *,
                          x_ticks, x_labels, x_size, x_rot, suppress_xt,
                          y_ticks, y_labels, y_size, y_rot, suppress_yt,
                          hide_t, hide_b, hide_l, hide_r):
    """Inside-out walks through the chrome stack on each side of the
    data area. Returns ``{"top", "bottom", "left", "right"}`` — pixels
    of chrome past the data edge on that side, up to BUT NOT INCLUDING
    the outermost frame label (title / xlabel / ylabel).

    Stack on each side (inside → outside):

    - ``top``    : top tick marks  (title positions independently above)
    - ``bottom`` : marks → tick band → sector band
    - ``left``   : marks → tick band → sector band
    - ``right``  : right tick marks

    One formula, used by both ``_required_margin`` (to reserve the band)
    and ``_render_inner`` (to position the outermost label past it).
    Keeps the two in lockstep without a DRY violation.
    """
    out_x = (_FRAME["tick_length"]
             if (st["x_marks"] and x_ticks and st["x_direction"] != "in")
             else 0)
    out_y = (_FRAME["tick_length"]
             if (st["y_marks"] and y_ticks and st["y_direction"] != "in")
             else 0)

    bottom = out_x if not hide_b else 0
    has_xtl = (not suppress_xt) and any(str(l) for l in x_labels)
    if has_xtl:
        bottom += _FRAME["tick_pad"] + tick_band_height(x_labels, x_size, x_rot)
    x_sec = st["x_sectors"]
    if x_sec is not None and x_sec.label and not hide_b:
        top_gap = _SECTORSPEC["label_pad"] if has_xtl else _FRAME["tick_pad"]
        bottom += top_gap + cap_height(x_size) + descender(x_size)

    left = out_y if not hide_l else 0
    has_ytl = (not suppress_yt) and any(str(l) for l in y_labels)
    if has_ytl:
        max_ytl_w = max((measure_text(str(l), y_size) for l in y_labels),
                        default=0.0)
        ytl_bbox_w, _ = rotated_label_bbox(max_ytl_w, y_size, y_rot)
        left += _FRAME["tick_pad"] + ytl_bbox_w
    y_sec = st["y_sectors"]
    if y_sec is not None and y_sec.label and not hide_l:
        sec_lbl_w = max((measure_text(str(n), y_size) for n in y_sec.names),
                        default=0.0)
        top_gap = _SECTORSPEC["label_pad"] if has_ytl else _FRAME["tick_pad"]
        left += top_gap + sec_lbl_w

    top = out_x if (st["x_top"] and not hide_t) else 0
    right = out_y if (st["y_right"] and not hide_r) else 0
    return {"top": top, "bottom": bottom, "left": left, "right": right}


# ---------------------------------------------------------------------------
# Tick label, minor-tick resolution, sectored spine segmentation
# (moved verbatim from core.py — only the chrome block uses these)
# ---------------------------------------------------------------------------

def _tick_label(s, x, y, size, angle, axis,
                fontstyle="normal", decoration="none", tag=None):
    """Render a single tick label as text-as-paths.

    Called for every tick label on every render — rotation is opt-in via
    `angle`. When `angle=0` (default) routes straight to `text_path` with
    the side-appropriate anchor; when nonzero, emits the glyphs at origin
    and wraps in `<g transform="translate(x,y) rotate(-angle)">`. The
    `angle` argument uses the convention positive = CCW on screen;
    SVG's native rotation is CW, so we negate at emission.

    Anchor direction depends on axis + rotation sign so the rotated text
    always grows AWAY from the data area: for bottom x-tick labels,
    positive rotation (CCW) uses anchor="end" (text extends downward);
    negative rotation (CW) uses anchor="start" (also extends downward —
    without this, CW rotation would push labels into the chart body).

    `fontstyle="italic"` propagates through `text_path` for synthesized
    oblique tick labels (common bio convention for gene names).
    `decoration="underline"|"overline"|"line-through"` adds a stroke line
    at the conventional offset."""
    color = _FONTSPEC["color"]
    if not angle:
        anchor = "middle" if axis == "x" else "end"
        return text_path(s, x, y, size, anchor=anchor, color=color,
                         fontstyle=fontstyle, decoration=decoration,
                         tag=tag)
    if axis == "x":
        anchor = "end" if angle > 0 else "start"
    else:
        anchor = "end"
    # Rotate via `text_path(..., rotate=angle)` so its bbox recording
    # captures the post-rotation hull. SVG-wise, rotating around the
    # anchor point (x, y) is equivalent to translating + rotating
    # around the origin; one transform attribute does both.
    return text_path(s, x, y, size, anchor=anchor, color=color,
                     fontstyle=fontstyle, decoration=decoration,
                     rotate=angle, tag=tag)


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

def emit_chrome(*,
                st, iw, ih,
                x_scale, y_scale,
                x_ticks, x_labels, y_ticks, y_labels,
                panel_opts,
                coord_object, coord_project,
                has_coord_frame, has_x_frame, has_x_sector_chrome,
                x_sec, y_sec,
                suppress_xt, suppress_yt):
    """Emit all panel chrome — spines, ticks, minor ticks, sector chrome,
    and (when present) the coordinate-owned ``draw_frame`` / ``draw_x_frame``
    hooks. Returns a list of SVG-fragment strings; caller extends its own
    ``parts``.

    Keyword-only — font / style / direction locals are derived from ``st``
    inside this function (none of them are referenced after the chrome pass
    so there's no value in plumbing them through the call site).
    """
    tick_size = _FONTSPEC["tick_size"]
    x_size = st["x_fontsize"] if st["x_fontsize"] is not None else tick_size
    y_size = st["y_fontsize"] if st["y_fontsize"] is not None else tick_size
    x_rot = st["x_rotation"] or 0
    y_rot = st["y_rotation"] or 0
    x_style = st.get("x_fontstyle") or "normal"
    y_style = st.get("y_fontstyle") or "normal"
    x_decor = st.get("x_decoration") or "none"
    y_decor = st.get("y_decoration") or "none"
    x_dir, y_dir = st["x_direction"], st["y_direction"]
    x_marks, y_marks = st["x_marks"], st["y_marks"]

    hide_l, hide_r = panel_opts.hide_left, panel_opts.hide_right
    hide_t, hide_b = panel_opts.hide_top, panel_opts.hide_bottom

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
                "x_decoration":  x_decor,
            }
        ))
    else:
        # x-ticks + labels — always Cartesian
        for t, lbl in zip(x_ticks, x_labels):
            x = x_scale(t)
            if x_marks:
                # Hidden sides (joined share-pair) drop tick marks too — marks
                # bleeding into the inter-panel gap read as visual clutter
                # when the two panels are meant to merge.
                if st["spine_bottom"] and not hide_b:
                    y1, y2 = x_bot_endpoints
                    col, sw = _side_stroke("bottom")
                    parts.append(segment(x, y1, x, y2, color=col, width=sw))
                if st["spine_top"] and st["x_top"] and not hide_t:
                    y1, y2 = x_top_endpoints
                    col, sw = _side_stroke("top")
                    parts.append(segment(x, y1, x, y2, color=col, width=sw))
            # Drop only labels redundant with a sharing sibling. A small label
            # overflow into a joined neighbor's collapsed margin is acceptable.
            if not suppress_xt:
                # baseline = mark_end + tick_pad + cap_height, so the label's cap
                # top sits flush with `tick_pad` past the visible mark (or the
                # spine, when the mark is inward / suppressed). Mirrors
                # `y_label_x`'s handling above for consistency.
                x_label_dy = (_FRAME["tick_pad"] if (x_dir == "in" or not x_marks)
                              else _FRAME["tick_length"] + _FRAME["tick_pad"])
                parts.append(_tick_label(str(lbl), x,
                                         ih + x_label_dy + cap_height(x_size),
                                         x_size, x_rot, axis="x",
                                         fontstyle=x_style, decoration=x_decor,
                                         tag="tick-x"))

        # Minor ticks — shorter than majors (frame.minor_tick_ratio), no
        # labels. Emit only when the user opted in via xticks(minor=True) or
        # xticks(minor=[...]).
        x_minor = _resolve_minor_ticks(st["x_minor"], x_scale, x_ticks)
        if x_minor and x_marks:
            minor_len = _FRAME["tick_length"] * _FRAME["minor_tick_ratio"]
            for t in x_minor:
                x = x_scale(t)
                if not math.isfinite(x):
                    continue
                if st["spine_bottom"] and not hide_b:
                    col, sw = _side_stroke("bottom")
                    if x_dir == "in":      y1, y2 = ih, ih - minor_len
                    elif x_dir == "out":   y1, y2 = ih, ih + minor_len
                    else:                  y1, y2 = ih + minor_len, ih - minor_len
                    parts.append(segment(x, y1, x, y2, color=col, width=sw))
                if st["spine_top"] and st["x_top"] and not hide_t:
                    col, sw = _side_stroke("top")
                    if x_dir == "in":      y1, y2 = 0, minor_len
                    elif x_dir == "out":   y1, y2 = 0, -minor_len
                    else:                  y1, y2 = -minor_len, minor_len
                    parts.append(segment(x, y1, x, y2, color=col, width=sw))

    # Sector chrome — internal walls + sector-name labels along the sectored
    # axis. Walls are conceptually side spines, so style resolves through
    # the same _side_stroke/_side_dash with "walls" as the target. The
    # c.spines(walls=False) toggle suppresses walls regardless of
    # `Sectors.divider`. Artists that span sectors (chord_links, ribbons)
    # also suppress walls via `ArtistSpec.crosses_sectors` — walls cutting
    # through cross-sector curves read as a layering bug.
    from .registry import get_artist as _get_artist
    _crossers = any(
        (_spec := _get_artist(a["type"])) is not None and _spec.crosses_sectors
        for a in st["artists"]
    )
    if x_sec is not None and (x_sec.divider or x_sec.label):
        sec_col, sec_w = _side_stroke("walls")
        sec_dash = _side_dash("walls")
        sec_pad  = _SECTORSPEC["label_pad"]
        sec = x_sec
        if sec.kind == "continuous":
            if hasattr(x_scale, "sector_pixel_ranges"):
                spans = x_scale.sector_pixel_ranges()
            else:
                # Plain linear (no sector gap) — synthesize spans from
                # data-coord boundaries.
                bs = sec.boundaries()
                spans = [(x_scale(bs[i]), x_scale(bs[i + 1]))
                         for i in range(len(sec.names))]
            label_xs = [x_scale(sec.center(n)) for n in sec.names]
        else:
            bw = x_scale.bandwidth
            spans = []
            for members in sec.members:
                xs = [x_scale(m) for m in members]
                spans.append((min(xs) - bw / 2, max(xs) + bw / 2))
            label_xs = [(lo + hi) / 2 for lo, hi in spans]
        divider_xs = _sector_walls(spans)
        if has_x_sector_chrome:
            # Coordinate owns x-sector chrome (e.g. ring → side walls per
            # sector bracketing the gap whitespace, computed via the same
            # `_sector_walls` helper but on cyclic t-space). Hand the coord
            # the normalized sector spans so it can build its own walls.
            parts.append(coord_object.draw_x_sector_chrome(
                coord_project, iw, ih,
                [(lo / iw, hi / iw) for lo, hi in spans],
                [x / iw for x in label_xs],
                list(sec.names),
                {
                    "divider_color":     sec_col,
                    "divider_width":     sec_w,
                    "divider_dash":      sec_dash,
                    "tick_pad":          _FRAME["tick_pad"],
                    "label_fontsize":    x_size,
                    "label_fontcolor":   _FONTSPEC["color"],
                    "label_fontstyle":   x_style,
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
                has_xtl = any(str(l) for l in x_labels)
                if has_xtl:
                    sec_baseline = (ih + _FRAME["tick_pad"]
                                    + tick_band_height(x_labels, x_size, x_rot)
                                    + sec_pad + cap_height(x_size))
                else:
                    sec_baseline = ih + _FRAME["tick_pad"] + cap_height(x_size)
                for name, cx in zip(sec.names, label_xs):
                    parts.append(_tick_label(str(name), cx, sec_baseline,
                                             x_size, x_rot, axis="x",
                                             fontstyle=x_style, decoration=x_decor,
                                             tag="sector-label"))
    if y_sec is not None and (y_sec.divider or y_sec.label):
        sec_col, sec_w = _side_stroke("walls")
        sec_dash = _side_dash("walls")
        sec_pad  = _SECTORSPEC["label_pad"]
        sec = y_sec
        if sec.kind == "continuous":
            if hasattr(y_scale, "sector_pixel_ranges"):
                spans = y_scale.sector_pixel_ranges()
            else:
                bs = sec.boundaries()
                spans = [(y_scale(bs[i]), y_scale(bs[i + 1]))
                         for i in range(len(sec.names))]
            label_ys = [y_scale(sec.center(n)) for n in sec.names]
        else:
            bh = y_scale.bandwidth
            spans = []
            for members in sec.members:
                ys = [y_scale(m) for m in members]
                spans.append((min(ys) - bh / 2, max(ys) + bh / 2))
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
            has_ytl = any(str(l) for l in y_labels)
            if has_ytl:
                ytl_w = max((measure_text(str(l), y_size) for l in y_labels),
                            default=0.0)
                y_label_x = -(_FRAME["tick_pad"] + ytl_w + sec_pad)
            else:
                y_label_x = -_FRAME["tick_pad"]
            for name, cy in zip(sec.names, label_ys):
                parts.append(_tick_label(str(name), y_label_x,
                                         cy + cap_height(y_size) / 2,
                                         y_size, y_rot, axis="y",
                                         fontstyle=y_style, decoration=y_decor,
                                         tag="sector-label"))

    # y-axis — coordinate-aware (left spine + ticks + labels via draw_frame)
    # or standard Cartesian.
    if has_coord_frame:
        # Normalize y tick positions to [0,1] r-space so draw_frame works for
        # any scale (numeric, log, categorical) without knowing the scale type.
        _y_ticks_r = [(ih - y_scale(t)) / ih for t in y_ticks]
        # When the coord also owns the x-sector chrome, hand the y-axis the
        # same sector_ts so it can break its spines at gap boundaries
        # (Circos: each sector is a bounded arc, the rings don't bleed
        # through gap whitespace). Cartesian / non-sector renders ignore it.
        _y_sector_ts = None
        if has_x_sector_chrome and x_sec is not None:
            if hasattr(x_scale, "sector_pixel_ranges"):
                _spr = x_scale.sector_pixel_ranges()
            elif x_sec.kind == "continuous":
                bs = x_sec.boundaries()
                _spr = [(x_scale(bs[i]), x_scale(bs[i + 1]))
                        for i in range(len(x_sec.names))]
            else:
                _spr = None  # categorical+circular not supported
            if _spr is not None:
                _y_sector_ts = [(lo / iw, hi / iw) for lo, hi in _spr]
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
                "y_decoration":  y_decor,
                "sector_ts":     _y_sector_ts,
            }
        ))
    else:
        y_label_x = -_FRAME["tick_pad"] if (y_dir == "in" or not y_marks) else -(_FRAME["tick_length"] + _FRAME["tick_pad"])
        for t, lbl in zip(y_ticks, y_labels):
            y = y_scale(t)
            if y_marks:
                if st["spine_left"] and not hide_l:
                    x1, x2 = y_left_endpoints
                    col, sw = _side_stroke("left")
                    parts.append(segment(x1, y, x2, y, color=col, width=sw))
                if st["spine_right"] and st["y_right"] and not hide_r:
                    x1, x2 = y_right_endpoints
                    col, sw = _side_stroke("right")
                    parts.append(segment(x1, y, x2, y, color=col, width=sw))
            if not suppress_yt:
                # `y + cap_height/2` places the baseline so the cap is vertically
                # centered on the tick line (cap top at y - cap/2, cap bottom at y + cap/2).
                parts.append(_tick_label(str(lbl), y_label_x, y + cap_height(y_size) / 2,
                                         y_size, y_rot, axis="y",
                                         fontstyle=y_style, decoration=y_decor,
                                         tag="tick-y"))

        y_minor = _resolve_minor_ticks(st["y_minor"], y_scale, y_ticks)
        if y_minor and y_marks:
            minor_len = _FRAME["tick_length"] * _FRAME["minor_tick_ratio"]
            for t in y_minor:
                y = y_scale(t)
                if not math.isfinite(y):
                    continue
                if st["spine_left"] and not hide_l:
                    col, sw = _side_stroke("left")
                    if y_dir == "in":      x1, x2 = 0, minor_len
                    elif y_dir == "out":   x1, x2 = 0, -minor_len
                    else:                  x1, x2 = -minor_len, minor_len
                    parts.append(segment(x1, y, x2, y, color=col, width=sw))
                if st["spine_right"] and st["y_right"] and not hide_r:
                    col, sw = _side_stroke("right")
                    if y_dir == "in":      x1, x2 = iw, iw - minor_len
                    elif y_dir == "out":   x1, x2 = iw, iw + minor_len
                    else:                  x1, x2 = iw + minor_len, iw - minor_len
                    parts.append(segment(x1, y, x2, y, color=col, width=sw))

    return parts
