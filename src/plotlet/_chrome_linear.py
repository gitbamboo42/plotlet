"""Chrome helpers for ``LinearCoordinate``.

Procedural counterparts of the two hooks ``LinearCoordinate`` exposes —
``svg_transform`` (affine matrix derived from three corners of the projected
unit parallelogram) and ``draw_y_chrome`` (left + top + right spines of the
parallelogram plus tilted y-tick marks and labels). ``LinearCoordinate``
itself stays as a thin parameter holder that wires its methods to these
helpers.

Lives in its own module to mirror ``_chrome_circular.py`` — a non-default
coord owns its chrome file once it grows past a handful of lines.
"""
from __future__ import annotations

import math

from .draw import segment, text_path, cap_height


def svg_transform(project, iw: float, ih: float) -> str:
    """SVG matrix that maps Cartesian artist output into a parallelogram.

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


def draw_y_chrome(project, iw, ih,
                  y_ticks_r, y_labels,
                  frame_opts) -> str:
    """Coordinate-aware y-axis: left, top, right spines + tilted y-ticks.

    ``y_ticks_r`` are tick positions pre-normalized to [0, 1] r-space;
    pass directly to ``project(0, r)``. The bottom spine stays Cartesian
    (drawn by the main renderer); this draws the other three sides of the
    parallelogram plus the y-tick marks/labels along the r-axis at t=0.
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
    # r values arrive pre-normalized to [0, 1] by the caller.
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
