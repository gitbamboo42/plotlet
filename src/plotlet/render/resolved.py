"""Resolved IR — the render pipeline's middle stage.

Second lowering of the pipeline, and the stage the render path passes
through: `render.render_svg` is `resolve_ir(ir).to_svg()`. `_ir.py`
compiles the journal into the figure IR (`FigureIR`) — loss-free,
round-trippable, still in user terms (ops, data columns, palette
names). `resolve_ir` lowers one step further and returns a `ResolvedIR`
whose `.root` is a **complete render plan**: the emit pass runs from a
tree rehydrated out of `.root` alone (`_rehydrate`), so every field
here is load-bearing — delete one and rendering breaks, not just
inspection.

What resolution bakes into the projection:

  * axes are `IRScale` — an alias of `scales._AxisDescriptor`, the same
    pre-pixel type the layout engine builds and consumes (zero schema
    drift); share classes reference one descriptor per class
  * `state` is the full replayed per-leaf state — artists with baked
    per-group hex colors, sector partitions, tick config, spines —
    exactly what the emit pass draws from (`chrome` is a curated view
    of the same dict for quick inspection)
  * effective margins (`margin` = `M_eff`), grown canvases, and the
    joined-edge `hide`/`suppress` annotations from the layout engine's
    measurement pre-pass
  * `theme` / `font` made explicit (the recorder kept them as ops)
  * cross-panel wiring by `pid`: share anchors and legend sources
  * insets resolved recursively — each inset panel carries its own
    trained scales and margins (they render from their plan at emit,
    not by re-resolving)

Geometry (pixel rects) stays symbolic — placement is the emit pass's
job, downstream. Hence "pre-layout".

Container-coordinate figures (Circular) are staged too: the coord's
`resolve_layout` runs at resolution (canvas fixpoint, ring splicing,
per-ring replay), the projection carries the true ring states — each
ring panel's dims ARE the shared overlay canvas — and rehydration
rebuilds the overlay plan from them, so the coord's `render_layout`
emits without re-resolving (pinned: emit never touches
`_build_panel_opts`).

The resolved IR is one-way, not a round-trip peer: it deliberately
drops what's needed to rebuild the journal. Same journal → same
resolved IR. The projection is frozen Python objects; `to_dict()`
gives a read-only JSON view for inspecting the pipeline (no loader, no
version — a real wire form waits for a consumer).

Draw-derived artist keys (`_color`, hist `_bin_groups`) are stamped at
resolve time (`_build_panel_opts`), so the projection carries final
colors and a rendered `ResolvedIR` stays field-equal to a fresh one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..scales import _AxisDescriptor as IRScale


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# `IRScale` above is `scales._AxisDescriptor` — same fields, same
# semantics. Aliased so the resolved IR's surface reads as "IR types"
# while the definition stays with the scale classes it factories.


@dataclass(frozen=True)
class IRArtist:
    """One artist entry post-`_replay`.

    `_replay` has already split `color=<column>` into per-group entries
    with resolved hex colors and legend labels in `props["opts"]` — no
    palette lookup left. Consumers read colors off `props`.
    """
    kind: str
    props: dict


@dataclass(frozen=True)
class IRCoord:
    kind: str            # "cartesian" (default) or a registered coord name
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class IRPanel:
    """One leaf of the composition — a self-contained render plan for
    that panel. `leaf_kind`:
      * `"data"` — normal chart with axes + artists
      * `"legend"` — standalone legend leaf (`legend` carries its config)
      * `"diagram"` — pre-rendered SVG leaf (`diagram_inner`)

    Non-data leaves carry sizing plus their own config; `scales` /
    `artists` / `state` / `chrome` are empty for them.
    """
    pid: int             # stable panel id within this ResolvedIR
    coord: IRCoord
    scales: dict         # {"x": IRScale, "y": IRScale} for data leaves
    artists: tuple       # curated view of state["artists"]
    chrome: dict         # curated view of identity/spine state
    state: dict          # the FULL replayed state the emit pass draws from
                         # (minus "insets"/"coordinate", lifted to fields)
    attachments: dict    # {"left","right","top","bottom"} → tuple[IRPanel]
    insets: tuple        # ((rect, IRPanel), ...) — each fully resolved
    data_width: float
    data_height: float
    canvas_width: float
    canvas_height: float
    margin: dict         # effective margin (M_eff) from the pre-pass
    margin_floor: dict   # the user/spec floor margin
    hide: dict           # {"left","right","top","bottom"} → bool
    suppress: dict       # {"left","right","top","bottom"} → bool (labels)
    share: dict          # {"x": pid | None, "y": pid | None} anchor refs
    theme: str | None
    font: str | None
    attachment_gap: float | None
    leaf_kind: str
    legend: dict | None = None       # legend-leaf config (sources by pid)
    diagram_inner: str | None = None


@dataclass(frozen=True)
class IRLayout:
    kind: str            # "h" | "v" | "grid"
    children: tuple      # (IRPanel | IRLayout | None, ...)
    grid_rows: int | None = None
    grid_cols: int | None = None
    share_x: dict = field(default_factory=dict)  # {"mode","hide_labels"} or {}
    share_y: dict = field(default_factory=dict)
    gap: dict = field(default_factory=dict)      # {"gap","gap_x","gap_y"}
    coord: IRCoord | None = None
    title: str | None = None                     # figure-title band text
    # True when the recorded layout carried any ops. Load-bearing at
    # emit: `_effective_children` absorbs op-less same-kind child
    # layouts, and the gap walk stops at op-carrying ancestors — the
    # rehydrated tree must collapse exactly like the original.
    had_state: bool = False


@dataclass(frozen=True)
class ResolvedIR:
    """The resolved figure. `.root` is the complete render plan —
    `to_svg()` rehydrates a working tree from it and runs the emit
    pass, so the projection users inspect *is* what renders. This holds
    for container-coordinate figures too: ring states are projected
    from the coord's own resolution and the rehydrated layout carries a
    rebuilt overlay plan, so the coord's `render_layout` emits without
    re-resolving."""
    root: "IRLayout"

    def to_svg(self, *, clean: bool = False, outer: bool = True) -> str:
        from .._spec import _OUTER_MARGIN
        from ._layout_engine import _emit_plan, _render_coord_root
        from ._nodes import _strip_plotlet_attrs
        out = dict(_OUTER_MARGIN) if outer else None
        plan = _rehydrate(self.root)
        coord_obj = getattr(plan.root, "_coordinate", None)
        if coord_obj is not None and hasattr(coord_obj, "render_layout"):
            svg = _render_coord_root(plan.root, outer=out)
        else:
            svg = _emit_plan(plan, outer=out)
        return _strip_plotlet_attrs(svg) if clean else svg

    def to_dict(self) -> dict:
        """Read-only dict view of the projection, `json.dumps`-able
        as-is — for eyeballing what resolution produced (the middle of
        the journal → IR → resolved IR → SVG pipeline). Plain dicts and
        lists; non-JSON leaf values ride in the same `_json_layer`
        envelopes the journal uses (`$sectors`, …), coordinates as
        their `IRCoord` {kind, params} dump.

        One-way on purpose: there is no `from_dict`, no version tag,
        no validator — this is a debug view, not a wire format. To
        reconstruct a figure, go back to the journal / figure IR."""
        from .._json_layer import json_safe
        return json_safe(_to_plain(self))


def _to_plain(v):
    """Dataclass IR → plain dict/list for `to_dict()`. Recurses only
    through the IR containers; leaf values pass through untouched for
    `json_safe` to envelope."""
    if isinstance(v, (ResolvedIR, IRPanel, IRLayout, IRScale, IRCoord,
                      IRArtist)):
        return {k: _to_plain(getattr(v, k)) for k in v.__dataclass_fields__}
    if isinstance(v, dict):
        return {k: _to_plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_to_plain(x) for x in v]
    return v


# ---------------------------------------------------------------------------
# Builder — RenderPlan → projection
# ---------------------------------------------------------------------------


def resolve_ir(ir) -> ResolvedIR:
    """Lower a `FigureIR` to its resolved IR — the second stage of the
    render pipeline. (The public `plotlet.resolve_ir` wraps this with
    `to_ir` coercion, so users can hand it a `Chart` / `Layout` /
    journal directly — this render-side entry takes the IR only, like
    everything behind the seam.)

    `render.render_svg` is `resolve_ir(ir).to_svg()` — every rendered
    figure passes through the artifact returned here, and the emit pass
    runs from the projection alone (container-coord roots excepted).
    One-way; same journal → same resolved IR."""
    from ._layout_engine import _build_plan
    from ._nodes import hydrate

    root = hydrate(ir)
    plan = _build_plan(root)
    pids = _assign_pids(plan.root)
    projection = _node_to_ir(plan.root, plan.panel_opts, plan.states, pids)
    return ResolvedIR(root=projection)


def _walk_all_leaves(node, out):
    """Deterministic full walk: children (plus any nodes embedded in a
    layout coord's params, e.g. `CircularCoordinate.inner`), then
    attachments, then insets — the pid assignment order. Mirrors the
    projection recursion."""
    if node is None:
        return
    if getattr(node, "_is_parent", False):
        for c in node._children:
            _walk_all_leaves(c, out)
        coord = getattr(node, "_coordinate", None)
        if coord is not None and hasattr(coord, "_to_dict"):
            _walk_coord_params(coord._to_dict(), out)
        return
    out.append(node)
    for side_list in (node._attached_left, node._attached_right,
                      node._attached_above, node._attached_below):
        for a in side_list:
            _walk_all_leaves(a, out)
    for _rect, inset in node._insets:
        _walk_all_leaves(inset, out)


def _walk_coord_params(v, out):
    from ._nodes import RenderNode
    if isinstance(v, RenderNode):
        _walk_all_leaves(v, out)
    elif isinstance(v, dict):
        for x in v.values():
            _walk_coord_params(x, out)
    elif isinstance(v, (list, tuple)):
        for x in v:
            _walk_coord_params(x, out)


def _assign_pids(root) -> dict[int, int]:
    leaves: list = []
    _walk_all_leaves(root, leaves)
    return {id(l): i for i, l in enumerate(leaves)}


def _node_to_ir(node, panel_opts, states, pids):
    if node._is_parent:
        return _layout_to_ir(node, panel_opts, states, pids)
    return _chart_to_ir(node, panel_opts, states, pids)


def _layout_to_ir(layout, panel_opts, states, pids):
    # A container-coord layout resolved its own overlay plan — its ring
    # states (spliced band coords, forced W×H, zero margins) are what
    # actually renders. Project children from that truth, not from the
    # rect pre-pass probe.
    coord_plan = getattr(layout, "_coord_plan", None)
    if coord_plan is not None:
        states = {**states,
                  **{id(l): st for l, st, _po in coord_plan.rings}}
        panel_opts = {**panel_opts,
                      **{id(l): po for l, _st, po in coord_plan.rings}}
    share_x = _last_call(layout, "share_x")
    share_y = _last_call(layout, "share_y")
    gap = {"gap": layout._gap, "gap_x": layout._gap_x, "gap_y": layout._gap_y}
    coord = (_coord_to_ir(layout._coordinate, panel_opts, states, pids)
             if layout._coordinate else None)
    return IRLayout(
        kind=layout._layout_kind,
        children=tuple(
            _node_to_ir(c, panel_opts, states, pids) if c is not None else None
            for c in layout._children
        ),
        grid_rows=layout._grid_rows,
        grid_cols=layout._grid_cols,
        share_x=share_x,
        share_y=share_y,
        gap=gap,
        coord=coord,
        title=layout._title_text or None,
        had_state=layout._had_state,
    )


def _last_call(layout, op_name):
    """Return the resolved kwargs of the last `op_name` call on layout,
    or an empty dict if never called. Entries may be 3-tuples (user
    calls) or 4-tuples (frame-default flagged) — index, don't unpack."""
    for entry in reversed(layout._calls):
        if entry[0] == op_name:
            args, kw = entry[1], entry[2]
            out = {"mode": args[0] if args else None}
            out.update(kw)
            return out
    return {}


# State keys lifted out of the projected state dict: insets carry live
# node objects (projected recursively into `IRPanel.insets`) and the
# coordinate is a live instance (projected as `IRCoord`, reconstructed
# through the coord registry at rehydration).
_LIFTED_STATE_KEYS = ("insets", "coordinate")


def _chart_to_ir(chart, panel_opts, states, pids):
    if chart._leaf_kind != "data":
        return _nondata_leaf_to_ir(chart, pids)

    st = states.get(id(chart))
    if st is None:
        # Not resolved by the plan this projection was taken from (an
        # inset's own attachment, say) — resolve it in isolation, the
        # same resolution its render would run.
        from ._layout_engine import _build_plan
        sub = _build_plan(chart)
        return _chart_to_ir(chart, sub.panel_opts, sub.states, pids)

    po = panel_opts.get(id(chart))
    scales = {}
    if po and po.x_axis is not None:
        scales["x"] = po.x_axis
    if po and po.y_axis is not None:
        scales["y"] = po.y_axis

    coord_obj = st.get("coordinate")
    ir_coord = (_coord_to_ir(coord_obj, panel_opts, states, pids)
                if coord_obj else IRCoord(kind="cartesian"))

    artists = tuple(_artist_to_ir(a) for a in st.get("artists", ()))
    chrome = _extract_chrome(st)
    state = {k: v for k, v in st.items() if k not in _LIFTED_STATE_KEYS}

    attachments = {
        "left":   tuple(_chart_to_ir(a, panel_opts, states, pids)
                        for a in chart._attached_left),
        "right":  tuple(_chart_to_ir(a, panel_opts, states, pids)
                        for a in chart._attached_right),
        "top":    tuple(_chart_to_ir(a, panel_opts, states, pids)
                        for a in chart._attached_above),
        "bottom": tuple(_chart_to_ir(a, panel_opts, states, pids)
                        for a in chart._attached_below),
    }

    # Insets are not part of the owner's resolution — each gets its own
    # isolated plan, exactly the resolution its render runs. Resolution
    # is idempotent, so pre-running it here is observationally free.
    insets = tuple(
        (tuple(rect), _resolve_inset(inset_chart, pids))
        for rect, inset_chart in chart._insets
    )

    margin = dict(po.M_eff) if po and po.M_eff else dict(chart._margin)
    hide = {s: getattr(po, f"hide_{s}", False) if po else False
            for s in ("left", "right", "top", "bottom")}
    suppress = {s: getattr(po, f"suppress_{s}_labels", False) if po else False
                for s in ("left", "right", "top", "bottom")}
    share = {
        "x": pids.get(id(chart._share_x)) if chart._share_x is not None else None,
        "y": pids.get(id(chart._share_y)) if chart._share_y is not None else None,
    }

    return IRPanel(
        pid=pids[id(chart)],
        coord=ir_coord,
        scales=scales,
        artists=artists,
        chrome=chrome,
        state=state,
        attachments=attachments,
        insets=insets,
        data_width=chart._data_width,
        data_height=chart._data_height,
        canvas_width=chart._canvas_width,
        canvas_height=chart._canvas_height,
        margin=margin,
        margin_floor=dict(chart._margin),
        hide=hide,
        suppress=suppress,
        share=share,
        theme=chart._theme,
        font=chart._font,
        attachment_gap=getattr(chart, "_attachment_gap", None),
        leaf_kind=chart._leaf_kind,
    )


def _resolve_inset(inset_chart, pids):
    """Project one inset with its own isolated resolution — the same
    `_build_plan` its render runs. The inset node is mutated the way
    rendering would mutate it (canvas growth, `_last_M_eff`); a second
    resolution at emit recomputes identical values."""
    from ._layout_engine import _build_plan
    sub = _build_plan(inset_chart)
    return _chart_to_ir(inset_chart, sub.panel_opts, sub.states, pids)


def _nondata_leaf_to_ir(chart, pids):
    """Legend / diagram leaves: sizing plus their own config."""
    legend = None
    if chart._leaf_kind == "legend":
        legend = {
            "sources": tuple(pids[id(s)] for s in chart._legend_sources),
            "names": tuple((pids[id(n)], v)
                           for n, v in chart._legend_names.items()),
            "group_by_chart": chart._legend_group_by_chart,
            "valign": chart._legend_valign,
            "ncols": chart._legend_ncols,
            "reverse": chart._legend_reverse,
            "manual": tuple(chart._legend_manual),
            "user_width": chart._legend_user_width,
            "user_height": chart._legend_user_height,
            "gap": chart._legend_gap,
        }
    return IRPanel(
        pid=pids[id(chart)],
        coord=IRCoord(kind="cartesian"),
        scales={},
        artists=(),
        chrome={},
        state={},
        attachments={"left": (), "right": (), "top": (), "bottom": ()},
        insets=(),
        data_width=chart._data_width,
        data_height=chart._data_height,
        canvas_width=chart._canvas_width,
        canvas_height=chart._canvas_height,
        margin=dict(chart._margin),
        margin_floor=dict(chart._margin),
        hide={s: False for s in ("left", "right", "top", "bottom")},
        suppress={s: False for s in ("left", "right", "top", "bottom")},
        share={"x": None, "y": None},
        theme=chart._theme,
        font=chart._font,
        attachment_gap=getattr(chart, "_attachment_gap", None),
        leaf_kind=chart._leaf_kind,
        legend=legend,
        diagram_inner=chart._diagram_inner,
    )


def _coord_to_ir(coord, panel_opts=None, states=None, pids=None):
    """Resolved coord object → `IRCoord`. Uses the same registry the
    journal uses for round-tripping. Any Chart-typed params (e.g.
    `CircularCoordinate.inner`) recurse into `IRPanel` so the coord
    params stay IR-native — no dangling Chart references."""
    from .._coord_registry import _COORD_REGISTRY
    for name, cls in _COORD_REGISTRY.items():
        if isinstance(coord, cls):
            raw = coord._to_dict() if hasattr(coord, "_to_dict") else {}
            params = {k: _coerce_param(v, panel_opts, states, pids)
                      for k, v in raw.items()}
            return IRCoord(kind=name, params=params)
    return IRCoord(kind=type(coord).__name__)


def _coerce_param(v, panel_opts, states, pids):
    """Recursively wrap node-typed coord params (e.g.
    `CircularCoordinate.inner`) as IRPanel."""
    from ._nodes import RenderNode
    if isinstance(v, RenderNode):
        return _chart_to_ir(v, panel_opts or {}, states or {},
                            pids or _assign_pids(v))
    if isinstance(v, dict):
        return {k: _coerce_param(x, panel_opts, states, pids)
                for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return type(v)(_coerce_param(x, panel_opts, states, pids) for x in v)
    return v


def _extract_chrome(st):
    """Chrome-relevant state fields for a data leaf: the curated
    identity fields plus resolved spine state (visibility flags are
    always present; per-side style overrides only when set)."""
    keys = (
        "title", "xlabel", "ylabel",
        "xscale", "yscale",
        "x_ticks", "y_ticks", "x_labels", "y_labels",
        "x_reverse", "y_reverse",
        "xlim", "ylim",
        "grid", "facecolor",
        "legend",
    )
    chrome = {k: st[k] for k in keys if k in st and st[k] is not None}
    chrome.update({k: v for k, v in st.items()
                   if k.startswith("spine_") and v is not None})
    return chrome


def _artist_to_ir(artist):
    kind = artist.get("type", "unknown")
    props = {k: v for k, v in artist.items() if k != "type"}
    return IRArtist(kind=kind, props=props)


# ---------------------------------------------------------------------------
# Rehydrator — projection → RenderPlan. The inverse of the builder for
# everything the emit pass reads; `ResolvedIR.to_svg()` runs on its
# output. No `materialize`, no `_replay` — the projection already
# carries the resolution; this pass only rebuilds the working shapes.
# ---------------------------------------------------------------------------


def _rehydrate(root: "IRLayout | IRPanel"):
    """Build a `RenderPlan` (tree + states + panel_opts) from the
    projection alone. Journals stay empty — emit reads only explicit
    fields (`_theme` / `_font` / `_title_text` / `_had_state`), so the
    rehydrated tree carries no synthesized ops of any kind."""
    from ._layout_engine import RenderPlan

    ctx = _RehydrateCtx()
    tree = _rehydrate_node(root, ctx, parent=None)
    for panel, node in ctx.wire_share:
        node._share_x = ctx.by_pid.get(panel.share["x"])
        node._share_y = ctx.by_pid.get(panel.share["y"])
    for panel, node in ctx.wire_legend:
        cfg = panel.legend
        node._legend_sources = [ctx.by_pid[p] for p in cfg["sources"]]
        node._legend_names = {ctx.by_pid[p]: v for p, v in cfg["names"]}
    return RenderPlan(tree, ctx.panel_opts, ctx.states)


class _RehydrateCtx:
    def __init__(self):
        self.by_pid: dict[int, object] = {}
        self.panel_opts: dict[int, object] = {}
        self.states: dict[int, dict] = {}
        self.wire_share: list = []
        self.wire_legend: list = []


def _rehydrate_node(ir, ctx, *, parent):
    from ._nodes import RenderLayout
    if isinstance(ir, IRLayout):
        children = [
            _rehydrate_node(c, ctx, parent=None) if c is not None else None
            for c in ir.children
        ]
        node = RenderLayout(ir.kind, children)
        node._parent = parent
        node._grid_rows = ir.grid_rows
        node._grid_cols = ir.grid_cols
        node._gap = ir.gap.get("gap")
        node._gap_x = ir.gap.get("gap_x")
        node._gap_y = ir.gap.get("gap_y")
        if ir.coord is not None:
            node._coordinate = _rehydrate_coord(ir.coord, ctx)
        node._title_text = ir.title or ""
        node._had_state = ir.had_state
        if (node._coordinate is not None
                and hasattr(node._coordinate, "resolve_layout")):
            # Staged container coord — rebuild its overlay plan so
            # `render_layout` at emit consumes it instead of
            # re-resolving from the empty journals.
            _rebuild_coord_plan(node, ctx)
        return node
    return _rehydrate_panel(ir, ctx, parent=parent)


def _rehydrate_panel(panel: "IRPanel", ctx, *, parent):
    from ._layout_engine import RenderPlan
    from ._nodes import RenderNode
    from .core import _PanelOpts

    node = RenderNode()
    node._parent = parent
    node._leaf_kind = panel.leaf_kind
    node._data_width = panel.data_width
    node._data_height = panel.data_height
    node._orig_data_width = panel.data_width
    node._orig_data_height = panel.data_height
    node._canvas_width = panel.canvas_width
    node._canvas_height = panel.canvas_height
    node._margin = dict(panel.margin_floor)
    node._diagram_inner = panel.diagram_inner
    node._theme = panel.theme
    node._font = panel.font
    if panel.attachment_gap is not None:
        node._attachment_gap = panel.attachment_gap

    ctx.by_pid[panel.pid] = node
    ctx.wire_share.append((panel, node))
    if panel.legend is not None:
        node._legend_group_by_chart = panel.legend["group_by_chart"]
        node._legend_valign = panel.legend["valign"]
        node._legend_ncols = panel.legend["ncols"]
        node._legend_reverse = panel.legend["reverse"]
        node._legend_manual = list(panel.legend["manual"])
        node._legend_user_width = panel.legend["user_width"]
        node._legend_user_height = panel.legend["user_height"]
        node._legend_gap = panel.legend["gap"]
        ctx.wire_legend.append((panel, node))

    side_attr = {"left": "_attached_left", "right": "_attached_right",
                 "top": "_attached_above", "bottom": "_attached_below"}
    for side, attached in panel.attachments.items():
        lst = getattr(node, side_attr[side])
        for sub in attached:
            child = _rehydrate_panel(sub, ctx, parent=node)
            child._is_attached = True
            lst.append(child)

    if panel.leaf_kind != "data":
        return node

    # Data leaf: rebuild state + panel opts. State is shallow-copied so
    # the lifted keys can be reinstated without touching the projection.
    st = dict(panel.state)
    if panel.coord.kind != "cartesian":
        st["coordinate"] = _rehydrate_coord(panel.coord, ctx)
    node._last_M_eff = dict(panel.margin)

    insets = []
    for rect, sub in panel.insets:
        inode = _rehydrate_panel(sub, ctx, parent=None)
        inode._inset_owner = node
        # The inset renders through `_render_layout`, which uses this
        # cached plan instead of re-resolving (rehydrated journals are
        # empty — there'd be no artists to replay).
        inode._resolved_plan = RenderPlan(
            inode,
            {id(inode): ctx.panel_opts[id(inode)]},
            {id(inode): ctx.states[id(inode)]},
        )
        insets.append((tuple(rect), inode))
        node._insets.append((tuple(rect), inode))
    st["insets"] = insets

    po = _PanelOpts(
        x_axis=panel.scales.get("x"),
        y_axis=panel.scales.get("y"),
        hide_left=panel.hide["left"], hide_right=panel.hide["right"],
        hide_top=panel.hide["top"], hide_bottom=panel.hide["bottom"],
        suppress_left_labels=panel.suppress["left"],
        suppress_right_labels=panel.suppress["right"],
        suppress_top_labels=panel.suppress["top"],
        suppress_bottom_labels=panel.suppress["bottom"],
        M_eff=dict(panel.margin),
    )
    ctx.states[id(node)] = st
    ctx.panel_opts[id(node)] = po
    return node


def _rebuild_coord_plan(node, ctx) -> None:
    """Rebuild a container coord's overlay plan on a rehydrated layout —
    ring order matches `resolve_layout`: `_iter_leaves` (children,
    depth-first), then the coord's `inner` disc chart. States and panel
    opts come from the rehydration context (the projection carried the
    spliced ring truth), the overlay canvas is the rings' own W×H
    (every ring was forced to it at resolution), and the title band
    recomputes from `_title_text` — same call, same ambient spec as the
    original resolution. `render_layout` then emits without
    re-resolving."""
    from ._layout_engine import _title_band_h
    from .coordinates import _CircularPlan

    ring_leaves = list(node._iter_leaves())
    inner = getattr(node._coordinate, "inner", None)
    if inner is not None:
        ring_leaves.append(inner)
    if not ring_leaves:
        return
    rings = [(l, ctx.states[id(l)], ctx.panel_opts[id(l)])
             for l in ring_leaves]
    node._coord_plan = _CircularPlan(
        root=node, W=ring_leaves[0]._data_width,
        H=ring_leaves[0]._data_height, band=_title_band_h(node),
        rings=rings)


def _rehydrate_coord(ir_coord: "IRCoord", ctx):
    """`IRCoord` → live coordinate instance, through the same registry
    the journal's `$coord` envelopes decode against. Node-typed params
    (IRPanel) rehydrate first."""
    from .._coord_registry import _COORD_REGISTRY
    cls = _COORD_REGISTRY.get(ir_coord.kind)
    if cls is None:
        raise ValueError(
            f"rehydrate: coordinate {ir_coord.kind!r} is not in the coord "
            f"registry — register it (register_coord_codec) before rendering."
        )
    kwargs = {k: _rehydrate_param(v, ctx) for k, v in ir_coord.params.items()}
    return cls(**kwargs)


def _rehydrate_param(v, ctx):
    if isinstance(v, IRPanel):
        return _rehydrate_panel(v, ctx, parent=None)
    if isinstance(v, dict):
        return {k: _rehydrate_param(x, ctx) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return type(v)(_rehydrate_param(x, ctx) for x in v)
    return v
