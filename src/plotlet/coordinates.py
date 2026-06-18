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
    instead.  ``x_ticks_t`` are tick positions pre-normalized to [0, 1]
    t-space.  ``frame_opts`` keys mirror ``draw_frame`` (x_fontsize,
    x_marks, x_show_labels, x_fontstyle, x_decoration in place of the
    y_ variants).

``draw_x_sector_chrome(project, iw, ih, sector_ts, label_ts, names, sec_opts) -> str``
    Replaces the Cartesian x-axis sector chrome (vertical dividers + bottom
    labels) — required when ``draw_x_frame`` is implemented AND the user
    sets ``c.sectors(axis="x")``.  ``sector_ts`` is a list of
    ``(start_t, end_t)`` for each sector in t-space (already accounting
    for any pixel gap between sectors); ``label_ts`` are the sector
    centers.  The hook decides whether to draw one divider per gap or two
    walls per sector — ``CircularCoordinate`` draws walls so each sector
    reads as a bounded wedge.  ``sec_opts`` carries divider style + label
    font style plus ``draw_dividers`` / ``draw_labels`` toggles.

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
    - ``c.sectors(axis="x")`` is supported (Circos-style wedges with
      radial dividers and tangential labels).  ``c.sectors(axis="y")``
      (concentric bands) is not yet supported and raises at render time.

    Parameters
    ----------
    r_inner : float, default 0.30
        Where the chart's ``r=0`` lands, as a fraction of the canvas
        outer radius. With ``r_outer=1.0`` (default) this is the ring's
        inner edge; for nested rings, set ``r_inner`` / ``r_outer``
        per chart to claim a sub-band of the canvas annulus.
    r_outer : float, default 1.0
        Where the chart's ``r=1`` lands, as a fraction of the canvas
        outer radius. Combine with ``r_inner`` to nest multiple rings
        inside one canvas (e.g. ``r_inner=0.5, r_outer=0.75`` for a
        middle band).
    gap : float, default 0.05
        Padding between outer ring edge and canvas edge, as a fraction
        of half the canvas size.
    wrap_gap_deg : float, default 0.0
        Angular gap (in degrees) at the 12 o'clock wrap-around boundary.
        With sectors set, matching ``wrap_gap_deg`` to your
        ``c.sectors(gap=N)`` (visually) gives the ring a symmetric look —
        otherwise the wrap-around joins back-to-back while internal
        boundaries show whitespace. Works without sectors too: produces
        an open arc instead of a closed ring.
    """

    def __init__(self, r_inner: float = 0.30, r_outer: float = 1.0,
                 gap: float = 0.05, wrap_gap_deg: float = 0.0):
        self.r_inner      = r_inner
        self.r_outer      = r_outer
        self.gap          = gap
        self.wrap_gap_deg = wrap_gap_deg

    @property
    def _wrap_gap_rad(self) -> float:
        return math.radians(self.wrap_gap_deg)

    def __call__(self, artist: dict, iw: float, ih: float):
        cx, cy, R, _ri = _cc.geometry(self.r_inner, self.gap, iw, ih)
        # Per-chart radial band: r ∈ [0, 1] maps to canvas radius
        # [r_inner * R_full, r_outer * R_full], where R_full is the
        # ungap-shrunk outer radius — so nested rings using fractions
        # of the canvas are consistent regardless of `gap`.
        R_full = min(iw, ih) / 2
        r_lo_px = self.r_inner * R_full * (1.0 - self.gap)
        r_hi_px = self.r_outer * R_full * (1.0 - self.gap)
        wrap = self._wrap_gap_rad

        def project(t: float, r: float):
            ang    = _cc.t_to_angle(t, wrap)
            radius = r_lo_px + r * (r_hi_px - r_lo_px)
            return cx + radius * math.cos(ang), cy - radius * math.sin(ang)

        return project

    # Each hook is a thin delegate to its counterpart in `_chrome_circular`.
    # Bodies live there so this module stays focused on the protocol +
    # small affine implementations.

    def warp_svg(self, body: str, project, iw: float, ih: float) -> str:
        return _cc.warp_svg(body, project, iw, ih)

    def derive_leaf_coords(self, leaves) -> list:
        """`Layout.coordinate(...)` overlay hook: produce a per-leaf
        coord that claims a sub-band of this annulus proportional to
        each leaf's ``data_height``. First leaf gets the outermost
        band; later leaves nest inward. Inherits this coord's ``gap``
        and ``wrap_gap_deg``."""
        c_lo, c_hi = self.r_inner, self.r_outer
        span = c_hi - c_lo
        total_h = sum(leaf._data_height for leaf in leaves) or 1.0
        cum = 0.0
        result = []
        for leaf in leaves:
            prop = leaf._data_height / total_h
            r_hi = c_hi - cum
            r_lo = r_hi - prop * span
            cum += prop * span
            result.append(CircularCoordinate(
                r_inner=r_lo, r_outer=r_hi,
                gap=self.gap, wrap_gap_deg=self.wrap_gap_deg,
            ))
        return result

    def clip_path_d(self, iw: float, ih: float) -> str:
        # Clip to *this* chart's r-band [r_inner, r_outer] — not the full
        # canvas annulus. Otherwise nested rings can't constrain data to
        # their own band and overflow into the bands of other rings.
        cx, cy = iw / 2, ih / 2
        R_full = min(iw, ih) / 2
        ri = self.r_inner * R_full * (1.0 - self.gap)
        R  = self.r_outer * R_full * (1.0 - self.gap)
        return _cc.clip_path_d(cx, cy, R, ri)

    def render_layout(self, root) -> str:
        """`Layout.coordinate(...)` strategy for `CircularCoordinate`:
        overlay every leaf onto one canvas, each through its own r-band
        sub-coord derived from `derive_leaf_coords`. Bodies are
        concatenated and wrapped in one fresh `<svg>`.

        Future coords (polar wedges, geographic facets, etc.) can
        implement their own `render_layout` with a different strategy —
        the dispatcher in `_layout_engine.py` is coord-agnostic and just
        delegates here.
        """
        import re
        from ._spec import SPEC, _FONTSPEC
        _SVG_BODY_RE = re.compile(r'<svg[^>]*>(.*)</svg>\s*$', re.DOTALL)

        leaves = list(root._iter_leaves())
        if not leaves:
            raise ValueError("Layout.coordinate(): no leaf charts to render")
        W = max(leaf._data_width  for leaf in leaves)
        H = max(leaf._data_height for leaf in leaves)
        leaf_coords = self.derive_leaf_coords(leaves)

        bodies = []
        for i, leaf in enumerate(leaves):
            # Snapshot to restore so repeat renders stay idempotent.
            n0 = len(leaf._calls)
            orig_dw, orig_dh = leaf._data_width, leaf._data_height
            orig_margin = dict(leaf._margin)
            try:
                has_own_coord = any(c[0] == "coordinate" for c in leaf._calls)
                if not has_own_coord:
                    leaf._calls.append(("coordinate", [leaf_coords[i]], {}))
                # Suppress per-leaf Cartesian chrome — it would warp into
                # nonsense in the ring.
                leaf._calls.extend([
                    ("title",  [""], {}),
                    ("xlabel", [""], {}),
                    ("ylabel", [""], {}),
                    ("xticks", [[]], {}),
                    ("yticks", [[]], {}),
                    ("spines", [], {"top": False, "right": False,
                                    "bottom": False, "left": False}),
                ])
                # Resize this leaf to fill the warp canvas; zero margins
                # so its data area is exactly (W × H).
                leaf._data_width  = W
                leaf._data_height = H
                leaf._margin = {"left": 0, "right": 0, "top": 0, "bottom": 0}
                leaf._canvas_width  = W
                leaf._canvas_height = H
                svg = leaf._to_svg_unchecked(outer=None)
            finally:
                del leaf._calls[n0:]
                leaf._data_width, leaf._data_height = orig_dw, orig_dh
                leaf._margin = orig_margin
                leaf._canvas_width  = orig_dw + orig_margin["left"] + orig_margin["right"]
                leaf._canvas_height = orig_dh + orig_margin["top"]  + orig_margin["bottom"]
            m = _SVG_BODY_RE.match(svg)
            if m is None:
                raise RuntimeError(
                    "CircularCoordinate.render_layout: leaf produced no <svg> wrapper"
                )
            bodies.append(m.group(1))

        body = "".join(bodies)
        bg = SPEC["figure"]["background"]
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
                f'font-family="{_FONTSPEC["family"]}" font-size="11" '
                f'style="background:{bg}">{body}</svg>')

    def draw_frame(self, project, iw, ih, y_ticks_r, y_labels, frame_opts) -> str:
        return _cc.draw_y_chrome(
            *_cc.geometry(self.r_inner, self.gap, iw, ih),
            self._wrap_gap_rad,
            y_ticks_r, y_labels, frame_opts,
        )

    def draw_x_frame(self, project, iw, ih, x_ticks_t, x_labels, frame_opts) -> str:
        cx, cy, R, _ri = _cc.geometry(self.r_inner, self.gap, iw, ih)
        return _cc.draw_x_chrome(cx, cy, R, self._wrap_gap_rad,
                                 x_ticks_t, x_labels, frame_opts)

    def draw_x_sector_chrome(self, project, iw, ih,
                             sector_ts, label_ts, names, sec_opts) -> str:
        return _cc.draw_x_sector_chrome(
            *_cc.geometry(self.r_inner, self.gap, iw, ih),
            self._wrap_gap_rad,
            sector_ts, label_ts, names, sec_opts,
        )
