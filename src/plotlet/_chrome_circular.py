"""Chrome helpers for ``CircularCoordinate``.

Procedural counterparts of the four optional hooks ``CircularCoordinate``
exposes on the coordinate protocol — ``warp_svg``, ``clip_path_d``,
``draw_y_chrome`` (the y-axis chrome on a ring), ``draw_x_chrome`` (angular
tick marks + labels outside the outer ring). ``CircularCoordinate`` itself
becomes a thin geometry/parameter holder that wires its methods to these
helpers.

Lives in its own module so ``coordinates.py`` stays focused on the protocol
+ small affine implementations. The default Cartesian chrome lives in
``_chrome.py`` and needs no separate naming.
"""
from __future__ import annotations

import math
import re

from .draw import circle, segment, text_path, cap_height, path


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def geometry(r_inner: float, gap: float, iw: float, ih: float):
    """Compute ``(cx, cy, R, ri)`` for a ring inscribed in ``iw × ih``.

    ``R`` is the outer radius, ``ri`` the inner radius; both are gap-shrunk
    from the canvas half-extent.
    """
    R  = min(iw, ih) / 2 * (1.0 - gap)
    ri = R * r_inner
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
# Non-affine warp — rewrite Cartesian artist SVG into ring space
# ---------------------------------------------------------------------------

def warp_svg(body: str, project, iw: float, ih: float) -> str:
    """Remap Cartesian pixel coords in an SVG fragment through ``project``.

    Order matters: circle → path → rect → line.  ``rect`` emits a fresh
    ``<path d="…">`` with already-warped coords; running the path
    substitution before rect prevents a double-warp.
    """
    def remap(x_str, y_str):
        t = float(x_str) / iw
        r = 1.0 - float(y_str) / ih
        px, py = project(t, r)
        return f"{px:.2f}", f"{py:.2f}"

    # 1. <circle cx cy r> — scatter / dot markers
    def sub_cxcy(m):
        nx, ny = remap(m.group(1), m.group(2))
        return f'cx="{nx}" cy="{ny}"'
    body = re.sub(r'cx="([^"]+)"\s+cy="([^"]+)"', sub_cxcy, body)

    # 2. <path d="…"> — polylines / polygons (M/L/Z only).
    # Skip when d contains bezier/arc commands (= glyph paths from
    # text_path); warping glyph control points would mangle the letters.
    def sub_path_d(m):
        d = m.group(1)
        if re.search(r'[CcQqAaHhVvSsTt]', d):
            return m.group(0)
        def remap_pair(pm):
            nx, ny = remap(pm.group(1), pm.group(2))
            return f"{nx},{ny}"
        return f'd="{re.sub(r"(-?[0-9.]+),(-?[0-9.]+)", remap_pair, d)}"'
    body = re.sub(r'd="([^"]+)"', sub_path_d, body)

    # 3. <rect x y width height> — bars / box markers.
    # Expand to a 4-corner <path>; runs after the path pass so it isn't
    # re-warped on a second sweep.
    def sub_rect(m):
        x, y = float(m.group(1)), float(m.group(2))
        w, h = float(m.group(3)), float(m.group(4))
        rest = m.group(5)
        bl = remap(str(x),     str(y + h))
        br = remap(str(x + w), str(y + h))
        tr = remap(str(x + w), str(y))
        tl = remap(str(x),     str(y))
        d = f"M{bl[0]},{bl[1]} L{br[0]},{br[1]} L{tr[0]},{tr[1]} L{tl[0]},{tl[1]}Z"
        return f'<path d="{d}"{rest}'
    body = re.sub(
        r'<rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)"([^>]*>)',
        sub_rect, body)

    # 4. <line x1 x2 y1 y2> — axvline / segment
    def sub_line(m):
        nx1, ny1 = remap(m.group(1), m.group(3))
        nx2, ny2 = remap(m.group(2), m.group(4))
        return f'x1="{nx1}" x2="{nx2}" y1="{ny1}" y2="{ny2}"'
    body = re.sub(
        r'x1="([^"]+)"\s+x2="([^"]+)"\s+y1="([^"]+)"\s+y2="([^"]+)"',
        sub_line, body)

    return body


# ---------------------------------------------------------------------------
# Annulus clip region
# ---------------------------------------------------------------------------

def clip_path_d(cx, cy, R, ri) -> str:
    """SVG path-d for an annular clip; renderer applies ``clip-rule="evenodd"``.

    Two concentric subpaths (outer ring, inner ring); evenodd fill leaves
    the annular region between them as the clip area.
    """
    return (
        f"M {cx - R:.2f},{cy:.2f} "
        f"A {R:.2f},{R:.2f} 0 1,0 {cx + R:.2f},{cy:.2f} "
        f"A {R:.2f},{R:.2f} 0 1,0 {cx - R:.2f},{cy:.2f} Z "
        f"M {cx - ri:.2f},{cy:.2f} "
        f"A {ri:.2f},{ri:.2f} 0 1,0 {cx + ri:.2f},{cy:.2f} "
        f"A {ri:.2f},{ri:.2f} 0 1,0 {cx - ri:.2f},{cy:.2f} Z"
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

    parts = []

    if sector_ts is None:
        # Closed rings — no sectors, draw both as full circles.
        for radius in (ri, R):
            parts.append(circle(cx, cy, radius,
                                stroke=spine_col, stroke_width=spine_w,
                                tag="spine"))
    else:
        # Sectored — each ring is a sequence of arc segments, one per
        # sector. The arcs run clockwise from start_t to end_t (SVG sweep=1
        # in y-down means clockwise on screen). Large-arc flag is set when
        # the angular extent exceeds 180°.
        for radius in (ri, R):
            for start_t, end_t in sector_ts:
                ang_s = t_to_angle(start_t, wrap_gap_rad)
                ang_e = t_to_angle(end_t,   wrap_gap_rad)
                x1 = cx + radius * math.cos(ang_s)
                y1 = cy - radius * math.sin(ang_s)
                x2 = cx + radius * math.cos(ang_e)
                y2 = cy - radius * math.sin(ang_e)
                large = 1 if abs(ang_s - ang_e) > math.pi else 0
                d = (f"M {x1:.2f},{y1:.2f} "
                     f"A {radius:.2f},{radius:.2f} 0 {large} 1 {x2:.2f},{y2:.2f}")
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
        # Two walls per sector — one at start_t, one at end_t.  Adjacent
        # sectors don't share a wall; whitespace from gap_px sits between
        # them.  The wrap-around between the last sector's end (t=1) and
        # the first sector's start (t=0) is bracketed by the same logic
        # under the wrap_gap angular shift.
        for start_t, end_t in sector_ts:
            for t in (start_t, end_t):
                ang = t_to_angle(t, wrap_gap_rad)
                ux, uy = math.cos(ang), -math.sin(ang)
                parts.append(segment(cx + ri * ux, cy + ri * uy,
                                     cx + R  * ux, cy + R  * uy,
                                     color=div_col, width=div_w, dash=div_dash,
                                     tag="sector-divider"))

    if draw_lbl:
        # Same tangential anchoring as `draw_x_chrome` tick labels — labels
        # sit a font-cap above the outer ring and rotate with the tangent.
        off = tp + cap_height(font_size) / 2
        for name, t in zip(names, label_ts):
            ang = t_to_angle(t, wrap_gap_rad)
            ux, uy = math.cos(ang), -math.sin(ang)
            lx, ly = cx + (R + off) * ux, cy + (R + off) * uy
            rot = math.degrees(math.atan2(uy, ux)) + 90.0
            if rot > 90:  rot -= 180
            if rot < -90: rot += 180
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
            off = tl + tp + cap_height(x_size) / 2
            lx, ly = cx + (R + off) * ux, cy + (R + off) * uy
            # Tangent direction rotated to text baseline.
            rot = math.degrees(math.atan2(uy, ux)) + 90.0
            # Keep text right-side-up: flip 180° when it would otherwise
            # read upside-down (bottom half of the ring).
            if rot > 90:  rot -= 180
            if rot < -90: rot += 180
            parts.append(text_path(str(lbl), lx, ly,
                                   x_size, anchor="middle", color=font_col,
                                   fontstyle=x_style, decoration=x_decor,
                                   rotate=rot, tag="tick-x"))

    return "".join(parts)
