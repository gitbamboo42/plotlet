"""Resolved IR — the pre-layout projection of a figure.

Second lowering stage of the pipeline. `_ir.py` compiles the journal
into the figure IR (`FigureIR`) — loss-free, round-trippable, still in
user terms (ops, data columns, palette names). `resolve_ir` lowers one
step further into a fully-resolved render plan:

  * axes are `IRScale` — an alias of `scales._AxisDescriptor`, the same
    pre-pixel type the layout engine builds and consumes, so the IR
    carries the descriptor directly (zero schema drift)
  * chrome (title / xlabel / ylabel / ...) is read straight off the
    replayed state dict
  * palettes are already baked into per-group artist entries by
    `_replay` — a `color=<column>` chart-aes fans out into one
    `IRArtist` per group with a resolved hex color, so the resolved IR
    inherits fully-resolved colors for free
  * per-leaf effective margins (`M_eff`) come from the layout engine's
    measurement pre-pass, not the user's floor

Geometry (rectangles) stays symbolic — that's the layout engine's job,
downstream of this projection. Hence "pre-layout".

Unlike the figure IR, the resolved IR is a *projection*, not a
round-trip peer: it answers "what does this figure resolve to" for
inspection, linting, and tooling, and deliberately drops the
information needed to rebuild the journal. Same journal → same
resolved IR.

Implementation reuses the figure IR's materializer, then the layout
engine's panel-opts pre-pass. The Chart/Layout tree is a private
staging area; the resolved IR is the artifact.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .scales import _AxisDescriptor as IRScale


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
    """One leaf of the composition. `leaf_kind`:
      * `"data"` — normal chart with axes + artists
      * `"legend"` — standalone legend leaf
      * `"diagram"` — pre-rendered SVG leaf (layout diagram)

    Non-data leaves carry only sizing; `scales` / `artists` / `chrome`
    are empty for them.
    """
    coord: IRCoord
    scales: dict         # {"x": IRScale, "y": IRScale} for data leaves
    artists: tuple
    chrome: dict
    attachments: dict    # {"left": tuple, "right": tuple, "top": tuple, "bottom": tuple}
    insets: tuple        # ((rect, IRPanel), ...)
    data_width: float
    data_height: float
    margin: dict         # effective margin from the layout pre-pass
    leaf_kind: str


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


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def resolve_ir(node):
    """Lower a plot to its resolved IR. Accepts anything `to_ir` does —
    a `Chart` / `Layout` / `FacetGrid`, a `Journal`, a `JournalNode`,
    or a `FigureIR`.

    The round-trip contract lives with the journal and the figure IR;
    the resolved IR sits below them and is a projection, not a
    round-trip peer. Same journal → same resolved IR."""
    from ._ir import to_ir, _materialize
    from ._layout_engine import _build_panel_opts
    from .chart import materialize

    ir = to_ir(node)
    root = _materialize(ir, ir.root_nid)
    materialize(root)
    panel_opts, states = _build_panel_opts(root)
    return _node_to_ir(root, panel_opts, states)


def _node_to_ir(node, panel_opts, states):
    if node._is_parent:
        return _layout_to_ir(node, panel_opts, states)
    return _chart_to_ir(node, panel_opts, states)


def _layout_to_ir(layout, panel_opts, states):
    share_x = _last_call(layout, "share_x")
    share_y = _last_call(layout, "share_y")
    gap = {"gap": layout._gap, "gap_x": layout._gap_x, "gap_y": layout._gap_y}
    coord = (_coord_to_ir(layout._coordinate, panel_opts, states)
             if layout._coordinate else None)
    return IRLayout(
        kind=layout._layout_kind,
        children=tuple(
            _node_to_ir(c, panel_opts, states) if c is not None else None
            for c in layout._children
        ),
        grid_rows=layout._grid_rows,
        grid_cols=layout._grid_cols,
        share_x=share_x,
        share_y=share_y,
        gap=gap,
        coord=coord,
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


def _chart_to_ir(chart, panel_opts, states):
    if chart._leaf_kind != "data":
        return _nondata_leaf_to_ir(chart)

    st = states.get(id(chart))
    if st is None:
        # Attachment leaves aren't in the main-tree traversal — replay manually.
        from ._layout_engine import _ancestor_calls
        from . import _attachments
        from .core import _replay
        effective = (_ancestor_calls(chart)
                     + _attachments.attachment_inherited_calls(chart)
                     + chart._calls)
        st = _replay(effective)

    po = panel_opts.get(id(chart))
    scales = {}
    if po and po.x_axis is not None:
        scales["x"] = po.x_axis
    if po and po.y_axis is not None:
        scales["y"] = po.y_axis

    coord_obj = st.get("coordinate")
    ir_coord = (_coord_to_ir(coord_obj, panel_opts, states)
                if coord_obj else IRCoord(kind="cartesian"))

    artists = tuple(_artist_to_ir(a) for a in st.get("artists", ()))
    chrome = _extract_chrome(st)

    attachments = {
        "left":   tuple(_chart_to_ir(a, panel_opts, states) for a in chart._attached_left),
        "right":  tuple(_chart_to_ir(a, panel_opts, states) for a in chart._attached_right),
        "top":    tuple(_chart_to_ir(a, panel_opts, states) for a in chart._attached_above),
        "bottom": tuple(_chart_to_ir(a, panel_opts, states) for a in chart._attached_below),
    }

    insets = tuple(
        (tuple(rect), _chart_to_ir(inset_chart, panel_opts, states))
        for rect, inset_chart in chart._insets
    )

    margin = dict(po.M_eff) if po and po.M_eff else dict(chart._margin)

    return IRPanel(
        coord=ir_coord,
        scales=scales,
        artists=artists,
        chrome=chrome,
        attachments=attachments,
        insets=insets,
        data_width=chart._data_width,
        data_height=chart._data_height,
        margin=margin,
        leaf_kind=chart._leaf_kind,
    )


def _nondata_leaf_to_ir(chart):
    """Legend / diagram leaves: minimal shell — sizing only, no axes."""
    return IRPanel(
        coord=IRCoord(kind="cartesian"),
        scales={},
        artists=(),
        chrome={},
        attachments={"left": (), "right": (), "top": (), "bottom": ()},
        insets=(),
        data_width=chart._data_width,
        data_height=chart._data_height,
        margin=dict(chart._margin),
        leaf_kind=chart._leaf_kind,
    )


def _coord_to_ir(coord, panel_opts=None, states=None):
    """Resolved coord object → `IRCoord`. Uses the same registry the
    journal uses for round-tripping. Any Chart-typed params (e.g.
    `CircularCoordinate.inner`) recurse into `IRPanel` so the coord
    params stay IR-native — no dangling Chart references."""
    from ._coord_registry import _COORD_REGISTRY
    for name, cls in _COORD_REGISTRY.items():
        if isinstance(coord, cls):
            raw = coord._to_dict() if hasattr(coord, "_to_dict") else {}
            params = {k: _coerce_param(v, panel_opts, states)
                      for k, v in raw.items()}
            return IRCoord(kind=name, params=params)
    return IRCoord(kind=type(coord).__name__)


def _coerce_param(v, panel_opts, states):
    """Recursively wrap Chart-typed coord params as IRPanel."""
    from .chart import Chart
    if isinstance(v, Chart):
        return _chart_to_ir(v, panel_opts or {}, states or {})
    if isinstance(v, dict):
        return {k: _coerce_param(x, panel_opts, states) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return type(v)(_coerce_param(x, panel_opts, states) for x in v)
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
