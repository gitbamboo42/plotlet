"""Coordinate transforms for non-Cartesian artist registrations.

Protocol
--------
A coordinate is a callable ``(artist_dict, iw, ih) -> project(t, r) -> (px, py)``.

Registration
------------
``c.coordinate(LinearCoordinate(angle=30))`` called once on a chart.  All
artists in the panel inherit it.  One coordinate per panel is enforced —
use separate panels for different coordinate systems.

Optional methods on the coordinate object unlock additional integration:

``draw_frame(project, iw, ih, y_ticks_r, y_labels, frame_opts) -> str``
    Replaces the Cartesian y-axis rendering (left spine, y ticks, y labels).
    ``y_ticks_r`` are tick positions pre-normalized to [0, 1] r-space
    (0 = bottom, 1 = top); pass them directly to ``project(0, r)``.
    ``frame_opts`` keys: spine_color, spine_width, tick_length, tick_pad,
    y_fontsize, font_color, y_marks, y_show_labels, y_fontstyle, y_decoration.

``draw_x_frame(project, iw, ih, x_ticks_t, x_labels, frame_opts) -> str``
    Replaces the Cartesian x-axis rendering (bottom spine, x ticks, x labels).
    Mirror of ``draw_frame`` for the t-axis.  When present, the standard
    bottom-spine + Cartesian x-tick block is skipped and this is emitted
    instead; the standard x-axis sector chrome is incompatible and raises.
    ``x_ticks_t`` are tick positions pre-normalized to [0, 1] t-space.
    ``frame_opts`` keys mirror ``draw_frame`` (x_fontsize, x_marks,
    x_show_labels, x_fontstyle, x_decoration in place of the y_ variants).

``svg_transform(project, iw, ih) -> str``
    Returns an SVG ``matrix(…)`` string.  When present, plotlet wraps the
    entire artist group in ``<g transform="…">`` so **existing artists work
    inside the coordinate without any changes** — they draw in Cartesian pixel
    space and the transform maps their output to the coordinate space.
    ``project`` is the closure already bound to the specific artist; derive the
    matrix from ``project(0,0)``, ``project(1,0)``, ``project(0,1)``.
    Only valid for *affine* coordinates (a parallelogram data area).
    When ``svg_transform`` is present, ``ctx.project`` is not set — artists
    should draw in Cartesian as usual.

``warp_svg(body, project, iw, ih) -> str``
    Non-affine analogue of ``svg_transform``.  Operates on the joined SVG
    body of the data-layer artists *after* they've drawn in Cartesian pixel
    space, rewriting coordinate attributes in-place through ``project``.
    Used by ``CircularCoordinate`` (rings can't be expressed as an affine
    matrix).  Caveats inherited from string-level warping: line segments
    become straight chords between warped endpoints; glyph paths (text)
    are passed through unwarped.

``clip_path_d(iw, ih) -> str``
    Returns an SVG path-data string used as the data-area clip region.
    When absent, the renderer falls back to the four-corner parallelogram
    polygon (correct for affine coordinates).  ``CircularCoordinate``
    returns an annulus; the renderer applies ``clip-rule="evenodd"`` so
    two concentric subpaths describe the ring.

``LinearCoordinate`` is the affine reference implementation (x-axis horizontal,
y-axis tilts).  ``CircularCoordinate`` is the non-affine reference (ring with
inner/outer radii), demonstrating the ``warp_svg`` / ``draw_x_frame`` /
``clip_path_d`` hooks.
"""
from __future__ import annotations

import math
import re


class LinearCoordinate:
    """Coordinate transform: x-axis stays horizontal, y-axis tilts.

    At ``angle=0`` (default) this is identical to a standard Cartesian chart.
    ``angle`` is the degrees the y-axis (r-axis) tilts clockwise from vertical:
    positive values tilt the y-axis to the right, negative to the left.
    The x-axis (t-axis) is always horizontal regardless of angle.

    ``origin`` is the pixel position of the (t=0, r=0) corner; defaults to
    the canvas bottom-left ``(0, ih)``.  ``length`` and ``thickness`` are the
    pixel extents along the x-axis and y-axis; they default to ``iw`` and
    ``ih`` so the coordinate fills the canvas at angle=0.
    Pass explicit values when placing a stub at an arbitrary position on a
    larger canvas.

    Panel-level usage (standard artists in a tilted frame)::

        c = pt.chart(...)
        c.coordinate(LinearCoordinate(angle=30))
        c.line(...)   # works unchanged via svg_transform

    ArtistSpec-level usage (intrinsically non-Cartesian artist)::

        spec = ArtistSpec(
            name="my_spine",
            record=..., draw=...,
            xdomain=lambda a: [0.0, 1.0],
            ydomain=lambda a: [0.0, 1.0],
            coordinate=LinearCoordinate(angle=30),
        )
    """

    def __init__(self, angle: float = 0.0,
                 origin=None,
                 length=None,
                 thickness=None):
        self.angle_deg  = angle
        self.origin     = origin     # (x, y) of (t=0, r=0); None → (0, ih)
        self.length     = length     # px along baseline;    None → iw
        self.thickness  = thickness  # px along normal axis; None → ih

    def __call__(self, artist: dict, iw: float, ih: float):
        a      = math.radians(self.angle_deg)
        cos_a  = math.cos(a)
        sin_a  = math.sin(a)
        ox, oy = self.origin    if self.origin    is not None else (0.0, float(ih))
        L      = self.length    if self.length    is not None else float(iw)
        T      = self.thickness if self.thickness is not None else float(ih)

        def project(t: float, r: float):
            # x-axis (t) is always horizontal; y-axis (r) tilts at `angle` from vertical
            #   r-direction = (sin_a, -cos_a) in SVG coords (y increases down)
            #   angle=0  → (0, -1) = straight up ✓
            #   angle=30 → (0.5, -0.866): up-and-right tilt ✓
            return (ox + t * L + r * T * sin_a,
                    oy          - r * T * cos_a)

        return project

    def svg_transform(self, project, iw: float, ih: float) -> str:
        """SVG matrix that maps Cartesian artist output into this coordinate.

        Derived from 3 corners of the unit parallelogram so it works for any
        ``project`` closure, including dynamic-angle subclasses.
        """
        bl_x, bl_y = project(0.0, 0.0)
        br_x, br_y = project(1.0, 0.0)
        tl_x, tl_y = project(0.0, 1.0)
        a = (br_x - bl_x) / iw
        b = (br_y - bl_y) / iw
        c = (bl_x - tl_x) / ih
        d = (bl_y - tl_y) / ih
        e = tl_x
        f = tl_y
        return f"matrix({a:.6f},{b:.6f},{c:.6f},{d:.6f},{e:.4f},{f:.4f})"

    def draw_frame(self, project, iw, ih,
                   y_ticks_r, y_labels,
                   frame_opts) -> str:
        """Draw the coordinate-aware y-axis: left spine, y tick marks, y labels.

        ``y_ticks_r`` are tick positions pre-normalized to [0,1] r-space;
        pass directly to ``project(0, r)``.  Replaces the Cartesian left
        spine and y-axis; x-axis stays Cartesian.
        """
        from .draw import segment, text_path, cap_height

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

        parts = []
        eps = 1e-5

        # True coordinate parallelogram: all four corners from project().
        # Bottom spine (BL→BR) is drawn by main Cartesian renderer.
        #   TL -------- TR       TL = project(0, 1)
        #   |            |       TR = project(1, 1)
        #   BL -------- BR       BL = project(0, 0),  BR = project(1, 0)
        bl_x, bl_y = project(0.0, 0.0)
        tl_x, tl_y = project(0.0, 1.0)
        br_x, br_y = project(1.0, 0.0)
        tr_x, tr_y = project(1.0, 1.0)

        for (sx1, sy1), (sx2, sy2) in (
            ((bl_x, bl_y), (tl_x, tl_y)),   # left  (r-axis, tilted)
            ((tl_x, tl_y), (tr_x, tr_y)),   # top   (horizontal, parallel to bottom)
            ((br_x, br_y), (tr_x, tr_y)),   # right (tilted, parallel to left)
        ):
            parts.append(segment(sx1, sy1, sx2, sy2,
                                 color=spine_col, width=spine_w, tag="spine"))

        # Y-ticks along the r-axis (t=0).
        # r values arrive pre-normalized to [0,1] by the caller.
        # Outward normal = -t-tangent at (0, r): points away from t>0 region.
        for r_f, lbl in zip(y_ticks_r, y_labels):
            px, py = project(0.0, r_f)
            ex, ey = project(eps, r_f)
            dx = (ex - px) / eps
            dy = (ey - py) / eps
            n = math.hypot(dx, dy) or 1.0
            ttx, tty = dx / n, dy / n
            onx, ony = -ttx, -tty   # outward: -t direction
            if y_marks:
                parts.append(segment(px, py, px + onx * tl, py + ony * tl,
                                     color=spine_col, width=spine_w))
            if show_yl:
                rot = -math.degrees(math.atan2(tty, ttx))
                off = tl + tp + cap_height(y_size)
                parts.append(text_path(str(lbl), px + onx * off, py + ony * off,
                                       y_size, anchor="middle", color=font_col,
                                       fontstyle=y_style, decoration=y_decor,
                                       rotate=rot, tag="tick-y"))

        return "".join(parts)


class CircularCoordinate:
    """Ring-shaped coordinate: t around the ring, r along the radius.

    Maps (t, r) → pixel (x, y) on an annulus.  ``t ∈ [0, 1]`` runs clockwise
    from 12 o'clock; ``r ∈ [0, 1]`` is radial depth (0 = inner edge,
    1 = outer edge).  Non-affine, so the ``svg_transform`` matrix path
    can't be used — the renderer instead applies ``warp_svg`` to the
    data-layer SVG body so standard plotlet artists (scatter, line,
    numeric_bar, hist, …) work unchanged.

    Caveats inherited from the string-level warp:

    - Line segments warp endpoint-by-endpoint and become straight chords
      across the ring.  Fine for dense data, visible for sparse — pass
      more points if you need smoother arcs.
    - Glyph paths (text drawn inside data artists) are passed through
      unwarped.  Frame-level text (titles, x/y tick labels via
      ``draw_x_frame`` / ``draw_frame``) is positioned in the coordinate
      directly and renders correctly.
    - Combining ``c.sectors(axis="x")`` with a ring is not supported and
      raises at render time.

    Parameters
    ----------
    r_inner : float, default 0.30
        Inner ring radius as a fraction of the outer radius.
    gap : float, default 0.05
        Padding between outer ring edge and canvas edge, as a fraction
        of half the canvas size.
    """

    def __init__(self, r_inner: float = 0.30, gap: float = 0.05):
        self.r_inner = r_inner
        self.gap     = gap

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _geometry(self, iw: float, ih: float):
        R  = min(iw, ih) / 2 * (1.0 - self.gap)
        ri = R * self.r_inner
        cx, cy = iw / 2, ih / 2
        return cx, cy, R, ri

    def __call__(self, artist: dict, iw: float, ih: float):
        cx, cy, R, ri = self._geometry(iw, ih)

        def project(t: float, r: float):
            ang    = math.pi / 2 - 2 * math.pi * t
            radius = ri + r * (R - ri)
            return cx + radius * math.cos(ang), cy - radius * math.sin(ang)

        return project

    # ------------------------------------------------------------------
    # Non-affine warp: rewrite Cartesian artist SVG into ring space
    # ------------------------------------------------------------------

    def warp_svg(self, body: str, project, iw: float, ih: float) -> str:
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

    # ------------------------------------------------------------------
    # Annulus clip region — replaces the renderer's parallelogram polygon
    # ------------------------------------------------------------------

    def clip_path_d(self, iw: float, ih: float) -> str:
        """SVG path-d for an annular clip; renderer applies clip-rule="evenodd".

        Two concentric subpaths (outer ring, inner ring); evenodd fill
        leaves the annular region between them as the clip area.
        """
        cx, cy, R, ri = self._geometry(iw, ih)
        return (
            f"M {cx - R:.2f},{cy:.2f} "
            f"A {R:.2f},{R:.2f} 0 1,0 {cx + R:.2f},{cy:.2f} "
            f"A {R:.2f},{R:.2f} 0 1,0 {cx - R:.2f},{cy:.2f} Z "
            f"M {cx - ri:.2f},{cy:.2f} "
            f"A {ri:.2f},{ri:.2f} 0 1,0 {cx + ri:.2f},{cy:.2f} "
            f"A {ri:.2f},{ri:.2f} 0 1,0 {cx - ri:.2f},{cy:.2f} Z"
        )

    # ------------------------------------------------------------------
    # Frame chrome: inner+outer ring spines + y-tick rings + labels
    # ------------------------------------------------------------------

    def draw_frame(self, project, iw, ih,
                   y_ticks_r, y_labels,
                   frame_opts) -> str:
        """Inner+outer ring spines + concentric y-tick rings + labels.

        Spines: filled circles at r=0 (inner) and r=1 (outer).
        Intermediate y-ticks: short radial marks at 12 o'clock (t=0) with
        labels stacked outward along the +y axis.  r=0 and r=1 coincide
        with the rings themselves and are skipped to avoid duplicates.
        """
        from .draw import circle, segment, text_path, cap_height

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

        cx, cy, R, ri = self._geometry(iw, ih)
        parts = []

        # Inner and outer ring spines
        for radius in (ri, R):
            parts.append(circle(cx, cy, radius,
                                stroke=spine_col, stroke_width=spine_w,
                                tag="spine"))

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

    # ------------------------------------------------------------------
    # X-frame chrome: angular tick marks + labels outside the outer ring
    # ------------------------------------------------------------------

    def draw_x_frame(self, project, iw, ih,
                     x_ticks_t, x_labels,
                     frame_opts) -> str:
        """Radial tick marks just outside the outer ring + tangential labels.

        Labels sit at one tick_length + tick_pad outside the ring, rotated
        to the tangent direction (flipped 180° when otherwise upside-down)
        so the text reads naturally regardless of where on the ring it is.
        """
        from .draw import segment, text_path, cap_height

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

        cx, cy, R, _ri = self._geometry(iw, ih)
        parts = []

        for t, lbl in zip(x_ticks_t, x_labels):
            ang = math.pi / 2 - 2 * math.pi * t
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
