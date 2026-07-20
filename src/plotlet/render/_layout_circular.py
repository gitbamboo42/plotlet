"""Container-layout strategy for ``CircularCoordinate``.

The resolve/emit halves of ``Layout.coordinate(CircularCoordinate(...))``:
overlay every leaf chart onto one shared canvas as concentric rings
(``resolve_layout`` → ``_CircularPlan`` → ``emit_layout``), plus the
canvas-size probe ``layout_size``.  ``CircularCoordinate``'s layout
methods are thin delegates into here — the same split its chrome hooks
use with ``_chrome_circular``.

Lives apart from ``_coord_circular.py`` because that module loads at
*record* time (instantiating the coord imports it; nothing imports it
eagerly), so it must not pull the render pipeline in.  This module runs
only at render time, so it imports the pipeline at the top like any
other render-half module.
"""
from __future__ import annotations

import math
from itertools import count

from .. import _regions
from .._spec import SPEC
from . import _chrome_circular as _cc
from ._attachments import _is_sectors_call
from ._coord_circular import CircularCoordinate
from ._layout_engine import (_ancestor_calls, _emit_layout_title, _node_style,
                             _resolve_panels, _title_band_h)
from ._resolution import TICK_CONTENT_KW, _expand_frame_defaults
from .emit import _panel_open, _render_inner


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


def _resolved_diameter(coord) -> float:
    return (coord.data_diameter if coord.data_diameter is not None
            else SPEC["size"]["data_diameter"])


def _canvas_metrics(coord, root, leaves):
    """Resolve ``(D, W, probe_states)`` — the data diameter, the
    square canvas edge (D + outward chrome on both sides), and the
    panel-state probe reused by ``resolve_layout``. Chrome pad is a
    fixpoint: auto-tick density reads the t-axis pixel span (= W),
    which itself depends on the pad. Tick count is monotone in the
    span and capped, so this settles in one or two rounds."""
    D = _resolved_diameter(coord)
    # State-only probe: the chrome pad reads the replayed states,
    # never margins or canvases — those are the circular resolve's
    # to dictate, so the rect margin measurement is skipped.
    _, probe_states = _resolve_panels(root, measure_margins=False)
    state = probe_states[id(leaves[0])]
    pad = _cc.chrome_pad(state, D)
    for _ in range(4):
        W = int(math.ceil(D + 2 * pad))
        pad2 = _cc.chrome_pad(state, W)
        if pad2 == pad:
            break
        pad = pad2
    W = int(math.ceil(D + 2 * pad))
    return D, W, probe_states


def layout_size(coord, root) -> tuple[int, int]:
    """The (W, H) the coord's `render_layout` will claim — consulted
    by `_atomic_size` so a ring embedded in a parent rect layout packs
    at its true footprint. Consumes the resolved plan when present —
    the probe must not re-run after `resolve_layout` spliced the ring
    journals (a spliced probe would measure different chrome)."""
    plan = getattr(root, "_coord_plan", None)
    if plan is not None:
        return plan.W, plan.W + plan.band
    leaves = list(root._iter_leaves())
    if not leaves:
        return 0, 0
    _, W, _ = _canvas_metrics(coord, root, leaves)
    return W, W + _title_band_h(root)


def _resolve_wrap_gap(coord, probe_state, W) -> float:
    """Resolve wrap_gap_deg=None → match the inter-sector gap visually.
    The t-axis spans W pixels; a sector gap of gap_px pixels occupies
    fraction gap_px/W of the full ring, i.e. 360*gap_px/W degrees."""
    if coord.wrap_gap_deg is not None:
        return coord.wrap_gap_deg
    x_sec = probe_state.get("x_sectors")
    gap_px = (x_sec.gap if (x_sec is not None and x_sec.gap is not None
                            and x_sec.gap > 0) else 0.0)
    return (360.0 * gap_px / W) if (gap_px > 0 and W > 0) else 0.0


def _ring_heights(root, leaves):
    """Radial band split: the layout's `.heights([...])` weights;
    None (unset) → equal bands."""
    heights = None
    for _c in root._calls:
        if _c[0] == "heights":
            heights = _c[1][0]
    if heights is not None and len(heights) != len(leaves):
        raise ValueError(
            f"Layout.heights(): {len(heights)} weights for "
            f"{len(leaves)} rings")
    return heights


def _decides_x_content(call) -> bool:
    name, args, kw = call[0], call[1], call[2]
    if name != "xticks":
        return False
    if any(a is not None for a in args[:2]):
        return True
    if any(kw.get(k) is not None for k in TICK_CONTENT_KW):
        return True
    lbls = kw.get("labels")
    return lbls is not None and not isinstance(lbls, bool)


def _resolve_ring(leaf, coord, D, W, H, *, is_outermost=False, prepend=()):
    # `prepend` carries inherited entries (today: dampened sectors
    # for the coord's `inner` chart) that need to be replayed before the
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
    has_xticks = any(
        _decides_x_content(c)
        for c in _expand_frame_defaults(leaf._calls[:n0]))
    if not is_outermost and not has_xticks:
        leaf._calls.append(("xticks", [[]], {"labels": False}))
    leaf._data_width  = W
    leaf._data_height = H
    # `_orig_data_*` too: the share-scaling reset inside
    # `_resolve_panels` restores dims from these, and once the
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
    _panel_opts, _states = _resolve_panels(leaf,
                                             measure_margins=False)
    layout_opts = _panel_opts[id(leaf)]
    layout_opts.M_eff = {"left": 0, "right": 0, "top": 0, "bottom": 0}
    # Share-scaling's aspect rederivation is the one canvas
    # writer left inside the pre-pass — re-force after it.
    leaf._canvas_width  = W
    leaf._canvas_height = H
    leaf._last_M_eff = dict(layout_opts.M_eff)
    return leaf, _states[id(leaf)], layout_opts


def _inner_prepend(root, inner) -> list:
    """Inherit the layout's sector partition onto the inner chart
    (coord side-leaf — Layout._iter_leaves skips it). Force
    divider/label off; outer ring carries the chrome. Emitted
    as `prepend=` entries to `_resolve_ring` so the inner's own
    journal stays untouched — no insert(0) into `inner._calls`.
    Skip per-axis when the inner has its own explicit sectors
    call on that axis (last-write-wins would have made the
    inherited entry lose anyway, but skipping is cheaper).

    Read the layout's sectors directly from `root._calls` (the
    journal of the Layout where `coordinate()` was declared)
    plus any cascadable sectors from ancestors of `root`.
    That's the actual source — `.sectors(...)` records on the
    Layout it's called on. Reading from the first leaf's journal
    instead would miss Layout-level entries, because cascade only
    deposits them at replay time, not on the leaf's own journal."""
    outer_calls = list(_ancestor_calls(root)) + list(root._calls)
    prepend: list = []
    for axis in ("x", "y"):
        if any(_is_sectors_call(c, axis) for c in inner._calls):
            continue
        outer = next((c for c in outer_calls
                      if _is_sectors_call(c, axis)), None)
        if outer is None:
            continue
        kw = dict(outer[2])
        kw["divider"] = False
        kw["label"]   = False
        prepend.append(("sectors", list(outer[1]), kw))
    return prepend


def resolve_layout(coord, root) -> "_CircularPlan":
    """Resolution half of the coord's `render_layout`: canvas metrics
    (chrome-pad fixpoint on the unspliced probe), wrap-gap and band
    derivation, then per ring — splice the leaf journal (band coord,
    chrome suppression) and replay it into a state dict. Caches the
    plan on `root` so `layout_size` and `render_layout` never re-probe
    a spliced tree."""
    leaves = list(root._iter_leaves())
    if not leaves:
        raise ValueError("Layout.coordinate(): no leaf charts to render")
    # The data annulus is exactly `data_diameter` across; chrome (tick
    # labels, sector labels) grows the canvas outward around it — the
    # circular counterpart of Cartesian margins around the data rect.
    # The probe runs with full layout context so layout-level
    # .sectors() propagates into the chrome measurement — and runs
    # before any splicing below, so it measures the user's journal.
    D, W, probe_states = _canvas_metrics(coord, root, leaves)
    H = W
    # Layout-level title: one band above the overlay canvas —
    # `_atomic_size` claims the same extra height for parent
    # placement (via `layout_size`). Leaf bodies (and their recorded
    # regions) shift down by the band.
    band = _title_band_h(root)

    wrap_gap = _resolve_wrap_gap(coord, probe_states[id(leaves[0])], W)
    heights = _ring_heights(root, leaves)

    leaf_coords = CircularCoordinate(
        data_diameter=D,
        r_inner=coord.r_inner, r_outer=coord.r_outer,
        wrap_gap_deg=wrap_gap,
        start_deg=coord.start_deg, end_deg=coord.end_deg,
    ).derive_leaf_coords(leaves, heights)

    rings = [_resolve_ring(leaf, c, D, W, H, is_outermost=(i == 0))
             for i, (leaf, c) in enumerate(zip(leaves, leaf_coords))]

    if coord.inner is not None:
        inner_coord = CircularCoordinate(
            data_diameter=D,
            r_inner=0.0, r_outer=coord.r_inner,
            wrap_gap_deg=wrap_gap,
            start_deg=coord.start_deg, end_deg=coord.end_deg,
        )
        rings.append(_resolve_ring(coord.inner, inner_coord, D, W, H,
                                   prepend=_inner_prepend(root, coord.inner)))

    plan = _CircularPlan(root=root, W=W, H=H, band=band, rings=rings)
    root._coord_plan = plan
    return plan


def emit_layout(plan: "_CircularPlan") -> tuple[int, int, str]:
    """Emit half: draw each resolved ring from its state onto the
    shared overlay canvas. No re-resolution — the plan carries
    everything (per-ring states, panel opts, canvas metrics)."""
    _ZERO_MARGIN = {"left": 0, "right": 0, "top": 0, "bottom": 0}
    # Shared across leaves so coord-clip `<clipPath id>`s don't
    # collide once each leaf's body is concatenated into one document.
    _clip_counter = count()
    W, H, band = plan.W, plan.H, plan.band

    bodies = []
    for leaf, state, layout_opts in plan.rings:
        with _node_style(leaf):
            # Emit just the panel body (no <svg> wrapper) — the
            # caller concatenates each leaf's body into the shared
            # overlay canvas (below the title band, when present).
            with _regions.translate(0, band):
                inner = _render_inner(state, W, H, _ZERO_MARGIN, layout_opts,
                                      clip_counter=_clip_counter)
            bodies.append(_panel_open(state, layout_opts, "translate(0,0)",
                                      _ZERO_MARGIN, W, H, (0, 0, W, H))
                          + inner + '</g>')

    body = "".join(bodies)
    if band:
        body = (_emit_layout_title(plan.root, 0, 0, W)
                + f'<g transform="translate(0,{band})">{body}</g>')
    return W, H + band, body
