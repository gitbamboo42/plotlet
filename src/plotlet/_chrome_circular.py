"""Chrome helpers for ``CircularCoordinate``.

Procedural counterparts of the hooks ``CircularCoordinate`` exposes on the
coordinate protocol — ``clip_path_d``, ``draw_y_chrome`` (the y-axis chrome
on a ring), ``draw_x_chrome`` (angular tick marks + labels outside the outer
ring). ``CircularCoordinate`` itself becomes a thin geometry/parameter
holder that wires its methods to these helpers.

Lives in its own module so ``coordinates.py`` stays focused on the protocol
+ small affine implementations. The default Cartesian chrome lives in
``_chrome.py`` and needs no separate naming.
"""
from __future__ import annotations

import math

from .draw import cap_height, descender, circle, coord, measure_text, path, segment, text_path


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def geometry(r_inner: float, gap: float, iw: float, ih: float,
             r_outer: float = 1.0):
    """Compute ``(cx, cy, R, ri)`` for a ring inscribed in ``iw × ih``.

    ``R`` is the outer radius, ``ri`` the inner radius; both are gap-shrunk
    from the canvas half-extent and scaled by ``r_outer`` / ``r_inner`` so
    nested charts (one ring in the outer band, chords in the inner disc)
    each get a band that matches their artist projection.
    """
    R_full = min(iw, ih) / 2 * (1.0 - gap)
    R  = R_full * r_outer
    ri = R_full * r_inner
    cx, cy = iw / 2, ih / 2
    return cx, cy, R, ri


def t_to_angle(t: float, wrap_gap_rad: float) -> float:
    """Map ``t ∈ [0, 1]`` to a clockwise angle on the ring.

    When ``wrap_gap_rad == 0`` this collapses to ``π/2 − 2πt`` (the closed
    ring with t=0 = t=1 = 12 o'clock). When > 0 the data range covers
    ``(2π − wrap_gap_rad)`` of the circle, leaving a symmetric gap straddling
    12 o'clock: ``t=0`` lands just past 12 o'clock clockwise, ``t=1`` just
    before it. The wrap-around boundary (visually centered at 12 o'clock)
    is at angle ``π/2`` exactly.
    """
    return math.pi / 2 - wrap_gap_rad / 2 - t * (2 * math.pi - wrap_gap_rad)


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
# Y-axis chrome — inner+outer ring spines + intermediate tick rings
# ---------------------------------------------------------------------------

def draw_y_chrome(cx, cy, R, ri, wrap_gap_rad,
                  y_ticks_r, y_labels,
                  frame_opts) -> str:
    """Inner+outer ring spines + concentric y-tick marks + labels.

    Spines: outline circles at r=0 (inner) and r=1 (outer). When
    ``frame_opts["sector_ts"]`` is supplied (Circos with x-sectors), each
    ring is broken into per-sector arc segments so the ring doesn't bleed
    through the gap whitespace — each sector reads as a bounded arc.
    Intermediate y-ticks: short radial marks at 12 o'clock with labels
    stacked outward along the +y axis.
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
    y_decor   = frame_opts.get("y_decoration", "none")
    sector_ts = frame_opts.get("sector_ts")

    spine_top    = frame_opts.get("spine_top",    True)
    spine_bottom = frame_opts.get("spine_bottom", True)

    parts = []

    if sector_ts is None:
        # Closed rings — no sectors, draw as full circles.
        # top → outer arc (R), bottom → inner arc (ri).
        for radius, show in ((ri, spine_bottom), (R, spine_top)):
            if show:
                parts.append(circle(cx, cy, radius,
                                    stroke=spine_col, stroke_width=spine_w,
                                    tag="spine"))
    else:
        # Sectored — each ring is a sequence of arc segments, one per
        # sector. The arcs run clockwise from start_t to end_t (SVG sweep=1
        # in y-down means clockwise on screen). Large-arc flag is set when
        # the angular extent exceeds 180°.
        for radius, show in ((ri, spine_bottom), (R, spine_top)):
            if not show:
                continue
            for start_t, end_t in sector_ts:
                ang_s = t_to_angle(start_t, wrap_gap_rad)
                ang_e = t_to_angle(end_t,   wrap_gap_rad)
                x1 = cx + radius * math.cos(ang_s)
                y1 = cy - radius * math.sin(ang_s)
                x2 = cx + radius * math.cos(ang_e)
                y2 = cy - radius * math.sin(ang_e)
                large = 1 if abs(ang_s - ang_e) > math.pi else 0
                d = (f"M {coord(x1)},{coord(y1)} "
                     f"A {coord(radius)},{coord(radius)} 0 {large} 1 {coord(x2)},{coord(y2)}")
                parts.append(path(d, stroke=spine_col,
                                  stroke_width=spine_w))

    # Intermediate y-ticks: skip exact 0/1 (they're the rings).
    for r_f, lbl in zip(y_ticks_r, y_labels):
        if r_f <= 1e-9 or r_f >= 1.0 - 1e-9:
            continue
        radius = ri + r_f * (R - ri)
        tx, ty = cx, cy - radius   # 12 o'clock position
        if y_marks:
            parts.append(segment(tx, ty, tx, ty - tl,
                                 color=spine_col, width=spine_w))
        if show_yl:
            off = tl + tp + cap_height(y_size)
            parts.append(text_path(str(lbl), tx, ty - off,
                                   y_size, anchor="middle", color=font_col,
                                   fontstyle=y_style, decoration=y_decor,
                                   tag="tick-y"))

    return "".join(parts)


# ---------------------------------------------------------------------------
# X-axis chrome — angular tick marks + tangentially-oriented labels
# ---------------------------------------------------------------------------

def draw_x_sector_chrome(cx, cy, R, ri, wrap_gap_rad,
                         sector_ts, label_ts, names,
                         sec_opts) -> str:
    """Radial walls at each sector's edges + tangential sector-name labels.

    ``sector_ts`` is a list of ``(start_t, end_t)`` for each sector in
    t-space.  Each sector gets TWO radial walls — one at its start, one
    at its end — so the gap whitespace between adjacent sectors sits
    between two parallel walls (Circos style).  The wrap-around at 12
    o'clock is handled by the same mechanism: the first sector's start
    and the last sector's end map to opposite sides of the wrap gap when
    ``wrap_gap_rad > 0``, giving two walls bracketing the wrap gap too.
    """
    div_col   = sec_opts["divider_color"]
    div_w     = sec_opts["divider_width"]
    div_dash  = sec_opts.get("divider_dash")
    tp        = sec_opts["tick_pad"]
    font_size = sec_opts["label_fontsize"]
    font_col  = sec_opts["label_fontcolor"]
    font_st   = sec_opts.get("label_fontstyle", "normal")
    font_dc   = sec_opts.get("label_decoration", "none")
    draw_div  = sec_opts["draw_dividers"]
    draw_lbl  = sec_opts["draw_labels"]

    parts = []

    if draw_div:
        # Paired radial walls at each internal boundary (and the wrap
        # boundary) — same `_sector_walls` helper used by the linear
        # chrome, just on cyclic t-space. At gap=0 / wrap_gap_deg=0
        # paired walls coincide and stack; semi-transparent strokes
        # compensate via alpha.
        from ._chrome import _sector_walls
        for t in _sector_walls(sector_ts, cyclic=True):
            ang = t_to_angle(t, wrap_gap_rad)
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
            ang = t_to_angle(t, wrap_gap_rad)
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
                                   fontstyle=font_st, decoration=font_dc,
                                   rotate=rot, tag="sector-label"))

    return "".join(parts)


def draw_x_chrome(cx, cy, R, wrap_gap_rad,
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
    x_decor   = frame_opts.get("x_decoration", "none")

    parts = []

    for t, lbl in zip(x_ticks_t, x_labels):
        ang = t_to_angle(t, wrap_gap_rad)
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
            w = measure_text(str(lbl), x_size)
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
                                   fontstyle=x_style, decoration=x_decor,
                                   rotate=rot, tag="tick-x"))

    return "".join(parts)
