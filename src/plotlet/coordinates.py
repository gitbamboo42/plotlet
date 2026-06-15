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
    The x-axis (bottom spine, x ticks, x labels) always stays Cartesian.
    ``y_ticks_r`` are tick positions pre-normalized to [0, 1] r-space
    (0 = bottom, 1 = top); pass them directly to ``project(0, r)``.
    ``frame_opts`` keys: spine_color, spine_width, tick_length, tick_pad,
    y_fontsize, font_color, y_marks, y_show_labels, y_fontstyle, y_decoration.

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

``LinearCoordinate`` is the reference implementation: x-axis stays horizontal,
y-axis tilts at ``angle`` degrees from vertical.  It implements both
``draw_frame`` and ``svg_transform``, so existing artists (scatter, line, bar,
…) work inside it automatically.
"""
from __future__ import annotations

import math


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
