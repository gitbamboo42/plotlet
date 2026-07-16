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



def _circular_x_tick_labels(st, dw):
    """The x-tick label strings the ring will actually draw.

    Mirrors the render's resolution (``_resolve_panel_inputs``) exactly, so
    the chrome reservation matches what's drawn — not a guess. Two cases the
    naive estimate got wrong: an autoscaled ring's labels ("0.0" … "1.0")
    are far wider than a ``max(xlim)`` estimate, and a *continuous-sector*
    axis draws NO auto tick labels (they're meaningless on a global-offset
    coord) — so reserving for phantom numeric ticks over-shrinks the ring.
    """
    from .core import (_axis_descriptor, _auto_major_ticks,
                       _resolve_tick_formatter)
    from .._spec import _FRAME
    x_axis = _axis_descriptor([st], "x")
    x_scale = (x_axis.build(0, dw)
               if (x_axis.kind == "category" or not x_axis.flip)
               else x_axis.build(dw, 0))
    x_ticks = (st["x_ticks"] if st["x_ticks"] is not None
               else _auto_major_ticks(x_scale, max(2, min(8, int(dw // _FRAME["tick_density_x_px"]))),
                                      st["x_step"], st["x_count"]))
    x_fmt = _resolve_tick_formatter(st["x_format"], x_scale)
    x_labels = (st["x_labels"] if st["x_labels"] is not None
                else [x_fmt(t) for t in x_ticks])
    # Continuous sectors: auto ticks are suppressed; explicit ticks are
    # replicated per-sector. Same branch as `_resolve_panel_inputs`.
    x_sec = st.get("x_sectors")
    if x_sec is not None and x_sec.kind == "continuous":
        _, x_labels = x_sec.expand_ticks(
            x_ticks if st["x_ticks"] is not None else [],
            x_labels if st["x_ticks"] is not None else [])
    return x_labels


def _circular_chrome_pad(st, dw) -> float:
    """Radial pixels of chrome past the outer arc for the outermost ring.

    Mirrors the stacking logic in ``emit_chrome`` / ``draw_x_sector_chrome``
    but works from the chart state dict (available after ``_build_panel_opts``)
    rather than from a live scale.  ``dw`` is the t-axis pixel span (the
    panel width auto ticks resolve against), used to resolve the real tick
    labels. Used by ``render_layout`` to grow the canvas outward around
    the data annulus so labels don't get clipped by the viewBox.

    Returns 0 when no chrome is drawn outside the ring.
    """
    from .._spec import SPEC, _FRAME, _FONTSPEC
    from ..draw import cap_height, measure_text

    tl        = _FRAME["tick_length"]
    tp        = _FRAME["tick_pad"]
    tick_size = _FONTSPEC["tick_size"]
    x_size    = st["x_fontsize"] if st["x_fontsize"] is not None else tick_size
    show_lbl  = st["x_show_labels"]
    x_ticks_v = st.get("x_ticks")   # None=auto, []=suppressed, [...]= explicit

    x_chrome = 0.0
    labels = (_circular_x_tick_labels(st, dw)
              if (show_lbl and x_ticks_v != []) else [])
    if labels:
        x_style  = st.get("x_fontstyle") or "normal"
        x_weight = st.get("x_fontweight") or "normal"
        max_w  = max(measure_text(l, x_size, x_style, x_weight) for l in labels)
        x_chrome = tl + tp + max_w
    elif st.get("x_marks", True) and x_ticks_v != []:
        x_chrome = tl                # marks only, no labels (or none drawn)

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


class _CircularPlan:
    """Resolved overlay plan for a container `CircularCoordinate` —
    the coord's counterpart of the rect engine's `RenderPlan`. `rings`
    is `[(leaf, state, panel_opts), …]` in draw order (children
    outermost-first, then the `inner` disc chart if any); `W`/`H` the
    shared canvas edge from the chrome-pad fixpoint; `band` the
    layout-title band height. Built by `resolve_layout`, cached on the
    layout node, consumed by `emit_layout` / `layout_size`."""

    def __init__(self, root, W: int, H: int, band: int, rings: list):
        self.root = root
        self.W = W
        self.H = H
        self.band = band
        self.rings = rings


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

    # Each hook is a thin delegate to its counterpart in `_chrome_circular`.
    # Bodies live there so this module stays focused on the protocol +
    # small affine implementations.

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

    def _resolved_diameter(self) -> float:
        from .._spec import SPEC
        return (self.data_diameter if self.data_diameter is not None
                else SPEC["size"]["data_diameter"])

    def _canvas_metrics(self, root, leaves):
        """Resolve ``(D, W, probe_states)`` — the data diameter, the
        square canvas edge (D + outward chrome on both sides), and the
        panel-state probe reused by ``render_layout``. Chrome pad is a
        fixpoint: auto-tick density reads the t-axis pixel span (= W),
        which itself depends on the pad. Tick count is monotone in the
        span and capped, so this settles in one or two rounds."""
        from ._layout_engine import _build_panel_opts
        D = self._resolved_diameter()
        # State-only probe: the chrome pad reads the replayed states,
        # never margins or canvases — those are the circular resolve's
        # to dictate, so the rect margin measurement is skipped.
        _, probe_states = _build_panel_opts(root, measure_margins=False)
        st = probe_states[id(leaves[0])]
        pad = _circular_chrome_pad(st, D)
        for _ in range(4):
            W = int(math.ceil(D + 2 * pad))
            pad2 = _circular_chrome_pad(st, W)
            if pad2 == pad:
                break
            pad = pad2
        W = int(math.ceil(D + 2 * pad))
        return D, W, probe_states

    def layout_size(self, root) -> tuple[int, int]:
        """The (W, H) this coord's `render_layout` will claim — consulted
        by `_atomic_size` so a ring embedded in a parent rect layout packs
        at its true footprint. Consumes the resolved plan when present —
        the probe must not re-run after `resolve_layout` spliced the ring
        journals (a spliced probe would measure different chrome)."""
        plan = getattr(root, "_coord_plan", None)
        if plan is not None:
            return plan.W, plan.W + plan.band
        from ._layout_engine import _title_band_h
        leaves = list(root._iter_leaves())
        if not leaves:
            return 0, 0
        _, W, _ = self._canvas_metrics(root, leaves)
        return W, W + _title_band_h(root)

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
        resolved plan caches on the layout node, so `resolve_ir` can
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

    def resolve_layout(self, root) -> "_CircularPlan":
        """Resolution half: canvas metrics (chrome-pad fixpoint on the
        unspliced probe), wrap-gap and band derivation, then per ring —
        splice the leaf journal (band coord, chrome suppression) and
        replay it into a state dict. Caches the plan on `root` so
        `layout_size` and `render_layout` never re-probe a spliced
        tree."""
        from ._layout_engine import _build_panel_opts, _title_band_h
        from .core import _expand_frame_defaults

        leaves = list(root._iter_leaves())
        if not leaves:
            raise ValueError("Layout.coordinate(): no leaf charts to render")
        # The data annulus is exactly `data_diameter` across; chrome (tick
        # labels, sector labels) grows the canvas outward around it — the
        # circular counterpart of Cartesian margins around the data rect.
        # The probe runs with full layout context so layout-level
        # .sectors() propagates into the chrome measurement — and runs
        # before any splicing below, so it measures the user's journal.
        D, W, _probe_states = self._canvas_metrics(root, leaves)
        H = W
        # Layout-level title: one band above the overlay canvas —
        # `_atomic_size` claims the same extra height for parent
        # placement (via `layout_size`). Leaf bodies (and their recorded
        # regions) shift down by the band.
        band = _title_band_h(root)

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

        # Radial band split: the layout's `.heights([...])` weights;
        # equal bands when unset.
        heights = None
        for _c in root._calls:
            if _c[0] == "heights":
                heights = _c[1][0]
        if heights is not None and len(heights) != len(leaves):
            raise ValueError(
                f"Layout.heights(): {len(heights)} weights for "
                f"{len(leaves)} rings")

        leaf_coords = CircularCoordinate(
            data_diameter=D,
            r_inner=self.r_inner, r_outer=self.r_outer,
            wrap_gap_deg=resolved_wrap_gap_deg,
            start_deg=self.start_deg, end_deg=self.end_deg,
        ).derive_leaf_coords(leaves, heights)

        def _resolve_leaf(leaf, coord, *, is_outermost=False, prepend=()):
            # `prepend` carries inherited entries (today: dampened sectors
            # for `self.inner`) that need to be replayed before the
            # leaf's own calls. The leaves here are renderer-private nodes,
            # rebuilt fresh for every figure render and resolved exactly
            # once per render — so the splices and dimension overrides
            # below mutate freely, with nothing to restore.
            n_prepend = len(prepend)
            if n_prepend:
                leaf._calls[:0] = list(prepend)
            n0 = len(leaf._calls)
            own = next((c for c in leaf._calls if c[0] == "coordinate"),
                       None)
            if own is None:
                leaf._calls.append(("coordinate", [coord], {}))
            elif (isinstance(own[1][0], CircularCoordinate)
                    and own[1][0].data_diameter is None):
                # A leaf-declared coord shares this canvas — bake the
                # resolved diameter in so its geometry matches the
                # sibling bands (idempotent; leaves are rebuilt fresh
                # per render).
                own[1][0].data_diameter = D
            # title / x|y label are layout-level — suppress per leaf so
            # they don't stack. Spines flow through to draw_frame so
            # top/bottom drive the outer/inner arcs.
            leaf._calls.extend([
                ("title",  [""], {}),
                ("xlabel", [""], {}),
                ("ylabel", [""], {}),
            ])
            # x-axis: only the outermost ring shows ticks/labels/sector
            # labels (conventionally, labels sit outside the
            # outermost track). Inner rings suppress unless the leaf's
            # replay input already carries an xticks entry that decides
            # tick CONTENT (positions or label text) — user-explicit,
            # or an artist frame-default (chord rings set their own
            # tick treatment), hence checking the expanded list, which
            # is exactly what `_replay` will see. Style-only entries
            # (marks=, rotation=, ...) don't opt out — a labeled
            # dendrogram / heatmap turning marks off still wants its
            # inner-ring labels suppressed like any other ring.
            # y-axis suppression comes from the leaf coord's own
            # `y_ticks=[]` default (`CircularCoordinate.__init__`);
            # opt in per leaf with an explicit `c.yticks(...)`.
            def _decides_x_content(call):
                name, args, kw = call[0], call[1], call[2]
                if name != "xticks":
                    return False
                if any(a is not None for a in args[:2]):
                    return True
                if kw.get("ticks") is not None:
                    return True
                lbls = kw.get("labels")
                return lbls is not None and not isinstance(lbls, bool)
            has_xticks = any(
                _decides_x_content(c)
                for c in _expand_frame_defaults(leaf._calls[:n0]))
            if not is_outermost and not has_xticks:
                leaf._calls.append(("xticks", [[]], {"labels": False}))
            leaf._data_width  = W
            leaf._data_height = H
            # `_orig_data_*` too: the share-scaling reset inside
            # `_build_panel_opts` restores dims from these, and once the
            # leaf is spliced onto the shared overlay canvas the ring
            # dims ARE its declared dims — the pre-splice user value has
            # no consumer left.
            leaf._orig_data_width  = W
            leaf._orig_data_height = H
            leaf._margin = {"left": 0, "right": 0, "top": 0, "bottom": 0}
            leaf._canvas_width  = W
            leaf._canvas_height = H
            # Circular chrome places labels at angular positions inside
            # the outward chrome pad already baked into W — no Cartesian
            # margin band. The rect pre-pass runs in state+descriptor
            # mode (no margin measurement, `M_eff` left `None`); the
            # zero margin is assigned as the truth, and the leaf records
            # what actually renders: a zero-margin panel on the W×H
            # overlay canvas (emit draws with `_ZERO_MARGIN`).
            _panel_opts, _states = _build_panel_opts(leaf,
                                                     measure_margins=False)
            po = _panel_opts[id(leaf)]
            po.M_eff = {"left": 0, "right": 0, "top": 0, "bottom": 0}
            # Share-scaling's aspect rederivation is the one canvas
            # writer left inside the pre-pass — re-force after it.
            leaf._canvas_width  = W
            leaf._canvas_height = H
            leaf._last_M_eff = dict(po.M_eff)
            return leaf, _states[id(leaf)], po

        rings = [_resolve_leaf(leaf, c, is_outermost=(i == 0))
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
                data_diameter=D,
                r_inner=0.0, r_outer=self.r_inner,
                wrap_gap_deg=resolved_wrap_gap_deg,
                start_deg=self.start_deg, end_deg=self.end_deg,
            )
            rings.append(_resolve_leaf(self.inner, inner_coord,
                                       prepend=inner_prepend))

        plan = _CircularPlan(root=root, W=W, H=H, band=band, rings=rings)
        root._coord_plan = plan
        return plan

    def emit_layout(self, plan: "_CircularPlan") -> tuple[int, int, str]:
        """Emit half: draw each resolved ring from its state onto the
        shared overlay canvas. No re-resolution — the plan carries
        everything (per-ring states, panel opts, canvas metrics)."""
        from itertools import count
        from ._layout_engine import _emit_layout_title, _node_style
        from .core import _panel_open, _render_inner
        from .. import _regions
        _ZERO_MARGIN = {"left": 0, "right": 0, "top": 0, "bottom": 0}
        # Shared across leaves so coord-clip `<clipPath id>`s don't
        # collide once each leaf's body is concatenated into one document.
        _clip_counter = count()
        W, H, band = plan.W, plan.H, plan.band

        bodies = []
        for leaf, st, po in plan.rings:
            with _node_style(leaf):
                # Emit just the panel body (no <svg> wrapper) — the
                # caller concatenates each leaf's body into the shared
                # overlay canvas (below the title band, when present).
                with _regions.translate(0, band):
                    inner = _render_inner(st, W, H, _ZERO_MARGIN, po,
                                          clip_counter=_clip_counter)
                bodies.append(_panel_open(st, po, "translate(0,0)",
                                          _ZERO_MARGIN, W, H, (0, 0, W, H))
                              + inner + '</g>')

        body = "".join(bodies)
        if band:
            body = (_emit_layout_title(plan.root, 0, 0, W)
                    + f'<g transform="translate(0,{band})">{body}</g>')
        return W, H + band, body

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
