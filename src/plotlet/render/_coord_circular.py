"""Coordinate transforms for non-Cartesian artist registrations.

Protocol
--------
A coordinate is a callable ``(artist_dict, iw, ih) -> project(t, r) -> (px, py)``.

Registration
------------
``c.coordinate(CircularCoordinate(...))`` called once on a chart.  All
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

Each coord opts in the artists that render correctly under it via one
``declare_coord_support(coord_short_name, [artist_names...])`` call —
typically next to the coord's class definition.  ``coord_short_name`` is
the class name minus the ``Coordinate`` suffix (e.g. ``"Circular"`` for
``CircularCoordinate``).  The renderer raises ``NotImplementedError`` if
an artist appearing under a coord wasn't declared as a supporter.
Non-affine coords like ``CircularCoordinate`` aren't covered by
``svg_transform``; supporting artists draw through ``ctx.warp`` (a
Cartesian-pixel → coord-pixel closure handed to ``draw.*`` helpers via
``project=``), so edges subdivide and primitives project at draw time.

``clip_path_d(iw, ih) -> str``
    Returns an SVG path-data string used as the data-area clip region.
    When absent, the renderer falls back to the four-corner parallelogram
    polygon (correct for affine coordinates).  ``CircularCoordinate``
    returns an annulus; the renderer applies ``clip-rule="evenodd"`` so
    two concentric subpaths describe the ring.

``CircularCoordinate`` is the reference non-affine implementation (ring with
inner/outer radii), demonstrating the warp draw contract and the
``draw_x_frame`` / ``clip_path_d`` hooks.  See ``docs/EXTENDING.md`` for a
minimal-coord example covering the protocol's bare requirements.
"""
from __future__ import annotations

import math

from . import _chrome_circular as _cc
from .._coord_registry import register_coord_codec
from ..registry import declare_coord_support


class CircularCoordinate:
    """Ring-shaped coordinate: t around the ring, r along the radius.

    Maps (t, r) → pixel (x, y) on an annulus.  ``t ∈ [0, 1]`` runs clockwise
    from 12 o'clock; ``r ∈ [0, 1]`` is radial depth (0 = inner edge,
    1 = outer edge).  Non-affine, so only artists listed in the
    ``declare_coord_support("Circular", [...])`` block at the bottom of
    this module render under it — they draw through ``ctx.warp`` so each
    geometry point projects at draw time.  Other artists raise
    ``NotImplementedError`` at render time.

    Caveats:

    - Glyph paths (text drawn inside data artists) project the anchor only;
      the glyph shape stays Cartesian.  Frame-level text (titles, x/y tick
      labels via ``draw_x_frame`` / ``draw_frame``) is positioned in the
      coordinate directly and renders correctly.
    - ``c.sectors(axis="x")`` is supported (wedges with radial
      dividers and tangential labels).  ``c.sectors(axis="y")``
      (concentric bands) is not yet supported and raises at render time.

    Parameters
    ----------
    data_diameter : float or None, default None
        Outer diameter of the data annulus in pixels — the circular
        counterpart of a Cartesian chart's ``data_width``/``data_height``.
        The set diameter is exactly what renders: chrome (tick labels,
        sector labels) grows the canvas outward around it, the same way
        Cartesian margins grow around the data rectangle. ``None`` takes
        the ``size.data_diameter`` spec default. Chart-level
        ``data_width``/``data_height`` play no role under this coord.
    r_inner : float, default 0.30
        Where the chart's ``r=0`` lands, as a fraction of the data
        radius (``data_diameter / 2``). With ``r_outer=1.0`` (default)
        this is the ring's inner edge; for nested rings, set ``r_inner``
        / ``r_outer`` per chart to claim a sub-band of the annulus.
    r_outer : float, default 1.0
        Where the chart's ``r=1`` lands, as a fraction of the data
        radius. Combine with ``r_inner`` to nest multiple rings
        inside one canvas (e.g. ``r_inner=0.5, r_outer=0.75`` for a
        middle band).
    wrap_gap_deg : float or None, default None
        Angular gap (in degrees) at the 12 o'clock wrap-around boundary.
        ``None`` (default) auto-derives the angle from the x-sector gap so
        the wrap boundary is visually indistinguishable from any other
        inter-sector gap. Pass an explicit float to override. Works without
        sectors too: produces an open arc instead of a closed ring. Ignored
        when ``start_deg`` / ``end_deg`` are set explicitly (partial arc).
    start_deg : float, default 0.0
        Angle (degrees, clockwise from 12 o'clock) at which ``t=0`` lands.
        Default 0 = top.
    end_deg : float, default 360.0
        Angle (degrees, clockwise from 12 o'clock) at which ``t=1`` lands.
        Default 360 = back to top (closed ring). Pair with ``start_deg``
        for a partial arc. Convention:
        ``0 ≤ start_deg < end_deg ≤ start_deg + 360``. For an arc that
        crosses 12 o'clock (e.g. 9 → 3 o'clock through 12), pass values
        like ``start_deg=270, end_deg=450``.
    inner : Chart, optional
        A separate ``pt.chart(...)`` rendered into the central disc
        ``r ∈ [0, r_inner]`` — the area no ring claims. Used to host
        circular chord/link artists (e.g. ``c.chord_links``) that
        share the t-axis with the rings but live in the inner disc.
        The leaves passed via ``(c1 / c2 / ...).coordinate(...)`` still
        tile the annulus exactly as today; this is additive. The inner
        chart needs its own ``xlim`` matching the rings; sectors declared
        on the layout auto-propagate to the inner chart (declare
        ``c.sectors(...)`` on the inner chart explicitly to opt out).
    """

    def __init__(self, data_diameter=None,
                 r_inner: float = 0.30, r_outer: float = 1.0,
                 wrap_gap_deg=None,
                 inner=None,
                 start_deg: float = 0.0, end_deg: float = 360.0):
        self.data_diameter = data_diameter
        self.r_inner      = r_inner
        self.r_outer      = r_outer
        self.wrap_gap_deg = wrap_gap_deg
        self.inner        = inner
        self.start_deg    = start_deg
        self.end_deg      = end_deg
        # Circular default: no y-ticks. Override per chart via `c.yticks(...)`.
        self.y_ticks      = []

    def _to_dict(self) -> dict:
        # `inner` may be a Chart — encoded as a $ref by the serializer's
        # recursive value walker, not flattened here.
        return {"data_diameter": self.data_diameter,
                "r_inner": self.r_inner, "r_outer": self.r_outer,
                "wrap_gap_deg": self.wrap_gap_deg,
                "inner": self.inner,
                "start_deg": self.start_deg, "end_deg": self.end_deg}

    @classmethod
    def _from_dict(cls, d: dict) -> "CircularCoordinate":
        return cls(data_diameter=d.get("data_diameter"),
                   r_inner=d.get("r_inner", 0.30),
                   r_outer=d.get("r_outer", 1.0),
                   wrap_gap_deg=d.get("wrap_gap_deg"),
                   inner=d.get("inner"),
                   start_deg=d.get("start_deg", 0.0),
                   end_deg=d.get("end_deg", 360.0))

    @property
    def _is_full_ring(self) -> bool:
        # User intent — a full ring (possibly with a wrap_gap_deg at top)
        # is "start/end at defaults"; anything else is a partial arc.
        # `wrap_gap_deg > 0` still counts as a full ring (sectors cyclic,
        # labels at 12 o'clock, today's behavior).
        return self.start_deg == 0.0 and self.end_deg == 360.0

    @property
    def _start_rad(self) -> float:
        # Full ring + wrap_gap_deg shifts inward by gap/2 from 12 o'clock.
        # Partial arc maps start_deg directly (clockwise from 12 → math).
        if self._is_full_ring and self.wrap_gap_deg is not None:
            return math.pi / 2 - math.radians(self.wrap_gap_deg / 2)
        return math.pi / 2 - math.radians(self.start_deg)

    @property
    def _end_rad(self) -> float:
        if self._is_full_ring and self.wrap_gap_deg is not None:
            return math.pi / 2 - math.radians(360.0 - self.wrap_gap_deg / 2)
        return math.pi / 2 - math.radians(self.end_deg)

    def __call__(self, artist: dict, iw: float, ih: float):
        cx, cy, r_hi_px, r_lo_px = _cc.geometry(
            self.r_inner, self.data_diameter, iw, ih, self.r_outer)
        start_rad = self._start_rad
        end_rad   = self._end_rad

        def project(t: float, r: float):
            ang    = _cc.t_to_angle(t, start_rad, end_rad)
            radius = r_lo_px + r * (r_hi_px - r_lo_px)
            return cx + radius * math.cos(ang), cy - radius * math.sin(ang)

        return project

    # Each hook is a thin delegate: chrome hooks to `_chrome_circular`,
    # the container-layout strategy to `_layout_circular`. Bodies live
    # there so this module stays focused on the protocol — and because
    # this module loads at *record* time (instantiating the coord
    # imports it), the delegates import lazily so the render pipeline
    # only loads on first render.

    def derive_leaf_coords(self, leaves, heights=None) -> list:
        """`Layout.coordinate(...)` overlay hook: produce a per-leaf
        coord that claims a sub-band of this annulus. Band thickness is
        proportional to ``heights`` (the layout's ``.heights([...])``
        weights; equal split when None). First leaf gets the outermost
        band; later leaves nest inward. Inherits this coord's
        ``data_diameter``, ``wrap_gap_deg``, and arc range
        (``start_deg`` / ``end_deg``)."""
        c_lo, c_hi = self.r_inner, self.r_outer
        span = c_hi - c_lo
        weights = (list(heights) if heights is not None
                   else [1.0] * len(leaves))
        total = sum(weights) or 1.0
        cum = 0.0
        result = []
        for w in weights:
            prop = w / total
            r_hi = c_hi - cum
            r_lo = r_hi - prop * span
            cum += prop * span
            result.append(CircularCoordinate(
                data_diameter=self.data_diameter,
                r_inner=r_lo, r_outer=r_hi,
                wrap_gap_deg=self.wrap_gap_deg,
                start_deg=self.start_deg, end_deg=self.end_deg,
            ))
        return result

    def layout_size(self, root) -> tuple[int, int]:
        """The (W, H) this coord's `render_layout` will claim — consulted
        by `_atomic_size` so a ring embedded in a parent rect layout packs
        at its true footprint."""
        from ._layout_circular import layout_size
        return layout_size(self, root)

    def clip_path_d(self, iw: float, ih: float) -> str:
        # Clip to *this* chart's r-band [r_inner, r_outer] — not the full
        # canvas annulus. Otherwise nested rings can't constrain data to
        # their own band and overflow into the bands of other rings.
        cx, cy, R, ri = _cc.geometry(self.r_inner, self.data_diameter,
                                     iw, ih, self.r_outer)
        return _cc.clip_path_d(cx, cy, R, ri)

    def render_layout(self, root) -> tuple[int, int, str]:
        """`Layout.coordinate(...)` strategy for `CircularCoordinate`:
        overlay every leaf onto one canvas, each through its own r-band
        sub-coord derived from `derive_leaf_coords`. When ``self.inner``
        is set, an extra leaf is rendered into the central disc
        ``[0, r_inner]`` via its own sub-coord. Returns `(W, H, body)` —
        the inner body with no `<svg>` wrapper, so the caller decides
        whether to wrap it for a standalone render or inline it inside
        a parent `<g translate>`.

        Two staged halves: `resolve_layout` (canvas fixpoint, band
        derivation, ring journals spliced and replayed → per-ring
        states) and `emit_layout` (draw each ring from its state). The
        resolved plan caches on the layout node, so `resolve` can
        run the resolution ahead of time and this call only emits.

        Future coords (polar wedges, geographic facets, etc.) implement
        their own `render_layout` with a different strategy — the
        dispatcher in `_layout_engine.py` is coord-agnostic and just
        delegates here.
        """
        plan = getattr(root, "_coord_plan", None)
        if plan is None:
            plan = self.resolve_layout(root)
        return self.emit_layout(plan)

    def resolve_layout(self, root):
        """Resolution half: canvas metrics (chrome-pad fixpoint on the
        unspliced probe), wrap-gap and band derivation, then per ring —
        splice the leaf journal (band coord, chrome suppression) and
        replay it into a state dict. Caches the plan on `root` so
        `layout_size` and `render_layout` never re-probe a spliced
        tree."""
        from ._layout_circular import resolve_layout
        return resolve_layout(self, root)

    def emit_layout(self, plan) -> tuple[int, int, str]:
        """Emit half: draw each resolved ring from its state onto the
        shared overlay canvas. No re-resolution — the plan carries
        everything (per-ring states, panel opts, canvas metrics)."""
        from ._layout_circular import emit_layout
        return emit_layout(plan)

    def draw_frame(self, project, iw, ih, y_ticks_r, y_labels, frame_opts) -> str:
        return _cc.draw_y_chrome(
            *_cc.geometry(self.r_inner, self.data_diameter, iw, ih,
                          self.r_outer),
            self._start_rad, self._end_rad, self._is_full_ring,
            y_ticks_r, y_labels, frame_opts,
        )

    def draw_x_frame(self, project, iw, ih, x_ticks_t, x_labels, frame_opts) -> str:
        if self._is_full_ring:
            # On a closed ring t=0 and t=1 are the same angle, so a tick at
            # each end of a continuous domain overprints itself at the seam
            # ("1.0" on top of "0.0"). Keep the first of any coincident pair
            # — matplotlib polar likewise shows 0°, not 360°. Partial arcs
            # keep both ends (different angles).
            seen, ticks, labels = set(), [], []
            for t, lbl in zip(x_ticks_t, x_labels):
                key = round(t % 1.0, 9)
                if key in seen:
                    continue
                seen.add(key)
                ticks.append(t)
                labels.append(lbl)
            x_ticks_t, x_labels = ticks, labels
        cx, cy, R, _ri = _cc.geometry(self.r_inner, self.data_diameter,
                                      iw, ih, self.r_outer)
        return _cc.draw_x_chrome(cx, cy, R,
                                 self._start_rad, self._end_rad,
                                 x_ticks_t, x_labels, frame_opts)

    def draw_x_sector_chrome(self, project, iw, ih,
                             sector_ts, label_ts, names, sec_opts) -> str:
        return _cc.draw_x_sector_chrome(
            *_cc.geometry(self.r_inner, self.data_diameter, iw, ih,
                          self.r_outer),
            self._start_rad, self._end_rad, self._is_full_ring,
            sector_ts, label_ts, names, sec_opts,
        )


# Which core artists render correctly under CircularCoordinate.
# Extension artists self-register from their own modules — see
# `extensions/<name>.py` for each `declare_coord_support` call.
declare_coord_support("Circular", [
    "scatter", "line", "step", "hist", "heatmap", "fill_between", "area",
    "bar", "errorbar",
    "strip", "swarm", "qq", "rug", "ecdf", "freqpoly", "pointplot",
    "regression", "boxplot", "violin", "density_1d",
    "dendrogram",
    "axhline", "axvline", "axhspan", "axvspan", "hlines", "vlines",
    "rect", "polygon", "polyline",
    "text", "annotate",
])

register_coord_codec(CircularCoordinate)
