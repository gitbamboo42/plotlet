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
from .registry import declare_coord_support



def _circular_chrome_pad(st) -> float:
    """Radial pixels of chrome past the outer arc for the outermost ring.

    Mirrors the stacking logic in ``emit_chrome`` / ``draw_x_sector_chrome``
    but works from the chart state dict (available after ``_build_panel_opts``)
    rather than from a live scale.  Used by ``render_layout`` to decide how
    much to expand the canvas so labels don't get clipped by the viewBox.

    Returns 0 when no chrome is drawn outside the ring.
    """
    from ._spec import SPEC, _FRAME, _FONTSPEC
    from .draw import cap_height, measure_text

    tl        = _FRAME["tick_length"]
    tp        = _FRAME["tick_pad"]
    tick_size = _FONTSPEC["tick_size"]
    x_size    = st["x_fontsize"] if st["x_fontsize"] is not None else tick_size
    show_lbl  = st["x_show_labels"]
    x_ticks_v = st.get("x_ticks")   # None=auto, []=suppressed, [...]= explicit

    x_chrome = 0.0
    has_lbl   = show_lbl and x_ticks_v != []
    if has_lbl:
        if x_ticks_v:                # explicit non-empty ticks
            raw_lbl = st.get("x_labels")
            labels = [str(l) for l in raw_lbl] if raw_lbl else [str(t) for t in x_ticks_v]
        else:                        # auto ticks — estimate from xlim
            xlim = st.get("xlim") or (0, 1)
            max_val = max(abs(xlim[0]), abs(xlim[1]))
            labels = [f"{max_val:.4g}"]
        max_w  = max((measure_text(l, x_size) for l in labels), default=0.0)
        x_chrome = tl + tp + max_w
    elif st.get("x_marks", True) and x_ticks_v != []:
        x_chrome = tl                # marks only, no labels

    # Sector labels stack outside tick chrome (same rule as linear)
    x_sec = st.get("x_sectors")
    if x_sec is not None and getattr(x_sec, "label", False) and show_lbl:
        sec_size  = x_sec.fontsize if x_sec.fontsize is not None else SPEC["sectors"]["label_size"]
        sec_cap   = cap_height(sec_size)
        label_pad = SPEC["sectors"]["label_pad"]
        base_off  = (x_chrome + label_pad) if x_chrome > 0.0 else tp
        # Use the flipped-label offset (conservative worst case)
        return base_off + sec_cap * 1.5
    return x_chrome


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
    wrap_gap_deg : float or None, default None
        Angular gap (in degrees) at the 12 o'clock wrap-around boundary.
        ``None`` (default) auto-derives the angle from the x-sector gap so
        the wrap boundary is visually indistinguishable from any other
        inter-sector gap. Pass an explicit float to override. Works without
        sectors too: produces an open arc instead of a closed ring.
    inner : Chart, optional
        A separate ``pt.chart(...)`` rendered into the central disc
        ``r ∈ [0, r_inner]`` — the area no ring claims. Used to host
        Circos-style chord/link artists (e.g. ``c.chord_links``) that
        share the t-axis with the rings but live in the inner disc.
        The leaves passed via ``(c1 / c2 / ...).coordinate(...)`` still
        tile the annulus exactly as today; this is additive. The inner
        chart needs its own ``xlim`` matching the rings; sectors declared
        on the layout auto-propagate to the inner chart (declare
        ``c.sectors(...)`` on the inner chart explicitly to opt out).
    """

    def __init__(self, r_inner: float = 0.30, r_outer: float = 1.0,
                 gap: float = 0.05, wrap_gap_deg=None,
                 inner=None):
        self.r_inner      = r_inner
        self.r_outer      = r_outer
        self.gap          = gap
        self.wrap_gap_deg = wrap_gap_deg
        self.inner        = inner

    def _to_dict(self) -> dict:
        # `inner` may be a Chart — encoded as a $ref by the serializer's
        # recursive value walker, not flattened here.
        return {"r_inner": self.r_inner, "r_outer": self.r_outer,
                "gap": self.gap, "wrap_gap_deg": self.wrap_gap_deg,
                "inner": self.inner}

    @classmethod
    def _from_dict(cls, d: dict) -> "CircularCoordinate":
        return cls(r_inner=d.get("r_inner", 0.30),
                   r_outer=d.get("r_outer", 1.0),
                   gap=d.get("gap", 0.05),
                   wrap_gap_deg=d.get("wrap_gap_deg"),
                   inner=d.get("inner"))

    @property
    def _wrap_gap_rad(self) -> float:
        return math.radians(self.wrap_gap_deg) if self.wrap_gap_deg is not None else 0.0

    def __call__(self, artist: dict, iw: float, ih: float):
        cx, cy, r_hi_px, r_lo_px = _cc.geometry(
            self.r_inner, self.gap, iw, ih, self.r_outer)
        wrap = self._wrap_gap_rad

        def project(t: float, r: float):
            ang    = _cc.t_to_angle(t, wrap)
            radius = r_lo_px + r * (r_hi_px - r_lo_px)
            return cx + radius * math.cos(ang), cy - radius * math.sin(ang)

        return project

    # Each hook is a thin delegate to its counterpart in `_chrome_circular`.
    # Bodies live there so this module stays focused on the protocol +
    # small affine implementations.

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
        cx, cy, R, ri = _cc.geometry(self.r_inner, self.gap, iw, ih,
                                     self.r_outer)
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

        Future coords (polar wedges, geographic facets, etc.) implement
        their own `render_layout` with a different strategy — the
        dispatcher in `_layout_engine.py` is coord-agnostic and just
        delegates here.
        """
        import re
        from itertools import count
        from ._layout_engine import _build_panel_opts
        from ._spec import active_theme
        from .core import _render as _core_render
        _SVG_BODY_RE = re.compile(r'<svg[^>]*>(.*)</svg>\s*$', re.DOTALL)
        _ZERO_MARGIN = {"left": 0, "right": 0, "top": 0, "bottom": 0}
        # Shared across leaves so coord-clip `<clipPath id>`s don't
        # collide once the per-leaf `<svg>` wrappers are stripped and
        # bodies are concatenated into one document.
        _clip_counter = count()

        leaves = list(root._iter_leaves())
        if not leaves:
            raise ValueError("Layout.coordinate(): no leaf charts to render")
        W = max(leaf._data_width  for leaf in leaves)
        H = max(leaf._data_height for leaf in leaves)

        # Probe the outermost leaf's state (with full layout context so
        # layout-level .sectors() propagates) to compute required chrome.
        # chrome_pad is independent of R, so the probe can run before the
        # geometry is finalised.
        _, _probe_states = _build_panel_opts(root)
        chrome_pad = _circular_chrome_pad(_probe_states[id(leaves[0])])

        # Compute an effective gap that shrinks R just enough for chrome to
        # fit within the original W×H canvas.  This keeps the size consistent
        # with _atomic_size (which also returns W×H) so adjacent panels in a
        # parent layout don't overlap.
        _half = min(W, H) / 2.0
        available = _half * (1.0 - (1.0 - self.gap) * self.r_outer)
        if chrome_pad > available and _half * self.r_outer > 0:
            effective_gap = 1.0 - (_half - chrome_pad) / (_half * self.r_outer)
            effective_gap = min(max(effective_gap, self.gap), 0.99)
        else:
            effective_gap = self.gap

        # Resolve wrap_gap_deg=None → match the inter-sector gap visually.
        # The t-axis spans W pixels; a sector gap of gap_px pixels occupies
        # fraction gap_px/W of the full ring, i.e. 360*gap_px/W degrees.
        if self.wrap_gap_deg is None:
            _x_sec = _probe_states[id(leaves[0])].get("x_sectors")
            _gap_px = (_x_sec.gap if (_x_sec is not None and _x_sec.gap is not None
                                      and _x_sec.gap > 0) else 0.0)
            resolved_wrap_gap_deg = (360.0 * _gap_px / W) if (_gap_px > 0 and W > 0) else 0.0
        else:
            resolved_wrap_gap_deg = self.wrap_gap_deg

        leaf_coords = CircularCoordinate(
            r_inner=self.r_inner, r_outer=self.r_outer,
            gap=effective_gap, wrap_gap_deg=resolved_wrap_gap_deg,
        ).derive_leaf_coords(leaves)

        def _render_leaf(leaf, coord, *, is_outermost=False, prepend=()):
            # `prepend` carries inherited entries (today: dampened sectors
            # for `self.inner`) that need to be replayed before the
            # leaf's own calls. Inserted at the front of `_calls` and
            # cleaned up in `finally` so the leaf's journal is untouched
            # across re-renders — no permanent fan-out / insert(0).
            n_prepend = len(prepend)
            if n_prepend:
                leaf._calls[:0] = list(prepend)
            n0 = len(leaf._calls)
            orig_dw, orig_dh = leaf._data_width, leaf._data_height
            orig_margin = dict(leaf._margin)
            try:
                has_own_coord = any(c[0] == "coordinate" for c in leaf._calls)
                if not has_own_coord:
                    leaf._calls.append(("coordinate", [coord], {}))
                # title / x|y label are layout-level — suppress per leaf so
                # they don't stack. Spines flow through to draw_frame so
                # top/bottom drive the outer/inner arcs.
                leaf._calls.extend([
                    ("title",  [""], {}),
                    ("xlabel", [""], {}),
                    ("ylabel", [""], {}),
                ])
                # x-axis: only the outermost ring shows ticks/labels/sector
                # labels (Circos convention: labels outside the outermost
                # track). Inner rings suppress unless the user explicitly
                # called xticks(...) on that leaf.
                # y-axis: marks and labels off by default for all rings —
                # the radial scale reads from the data, not from tick marks.
                # Users can opt in with an explicit yticks(...) call.
                has_xticks = any(c[0] == "xticks" for c in leaf._calls[:n0])
                has_yticks = any(c[0] == "yticks" for c in leaf._calls[:n0])
                if not is_outermost and not has_xticks:
                    leaf._calls.append(("xticks", [[]], {"labels": False}))
                if not has_yticks:
                    leaf._calls.append(("yticks", [[]], {}))
                leaf._data_width  = W
                leaf._data_height = H
                leaf._margin = {"left": 0, "right": 0, "top": 0, "bottom": 0}
                leaf._canvas_width  = W
                leaf._canvas_height = H
                # Circular chrome places labels at angular positions inside
                # the gap zone — no Cartesian margin band needed. Calling
                # _build_panel_opts + _render with zero margin bypasses the
                # margin recomputation that _to_svg_unchecked would do,
                # which avoids a translate(N,0) offset that would misalign
                # this leaf with others rendered onto the same canvas.
                _panel_opts, _states = _build_panel_opts(leaf)
                _st = _states[id(leaf)]
                _theme = None
                for _c in leaf._calls:
                    if _c[0] == "theme": _theme = _c[1][0] if _c[1] else None
                with active_theme(_theme):
                    svg = _core_render(_st, W, H, _ZERO_MARGIN, outer=None,
                                       clip_counter=_clip_counter)
            finally:
                # Strip trailing render-time additions first, then the
                # prepended entries from the front. Order matters — n0
                # is computed after the prepend, so leaf._calls[n0:] is
                # the trailing block.
                del leaf._calls[n0:]
                if n_prepend:
                    del leaf._calls[:n_prepend]
                leaf._data_width, leaf._data_height = orig_dw, orig_dh
                leaf._margin = orig_margin
                leaf._canvas_width  = orig_dw + orig_margin["left"] + orig_margin["right"]
                leaf._canvas_height = orig_dh + orig_margin["top"]  + orig_margin["bottom"]
            m = _SVG_BODY_RE.match(svg)
            if m is None:
                raise RuntimeError(
                    "CircularCoordinate.render_layout: leaf produced no <svg> wrapper"
                )
            return m.group(1)

        bodies = [_render_leaf(leaf, c, is_outermost=(i == 0))
                  for i, (leaf, c) in enumerate(zip(leaves, leaf_coords))]

        if self.inner is not None:
            # Inherit the layout's sector partition onto the inner chart
            # (coord side-leaf — Layout._iter_leaves skips it). Force
            # divider/label off; outer ring carries the chrome. Emitted
            # as `prepend=` entries to `_render_leaf` so the inner's own
            # journal stays untouched — no insert(0) into `self.inner._calls`.
            # Skip per-axis when the inner has its own explicit sectors
            # call on that axis (last-write-wins would have made the
            # inherited entry lose anyway, but skipping is cheaper).
            #
            # Read the layout's sectors directly from `root._calls` (the
            # journal of the Layout where `coordinate()` was declared)
            # plus any cascadable sectors from ancestors of `root`.
            # That's the actual source — `.sectors(...)` records on the
            # Layout it's called on. The previous version read from
            # `leaves[0]._calls`, which misses Layout-level entries
            # because cascade only deposits them at replay time, not on
            # the leaf's own journal.
            from ._attachments import _is_sectors_call
            from ._layout_engine import _ancestor_calls
            outer_calls = list(_ancestor_calls(root)) + list(root._calls)
            inner_prepend: list = []
            for _axis in ("x", "y"):
                if any(_is_sectors_call(c, _axis) for c in self.inner._calls):
                    continue
                _outer = next((c for c in outer_calls
                               if _is_sectors_call(c, _axis)), None)
                if _outer is None:
                    continue
                _kw = dict(_outer[2])
                _kw["divider"] = False
                _kw["label"]   = False
                inner_prepend.append(("sectors", list(_outer[1]), _kw))
            inner_coord = CircularCoordinate(
                r_inner=0.0, r_outer=self.r_inner,
                gap=effective_gap, wrap_gap_deg=resolved_wrap_gap_deg,
            )
            bodies.append(_render_leaf(self.inner, inner_coord,
                                       prepend=inner_prepend))

        return W, H, "".join(bodies)

    def draw_frame(self, project, iw, ih, y_ticks_r, y_labels, frame_opts) -> str:
        return _cc.draw_y_chrome(
            *_cc.geometry(self.r_inner, self.gap, iw, ih, self.r_outer),
            self._wrap_gap_rad,
            y_ticks_r, y_labels, frame_opts,
        )

    def draw_x_frame(self, project, iw, ih, x_ticks_t, x_labels, frame_opts) -> str:
        cx, cy, R, _ri = _cc.geometry(self.r_inner, self.gap, iw, ih,
                                      self.r_outer)
        return _cc.draw_x_chrome(cx, cy, R, self._wrap_gap_rad,
                                 x_ticks_t, x_labels, frame_opts)

    def draw_x_sector_chrome(self, project, iw, ih,
                             sector_ts, label_ts, names, sec_opts) -> str:
        return _cc.draw_x_sector_chrome(
            *_cc.geometry(self.r_inner, self.gap, iw, ih, self.r_outer),
            self._wrap_gap_rad,
            sector_ts, label_ts, names, sec_opts,
        )


# Which core artists render correctly under CircularCoordinate.
# Extension artists self-register from their own modules — see
# `extensions/<name>.py` for each `declare_coord_support` call.
declare_coord_support("Circular", [
    "scatter", "line", "step", "hist", "heatmap", "fill_between", "area",
])
