"""Chrome emission — the drawing half of panel chrome.

Called from `emit._render_inner` once per panel: ``emit_chrome``
(spines, ticks, sector chrome, coord-owned frames) between the
data-layer and margin-band passes, then ``emit_frame_labels`` (xlabel /
ylabel / title / subtitle / caption). Both return lists of SVG-fragment
strings; every input arrives through explicit arguments — no module
globals, no implicit state. All band geometry comes from
`_chrome_bands` — emit draws the bands, it never re-derives them — and
the visibility flags come decided from `_chrome_visibility`.

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
                    text_block_height)
from .. import _regions
from ..scales import _LogScale
from ._chrome_bands import (_axis_band_stack, _outward_mark_extent,
                            axis_label_band, radial_tick_chrome_extent,
                            sector_walls, _sector_pixel_spans,
                            title_band_stack)

_SECTORSPEC = SPEC["sectors"]



# ---------------------------------------------------------------------------
# Tick label, minor-tick resolution, sectored spine segmentation
# (only the chrome block uses these)
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
    out = []
    if isinstance(scale, _LogScale):
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



def _spine_segments(side, iw, ih, x_ranges, y_ranges):
    """Yield ``(x1, y1, x2, y2)`` per spine segment for ``side``.

    The spine is the outer envelope. When the parallel-to-spine axis is
    sectored (top/bottom + x-sectors, or left/right + y-sectors), the
    segment breaks per sector so each sector reads as its own bounded
    edge. Internal partitions (verticals when x is sectored, horizontals
    when y is sectored) are emitted separately as sector walls — see
    ``sector_walls``.
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
# Spine / wall styling + sector geometry — shared by the emit blocks
# ---------------------------------------------------------------------------

def _pick(*candidates):
    for v in candidates:
        if v is not None: return v
    return None


def _side_stroke(state, side):
    """Stroke ``(color, width)`` for any spine target — a side name or
    ``"walls"``. Resolution: per-target override > ``c.spines()`` base >
    ``_FRAME`` spec."""
    col = _pick(state[f"spine_{side}_color"], state["spine_base_color"], _FRAME["color"])
    w   = _pick(state[f"spine_{side}_width"], state["spine_base_width"], _FRAME["width"])
    return resolve_color(col), w


def _side_dash(state, side):
    return _pick(state[f"spine_{side}_linestyle"], state["spine_base_linestyle"])


def _sector_geometry(scale, sec):
    """Pixel spans, label centers, and wall positions for a sectored
    axis — the geometry both sector-chrome blocks read. Continuous
    sectors center each label at the sector's data-space center;
    categorical sectors at the span's pixel midpoint."""
    spans = _sector_pixel_spans(scale, sec)
    if sec.kind == "continuous":
        centers = [scale(sec.center(n)) for n in sec.names]
    else:
        centers = [(lo + hi) / 2 for lo, hi in spans]
    return spans, centers, sector_walls(spans)



# ---------------------------------------------------------------------------
# Emit blocks — one per chrome concern; each returns its own fragment list
# ---------------------------------------------------------------------------

def _emit_spines(state, inp, iw, ih, *, has_coord_frame, has_x_frame):
    """Spines — toggleable per side via `c.spines(top=False, right=False,
    ...)`, restylable via `c.spines(top={"color": "red", "width": 1.5})`.
    Sides owned by the coordinate are skipped (left/top/right under
    ``draw_frame``, bottom under ``draw_x_frame``) — the coord draws its
    own. `_spine_segments` breaks each side into per-sector pieces when
    a sectored scale is active, so each sector reads as its own bounded
    subplot. Plain linear / categorical paths yield one full-side
    segment."""
    spine_on = inp.chrome["spines"]
    x_ranges = (inp.x_scale.sector_pixel_ranges()
                if hasattr(inp.x_scale, "sector_pixel_ranges") else None)
    y_ranges = (inp.y_scale.sector_pixel_ranges()
                if hasattr(inp.y_scale, "sector_pixel_ranges") else None)
    parts = []
    for side in ("top", "bottom", "left", "right"):
        if side in ("left", "top", "right") and has_coord_frame:
            continue
        if side == "bottom" and has_x_frame:
            continue
        if not spine_on[side]:
            continue
        col, w = _side_stroke(state, side)
        dash = _side_dash(state, side)
        for sx1, sy1, sx2, sy2 in _spine_segments(side, iw, ih,
                                                  x_ranges, y_ranges):
            parts.append(segment(sx1, sy1, sx2, sy2,
                                 color=col, width=w, dash=dash, tag="spine"))
    return parts


def _emit_x_axis(state, inp, iw, ih, *, coord_object, coord_project,
                 has_x_frame):
    """x-axis — coordinate-aware (bottom spine + ticks + labels via
    ``draw_x_frame``) or standard Cartesian ticks + labels + minor
    ticks."""
    x_scale = inp.x_scale
    x_ticks, x_labels = inp.x_ticks, inp.x_labels
    x_size, x_rot = inp.x_size, inp.x_rot
    x_style  = state.get("x_fontstyle") or "normal"
    x_weight = state.get("x_fontweight") or "normal"
    x_decor  = state.get("x_decoration") or "none"
    x_pol = inp.chrome["x"]
    parts = []

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
                "x_marks":       x_pol["draw_marks"],
                "x_show_labels": x_pol["draw_labels"],
                "x_fontstyle":   x_style,
                "x_fontweight":  x_weight,
                "x_decoration":  x_decor,
            }
        ))
        return parts

    # Tick-mark endpoints relative to the spine. "in" goes inside the data
    # area, "out" goes outside, "inout" spans both sides at full length each.
    x_dir = state["x_direction"]
    bot_in, bot_out = ih - _FRAME["tick_length"], ih + _FRAME["tick_length"]  # bottom spine offsets
    top_in, top_out = _FRAME["tick_length"], -_FRAME["tick_length"]           # top spine offsets
    if x_dir == "in":      x_bot_endpoints, x_top_endpoints = (ih, bot_in),  (0, top_in)
    elif x_dir == "out":   x_bot_endpoints, x_top_endpoints = (ih, bot_out), (0, top_out)
    else:                  x_bot_endpoints, x_top_endpoints = (bot_out, bot_in), (top_out, top_in)

    # x-ticks + labels — always Cartesian. Whole block flips wholesale
    # by `x_side`: spine attachment, tick-mark endpoints, label anchor.
    x_side = x_pol["side"]
    if x_side == "bottom":
        x_endpoints = x_bot_endpoints
        y_band_edge_sign = 1   # band grows downward from y=ih
        x_band_y0 = ih
    else:
        x_endpoints = x_top_endpoints
        y_band_edge_sign = -1  # band grows upward from y=0
        x_band_y0 = 0
    # No visible outward mark (inward, disabled, or dropped on a
    # joined share-pair side) → labels sit flush at tick_pad past
    # the spine line.
    x_label_dy = _axis_band_stack(
        mark=_outward_mark_extent(x_pol, x_ticks))["label_off"]
    # Mark endpoints + stroke, resolved once for majors and minors alike;
    # the label-only path (draw_marks off) never reads them.
    y1, y2 = x_endpoints
    col, sw = _side_stroke(state, x_side)

    for t, lbl in zip(x_ticks, x_labels):
        x = x_scale(t)
        # draw_marks already folds share-pair hiding — marks bleeding
        # into the inter-panel gap read as visual clutter when the
        # two panels are meant to merge.
        if x_pol["draw_marks"]:
            parts.append(segment(x, y1, x, y2, color=col, width=sw))
        # Drop only labels redundant with a sharing sibling. A small label
        # overflow into a joined neighbor's collapsed margin is acceptable.
        if x_pol["draw_labels"]:
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
    x_minor = _resolve_minor_ticks(state["x_minor"], x_scale, x_ticks)
    if x_minor and x_pol["draw_marks"]:
        minor_len = _FRAME["tick_length"] * _FRAME["minor_tick_ratio"]
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
    return parts


def _emit_x_sector_chrome(state, inp, iw, ih, x_sec, *,
                          coord_object, coord_project, has_x_sector_chrome):
    """Sector chrome along x — internal walls + sector-name labels.

    Walls are conceptually side spines, so style resolves through the
    same ``_side_stroke`` / ``_side_dash`` with ``"walls"`` as the
    target. Visibility (walls toggle, crossing-artist wall suppression,
    label suppression / hiding) is decided in `_chrome_visibility` — the
    ``draw_sector_dividers`` / ``draw_sector_labels`` flags gate entry
    and emission alike; ``x_sec`` supplies geometry only."""
    x_pol = inp.chrome["x"]
    if not (x_pol["draw_sector_dividers"] or x_pol["draw_sector_labels"]):
        return []
    x_scale = inp.x_scale
    x_ticks, x_labels = inp.x_ticks, inp.x_labels
    x_size = inp.x_size
    x_style  = state.get("x_fontstyle") or "normal"
    x_weight = state.get("x_fontweight") or "normal"
    x_decor  = state.get("x_decoration") or "none"
    sec_col, sec_w = _side_stroke(state, "walls")
    sec_dash = _side_dash(state, "walls")
    sec_pad  = _SECTORSPEC["label_pad"]
    sec = x_sec
    spans, label_xs, divider_xs = _sector_geometry(x_scale, sec)
    parts = []
    if has_x_sector_chrome:
        # Coordinate owns x-sector chrome (e.g. ring → side walls per
        # sector bracketing the gap whitespace, computed via the same
        # `sector_walls` helper but on cyclic t-space). Hand the coord
        # the normalized sector spans so it can build its own walls.
        #
        # x_chrome_extent: radial pixels past the outer arc already
        # consumed by tick marks + labels (drawn by draw_x_frame), via
        # the shared `radial_tick_chrome_extent` — `_chrome_circular.chrome_pad`
        # reserves the same stack, so sector labels clear tick chrome
        # without overlap. When zero (no ticks on this ring), sector
        # labels fall back to the plain tick_pad gap. Tick labels are
        # radial: the widest one is the conservative stacking bound.
        _tp = _FRAME["tick_pad"]
        _has_x_labels = any(str(l) for l in x_labels) and x_pol["draw_labels"]
        _max_w = (max((measure_text(str(l), x_size, x_style, x_weight)
                       for l in x_labels), default=0.0)
                  if _has_x_labels else 0.0)
        x_chrome_extent = radial_tick_chrome_extent(
            has_labels=_has_x_labels, max_label_w=_max_w,
            has_marks=x_pol["draw_marks"] and bool(x_ticks))
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
                "draw_dividers":     x_pol["draw_sector_dividers"],
                "draw_labels":       x_pol["draw_sector_labels"],
            },
        ))
        return parts

    if x_pol["draw_sector_dividers"]:
        for x in divider_xs:
            parts.append(segment(x, 0, x, ih,
                                 color=sec_col, width=sec_w, dash=sec_dash,
                                 tag="sector-divider"))
    if x_pol["draw_sector_labels"]:
        # Shared stack walk: flush against the spine when no tick band
        # is between them, past the rotation-aware tick band otherwise
        # (same rule the reservation reads). `sector_off_spine` is the
        # legacy from-the-spine offset — see the skew note on
        # `_axis_band_stack`. The whole band flips to the top edge with
        # `xticks(side="top")`, like the tick-label block in
        # `_emit_x_axis`.
        _sec_x_size = sec.fontsize if sec.fontsize is not None else _SECTORSPEC["label_size"]
        _sec_x_rot  = sec.rotation if sec.rotation is not None else 0
        has_xtl = any(str(l) for l in x_labels)
        _sec_band = _axis_band_stack(
            mark=_outward_mark_extent(x_pol, x_ticks),
            label_extent=(tick_band_height(x_labels, x_size, inp.x_rot,
                                           x_style, x_weight)
                          if has_xtl else 0.0),
            has_labels=has_xtl)["sector_off_spine"]
        if x_pol["side"] == "bottom":
            # cap_height * cos(rot) is the y-offset from the band top
            # to the anchor — 0 at 90° (anchor at top, text hangs
            # down), cap_height at 0° (baseline one cap below).
            sec_baseline = (ih + _sec_band
                            + cap_height(_sec_x_size)
                            * math.cos(math.radians(_sec_x_rot)))
        else:
            # Top-edge mirror of the tick-label formula: text sits
            # above the band edge, hanging by its descender.
            sec_baseline = (-_sec_band
                            - descender(_sec_x_size)
                            * math.cos(math.radians(_sec_x_rot)))
        for name, cx in zip(sec.names, label_xs):
            parts.append(_tick_label(str(name), cx, sec_baseline,
                                     _sec_x_size, _sec_x_rot, axis="x",
                                     side=x_pol["side"],
                                     fontstyle=x_style, fontweight=x_weight,
                                     decoration=x_decor,
                                     tag="sector-label"))
    return parts


def _emit_y_sector_chrome(state, inp, iw, y_sec):
    """Sector chrome along y — mirror of `_emit_x_sector_chrome` minus
    the coord hand-off (a coord frame owns the radial axis outright, so
    y-sector chrome is linear-only)."""
    y_pol = inp.chrome["y"]
    if not (y_pol["draw_sector_dividers"] or y_pol["draw_sector_labels"]):
        return []
    y_scale = inp.y_scale
    y_labels = inp.y_labels
    y_size = inp.y_size
    y_style  = state.get("y_fontstyle") or "normal"
    y_weight = state.get("y_fontweight") or "normal"
    y_decor  = state.get("y_decoration") or "none"
    sec_col, sec_w = _side_stroke(state, "walls")
    sec_dash = _side_dash(state, "walls")
    sec = y_sec
    _, label_ys, divider_ys = _sector_geometry(y_scale, sec)
    parts = []
    if y_pol["draw_sector_dividers"]:
        for y in divider_ys:
            parts.append(segment(0, y, iw, y,
                                 color=sec_col, width=sec_w, dash=sec_dash,
                                 tag="sector-divider"))
    if y_pol["draw_sector_labels"]:
        # Shared stack walk: flush against the spine when no tick label
        # column exists to its inside, past the tick labels otherwise.
        # `sector_off_spine` is the legacy from-the-spine offset — see
        # the skew note on `_axis_band_stack`. The whole column flips to
        # the right edge with `yticks(side="right")`, like the
        # tick-label block in `_emit_y_axis`.
        _sec_y_size = sec.fontsize if sec.fontsize is not None else _SECTORSPEC["label_size"]
        has_ytl = any(str(l) for l in y_labels)
        _sec_band = _axis_band_stack(
            mark=_outward_mark_extent(y_pol, inp.y_ticks),
            label_extent=(max((measure_text(str(l), y_size, y_style, y_weight)
                               for l in y_labels), default=0.0)
                          if has_ytl else 0.0),
            has_labels=has_ytl)["sector_off_spine"]
        if y_pol["side"] == "left":
            y_label_x = -_sec_band
        else:
            y_label_x = iw + _sec_band
        for name, cy in zip(sec.names, label_ys):
            parts.append(_tick_label(str(name), y_label_x,
                                     cy + cap_height(_sec_y_size) / 2,
                                     _sec_y_size, 0, axis="y",
                                     side=y_pol["side"],
                                     fontstyle=y_style, fontweight=y_weight,
                                     decoration=y_decor,
                                     tag="sector-label"))
    return parts


def _emit_y_axis(state, inp, iw, ih, *, coord_object, coord_project,
                 has_coord_frame, has_x_sector_chrome, x_sec):
    """y-axis — coordinate-aware (left spine + ticks + labels via
    ``draw_frame``) or standard Cartesian ticks + labels + minor
    ticks."""
    y_scale = inp.y_scale
    y_ticks, y_labels = inp.y_ticks, inp.y_labels
    y_size, y_rot = inp.y_size, inp.y_rot
    y_style  = state.get("y_fontstyle") or "normal"
    y_weight = state.get("y_fontweight") or "normal"
    y_decor  = state.get("y_decoration") or "none"
    y_pol = inp.chrome["y"]
    parts = []

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
                            for lo, hi in _sector_pixel_spans(inp.x_scale, x_sec)]
        spine_on = inp.chrome["spines"]
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
                "y_marks":       y_pol["draw_marks"],
                "y_show_labels": y_pol["draw_labels"],
                "y_fontstyle":   y_style,
                "y_fontweight":  y_weight,
                "y_decoration":  y_decor,
                "y_side":        y_pol["side"],
                "sector_ts":     _y_sector_ts,
                "spine_top":     spine_on["top"],
                "spine_bottom":  spine_on["bottom"],
            }
        ))
        return parts

    # Tick-mark endpoints relative to the spine — same in/out/inout rule
    # as the x-axis table in `_emit_x_axis`.
    y_dir = state["y_direction"]
    left_in, left_out  = _FRAME["tick_length"], -_FRAME["tick_length"]        # left spine offsets (x = 0)
    right_in, right_out = iw - _FRAME["tick_length"], iw + _FRAME["tick_length"]
    if y_dir == "in":      y_left_endpoints, y_right_endpoints = (0, left_in),  (iw, right_in)
    elif y_dir == "out":   y_left_endpoints, y_right_endpoints = (0, left_out), (iw, right_out)
    else:                  y_left_endpoints, y_right_endpoints = (left_out, left_in), (right_out, right_in)

    # y-ticks + labels — Cartesian. Like the x block, flip wholesale
    # by `y_side`: spine attachment, tick-mark endpoints, label anchor.
    y_side = y_pol["side"]
    y_label_dx = _axis_band_stack(
        mark=_outward_mark_extent(y_pol, y_ticks))["label_off"]
    if y_side == "left":
        y_endpoints = y_left_endpoints
        x_band_edge_sign = -1  # band grows leftward from x=0
        y_band_x0 = 0
        y_label_x = -y_label_dx
    else:
        y_endpoints = y_right_endpoints
        x_band_edge_sign = 1   # band grows rightward from x=iw
        y_band_x0 = iw
        y_label_x = iw + y_label_dx
    # Mark endpoints + stroke, resolved once for majors and minors alike;
    # the label-only path (draw_marks off) never reads them.
    x1, x2 = y_endpoints
    col, sw = _side_stroke(state, y_side)

    for t, lbl in zip(y_ticks, y_labels):
        y = y_scale(t)
        if y_pol["draw_marks"]:
            parts.append(segment(x1, y, x2, y, color=col, width=sw))
        if y_pol["draw_labels"]:
            # `y + cap_height/2` places the baseline so the cap is vertically
            # centered on the tick line (cap top at y - cap/2, cap bottom at y + cap/2).
            parts.append(_tick_label(str(lbl), y_label_x, y + cap_height(y_size) / 2,
                                     y_size, y_rot, axis="y", side=y_side,
                                     fontstyle=y_style, fontweight=y_weight,
                                     decoration=y_decor,
                                     tag="tick-y"))

    y_minor = _resolve_minor_ticks(state["y_minor"], y_scale, y_ticks)
    if y_minor and y_pol["draw_marks"]:
        minor_len = _FRAME["tick_length"] * _FRAME["minor_tick_ratio"]
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



# ---------------------------------------------------------------------------
# Chrome entry point
# ---------------------------------------------------------------------------

def emit_chrome(*, state, inp, iw, ih,
                coord_object, coord_project,
                has_coord_frame, has_x_frame, has_x_sector_chrome,
                x_sec, y_sec):
    """Emit all panel chrome — spines, ticks, minor ticks, sector chrome,
    and (when present) the coordinate-owned ``draw_frame`` / ``draw_x_frame``
    hooks. Returns a list of SVG-fragment strings; caller extends its own
    ``parts``.

    ``inp`` carries the resolved per-panel axis context (scales, ticks,
    labels, sizes, rotations, and the decided ``chrome`` visibility
    flags with their side routing); everything else here is pure render
    state pulled from ``state`` or the coord descriptor args.

    Each ``_emit_*`` block owns one concern and returns its own fragment
    list; the concatenation order below is the SVG paint order.
    """
    # Panel region — recorded in the sink so layout-debug consumers
    # (`chart.regions()`, layout_diagram detail mode) can ask "did
    # anything overflow this panel?". Panel-local coords: (0, 0)
    # is the inner-margin corner; (iw, ih) is the data-area extent.
    _regions.record("rect", (0, 0, iw, ih), name="panel")

    parts = []
    parts += _emit_spines(state, inp, iw, ih,
                          has_coord_frame=has_coord_frame,
                          has_x_frame=has_x_frame)
    parts += _emit_x_axis(state, inp, iw, ih,
                          coord_object=coord_object,
                          coord_project=coord_project,
                          has_x_frame=has_x_frame)
    parts += _emit_x_sector_chrome(state, inp, iw, ih, x_sec,
                                   coord_object=coord_object,
                                   coord_project=coord_project,
                                   has_x_sector_chrome=has_x_sector_chrome)
    parts += _emit_y_sector_chrome(state, inp, iw, y_sec)
    parts += _emit_y_axis(state, inp, iw, ih,
                          coord_object=coord_object,
                          coord_project=coord_project,
                          has_coord_frame=has_coord_frame,
                          has_x_sector_chrome=has_x_sector_chrome,
                          x_sec=x_sec)
    return parts



# ---------------------------------------------------------------------------
# Frame labels — xlabel / ylabel / title / subtitle / caption
# ---------------------------------------------------------------------------

def emit_frame_labels(state, inp, iw, ih, chrome, *, top_legend_outset=0,
                      bottom_legend_outset=0):
    """Emit xlabel / ylabel / title / subtitle / caption as SVG
    fragments. Walks inside-out from the data area: past the chrome band
    on the active side, past the label's own (2-px gap + label_size)
    block, then the subtitle and title blocks above the top-side xlabel
    (when the x band sits on top). The caption is the outermost bottom
    element — small, right-aligned (ggplot's `labs(caption=)`).

    ``top_legend_outset`` / ``bottom_legend_outset`` are the extra strips
    the title (resp. caption) must hop over when an outside top/bottom
    inline legend sits in between (``leg_lh + legend_gap``); 0 otherwise.
    """
    label_size = _FONTSPEC["label_size"]
    title_size = _FONTSPEC["title_size"]
    text_color = _FONTSPEC["color"]
    x_pol, y_pol = inp.chrome["x"], inp.chrome["y"]
    parts = []
    xlabel_band = axis_label_band(state, x_pol, "x")

    # `text_path` anchors multi-line text at the FIRST line's baseline with
    # lines flowing downward. On bottom/right sides the block naturally
    # grows away from the data area, so single-line anchor formulas hold;
    # on top/left the anchor shifts outward by the extra-lines height
    # (`block - size`, zero for one line) so the LAST line lands in the
    # single-line slot and the block grows outward instead of into the axis.

    if x_pol["draw_axis_label"]:
        # Walk past the chrome stack + 2-px gap + full label_size, then back
        # up by descender to land on the baseline. Bottom: y positive past
        # ih. Top: y negative past 0 — same descender adjustment lands the
        # visible glyph bottom at the band's inner edge.
        xlabel_extra = text_block_height(state["xlabel"], label_size) - label_size
        if x_pol["side"] == "bottom":
            xlabel_baseline = ih + chrome["bottom"] + 2 + label_size - descender(label_size)
        else:
            xlabel_baseline = -(chrome["top"] + 2 + descender(label_size) + xlabel_extra)
        parts.append(text_path(state["xlabel"], iw / 2, xlabel_baseline,
                                label_size, anchor="middle", color=text_color,
                                tag="xlabel"))

    if y_pol["draw_axis_label"]:
        # Walk past the chrome stack + 2-px gap, then half label_size to
        # land on the rotated text's center. Left: cx negative (outside
        # panel on left) — under rotate=90 extra lines flow toward +x
        # (the panel), so the anchor shifts left by the extra-lines
        # height. Right: cx positive past iw, extra lines flow outward.
        ylabel_extra = text_block_height(state["ylabel"], label_size) - label_size
        if y_pol["side"] == "left":
            ylabel_cx = -(chrome["left"] + 2 + label_size / 2 + ylabel_extra)
        else:
            ylabel_cx = iw + chrome["right"] + 2 + label_size / 2
        parts.append(text_path(state["ylabel"], ylabel_cx, ih / 2,
                                label_size, anchor="middle",
                                color=text_color, rotate=90, tag="ylabel"))

    if state["title"] or state["subtitle"]:
        # Block offsets come from the shared `title_band_stack`, so this
        # placement and the reservation walk identical arithmetic.
        top_xlabel = xlabel_band if x_pol["side"] == "top" else 0
        base = chrome["top"] + top_xlabel + top_legend_outset
        stack = title_band_stack(state)
        if state["subtitle"]:
            subtitle_size = _FONTSPEC["subtitle_size"]
            sub_extra = text_block_height(state["subtitle"], subtitle_size) - subtitle_size
            sub_y = -(base + stack["subtitle_off"] + descender(subtitle_size) + sub_extra)
            parts.append(text_path(state["subtitle"], iw / 2, sub_y,
                                    subtitle_size, anchor="middle",
                                    color=text_color, tag="subtitle"))
        if state["title"]:
            title_extra = text_block_height(state["title"], title_size) - title_size
            title_y = -(base + stack["title_off"] + descender(title_size) + title_extra)
            parts.append(text_path(state["title"], iw / 2, title_y, title_size,
                                    anchor="middle", color=text_color,
                                    tag="title"))

    if state["caption"]:
        # Outermost bottom element: past the bottom chrome, bottom-side
        # xlabel block, and any bottom-position legend. First-line
        # baseline anchored so multi-line captions grow downward.
        caption_size = _FONTSPEC["caption_size"]
        bottom_xlabel = xlabel_band if x_pol["side"] == "bottom" else 0
        caption_y = (ih + chrome["bottom"] + bottom_xlabel
                     + bottom_legend_outset + _PADSPEC["caption"]
                     + caption_size - descender(caption_size))
        parts.append(text_path(state["caption"], iw, caption_y, caption_size,
                                anchor="end", color=text_color,
                                tag="caption"))

    return parts
