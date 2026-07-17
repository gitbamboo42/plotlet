"""Render-side node tree — the renderer's private mirror of a figure.

`hydrate` builds this tree from a `FigureIR`; the layout engine walks
and mutates it freely (share scaling, measured margins, canvas growth)
without ever touching the user's `Chart` / `Layout` objects. Field
names deliberately mirror the recorder classes' — the engine is
duck-typed over them, so recorder trees and render trees stay drop-in
interchangeable for every walker (internal tests and tools poke engine
functions with recorder trees directly).

Hydration copies IR ops verbatim into `_calls` — no recorder re-entry.
Ops are already normalized: aes / data injection happened at record
time, and artist frame_defaults regenerate inside `_replay`.
`materialize` then derives the wired field state (share anchors,
attachment lists, layout gaps, coordinates, per-node style and layout
title) from those ops before the engine reads it — `_build_plan`
calls it at entry. Past materialize, the engine reads fields only;
journals are consumed once more at `_replay` and never at emit.
"""
from __future__ import annotations

import re

from .._spec import _MARGIN_FLOOR, _OUTER_MARGIN, _SIZESPEC, _LAYOUTSPEC
from .._tree import compute_share_classes, normalize_share_mode
from ..utils import _to_px


class RenderNode:
    """One leaf panel — data chart, legend, or diagram."""

    _is_parent: bool = False

    def __init__(self):
        self._calls: list[tuple[str, list, dict]] = []
        self._margin = dict(_MARGIN_FLOOR)
        self._data_width = 0
        self._data_height = 0
        self._orig_data_width = 0
        self._orig_data_height = 0
        self._canvas_width = 0
        self._canvas_height = 0
        self._parent = None
        self._share_x: "RenderNode | None" = None
        self._share_y: "RenderNode | None" = None
        self._share_hide_labels_x = True
        self._share_hide_labels_y = True
        self._leaf_kind = "data"
        self._legend_sources: list[RenderNode] = []
        self._legend_names: dict = {}
        self._legend_group_by_chart = True
        self._legend_valign = "middle"
        self._legend_ncols = 1
        self._legend_reverse = False
        self._legend_manual: list = []
        self._legend_user_width = None
        self._legend_user_height = None
        self._legend_gap = None
        self._diagram_inner = None
        self._insets: list[tuple[tuple, RenderNode]] = []
        self._inset_owner: "RenderNode | None" = None
        self._attached_left:  list[RenderNode] = []
        self._attached_right: list[RenderNode] = []
        self._attached_above: list[RenderNode] = []
        self._attached_below: list[RenderNode] = []
        self._is_attached = False
        self._last_M_eff: dict | None = None
        self._theme: str | None = None
        self._font: str | None = None


class RenderLayout:
    """A composition node — mirrors `Layout`'s engine-facing surface."""

    _is_parent: bool = True

    def __init__(self, layout_kind: str, children: list):
        self._layout_kind = layout_kind
        self._children = list(children)
        self._parent = None
        self._calls: list[tuple[str, list, dict]] = []
        self._gap = None
        self._gap_x = None
        self._gap_y = None
        self._grid_rows = None
        self._grid_cols = None
        self._virtual_grid_aligned = False
        self._coordinate = None
        self._had_state = False
        self._title_text = ""
        for child in self._children:
            if child is not None:
                child._parent = self

    def _effective_children(self) -> list:
        """The engine's view of this node's children — absorb same-kind
        child layouts with no recorded state so `(a|b) | c` reads as one
        flat 3-cell row. Mirrors `Layout._effective_children` (which
        checks `_calls` directly; here the journal fact is stamped onto
        `_had_state` by `materialize`)."""
        out: list = []
        for child in self._children:
            if (child is not None and child._is_parent
                    and child._layout_kind == self._layout_kind
                    and not child._had_state):
                out.extend(child._effective_children())
            else:
                out.append(child)
        return out

    def _iter_leaves(self):
        """Depth-first yield of every leaf under this layout (children
        only — attachments are reached via their hosts)."""
        for child in self._children:
            if child is None:
                continue
            if getattr(child, "_is_parent", False):
                yield from child._iter_leaves()
            else:
                yield child


# ---------------------------------------------------------------------------
# Hydration — FigureIR → render tree
# ---------------------------------------------------------------------------


def _chart_node(init: dict) -> RenderNode:
    """Data leaf from a `chart` node's init. Defaults mirror
    `Chart.__init__`: spec-floor margin, spec-default data dims,
    canvas = data + margin. `data` / aes keys in the init are recorder
    state already baked into the ops — the render tree never reads
    them."""
    node = RenderNode()
    dw = _to_px(init.get("data_width"))
    dh = _to_px(init.get("data_height"))
    margin = init.get("margin")
    node._margin = dict(margin) if margin is not None else dict(_MARGIN_FLOOR)
    node._data_width  = dw if dw is not None else _SIZESPEC["data_width"]
    node._data_height = dh if dh is not None else _SIZESPEC["data_height"]
    node._orig_data_width  = node._data_width
    node._orig_data_height = node._data_height
    node._canvas_width  = node._data_width  + node._margin["left"] + node._margin["right"]
    node._canvas_height = node._data_height + node._margin["top"]  + node._margin["bottom"]
    return node


def _leaf_node(kind: str, init: dict, nid_to_node: dict) -> RenderNode:
    """Legend / diagram leaf — the canvas is the dimensional primitive;
    data dims stay zero so accidental reads contribute nothing."""
    node = RenderNode()
    node._leaf_kind = kind
    node._canvas_width  = int(init["canvas_width"])
    node._canvas_height = int(init["canvas_height"])
    margin = init.get("margin")
    node._margin = dict(margin) if margin is not None else dict(_MARGIN_FLOOR)
    if kind == "legend":
        # `legend_sources` are raw nids (positional reference form);
        # `legend_names_pairs` keys arrive as already-decoded nodes via
        # the `$node` envelope.
        node._legend_sources = [nid_to_node[n]
                                for n in init.get("legend_sources", [])]
        node._legend_names = dict(init.get("legend_names_pairs", []))
        node._legend_group_by_chart = init.get("legend_group_by_chart", True)
        node._legend_valign = init.get("legend_valign")
        node._legend_ncols = init.get("legend_ncols", 1)
        node._legend_reverse = init.get("legend_reverse", False)
        node._legend_manual = list(init.get("legend_manual", []))
        node._legend_user_width = init.get("legend_user_width")
        node._legend_user_height = init.get("legend_user_height")
        node._legend_gap = init.get("legend_gap")
    if kind == "diagram":
        node._diagram_inner = init.get("diagram_inner")
    return node


def hydrate(ir):
    """Build the render tree from a `FigureIR` — a single forward pass
    over the dependency-ordered node table. Ops copy verbatim into
    `_calls` (values decoded back to live objects); insets bind
    directly. Derived field state is NOT wired here — `materialize`
    does that, and every engine entry point calls it first.

    Validates first: the IR may be hand-authored or JSON-loaded, so
    hydration can't assume the recorder's guarantees. Every render path
    enters through here, so validating here covers them all."""
    from .._json_layer import _decode
    from ._validate import validate

    validate(ir)
    nid_to_node: dict[int, object] = {}
    for n in ir.nodes:
        init = _decode(n.init, nid_to_node)
        if n.kind == "chart":
            node = _chart_node(init)
        elif n.kind in ("legend", "diagram"):
            node = _leaf_node(n.kind, init, nid_to_node)
        elif n.kind == "layout":
            node = RenderLayout(
                init["layout_kind"],
                [nid_to_node[c] if c is not None else None
                 for c in init["children"]],
            )
            if init.get("grid_rows") is not None:
                node._grid_rows = init["grid_rows"]
            if init.get("grid_cols") is not None:
                node._grid_cols = init["grid_cols"]
        else:
            raise ValueError(f"hydrate: unknown node kind {n.kind!r}")

        node._calls = [
            (op["op"],
             [_decode(a, nid_to_node) for a in op["args"]],
             {k: _decode(v, nid_to_node) for k, v in op["kwargs"].items()})
            for op in n.ops
        ]
        for ins in n.insets:
            inset = nid_to_node[ins["chart_nid"]]
            inset._inset_owner = node
            node._insets.append((tuple(ins["rect"]), inset))
        nid_to_node[n.nid] = node

    return nid_to_node[ir.root_nid]


# ---------------------------------------------------------------------------
# Derived state — re-derive wired fields from the recorded ops. The sole
# writer of `_share_*`, `_attached_*`, `_coordinate`, `_gap*`,
# `_virtual_grid_aligned`, `_had_state`, `_title_text`, `_theme`,
# `_font` on the tree it's given. (The rehydrator in `resolved_ir.py` sets
# the same fields directly from the projection — its trees never pass
# through here.)
# ---------------------------------------------------------------------------

# Names materialize knows how to dispatch on a layout journal entry. New
# Layout state methods must either be listed here (with a dispatch arm
# in the loop below) or in `_LAYOUT_PASSTHROUGH` (consumed elsewhere —
# `sectors` by the `_ancestor_calls` cascade at replay time, `title` by
# the `_title_text` stamp in the reset loop, `heights` by the container
# coord's `resolve_layout` band split).
_LAYOUT_MATERIALIZED = frozenset({
    "share_x", "share_y", "coordinate", "gap", "align_x", "align_y",
})
_LAYOUT_PASSTHROUGH = frozenset({"sectors", "title", "heights"})


def _last_title(calls) -> str:
    """Last-recorded layout `title` op ('' when untitled)."""
    text = ""
    for entry in calls:
        if entry[0] == "title":
            args = entry[1]
            text = args[0] if args and args[0] is not None else ""
    return text


def _stamp_style(leaf) -> None:
    """Derive the explicit `_theme` / `_font` fields from the leaf's
    journal, last call wins. `None` means never set — a passthrough for
    `active_theme` / `active_font`. Emit reads only the fields
    (`_node_style` in the layout engine), never the journal."""
    theme = None
    font = None
    for entry in leaf._calls:
        name, args, kw = entry[0], entry[1], entry[2]
        if name == "theme":
            theme = args[0] if args else None
        elif name == "font":
            font = args[0] if args else kw.get("family")
    leaf._theme = theme
    leaf._font = font


def _coord_param_nodes(v):
    """Leaf nodes riding inside a coordinate's params (e.g.
    `CircularCoordinate.inner`) — outside the child/attachment walk,
    but replayed and emitted like any ring leaf, so they need the same
    style stamp."""
    if hasattr(v, "_calls") and not getattr(v, "_is_parent", False):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _coord_param_nodes(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _coord_param_nodes(x)


def _walk_tree(root):
    """Yield every node reachable from `root` — layouts via `_children`,
    leaves via their `_attached_*` lists. Order: parent before children,
    so apply passes that depend on parent state run cleanly."""
    yield root
    if root._is_parent:
        for child in root._children:
            if child is not None:
                yield from _walk_tree(child)
    else:
        for atch in (*root._attached_left, *root._attached_right,
                     *root._attached_above, *root._attached_below):
            yield from _walk_tree(atch)


def _apply_attach(host, side: str, charts, *, hide_labels: bool,
                  gap) -> None:
    """Wire one recorded `attach_{side}` entry into field state. Also
    sets each attachment's `_parent` to the host — on a recorder tree
    that was already done at record time (idempotent overwrite); on a
    hydrated tree this is the only writer."""
    target_list = {
        "left":  host._attached_left,
        "right": host._attached_right,
        "above": host._attached_above,
        "below": host._attached_below,
    }[side]
    share_axis = "y" if side in ("left", "right") else "x"
    share_attr = "_share_x" if share_axis == "x" else "_share_y"
    for c in charts:
        c._parent = host
        setattr(c, share_attr, host)
        c._is_attached = True
        if not hide_labels:
            # Per-leaf flag read by the joined-pair walk; setting it on
            # the attachment alone is enough — `_mark_joined_pair`
            # skips the hide step if either side opts out.
            hide_flag = f"_share_hide_labels_{share_axis}"
            setattr(c, hide_flag, False)
        # Per-attachment gap to inward neighbor. None falls back to the
        # spec default at allocate time so a theme override flows in.
        c._attachment_gap = (float(gap) if gap is not None
                             else _LAYOUTSPEC["attach_gap"])
        target_list.append(c)


def _apply_share(layout, axis: str, mode, *, hide_labels: bool = True) -> None:
    """Wire one recorded `share_{x,y}` entry. Validation already fired
    at record time (`Layout._validate_share`), so the journal here is
    trusted."""
    norm = normalize_share_mode(axis, mode)
    if norm == "none":
        return
    if norm in ("col", "row") and layout._layout_kind != "grid":
        # Mark for `_coordinate_margins` to run the per-column /
        # per-row coordination — alignment is opt-in so the user
        # can't be surprised when sub-layout widths differ.
        layout._virtual_grid_aligned = True
    classes = compute_share_classes(layout, norm)
    attr = "_share_x" if axis == "x" else "_share_y"
    hide_attr = f"_share_hide_labels_{axis}"
    for cls in classes:
        if len(cls) < 2:
            continue
        anchor = cls[0]
        for leaf in cls[1:]:
            setattr(leaf, attr, anchor)
        if not hide_labels:
            # Flag every leaf in the class (anchor included) so the
            # joined-pair walk skips hide_* / suppress_*_labels on
            # both sides of every joint in this share class.
            for leaf in cls:
                setattr(leaf, hide_attr, False)


def materialize(root):
    """Re-derive wired field state from recorded journals.

    Resets the derived fields produced by `share_x/y`, `align_x/y`,
    `coordinate`, `gap`, and `attach_*` entries, then replays each
    node's `_calls` to rebuild them.

    `sectors` is journaled but not materialized here — it has no
    long-lived field; the cascade in `_ancestor_calls` reads it
    directly off the journal at replay time.

    Duck-typed: works on the hydrated render tree (the normal case —
    `_build_plan` calls this at entry) and equally on a recorder
    tree, for internal tests and tools that poke engine functions
    directly. Idempotent."""
    nodes = list(_walk_tree(root))
    layouts = [n for n in nodes if n._is_parent]
    charts  = [n for n in nodes if not n._is_parent]

    # Reset derived state. Tree structure (_children, _layout_kind,
    # _grid_rows/_cols) is not materialized — it's set at construction.
    # `_had_state` / `_title_text` stamp here rather than in the replay
    # loop below: `_apply_share` walks `_effective_children`, which
    # reads `_had_state`, so the stamp must land first.
    for la in layouts:
        la._coordinate = None
        la._gap = None
        la._gap_x = None
        la._gap_y = None
        la._virtual_grid_aligned = False
        la._had_state = bool(la._calls)
        la._title_text = _last_title(la._calls)
    for ch in charts:
        ch._attached_left  = []
        ch._attached_right = []
        ch._attached_above = []
        ch._attached_below = []
        ch._is_attached = False
        ch._share_x = None
        ch._share_y = None
        ch._share_hide_labels_x = True
        ch._share_hide_labels_y = True

    # Attach entries first — they set `_share_x/_share_y` on attached
    # charts (host as anchor). Layout share/align replays after and may
    # override, matching the user-build order (build attachments, then
    # compose into a layout, then share).
    for ch in charts:
        for entry in ch._calls:
            name = entry[0]
            if name.startswith("attach_"):
                side = name[len("attach_"):]
                _apply_attach(ch, side, entry[1],
                              hide_labels=entry[2].get("hide_labels", True),
                              gap=entry[2].get("gap"))

    for la in layouts:
        for entry in la._calls:
            name, args, kw = entry[0], entry[1], entry[2]
            # Closed-set guard. A new `Layout.foo()` that records `("foo",
            # …)` but has no dispatch arm below would silently no-op at
            # render — fail loudly here so the bug surfaces on the first
            # `to_svg()` instead of as a missing visual effect.
            if name in _LAYOUT_PASSTHROUGH:
                continue
            if name not in _LAYOUT_MATERIALIZED:
                raise AssertionError(
                    f"materialize: layout _calls entry {name!r} has no "
                    f"branch below and is not in _LAYOUT_PASSTHROUGH. "
                    f"Add a dispatch arm or list it as passthrough."
                )
            if name == "share_x":
                _apply_share(la, "x", args[0],
                             hide_labels=kw.get("hide_labels", True))
            elif name == "share_y":
                _apply_share(la, "y", args[0],
                             hide_labels=kw.get("hide_labels", True))
            elif name == "coordinate":
                la._coordinate = args[0]
            elif name == "gap":
                if args:
                    la._gap = float(args[0])
                    la._gap_x = None
                    la._gap_y = None
                if "x" in kw: la._gap_x = float(kw["x"])
                if "y" in kw: la._gap_y = float(kw["y"])
            elif name == "align_x":
                la._virtual_grid_aligned = True
            elif name == "align_y":
                la._virtual_grid_aligned = True

    # Style fields last, on a fresh walk: on a hydrated tree the attach
    # pass above is what makes attached charts reachable, and the
    # coordinate arm is what exposes coord-embedded nodes
    # (`CircularCoordinate.inner`) — the first walk missed both.
    for n in _walk_tree(root):
        if n._is_parent:
            coord = n._coordinate
            if coord is not None and hasattr(coord, "_to_dict"):
                for emb in _coord_param_nodes(coord._to_dict()):
                    _stamp_style(emb)
        else:
            _stamp_style(n)

    return root


# ---------------------------------------------------------------------------
# Render entry — the seam the front half calls, IR in, SVG out.
# ---------------------------------------------------------------------------

# Strip every `data-plotlet-*="..."` attribute. The leading space is part of
# the match so we don't leave a double space behind — every attr is emitted
# with a leading separator (see `_attrs_str` in emit.py and the inline
# `f'data-plotlet-...'` writes in `_layout_engine.py`, which sit after another
# attr or end up with their own trailing space).
_CLEAN_ATTR_RE = re.compile(r' data-plotlet-[\w-]+="[^"]*"')
# Strip `<metadata data-plotlet-payload="...">...</metadata>` blocks. CDATA
# content can include `<` `>` `&` and even a literal `</metadata>`, so the
# match anchors on `]]></metadata>` — `_category_metadata` in emit.py splits
# every content `]]>` across CDATA sections, so that terminator sequence
# appears exactly once per block.
_CLEAN_METADATA_RE = re.compile(
    r'<metadata data-plotlet-payload="[^"]*"><!\[CDATA\[.*?\]\]></metadata>',
    re.DOTALL,
)


def _strip_plotlet_attrs(svg: str) -> str:
    """Remove every `data-plotlet-*` attribute and `<metadata
    data-plotlet-payload=...>` block from a rendered SVG. Used by
    `to_svg(clean=True)` for users who want a plain SVG with no AI/schema
    metadata. Class names like `plotlet-artist` stay — they're structural,
    not metadata."""
    svg = _CLEAN_METADATA_RE.sub("", svg)
    svg = _CLEAN_ATTR_RE.sub("", svg)
    return svg


def render_svg(ir, *, clean: bool = False, outer: bool = True) -> str:
    """Render a `FigureIR` to the standalone SVG string — the staged
    pipeline: `resolve_ir(ir)` lowers to the resolved IR (hydrate,
    materialize, replay, train scales, coordinate margins), then
    `.to_svg()` emits from that artifact. Every rendered figure passes
    through the resolved stage — inspection (`pt.resolve_ir`) and
    rendering are two views of one resolution. `outer=False` drops the
    figure-level breathing-room margin — the inner render tools embed
    (`layout_diagram`) or measure against."""
    from .resolved_ir import resolve_ir
    return resolve_ir(ir).to_svg(clean=clean, outer=outer)
