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

from . import _chrome_linear as _cl
from . import _chrome_circular as _cc


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

    # Each hook is a thin delegate to its counterpart in `_chrome_linear`.
    # Bodies live there so this module stays focused on the protocol +
    # small coord parameters.

    def svg_transform(self, project, iw: float, ih: float) -> str:
        return _cl.svg_transform(project, iw, ih)

    def draw_frame(self, project, iw, ih, y_ticks_r, y_labels, frame_opts) -> str:
        return _cl.draw_y_chrome(project, iw, ih, y_ticks_r, y_labels, frame_opts)


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

    def __call__(self, artist: dict, iw: float, ih: float):
        cx, cy, R, ri = _cc.geometry(self.r_inner, self.gap, iw, ih)

        def project(t: float, r: float):
            ang    = math.pi / 2 - 2 * math.pi * t
            radius = ri + r * (R - ri)
            return cx + radius * math.cos(ang), cy - radius * math.sin(ang)

        return project

    # Each hook is a thin delegate to its counterpart in `_chrome_circular`.
    # Bodies live there so this module stays focused on the protocol +
    # small affine implementations.

    def warp_svg(self, body: str, project, iw: float, ih: float) -> str:
        return _cc.warp_svg(body, project, iw, ih)

    def clip_path_d(self, iw: float, ih: float) -> str:
        return _cc.clip_path_d(*_cc.geometry(self.r_inner, self.gap, iw, ih))

    def draw_frame(self, project, iw, ih, y_ticks_r, y_labels, frame_opts) -> str:
        return _cc.draw_y_chrome(
            *_cc.geometry(self.r_inner, self.gap, iw, ih),
            y_ticks_r, y_labels, frame_opts,
        )

    def draw_x_frame(self, project, iw, ih, x_ticks_t, x_labels, frame_opts) -> str:
        cx, cy, R, _ri = _cc.geometry(self.r_inner, self.gap, iw, ih)
        return _cc.draw_x_chrome(cx, cy, R, x_ticks_t, x_labels, frame_opts)
