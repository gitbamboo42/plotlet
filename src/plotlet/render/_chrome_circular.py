"""Chrome helpers for ``CircularCoordinate``.

Procedural counterparts of the hooks ``CircularCoordinate`` exposes on the
coordinate protocol — ``clip_path_d``, ``draw_y_chrome`` (the y-axis chrome
on a ring), ``draw_x_chrome`` (angular tick marks + labels outside the outer
ring). ``CircularCoordinate`` itself becomes a thin geometry/parameter
holder that wires its methods to these helpers.

Lives in its own module so ``_coord_circular.py`` stays focused on the
coordinate protocol and the ring layout. The ring's radial reservation
(``chrome_pad``) lives here too, beside the drawing it must mirror. The default Cartesian chrome lives in
``_chrome_emit.py`` and needs no separate naming.
"""
from __future__ import annotations

import math

from ..draw import cap_height, descender, circle, coord, measure_text, path, segment, text_path


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def geometry(r_inner: float, data_diameter, iw: float, ih: float,
             r_outer: float = 1.0):
    """Compute ``(cx, cy, R, ri)`` for a ring of ``data_diameter`` pixels
    centered in ``iw × ih``.

    ``R`` is the outer radius, ``ri`` the inner radius; both are exact
    fractions (``r_outer`` / ``r_inner``) of ``data_diameter / 2`` so
    nested charts (one ring in the outer band, chords in the inner disc)
    each get a band that matches their artist projection. The canvas is
    sized by the caller (``render_layout``) as data_diameter + chrome, so
    the set diameter *is* the rendered data region — chrome grows the
    canvas outward instead of shrinking the ring. ``data_diameter=None``
    falls back to filling the canvas (``min(iw, ih)``).
    """
    R_full = (data_diameter if data_diameter is not None
              else min(iw, ih)) / 2.0
    R  = R_full * r_outer
    ri = R_full * r_inner
    cx, cy = iw / 2, ih / 2
    return cx, cy, R, ri


def t_to_angle(t: float, start_rad: float, end_rad: float) -> float:
    """Map ``t ∈ [0, 1]`` linearly between two ring angles.

    ``start_rad`` is the math-convention angle at t=0; ``end_rad`` at t=1.
    Both are in standard math angles (0 = 3 o'clock, π/2 = 12 o'clock,
    increasing counter-clockwise) — the clockwise sweep on screen comes
    from ``end_rad < start_rad`` (the usual case for a CW ring).

    For the today-default full ring with optional wrap gap, the caller
    sets ``start_rad = π/2 − wrap_gap_rad/2``, ``end_rad = start_rad −
    (2π − wrap_gap_rad)`` — so the formula collapses to the previous
    ``π/2 − wrap_gap_rad/2 − t·(2π − wrap_gap_rad)``. For a partial arc
    from clockwise-degrees ``[A, B]``, ``start_rad = π/2 − radians(A)``
    and ``end_rad = π/2 − radians(B)``.
    """
    return start_rad + t * (end_rad - start_rad)


# ---------------------------------------------------------------------------
# Annulus clip region
# ---------------------------------------------------------------------------

def clip_path_d(cx, cy, R, ri) -> str:
    """SVG path-d for an annular clip; renderer applies ``clip-rule="evenodd"``.

    Two concentric subpaths (outer ring, inner ring); evenodd fill leaves
    the annular region between them as the clip area.
    """
    return (
        f"M {coord(cx - R)},{coord(cy)} "
        f"A {coord(R)},{coord(R)} 0 1,0 {coord(cx + R)},{coord(cy)} "
        f"A {coord(R)},{coord(R)} 0 1,0 {coord(cx - R)},{coord(cy)} Z "
        f"M {coord(cx - ri)},{coord(cy)} "
        f"A {coord(ri)},{coord(ri)} 0 1,0 {coord(cx + ri)},{coord(cy)} "
        f"A {coord(ri)},{coord(ri)} 0 1,0 {coord(cx - ri)},{coord(cy)} Z"
    )


# ---------------------------------------------------------------------------
# Reservation — radial chrome pad, kept beside the drawing it must mirror
# ---------------------------------------------------------------------------


def _x_tick_labels(state, dw):
    """The x-tick label strings the ring will actually draw.

    Reads the same shared derivations both Cartesian chrome passes read
    (`_axis_ticks_labels` at the reservation-pass `_descriptor_scale`),
    so the chrome reservation matches what's drawn — not a guess. Two
    cases a naive estimate got wrong: an autoscaled ring's labels
    ("0.0" … "1.0") are far wider than a ``max(xlim)`` estimate, and a
    *continuous-sector* axis draws NO auto tick labels (they're
    meaningless on a global-offset coord) — so reserving for phantom
    numeric ticks over-shrinks the ring.
    """
    from ._resolution import _axis_ticks_labels, _descriptor_scale
    _, x_labels = _axis_ticks_labels(
        state, "x", _descriptor_scale(state, "x", dw), dw)
    return x_labels


def chrome_pad(state, dw) -> float:
    """Radial pixels of chrome past the outer arc for the outermost ring.

    Visibility comes from the same `_chrome_visibility.resolve_axis_chrome` the
    emit pass reads — rings carry no share-pair hiding or label
    suppression, so the layout flags are all False. The tick-chrome
    extent comes from the same `_chrome_bands.radial_tick_chrome_extent` the
    ``draw_x_sector_chrome`` hand-off reads; only the sector-label
    flush rule below is local.
    ``dw`` is the t-axis pixel span (the panel width auto ticks resolve
    against), used to resolve the real tick labels. Used by
    ``render_layout`` to grow the canvas outward around the data
    annulus so labels don't get clipped by the viewBox.

    Returns 0 when no chrome is drawn outside the ring.
    """
    from .._spec import SPEC, _FRAME, _FONTSPEC
    from ._chrome_bands import radial_tick_chrome_extent
    from ._chrome_visibility import resolve_axis_chrome

    pol = resolve_axis_chrome(state)["x"]

    tp        = _FRAME["tick_pad"]
    tick_size = _FONTSPEC["tick_size"]
    x_size    = state["x_fontsize"] if state["x_fontsize"] is not None else tick_size
    x_ticks_v = state.get("x_ticks")   # None=auto, []=suppressed, [...]= explicit

    labels = (_x_tick_labels(state, dw)
              if (pol["draw_labels"] and x_ticks_v != []) else [])
    if labels:
        x_style  = state.get("x_fontstyle") or "normal"
        x_weight = state.get("x_fontweight") or "normal"
        max_w  = max(measure_text(l, x_size, x_style, x_weight) for l in labels)
    else:
        max_w = 0.0
    x_chrome = radial_tick_chrome_extent(
        has_labels=bool(labels), max_label_w=max_w,
        has_marks=pol["draw_marks"] and x_ticks_v != [])

    # Sector labels stack outside tick chrome (same rule as linear)
    x_sec = state.get("x_sectors")
    if pol["draw_sector_labels"]:
        sec_size  = x_sec.fontsize if x_sec.fontsize is not None else SPEC["sectors"]["label_size"]
        sec_cap   = cap_height(sec_size)
        label_pad = SPEC["sectors"]["label_pad"]
        base_off  = (x_chrome + label_pad) if x_chrome > 0.0 else tp
        # Use the flipped-label offset (conservative worst case)
        return base_off + sec_cap * 1.5
    return x_chrome


# ---------------------------------------------------------------------------
# Y-axis chrome — inner+outer ring spines + intermediate tick rings
# ---------------------------------------------------------------------------

def draw_y_chrome(cx, cy, R, ri, start_rad, end_rad, is_full_ring,
                  y_ticks_r, y_labels,
                  frame_opts) -> str:
    """Inner+outer ring spines + radial y-tick marks + labels.

    ``is_full_ring`` is user intent (start_deg/end_deg at defaults) and
    distinguishes a closed ring — possibly with a `wrap_gap_deg` gap at
    12 o'clock — from a partial arc.

    Spines: closed circles when full ring + no sectors; per-sector arcs
    when sectors are set; a single open arc (start_rad → end_rad) for
    partial arc + no sectors.

    Y-label placement follows ``frame_opts["y_side"]``: ``"left"`` →
    12 o'clock (full) / ``start_rad`` (partial); ``"right"`` →
    6 o'clock (full) / ``end_rad`` (partial). Tick marks point outward
    along the radial direction; labels stack outward along the same axis.
    """
    spine_col = frame_opts["spine_color"]
    spine_w   = frame_opts["spine_width"]
    tl        = frame_opts["tick_length"]
    tp        = frame_opts["tick_pad"]
    y_size    = frame_opts["y_fontsize"]
    font_col  = frame_opts["font_color"]
    y_marks   = frame_opts["y_marks"]
    show_yl   = frame_opts["y_show_labels"]
    y_style   = frame_opts.get("y_fontstyle", "normal")
    y_weight  = frame_opts.get("y_fontweight", "normal")
    y_decor   = frame_opts.get("y_decoration", "none")
    sector_ts = frame_opts.get("sector_ts")
    y_side    = frame_opts.get("y_side", "left")

    spine_top    = frame_opts.get("spine_top",    True)
    spine_bottom = frame_opts.get("spine_bottom", True)

    parts = []

    if sector_ts is None:
        if is_full_ring:
            # Closed rings — draw as full circles.
            for radius, show in ((ri, spine_bottom), (R, spine_top)):
                if show:
                    parts.append(circle(cx, cy, radius,
                                        stroke=spine_col, stroke_width=spine_w,
                                        tag="spine"))
        else:
            # Partial arc, no sectors — one open arc per spine. SVG
            # sweep=1 renders CW on a y-down canvas; the typical case
            # `end_rad < start_rad` (math angle decreasing = screen CW)
            # is therefore sweep=1.
            span = abs(end_rad - start_rad)
            large = 1 if span > math.pi else 0
            sweep = 1 if end_rad < start_rad else 0
            for radius, show in ((ri, spine_bottom), (R, spine_top)):
                if not show:
                    continue
                x1 = cx + radius * math.cos(start_rad)
                y1 = cy - radius * math.sin(start_rad)
                x2 = cx + radius * math.cos(end_rad)
                y2 = cy - radius * math.sin(end_rad)
                d = (f"M {coord(x1)},{coord(y1)} "
                     f"A {coord(radius)},{coord(radius)} 0 {large},{sweep} "
                     f"{coord(x2)},{coord(y2)}")
                parts.append(path(d, stroke=spine_col, stroke_width=spine_w,
                                  fill="none"))
    else:
        # Sectored — per-sector arcs (same as today for full ring;
        # works for partial because the projection clamps t∈[0,1]).
        for radius, show in ((ri, spine_bottom), (R, spine_top)):
            if not show:
                continue
            for start_t, end_t in sector_ts:
                ang_s = t_to_angle(start_t, start_rad, end_rad)
                ang_e = t_to_angle(end_t,   start_rad, end_rad)
                x1 = cx + radius * math.cos(ang_s)
                y1 = cy - radius * math.sin(ang_s)
                x2 = cx + radius * math.cos(ang_e)
                y2 = cy - radius * math.sin(ang_e)
                large = 1 if abs(ang_s - ang_e) > math.pi else 0
                d = (f"M {coord(x1)},{coord(y1)} "
                     f"A {coord(radius)},{coord(radius)} 0 {large} 1 {coord(x2)},{coord(y2)}")
                parts.append(path(d, stroke=spine_col,
                                  stroke_width=spine_w))

    if not is_full_ring:
        # Radial caps at the two open ends — connect inner ring to outer
        # ring at start_rad and end_rad so the partial arc reads as a
        # bounded annular sector rather than an open horseshoe. Skipped
        # for full ring (no open edges).
        for ang in (start_rad, end_rad):
            ux, uy = math.cos(ang), -math.sin(ang)
            parts.append(segment(cx + ri * ux, cy + ri * uy,
                                 cx + R  * ux, cy + R  * uy,
                                 color=spine_col, width=spine_w))

    # Y-tick / label radial axis.
    if is_full_ring:
        label_ang = math.pi / 2 if y_side == "left" else -math.pi / 2
    else:
        label_ang = start_rad if y_side == "left" else end_rad
    ux, uy = math.cos(label_ang), -math.sin(label_ang)
    # Skip exact 0/1 (they're the rings themselves).
    for r_f, lbl in zip(y_ticks_r, y_labels):
        if r_f <= 1e-9 or r_f >= 1.0 - 1e-9:
            continue
        radius = ri + r_f * (R - ri)
        tx, ty = cx + radius * ux, cy + radius * uy
        if y_marks:
            parts.append(segment(tx, ty,
                                 tx + tl * ux, ty + tl * uy,
                                 color=spine_col, width=spine_w))
        if show_yl:
            off = tl + tp + cap_height(y_size)
            lx, ly = cx + (radius + off) * ux, cy + (radius + off) * uy
            # Horizontal text; anchor follows the radial direction so the
            # label extends OUTWARD from the tick (not back into data).
            if ux > 0.1:    anchor = "start"
            elif ux < -0.1: anchor = "end"
            else:            anchor = "middle"
            parts.append(text_path(str(lbl), lx, ly,
                                   y_size, anchor=anchor, color=font_col,
                                   fontstyle=y_style, fontweight=y_weight,
                                   decoration=y_decor,
                                   tag="tick-y"))

    return "".join(parts)


# ---------------------------------------------------------------------------
# X-axis chrome — angular tick marks + tangentially-oriented labels
# ---------------------------------------------------------------------------

def draw_x_sector_chrome(cx, cy, R, ri, start_rad, end_rad, is_full_ring,
                         sector_ts, label_ts, names,
                         sec_opts) -> str:
    """Radial walls at each sector's edges + tangential sector-name labels.

    ``sector_ts`` is a list of ``(start_t, end_t)`` for each sector in
    t-space.  Each sector gets TWO radial walls — one at its start, one
    at its end — so the gap whitespace between adjacent sectors sits
    between two parallel walls.  ``is_full_ring=True``
    treats sector boundaries as cyclic so the wrap boundary at the
    start/end of the data range gets walls bracketing it; partial arc
    is acyclic (open ends, no wrap walls).
    """
    div_col   = sec_opts["divider_color"]
    div_w     = sec_opts["divider_width"]
    div_dash  = sec_opts.get("divider_dash")
    tp        = sec_opts["tick_pad"]
    font_size = sec_opts["label_fontsize"]
    font_col  = sec_opts["label_fontcolor"]
    font_st   = sec_opts.get("label_fontstyle", "normal")
    font_wt   = sec_opts.get("label_fontweight", "normal")
    font_dc   = sec_opts.get("label_decoration", "none")
    draw_div  = sec_opts["draw_dividers"]
    draw_lbl  = sec_opts["draw_labels"]

    parts = []

    if draw_div:
        # Paired radial walls at each internal boundary (and the wrap
        # boundary when full ring) — same `sector_walls` helper used
        # by the linear chrome, on cyclic t-space for a closed ring or
        # acyclic for a partial arc. At gap=0 / wrap_gap_deg=0 paired
        # walls coincide and stack; semi-transparent strokes compensate
        # via alpha.
        from ._chrome_bands import sector_walls
        for t in sector_walls(sector_ts, cyclic=is_full_ring):
            ang = t_to_angle(t, start_rad, end_rad)
            ux, uy = math.cos(ang), -math.sin(ang)
            parts.append(segment(cx + ri * ux, cy + ri * uy,
                                 cx + R  * ux, cy + R  * uy,
                                 color=div_col, width=div_w, dash=div_dash,
                                 tag="sector-divider"))

    if draw_lbl:
        # Labels sit a font-cap above the outer ring, rotated tangent to the
        # ring (parallel to the sector's arc). Bottom-half labels are flipped
        # 180° so they read upright rather than upside down. For natural
        # (un-flipped) labels the baseline is the inner edge of the text;
        # for flipped labels the cap top is the inner edge — so flipped
        # labels need an extra cap-height of outward offset to keep the
        # visible gap to the ring symmetric.
        cap = cap_height(font_size)
        x_ext = sec_opts.get("x_chrome_extent", 0.0)
        lbl_pad = sec_opts.get("label_pad", tp)
        # Stack outside tick chrome when present (mirrors linear: tick marks →
        # tick labels → sector labels from spine outward). Fall back to plain
        # tick_pad when no tick chrome is drawn on this ring.
        base_off = (x_ext + lbl_pad) if x_ext > 0.0 else tp
        off_natural = base_off + cap / 2
        off_flipped = base_off + cap / 2 + cap
        for name, t in zip(names, label_ts):
            ang = t_to_angle(t, start_rad, end_rad)
            # Tangent (CW around ring) — text tops point outward on the top
            # half; antiflip clamp keeps bottom-half labels upright (their
            # tops then point inward, but reading direction stays natural).
            rot = math.degrees(ang) - 90.0
            rot = ((rot + 180.0) % 360.0) - 180.0
            flipped = rot > 90.0 or rot < -90.0
            if rot > 90.0:  rot -= 180.0
            if rot < -90.0: rot += 180.0
            off = off_flipped if flipped else off_natural
            ux, uy = math.cos(ang), -math.sin(ang)
            lx, ly = cx + (R + off) * ux, cy + (R + off) * uy
            parts.append(text_path(str(name), lx, ly,
                                   font_size, anchor="middle", color=font_col,
                                   fontstyle=font_st, fontweight=font_wt,
                                   decoration=font_dc,
                                   rotate=rot, tag="sector-label"))

    return "".join(parts)


def draw_x_chrome(cx, cy, R, start_rad, end_rad,
                  x_ticks_t, x_labels,
                  frame_opts) -> str:
    """Radial tick marks just outside the outer ring + tangential labels.

    Labels sit one ``tick_length + tick_pad`` outside the ring, rotated to
    the tangent direction (flipped 180° when otherwise upside-down) so the
    text reads naturally regardless of where on the ring it is.
    """
    spine_col = frame_opts["spine_color"]
    spine_w   = frame_opts["spine_width"]
    tl        = frame_opts["tick_length"]
    tp        = frame_opts["tick_pad"]
    x_size    = frame_opts["x_fontsize"]
    font_col  = frame_opts["font_color"]
    x_marks   = frame_opts["x_marks"]
    show_xl   = frame_opts["x_show_labels"]
    x_style   = frame_opts.get("x_fontstyle", "normal")
    x_weight  = frame_opts.get("x_fontweight", "normal")
    x_decor   = frame_opts.get("x_decoration", "none")

    parts = []

    for t, lbl in zip(x_ticks_t, x_labels):
        ang = t_to_angle(t, start_rad, end_rad)
        # Outward radial unit vector (SVG y-down).
        ux, uy = math.cos(ang), -math.sin(ang)
        ox, oy = cx + R * ux, cy + R * uy
        if x_marks:
            parts.append(segment(ox, oy,
                                 ox + tl * ux, oy + tl * uy,
                                 color=spine_col, width=spine_w))
        if show_xl:
            # Labels are radial: inner edge sits at R+tl+tp, center at
            # R+tl+tp+w/2 where w is this label's own rendered width.
            w = measure_text(str(lbl), x_size, x_style, x_weight)
            off = tl + tp + w / 2
            lx, ly = cx + (R + off) * ux, cy + (R + off) * uy
            # Same tangential rotation formula as sector labels so all
            # angular text leans consistently around the ring.
            rot = math.degrees(ang)
            rot = ((rot + 180.0) % 360.0) - 180.0
            if rot > 90.0:  rot -= 180.0
            if rot < -90.0: rot += 180.0
            # Tangential centering: mirror the linear _tick_label fix. The
            # radial label's cap extends in the tangential direction; shift
            # the anchor so the cap midpoint (not the baseline) aligns with
            # the radius line. cos(rot_rad - ang) = +1 unflipped, -1 flipped.
            _cap_shift = (cap_height(x_size) - descender(x_size)) / 2
            _ts = _cap_shift * math.cos(math.radians(rot) - ang)
            lx += _ts * math.sin(ang)
            ly += _ts * math.cos(ang)
            parts.append(text_path(str(lbl), lx, ly,
                                   x_size, anchor="middle", color=font_col,
                                   fontstyle=x_style, fontweight=x_weight,
                                   decoration=x_decor,
                                   rotate=rot, tag="tick-x"))

    return "".join(parts)
