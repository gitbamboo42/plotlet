"""Private render engine — walks the render tree (`RenderNode` /
`RenderLayout`, hydrated from a `FigureIR`), coordinates margins,
allocates pixel rects, and emits the SVG. Duck-typed over the node
field protocol, so tests can poke engine functions with any tree that
mirrors those fields.

Used by both single-chart and multi-panel renders: a lone leaf is
treated as a degenerate single-cell tree by `_resolve_panels`, sharing
the same coordination pipeline that multi-panel layouts use. This is
what makes the outside-legend reservation and the per-leaf theme scoping
have one source of truth.

Pipeline (in order):

  * **Share pre-pass** — `_apply_share_scaling`, `_build_axis_descriptors`.
    Leaves connected by `share_x=` / `share_y=` get their data dims
    coordinated and share one axis descriptor per equivalence class.

  * **Joined-side annotation** — `_annotate_collapses`,
    `_propagate_grid_joins`. Mark `hide_*` / `suppress_*_labels` so
    inner-edge tick labels and axis labels drop where adjacent panels
    join, and the joined-side margin collapses to the floor.

  * **Measure-driven margin** — `_compute_measured_margins`,
    `_coordinate_margins`, `_pad_canvases`. Per-leaf preliminary margin,
    then per-column/row coordination so cells in the same column/row
    have aligned data regions. Each leaf's measurement runs under its
    own `active_theme` so spec values affecting margins (tick_length,
    font sizes) reflect that leaf's theme.

  * **Allocation** — `_measure`, `_natural_size`, `_allocate`. Sum-sizes
    composition derives the parent's total from its children plus gaps;
    `_allocate` walks the tree and assigns each leaf a pixel rect.

  * **Emit** — `_emit_plan` writes one outer `<svg>` with one
    `<g transform>` per leaf, calling `_render_inner` from `emit.py`.
    Every render reaches it through the resolved stage — the
    plan it consumes is always rehydrated from a `ResolvedIR`.

See `docs/SUBPLOTS.md` for the design rationale.
"""
from __future__ import annotations

import contextlib
import math

from graphlib import CycleError, TopologicalSorter
from itertools import count

from .._spec import (SPEC, _FIGSPEC, _LAYOUTSPEC, _FONTSPEC, _PADSPEC,
                     active_font, active_theme)
from ._resolution import (
    _replay, _enforce_floors, _required_margin,
    _axis_descriptor,
    _PanelOpts,
    _prebin_hist, _stamp_artist_colors,
)
from .emit import _figure_root_attrs, _panel_open, _render_inner
from ..scales import _AxisDescriptor
from .._tree import iter_leaves as _iter_leaves
from . import _attachments
from .. import _regions
from ..draw import coord, descender, svg_family, text_path, text_block_height


def _funnel_leaf(root):
    """The single leaf a root funnels to — the 1×1 wrapper
    `journal_to_ir` mints around a lone chart — or `None` for roots
    with sibling panels."""
    node = root
    while getattr(node, "_is_parent", False):
        children = [c for c in node._children if c is not None]
        if len(children) != 1:
            return None
        node = children[0]
    return node


@contextlib.contextmanager
def _node_style(node):
    """Theme + font scoping for one node's measurement/render. Every
    site that measures or emits text enters this ONE helper, so
    measurement can never disagree with render about the active face
    (which would corrupt margin math). Font nests inside theme so a
    `font` call overrides the theme's `font.family`. Reads the explicit
    `_theme` / `_font` fields (stamped by `materialize`, or set
    directly by the rehydrator) — never the journal; `None` is a
    passthrough for `active_theme` / `active_font`. A node missing the
    fields was never materialized — same caller contract as
    `_resolve_panels` / `_measure` / `_allocate`; fail with the
    contract spelled out, not an incidental AttributeError."""
    if not hasattr(node, "_theme") or not hasattr(node, "_font"):
        raise AssertionError(
            f"_node_style: {type(node).__name__} carries no _theme/_font "
            f"fields. Run materialize(root) over the tree before "
            f"measurement or emit.")
    with active_theme(node._theme):
        with active_font(node._font):
            yield


@contextlib.contextmanager
def _figure_style(root):
    """Theme + font scoping for the outer `<svg>` (figure background,
    root font-family attr). A root that funnels to a single leaf takes
    that leaf's style, so a lone dark chart gets a dark canvas; roots
    with sibling panels take none — themes and fonts are per-chart, and
    each leaf's own `_node_style` block scopes its chrome."""
    leaf = _funnel_leaf(root)
    if leaf is None:
        yield
        return
    with _node_style(leaf):
        yield


# ---------------------------------------------------------------------------
# Layout-level title — one centered band above a titled layout's rect,
# styled like a panel title. Rect layouts get it via `_measure` /
# `_allocate` / the placement emit below; coord-bearing layouts draw
# their own inside `coord.render_layout` (the band is part of the (W, H)
# they claim, kept in sync via `_atomic_size`).
# ---------------------------------------------------------------------------

def _layout_title(node) -> str:
    """A layout's figure-title text ('' when untitled or not a layout)
    — the explicit `_title_text` field stamped by `materialize` (or set
    directly by the rehydrator)."""
    if not getattr(node, "_is_parent", False):
        return ""
    return node._title_text


def _title_band_h(node) -> int:
    """Vertical pixels the title band adds above a titled layout's
    content — the panel-title block (`pad.title` gap + title glyph-block
    height, one line_height more per `\\n`), so composed and single-panel
    titles share one rhythm. Ceiled to an int: the band feeds the root
    canvas width/height, which stay integer px."""
    title = _layout_title(node)
    if not title:
        return 0
    return math.ceil(_PADSPEC["title"] + text_block_height(title, _FONTSPEC["title_size"]))


def _emit_layout_title(node, x: float, y: float, w: float) -> str:
    """The band's text fragment: centered over the layout's width, cap
    top at the band top, `pad.title` clear of the content below. Same
    text-as-paths emit as panel titles (`tag=` records the region)."""
    size = _FONTSPEC["title_size"]
    return text_path(_layout_title(node), x + w / 2,
                     y + size - descender(size), size,
                     anchor="middle", color=_FONTSPEC["color"],
                     tag="title")


# Layout gaps stay captured — they're parent-level positional, not
# per-leaf-themable. Font family and background read live from the spec
# so a leaf's `c.theme(...)` propagates to the surrounding canvas.
_GAP = _LAYOUTSPEC["gap"]
_LEGEND_GAP = _LAYOUTSPEC["legend_gap"]


# ---------------------------------------------------------------------------
# Gap rules — when adjacent leaves coordinate on the orthogonal axis,
# the gap between them collapses to 0.
# ---------------------------------------------------------------------------

def _share_root(leaf, axis: str):
    """Walk the share chain on `axis` ("x" or "y") to its root — the
    topmost leaf in the chain that shares with no one. Two leaves are in
    the same share-equivalence class on `axis` iff their roots are the
    same object. Cycle-safe (the validation pass already rejects cycles,
    but the `seen` guard makes this safe to call even before validation)."""
    attr = "_share_x" if axis == "x" else "_share_y"
    cur = leaf
    seen: set[int] = set()
    while True:
        nxt = getattr(cur, attr, None)
        if nxt is None or id(nxt) in seen:
            return cur
        seen.add(id(cur))
        cur = nxt


def _resolve_gap(a, b, *, axis: str) -> float:
    """Resolve the inter-panel gap for a boundary on `axis` ("h" between
    columns / "v" between rows). Falls back in this order, most-specific
    first:

      1. Per-axis parent override   (`._gap_x` / `._gap_y`)
      2. Unified parent override    (`._gap`, set via `.gap(value)`)
      3. Per-axis spec default      (`layout.gap_x` / `gap_y`)
      4. Unified spec default       (`layout.gap`)

    Walks up through "absorbed" ancestors — same-kind Layouts with no
    recorded state that `_effective_children()` flattens through.
    `(a|b) | c` records nested, so `a._parent` is the inner Layout; but
    the gap setting lives on whichever outer Layout actually scopes a,
    b, c as siblings. Stop the walk at the first ancestor that recorded
    its own state (`_had_state`) — its scope is real, not pass-through.

    Both-None happens when an entire grid boundary is empty cells; the
    spec default is the right answer there."""
    per_axis_attr = "_gap_x" if axis == "h" else "_gap_y"
    spec_per_axis = _LAYOUTSPEC.get("gap_x" if axis == "h" else "gap_y")
    parent = (a._parent if a is not None else None) \
          or (b._parent if b is not None else None)
    while parent is not None:
        per_axis = getattr(parent, per_axis_attr, None)
        if per_axis is not None:
            return per_axis
        if parent._gap is not None:
            return parent._gap
        if parent._had_state:
            break
        parent = parent._parent
    if spec_per_axis is not None:
        return spec_per_axis
    return _GAP


def _pair_gap(a, b, *, axis: str) -> float:
    """Gap between two adjacent cells.

    Two regimes:
      - Legend ↔ its source (or any data sibling, if the legend has no
        explicit source) → `legend_gap`, a small intentional separation
        that's not a share-pair joint and doesn't trigger spine/label
        suppression.
      - Anything else → the parent's gap (set via `.gap(N)` on any
        Layout — `|`-, `/`-, or `pt.grid`-built), or the spec default
        if unset. Joined
        share-pairs use this same gap too: their close-side breathing
        comes from the floor + content-aware `_required_margin` (joined
        sides have no tick labels / axis labels / title → just floor),
        so `gap` is genuinely extra inter-panel space layered on top.
    """
    default_gap = _resolve_gap(a, b, axis=axis)
    if a is None or b is None or a._is_parent or b._is_parent:
        return default_gap
    a_leg = a._leaf_kind == "legend"
    b_leg = b._leaf_kind == "legend"
    if a_leg ^ b_leg:
        leg   = a if a_leg else b
        other = b if a_leg else a
        if not leg._legend_sources or other in leg._legend_sources:
            return leg._legend_gap if leg._legend_gap is not None else _LEGEND_GAP
    return default_gap


def _gaps_h(children: list) -> list[float]:
    return [_pair_gap(children[i], children[i + 1], axis="h")
            for i in range(len(children) - 1)]


def _gaps_v(children: list) -> list[float]:
    return [_pair_gap(children[i], children[i + 1], axis="v")
            for i in range(len(children) - 1)]


def _grid_col_gap(children: list, rows: int, cols: int, c: int) -> float:
    """Gap between grid columns c and c+1: min over all rows. If any row
    has a joined pair across this column boundary, the whole boundary
    collapses — otherwise the default gap."""
    return min(
        _pair_gap(children[r * cols + c], children[r * cols + c + 1], axis="h")
        for r in range(rows)
    )


def _grid_row_gap(children: list, rows: int, cols: int, r: int) -> float:
    return min(
        _pair_gap(children[r * cols + c], children[(r + 1) * cols + c], axis="v")
        for c in range(cols)
    )


# ---------------------------------------------------------------------------
# Measurement — recursive (W, H) for a node, honoring leaf size hints.
# ---------------------------------------------------------------------------

def _leaf_rect_size(leaf) -> tuple[int, int]:
    """The leaf's intrinsic canvas size. For data leaves: data region
    + measure-driven margin (set by the layout pre-pass). For legend
    and diagram leaves: the explicit canvas dims set at construction.
    Doubles as the relative size hint when the parent allocates space."""
    return leaf._canvas_width, leaf._canvas_height


def _is_atomic(node) -> bool:
    """A node the placement system treats as a single opaque block.

    Leaves are atomic by definition. Coord-bearing Layouts are too —
    they own their own render strategy (e.g. `CircularCoordinate` overlays
    children on one ring canvas), and decomposing them into the parent
    rectangular grid would render their leaves in Cartesian. Letting
    `_measure` / `_allocate` stop at them keeps the rect path unaware of
    coord internals; the placement loop dispatches on the coord at emit
    time."""
    if not getattr(node, "_is_parent", False):
        return True
    coord = getattr(node, "_coordinate", None)
    return coord is not None and hasattr(coord, "render_layout")


def _atomic_size(node) -> tuple[int, int]:
    """Canvas size for an atomic node. Leaves use their declared
    `_canvas_*`; coord-bearing Layouts ask the coord (`layout_size`)
    for the (W, H) its `render_layout` will claim, so the parent packs
    the true footprint. Coords without the hook fall back to the
    max-of-leaf-dims formula."""
    if not node._is_parent:
        return _leaf_rect_size(node)
    coord = getattr(node, "_coordinate", None)
    if coord is not None and hasattr(coord, "layout_size"):
        return coord.layout_size(node)
    leaves = [l for l in node._iter_leaves() if l._leaf_kind == "data"]
    if not leaves:
        return 0, 0
    return (max(l._data_width  for l in leaves),
            max(l._data_height for l in leaves) + _title_band_h(node))


def _measure(node) -> tuple[int, int]:
    """The pixel (W, H) the node wants.

    Component-first: a leaf reports its declared size; a parent reports
    sum-of-children plus gaps in the layout direction, and max-of-children
    in the orthogonal direction. The figure size emerges from composition,
    so a 100-row heatmap stays 100 rows tall and an attached dendrogram
    sits next to it at its own natural width."""
    if _is_atomic(node):
        w, h = _atomic_size(node)
        if not node._is_parent and _attachments.has_attachments(node):
            l, r = _attachments.attached_size_h(node)
            a, b = _attachments.attached_size_v(node)
            w += l + r
            h += a + b
        return w, h
    band = _title_band_h(node)
    if node._layout_kind == "h":
        eff = node._effective_children()
        sizes = [_measure(c) for c in eff]
        gaps = _gaps_h(eff)
        W = sum(w for w, _ in sizes) + sum(gaps)
        H = max(h for _, h in sizes)
        return W, H + band
    if node._layout_kind == "v":
        eff = node._effective_children()
        sizes = [_measure(c) for c in eff]
        gaps = _gaps_v(eff)
        W = max(w for w, _ in sizes)
        H = sum(h for _, h in sizes) + sum(gaps)
        return W, H + band
    # grid — each column's width is the max natural canvas across cells
    # in that column; each row's height likewise.
    rows, cols = node._grid_rows, node._grid_cols
    children = node._children
    col_widths = [0.0] * cols
    row_heights = [0.0] * rows
    for r in range(rows):
        for c in range(cols):
            cell = children[r * cols + c]
            if cell is None:
                continue
            cw, ch = _measure(cell)
            if cw > col_widths[c]: col_widths[c] = cw
            if ch > row_heights[r]: row_heights[r] = ch
    h_gaps = [_grid_col_gap(children, rows, cols, c) for c in range(cols - 1)]
    v_gaps = [_grid_row_gap(children, rows, cols, r) for r in range(rows - 1)]
    W = int(round(sum(col_widths) + sum(h_gaps)))
    H = int(round(sum(row_heights) + sum(v_gaps)))
    return W, H + band


def _natural_size(root) -> tuple[int, int]:
    """The figure's natural (W, H), including measure-driven margin growth
    and any share-scaling coordination between leaves. Runs the pre-pass
    so every data leaf's `_canvas_*` reflects the final body+margin total,
    then sums those across the composition.

    Mutates `root` — pass a deep copy if you need a non-destructive
    measurement. Used by `Chart.fit()`."""
    _, states = _resolve_panels(root)
    # Legend leaves harvest their content size from sibling data leaves;
    # without this, layouts containing a layout-level legend would report
    # a stale 1×1 placeholder canvas.
    from ._legend import _size_legends
    _size_legends(root, states)
    return _measure(root)


def _data_total_size(node) -> tuple[float, float]:
    """Sum of `_data_width` / `_data_height` across all data leaves in
    the node's tree, combined the same way `_measure` combines canvases
    (sum along layout direction, max orthogonally). Non-data leaves
    contribute zero — their canvases live in the "overhead" budget that
    `Chart.fit()` subtracts when solving for the scale factor.

    Used so `fit()` can solve `target = s * data_total + overhead`
    directly in one pass instead of converging geometrically via
    `s = target / natural`."""
    if _is_atomic(node):
        # Leaves contribute their data dims (for data leaves) or 0
        # (for legend/diagram). Coord-bearing Layouts are opaque to the
        # rect parent and contribute 0 — their internal scale doesn't
        # participate in `fit()`'s data-area solve.
        if not node._is_parent and node._leaf_kind == "data":
            return float(node._data_width), float(node._data_height)
        return 0.0, 0.0
    if node._layout_kind == "h":
        sizes = [_data_total_size(c) for c in node._effective_children()]
        return sum(w for w, _ in sizes), max((h for _, h in sizes), default=0.0)
    if node._layout_kind == "v":
        sizes = [_data_total_size(c) for c in node._effective_children()]
        return max((w for w, _ in sizes), default=0.0), sum(h for _, h in sizes)
    # grid
    rows, cols = node._grid_rows, node._grid_cols
    children = node._children
    col_w = [0.0] * cols
    row_h = [0.0] * rows
    for r in range(rows):
        for c in range(cols):
            cell = children[r * cols + c]
            if cell is None:
                continue
            cw, ch = _data_total_size(cell)
            if cw > col_w[c]: col_w[c] = cw
            if ch > row_h[r]: row_h[r] = ch
    return sum(col_w), sum(row_h)


def _hint_ratios(sizes: list[float], n: int) -> list[float]:
    """Turn measured natural sizes into per-cell ratios. If everything is 0
    (e.g. an all-None grid column) fall back to equal share."""
    total = sum(sizes)
    if total <= 0:
        return [1.0 / n] * n
    return [s / total for s in sizes]


# ---------------------------------------------------------------------------
# Allocation — assigns a pixel rect to each leaf.
# ---------------------------------------------------------------------------

# `_iter_leaves` is `_tree.iter_leaves` (imported above) — the shared
# attachment-aware walk, also used by the share-class computation.


_CASCADING_NAMES = frozenset({"sectors"})


def _ancestor_calls(leaf) -> list[tuple]:
    """Collect cascadable `_calls` entries from `leaf`'s ancestors,
    yielded root-first. Used by `_resolve_panels` to prepend ancestor
    state declarations to the leaf's own `_calls` before `_replay`.
    Cascade replaces the old "Layout pushes into each leaf's _calls at
    index 0" propagation: Layout never mutates a leaf's journal;
    leaves read up the parent chain at render time.

    Filtered to `_CASCADING_NAMES` so we don't drag a parent's own
    artists/frame methods into a leaf's replay. Only entries that
    inherit *into* leaves cascade — today just `sectors`. Other
    journaled Layout state (`share_x/y`, `align_x/y`, `coordinate`,
    `gap`) is consumed at the Layout where it's declared by
    `materialize()`, not at the leaf. Attached charts have a leaf
    ancestor (the host) whose `_calls` contains artists — those must
    not bleed into the attachment's replay; the name filter is the
    guard.

    Entries returned in root-to-leaf order so they replay first;
    `_replay`'s sectors-to-front pass orders sectors among themselves
    by appearance, and a leaf's own sectors entry (later in the
    combined list) wins via last-write-wins on `state[\"{axis}_sectors\"]`.
    """
    # Walk only layout ancestors. An attached chart's `_parent` is its
    # host (a leaf), and an attached chart shares only one axis with
    # its host — sector cascade through the host would leak the host's
    # other-axis sectors. Attachment inheritance is handled separately
    # by `_attachments.attachment_inherited_calls` with axis filtering
    # and display damping (`divider=False`, `label=False`).
    chain = []
    p = getattr(leaf, "_parent", None)
    while p is not None and getattr(p, "_is_parent", False):
        chain.append(p)
        p = getattr(p, "_parent", None)
    chain.reverse()
    out: list[tuple] = []
    for node in chain:
        for c in getattr(node, "_calls", ()):
            if c[0] in _CASCADING_NAMES:
                out.append(c)
    return out


def _allocate(node, x: float, y: float, w: float, h: float, out: list):
    """Walk the tree, recording (leaf, rect) pairs into `out`. Leaf size hints
    (set via `pt.chart(data_width=, data_height=)` or the canvas_* form)
    act as relative ratios — so a narrow colorbar leaf in
    `hm | pt.colorbar(hm)` self-sizes without forcing the user to declare
    explicit widths.

    A titled rect layout additionally records itself with its band rect
    — the placement loop draws the band text there — and its children
    allocate below the band. Coord-bearing layouts are atomic here and
    band themselves inside `coord.render_layout`."""
    if _is_atomic(node):
        if not node._is_parent and _attachments.has_attachments(node):
            # Carve out the slot for the host itself, then place
            # attachments in the surrounding margin space.
            l, r = _attachments.attached_size_h(node)
            a, b = _attachments.attached_size_v(node)
            host_x = x + l
            host_y = y + a
            host_w = w - l - r
            host_h = h - a - b
            out.append((node, (host_x, host_y, host_w, host_h)))
            _attachments.allocate(node, host_x, host_y, host_w, host_h, out)
            return
        out.append((node, (x, y, w, h)))
        return
    band = _title_band_h(node)
    if band:
        out.append((node, (x, y, w, band)))
        y += band
        h -= band
    if node._layout_kind == "h":
        eff = node._effective_children()
        gaps = _gaps_h(eff)
        remaining = w - sum(gaps)
        sizes = [_measure(c)[0] for c in eff]
        ratios = _hint_ratios(sizes, len(eff))
        cx = x
        for i, c in enumerate(eff):
            per = remaining * ratios[i]
            _allocate(c, cx, y, per, h, out)
            cx += per
            if i < len(gaps):
                cx += gaps[i]
        return
    if node._layout_kind == "v":
        eff = node._effective_children()
        gaps = _gaps_v(eff)
        remaining = h - sum(gaps)
        sizes = [_measure(c)[1] for c in eff]
        ratios = _hint_ratios(sizes, len(eff))
        cy = y
        for i, c in enumerate(eff):
            per = remaining * ratios[i]
            _allocate(c, x, cy, w, per, out)
            cy += per
            if i < len(gaps):
                cy += gaps[i]
        return
    # grid
    rows, cols = node._grid_rows, node._grid_cols
    children = node._children
    h_gaps = [_grid_col_gap(children, rows, cols, c) for c in range(cols - 1)]
    v_gaps = [_grid_row_gap(children, rows, cols, r) for r in range(rows - 1)]
    rem_w = w - sum(h_gaps)
    rem_h = h - sum(v_gaps)
    col_meas = [0.0] * cols
    row_meas = [0.0] * rows
    for r in range(rows):
        for c in range(cols):
            cell = children[r * cols + c]
            if cell is None: continue
            cw, ch = _measure(cell)
            if cw > col_meas[c]: col_meas[c] = cw
            if ch > row_meas[r]: row_meas[r] = ch
    col_ws = [rem_w * r for r in _hint_ratios(col_meas, cols)]
    row_hs = [rem_h * r for r in _hint_ratios(row_meas, rows)]
    cy = y
    for r in range(rows):
        cx = x
        for c in range(cols):
            cell = children[r * cols + c]
            if cell is not None:
                _allocate(cell, cx, cy, col_ws[c], row_hs[r], out)
            cx += col_ws[c]
            if c < cols - 1: cx += h_gaps[c]
        cy += row_hs[r]
        if r < rows - 1: cy += v_gaps[r]


# ---------------------------------------------------------------------------
# Share-scaling pre-pass — coordinate sibling sizes via aspect-ratio
# scaling. The shared dimension is forced to the anchor's; the orthogonal
# dimension preserves the leaf's original aspect ratio (single-axis case)
# or is forced to the orthogonal anchor's (both-axes case).
# ---------------------------------------------------------------------------

def _aspect_span(desc, axis: str) -> float:
    """Domain span of one axis in the units `aspect=` locks — linear
    data units, or decades on a log scale."""
    if desc.kind == "linear":
        if desc.sector_lengths and desc.sector_gap_px:
            raise ValueError(
                "c.aspect(...) doesn't compose with sectored axes — the "
                "inter-sector gaps break the unit-to-pixel proportion."
            )
        return desc.hi - desc.lo
    if desc.kind == "log":
        return math.log10(desc.hi / desc.lo)
    raise ValueError(
        f"c.aspect(...) needs linear or log scales on both axes; the "
        f"{axis} axis resolved to {desc.kind!r}."
    )


def _aspect_dims(state, xd, yd, w: float, h: float, *,
                 w_locked: bool, h_locked: bool) -> tuple[float, float]:
    """Rederive one panel's data dims so `state["aspect"]` holds: one y data
    unit spans `aspect` × the pixels of one x data unit. The width is the
    free variable's anchor (body-first: `data_width` is what the user
    declared) unless a share class already locks the height."""
    r = state["aspect"]
    if state.get("coordinate") is not None:
        raise ValueError("c.aspect(...) applies to Cartesian panels only.")
    if xd.kind != yd.kind:
        raise ValueError(
            f"c.aspect(...) needs the same scale kind on both axes; got "
            f"x={xd.kind!r}, y={yd.kind!r}."
        )
    x_span = _aspect_span(xd, "x")
    y_span = _aspect_span(yd, "y")
    if x_span <= 0 or y_span <= 0:
        return w, h
    if w_locked and h_locked:
        # Both dims are forced by share anchors. When the forced dims
        # already satisfy the lock, accept them — the facet case: every
        # panel copies the anchor's dims and reads the same class-union
        # domains, so the anchor's own rederivation holds here too.
        if abs(h - r * w * y_span / x_span) <= 0.5:
            return w, h
        raise ValueError(
            "c.aspect(...) conflicts with sharing both axes — the share "
            "class fixes both panel dimensions, and they don't satisfy "
            "the requested ratio."
        )
    # The figure root rounds total W/H to integer px — round the derived
    # dim here so the lock degrades by at most half a pixel, instead of
    # the root rounding silently shaving the data region.
    if h_locked:
        return round(h * x_span / (r * y_span)), h
    return w, round(r * w * y_span / x_span)


def _apply_share_scaling(leaves: list, states: dict[int, dict],
                         x_desc: dict, y_desc: dict) -> None:
    """Mutate non-anchor leaves' `_data_width` / `_data_height` to
    coordinate with their share anchors, then rederive dims on leaves
    with a `c.aspect(...)` lock (the descriptors carry the resolved
    domains the lock needs). Reads from `_orig_data_*` each call so the
    operation is idempotent across re-renders."""
    # Reset to the user's original dims first so scaling is computed from a
    # clean baseline regardless of prior renders.
    for leaf in leaves:
        leaf._data_width  = leaf._orig_data_width
        leaf._data_height = leaf._orig_data_height

    # Apply scaling in topo order so anchors of chained share-classes
    # have settled before sharers depend on them — an aspect-locked
    # anchor's rederived height is what its sharers copy.
    for leaf in _topo_order(leaves):
        sx = leaf._share_x
        sy = leaf._share_y
        aspect = states[id(leaf)]["aspect"]
        if sx is None and sy is None and aspect is None:
            continue
        old_w = leaf._data_width
        old_h = leaf._data_height
        if sx is not None and sy is not None:
            # Both axes shared — force both, no aspect preservation
            new_w = sx._data_width
            new_h = sy._data_height
        elif sx is not None:
            # Width forced to anchor; height scales to preserve aspect —
            # except for attached charts, which keep the user's height as-is
            # (attachments lock only the shared dim; the other side is
            # user-controlled, matching axis-decoration semantics).
            new_w = sx._data_width
            if leaf._is_attached:
                new_h = old_h
            else:
                new_h = old_h * (new_w / old_w) if old_w > 0 else old_h
        elif sy is not None:
            new_h = sy._data_height
            if leaf._is_attached:
                new_w = old_w
            else:
                new_w = old_w * (new_h / old_h) if old_h > 0 else old_w
        else:
            new_w, new_h = old_w, old_h
        if aspect is not None:
            new_w, new_h = _aspect_dims(
                states[id(leaf)], x_desc[id(leaf)], y_desc[id(leaf)],
                new_w, new_h,
                w_locked=sx is not None, h_locked=sy is not None)
        leaf._data_width  = new_w
        leaf._data_height = new_h
        # Refresh derived canvas dims so downstream `_measure` sees them.
        leaf._canvas_width  = new_w + leaf._margin["left"]   + leaf._margin["right"]
        leaf._canvas_height = new_h + leaf._margin["top"]    + leaf._margin["bottom"]


# ---------------------------------------------------------------------------
# Scale-share pre-pass — topo-sort leaves by share_x / share_y, then build
# one axis descriptor per share-equivalence class.
# ---------------------------------------------------------------------------

def _validate_share_targets(leaves: list) -> None:
    """Every share target must itself be a leaf in the same composition."""
    leaf_ids = {id(l) for l in leaves}
    for leaf in leaves:
        for attr, axis in (("_share_x", "x"), ("_share_y", "y")):
            src = getattr(leaf, attr)
            if src is None:
                continue
            if getattr(src, "_is_parent", True):
                # Also catches non-node garbage: anything without the
                # node protocol can't be a share target.
                raise ValueError(
                    f"share_{axis}= target must be a leaf chart, not a composed parent."
                )
            if id(src) not in leaf_ids:
                raise ValueError(
                    f"share_{axis}= target is not part of this composition. "
                    f"Both charts must be composed into the same parent."
                )


def _topo_order(leaves: list) -> list:
    """Topo-sort leaves so each one's share source is visited first. Cycles
    raise with a friendly message."""
    ts = TopologicalSorter()
    for leaf in leaves:
        srcs = [s for s in (leaf._share_x, leaf._share_y) if s is not None]
        ts.add(leaf, *srcs)
    try:
        return list(ts.static_order())
    except CycleError as exc:
        raise ValueError(
            "share_x= / share_y= forms a cycle; charts cannot share scales "
            "with each other circularly."
        ) from exc


def _build_axis_descriptors(leaves: list,
                            states: dict[int, dict]
                            ) -> tuple[dict[int, _AxisDescriptor],
                                       dict[int, _AxisDescriptor]]:
    """Compute per-leaf x/y axis descriptors. Members of a share class get
    a single descriptor built from the union of their data; the anchor's
    scale, xlim/ylim, category order, etc. win for policy."""
    _validate_share_targets(leaves)
    x_desc: dict[int, _AxisDescriptor] = {}
    y_desc: dict[int, _AxisDescriptor] = {}
    # Group by share-root for each axis; each group gets one descriptor
    # built from the union of all member states.
    for axis, attr, out in (
        ("x", "_share_x", x_desc),
        ("y", "_share_y", y_desc),
    ):
        classes: dict[int, list] = {}
        for leaf in leaves:
            root = _share_root(leaf, axis)
            classes.setdefault(id(root), []).append(leaf)
        for class_leaves in classes.values():
            anchor = next((l for l in class_leaves if getattr(l, attr) is None),
                          class_leaves[0])
            ordered = [anchor] + [l for l in class_leaves if l is not anchor]
            desc = _axis_descriptor([states[id(l)] for l in ordered], axis)
            for l in class_leaves:
                out[id(l)] = desc
    return x_desc, y_desc


# ---------------------------------------------------------------------------
# Per-leaf hide flags — wherever a joined share-pair fires (two adjacent
# leaves on the same share-equivalence class on the orthogonal axis),
# the inner side of each panel drops its tick labels / axis label / title.
# The matching margin naturally shrinks to the floor (`_required_margin`
# reads these flags via `panel_opts` so it doesn't reserve space for
# content the renderer will skip).
# ---------------------------------------------------------------------------

def _mark_joined_pair(a, b, *, axis: str,
                      states: dict[int, dict],
                      out: dict[int, _PanelOpts]) -> None:
    """If `a` and `b` are joined along `axis` (i.e., share-equivalent on the
    orthogonal axis), set `hide_*` on both sides of the joint and
    `suppress_*_labels` on the side whose tick labels would duplicate the
    neighbor's — or render unanchored over the joint when that panel's
    axis sits ON the joint edge. The suppression target follows each
    panel's ``x_side`` / ``y_side``, so an `xticks(side="top")` panel in
    a v-stack drops its top-edge labels at the joint rather than the
    bottom-edge ones (which wouldn't render anyway).

    Recurses on parent-vs-parent pairs of the orthogonal direction with
    equal cell counts (e.g., two h-rows in a v-stack pair column-by-column),
    so a composed "v-of-h" with cross-row x-sharing collapses spines
    between vertically-adjacent panels at matching positions."""
    if a is None or b is None:
        return
    if a._is_parent and b._is_parent:
        inner = "h" if axis == "v" else "v"
        if a._layout_kind == inner and b._layout_kind == inner:
            a_eff = a._effective_children()
            b_eff = b._effective_children()
            if len(a_eff) == len(b_eff):
                for ac, bc in zip(a_eff, b_eff):
                    _mark_joined_pair(ac, bc, axis=axis,
                                      states=states, out=out)
        return
    if a._is_parent or b._is_parent:
        return
    if a._leaf_kind != "data" or b._leaf_kind != "data":
        return
    share_axis = "y" if axis == "h" else "x"
    if _share_root(a, share_axis) is not _share_root(b, share_axis):
        return
    # Per-leaf opt-out (set by `share_x(..., hide_labels=False)`). If either
    # cell in the pair has it off, skip the hide/suppress on this joint so
    # both panels render their own labels at the shared boundary.
    hide_attr = f"_share_hide_labels_{share_axis}"
    if not (getattr(a, hide_attr, True) and getattr(b, hide_attr, True)):
        return
    if axis == "h":
        # h-stack: a (left) joins b (right) along their shared y-axis.
        # The panel whose y-axis sits AT the joined edge gets its tick
        # labels suppressed — the spine is already gone via hide_*.
        out[id(a)].hide_right = True
        out[id(b)].hide_left = True
        if states[id(a)]["y_side"] == "right":
            out[id(a)].suppress_right_labels = True
        if states[id(b)]["y_side"] == "left":
            out[id(b)].suppress_left_labels = True
    else:
        # v-stack: a (top) joins b (bottom) along their shared x-axis.
        out[id(a)].hide_bottom = True
        out[id(b)].hide_top = True
        if states[id(a)]["x_side"] == "bottom":
            out[id(a)].suppress_bottom_labels = True
        if states[id(b)]["x_side"] == "top":
            out[id(b)].suppress_top_labels = True


def _annotate_collapses(node, states: dict[int, dict],
                         out: dict[int, _PanelOpts]) -> None:
    """Walk the tree, marking joined-pair flags on every adjacent pair of
    leaves that share an axis (orthogonal to the layout direction)."""
    if not node._is_parent:
        return
    if node._layout_kind in ("h", "v"):
        axis = node._layout_kind
        eff = node._effective_children()
        for a, b in zip(eff, eff[1:]):
            _mark_joined_pair(a, b, axis=axis, states=states, out=out)
        for c in eff:
            _annotate_collapses(c, states, out)
        return
    rows, cols = node._grid_rows, node._grid_cols
    children = node._children
    for r in range(rows):
        for c in range(cols - 1):
            _mark_joined_pair(children[r * cols + c],
                              children[r * cols + c + 1], axis="h",
                              states=states, out=out)
    for c in range(cols):
        for r in range(rows - 1):
            _mark_joined_pair(children[r * cols + c],
                              children[(r + 1) * cols + c], axis="v",
                              states=states, out=out)
    for cell in children:
        if cell is not None:
            _annotate_collapses(cell, states, out)


def _propagate_grid_joins(node, out: dict[int, _PanelOpts]) -> None:
    """Within a grid, propagate `hide_*` (margin) flags column-wise and
    row-wise so panels in the same column/row share effective margins and
    their data areas stay aligned. `suppress_*_labels` does NOT propagate
    so a column-aligned track that doesn't actually share an axis still
    renders its own tick labels."""
    if not node._is_parent:
        return
    if node._layout_kind == "grid":
        rows, cols = node._grid_rows, node._grid_cols
        children = node._children
        # Legend leaves are excluded from margin propagation — they have
        # their own internal margin model and aren't in `out` at all.
        def _data_cells(idxs):
            return [children[i] for i in idxs
                    if children[i] is not None
                    and children[i]._leaf_kind == "data"]
        for c in range(cols):
            cells = _data_cells([r * cols + c for r in range(rows)])
            if not cells: continue
            any_l = any(out[id(cell)].hide_left  for cell in cells)
            any_r = any(out[id(cell)].hide_right for cell in cells)
            for cell in cells:
                if any_l: out[id(cell)].hide_left  = True
                if any_r: out[id(cell)].hide_right = True
        for r in range(rows):
            cells = _data_cells([r * cols + c for c in range(cols)])
            if not cells: continue
            any_t = any(out[id(cell)].hide_top    for cell in cells)
            any_b = any(out[id(cell)].hide_bottom for cell in cells)
            for cell in cells:
                if any_t: out[id(cell)].hide_top    = True
                if any_b: out[id(cell)].hide_bottom = True
    for cell in node._children:
        if cell is not None:
            _propagate_grid_joins(cell, out)


def _replay_leaves(leaves) -> dict[int, dict]:
    """Replay every data leaf's effective call list into its state dict.

    Each leaf replays under its own theme so state defaults (spine
    visibility, tick direction) and any measurement reads pick up the
    theme's values. Multi-panel layouts may mix themes; each leaf
    carries its own context.

    Effective replay input per leaf: ancestor Layout cascade, then
    attachment inheritance from the host (dampened sectors), then the
    leaf's own `_calls`. Three sources, concatenated in priority
    order — `_replay`'s sectors-to-front pass orders sectors among
    themselves by appearance, and the leaf's own entry (last) wins
    via last-write on `state["{axis}_sectors"]`. No node ever mutates
    another node's journal."""
    states = {}
    for l in leaves:
        with _node_style(l):
            effective = (_ancestor_calls(l)
                         + _attachments.attachment_inherited_calls(l)
                         + l._calls)
            state = _replay(effective)
            state["insets"] = getattr(l, "_insets", [])
            # Stamp draw-derived artist keys at resolve time — the
            # resolved IR carries final colors and hist bins, and a
            # rendered ResolvedIR stays field-equal to a fresh one
            # (the draw-side recomputation is idempotent).
            _prebin_hist(state)
            _stamp_artist_colors(state)
            states[id(l)] = state
    return states


def _resolve_panels(root, *, measure_margins=True
                    ) -> tuple[dict[int, _PanelOpts], dict[int, dict]]:
    """One pass over the tree that produces (panel_opts, replayed states).

    For body-first leaves, also computes a measure-driven effective
    margin (per-leaf measurement, then per-column/row coordination so
    cells in the same grid column/row align), and mutates each leaf's
    `_canvas_width`/`_canvas_height` to match — `_measure` reads those
    when summing the parent's natural canvas, so layout sees the final
    grown-to-fit dimensions on the first walk.

    ``measure_margins=False`` stops after states, descriptors, and the
    join/collapse annotations: no margin measurement, no canvas
    mutation, every `M_eff` left `None` for the caller to assign. For
    callers that dictate panel geometry themselves — the circular
    resolve forces each ring onto the shared overlay canvas with zero
    margin, so a measured Cartesian margin would be wrong work thrown
    away.

    Legend leaves are skipped — they have no x/y axes, no artists, and
    render through their own pipeline (see `render/_legend.py`).

    Assumes `materialize(root)` has already run (`_build_plan` does it
    at entry). Internal callers (tests, debugging) that bypass
    `_build_plan` must materialize themselves first — same contract as
    `_measure`, `_allocate`, `_natural_size`."""
    # Collect data leaves.
    leaves = [l for l in _iter_leaves(root) if l._leaf_kind == "data"]
    # Replay every leaf into its settled state dict.
    states = _replay_leaves(leaves)
    # Axis descriptors before share scaling: both are pure data-space
    # (no pixel dims involved), and the scaling pass needs the resolved
    # domains to honor `c.aspect(...)` locks.
    x_desc, y_desc = _build_axis_descriptors(leaves, states)
    _apply_share_scaling(leaves, states, x_desc, y_desc)
    # Blank per-leaf opts; the annotation passes below fill them in.
    panel_opts = {
        id(l): _PanelOpts(x_axis=x_desc[id(l)], y_axis=y_desc[id(l)])
        for l in leaves
    }
    # Joined-edge annotation: siblings, attachments, then grid rows/cols.
    _annotate_collapses(root, states, panel_opts)
    _attachments.annotate_joined_pairs(leaves, states, panel_opts)
    _propagate_grid_joins(root, panel_opts)
    # Move a host's title/subtitle to its outermost top attachment.
    _attachments.promote_titles(leaves, states)
    # Margins: measure per leaf, align per row/column, grow canvases.
    if measure_margins:
        _compute_measured_margins(leaves, states, panel_opts)
        _coordinate_margins(root, panel_opts)
        _update_canvases_for_margins(leaves, panel_opts)
    return panel_opts, states


def _compute_measured_margins(leaves: list,
                              states: dict[int, dict],
                              panel_opts: dict[int, _PanelOpts]) -> None:
    """Per-leaf preliminary effective margin = floor + content-required.

    `_required_margin` reads the leaf's `panel_opts` so joined share-pair
    sides naturally drop their tick-label / xlabel / ylabel / title
    reservations (the renderer suppresses these via `hide_*` /
    `suppress_*_labels`). No separate joined-side override needed — the
    floor is what's left, just like any other empty side.

    Each leaf's measurement runs under its own `active_theme` so spec
    values that affect margins (tick_length, font sizes, pad spec)
    reflect the leaf's theme overrides, not the ambient theme."""
    for leaf in leaves:
        layout_opts = panel_opts[id(leaf)]
        with _node_style(leaf):
            M_floor = _enforce_floors(leaf._margin)
            M_req = _required_margin(states[id(leaf)],
                                     leaf._data_width,
                                     leaf._data_height,
                                     layout_opts=layout_opts)
        layout_opts.M_eff = {side: M_floor[side] + M_req[side] for side in M_floor}


def _body_cell(cell, panel_opts: dict[int, _PanelOpts]) -> bool:
    """Cells eligible for per-column/row margin coordination — data
    leaves whose preliminary margin has been computed."""
    return (cell is not None
            and not cell._is_parent
            and cell._leaf_kind == "data"
            and panel_opts.get(id(cell)) is not None
            and panel_opts[id(cell)].M_eff is not None)


def _coordinate_pair(cells: list, panel_opts: dict[int, _PanelOpts],
                     sides: tuple[str, str]) -> None:
    """Take max per side across `cells`, write back to each cell's M_eff.
    `sides` is e.g. ("left", "right") for column-coordination or
    ("top", "bottom") for row-coordination."""
    if not cells:
        return
    s1, s2 = sides
    m1 = max(panel_opts[id(c)].M_eff[s1] for c in cells)
    m2 = max(panel_opts[id(c)].M_eff[s2] for c in cells)
    for c in cells:
        layout_opts = panel_opts[id(c)]
        layout_opts.M_eff = {**layout_opts.M_eff, s1: m1, s2: m2}


def _virtual_grid_children(node, inner_kind: str) -> list | None:
    """If `node` has been marked as a virtual grid (via `share_x("col")`
    or `share_y("row")`) and every child is a same-kind parent with
    equal cell count, return the children. Otherwise None — composition
    keeps its "two independent rows" semantics by default; alignment is
    opt-in via share so the user can't be surprised by phantom padding
    when their per-cell widths happen not to match across rows."""
    if not getattr(node, "_virtual_grid_aligned", False):
        return None
    kids = node._effective_children()
    if not kids:
        return None
    if not all(c is not None and c._is_parent and c._layout_kind == inner_kind
               for c in kids):
        return None
    if len(set(len(c._effective_children()) for c in kids)) != 1:
        return None
    return kids


def _coordinate_margins(node, panel_opts: dict[int, _PanelOpts]) -> None:
    """Walk the tree; at each parent, push body-first cells in the same
    column/row to share the wider margin so their data regions align.

    Horizontal parents share top/bottom across all children (one row).
    Vertical parents share left/right (one column). Grids share
    left/right per column and top/bottom per row.

    v-of-h and h-of-v compositions that have been marked
    `_virtual_grid_aligned` (by `share_x("col")` / `share_y("row")`)
    get an extra column-/row-wise pass so leaves at matching positions
    across sub-layouts coordinate margins and canvas widths — making
    the same column line up across rows.

    Canvas-first cells, parents, and legend leaves are excluded — they
    have their own margin policy and shouldn't pull body-first siblings
    around. Joined share-pair sides already collapsed naturally during
    `_compute_measured_margins` (hide-aware `_required_margin`), so a max
    here just picks up the smaller-margin side as expected."""
    if not node._is_parent:
        return
    if node._layout_kind == "h":
        eff = node._effective_children()
        cells = [c for c in eff if _body_cell(c, panel_opts)]
        _coordinate_pair(cells, panel_opts, ("top", "bottom"))
        _pad_canvases(cells, panel_opts, axis="h")
        v_kids = _virtual_grid_children(node, "v")
        if v_kids is not None:
            v_kid_cells = [col._effective_children() for col in v_kids]
            n_rows = len(v_kid_cells[0])
            for r in range(n_rows):
                row_cells = [col[r] for col in v_kid_cells]
                body = [cell for cell in row_cells if _body_cell(cell, panel_opts)]
                _coordinate_pair(body, panel_opts, ("top", "bottom"))
                _pad_canvases(body, panel_opts, axis="h")
        for c in eff:
            if c is not None:
                _coordinate_margins(c, panel_opts)
        return
    if node._layout_kind == "v":
        eff = node._effective_children()
        cells = [c for c in eff if _body_cell(c, panel_opts)]
        _coordinate_pair(cells, panel_opts, ("left", "right"))
        _pad_canvases(cells, panel_opts, axis="v")
        h_kids = _virtual_grid_children(node, "h")
        if h_kids is not None:
            h_kid_cells = [row._effective_children() for row in h_kids]
            n_cols = len(h_kid_cells[0])
            for c in range(n_cols):
                col_cells = [row[c] for row in h_kid_cells]
                body = [cell for cell in col_cells if _body_cell(cell, panel_opts)]
                _coordinate_pair(body, panel_opts, ("left", "right"))
                _pad_canvases(body, panel_opts, axis="v")
        for c in eff:
            if c is not None:
                _coordinate_margins(c, panel_opts)
        return
    # grid
    rows, cols = node._grid_rows, node._grid_cols
    children = node._children
    for c in range(cols):
        col_cells = [children[r * cols + c] for r in range(rows)]
        body = [cell for cell in col_cells if _body_cell(cell, panel_opts)]
        _coordinate_pair(body, panel_opts, ("left", "right"))
        _pad_canvases(body, panel_opts, axis="v")
    for r in range(rows):
        row_cells = [children[r * cols + c] for c in range(cols)]
        body = [cell for cell in row_cells if _body_cell(cell, panel_opts)]
        _coordinate_pair(body, panel_opts, ("top", "bottom"))
        _pad_canvases(body, panel_opts, axis="h")
    for cell in children:
        if cell is not None:
            _coordinate_margins(cell, panel_opts)


def _pad_canvases(cells: list, panel_opts: dict[int, _PanelOpts],
                  *, axis: str) -> None:
    """Equalize canvases across `cells` by padding the slack onto one
    margin side, so every cell ends up with the same canvas dimension
    along `axis` ('h' = canvas_h via bottom-margin pad; 'v' = canvas_w
    via right-margin pad). Honors data dimensions per leaf — the user's
    `data_width=` / `data_height=` is never altered, only the margin
    that fills the row/column slack."""
    if not cells:
        return
    if axis == "h":
        side, dim_attr, sides = "bottom", "_data_height", ("top", "bottom")
    else:
        side, dim_attr, sides = "right", "_data_width", ("left", "right")

    def canvas_dim(cell):
        m = panel_opts[id(cell)].M_eff
        return getattr(cell, dim_attr) + m[sides[0]] + m[sides[1]]

    target = max(canvas_dim(c) for c in cells)
    for c in cells:
        m = panel_opts[id(c)].M_eff
        slack = target - canvas_dim(c)
        if slack > 0:
            panel_opts[id(c)].M_eff = {**m, side: m[side] + slack}


def _update_canvases_for_margins(leaves: list,
                                 panel_opts: dict[int, _PanelOpts]) -> None:
    """Mutate each data leaf's `_canvas_width` / `_canvas_height` to
    match the coordinated effective margin. Layout's `_measure` reads
    the canvas, so this is what makes max-per-column/row see the
    grown-to-fit dimensions."""
    for leaf in leaves:
        M = panel_opts[id(leaf)].M_eff
        leaf._canvas_width  = leaf._data_width  + M["left"] + M["right"]
        leaf._canvas_height = leaf._data_height + M["top"]  + M["bottom"]
        # Cache the effective margin on the leaf so `_attachments.allocate`
        # can read per-side margins to compute data-area-aligned offsets
        # without threading panel_opts through the allocation recursion.
        leaf._last_M_eff = dict(M)




class RenderPlan:
    """The resolution pass's complete output — the working set the emit
    pass consumes. `root` is the materialized render tree (canvases
    grown to their measured margins), `states` the replayed per-leaf
    state dicts, `panel_opts` the per-leaf axis descriptors + effective
    margins. Wrapped by the public `ResolvedIR` (`resolved_ir.py`): the
    projection users inspect and this plan are two views of one
    resolution — the emit pass renders from exactly what `resolve`
    reports."""

    def __init__(self, root, panel_opts: dict, states: dict):
        self.root = root
        self.panel_opts = panel_opts
        self.states = states


def _build_plan(root) -> RenderPlan:
    """Resolution pass: materialize wired state, replay every leaf,
    train axis descriptors, coordinate share scaling and margins, size
    legend leaves, and resolve every container-coord layout's overlay
    plan. Everything downstream (`_emit_plan`, and the coord
    `render_layout` delegation) consumes the plan; nothing re-resolves.

    Despite the pure-sounding name, this pass MUTATES the hydrated tree
    in place: `_apply_share_scaling` writes `_data_width`/`_data_height`,
    the margin passes write `_last_M_eff` and `_canvas_width`/
    `_canvas_height`. Each mutating pass resets from the `_orig_*`
    fields first, so re-running the whole pass is idempotent — see
    those two functions for the per-field details."""
    from ._nodes import materialize
    materialize(root)
    panel_opts, states = _resolve_panels(root)
    # Override each legend leaf's intrinsic _fig size with its
    # content-driven size before measure runs.
    from ._legend import _size_legends
    _size_legends(root, states)
    _resolve_coord_layouts(root)
    return RenderPlan(root, panel_opts, states)


def _resolve_coord_layouts(node) -> None:
    """Resolve the overlay plan of every container-coord layout under
    `node` (root and embedded alike) so measure (`layout_size`),
    placement, and emit all consume the cached plan instead of
    re-resolving. Children first — a nested coord layout resolves
    before its parent might consult it. Coords that implement
    `render_layout` without the staged `resolve_layout` keep their
    old at-emit behavior."""
    if node is None or not getattr(node, "_is_parent", False):
        return
    for child in node._children:
        _resolve_coord_layouts(child)
    coord_obj = getattr(node, "_coordinate", None)
    if (coord_obj is not None and hasattr(coord_obj, "resolve_layout")
            and getattr(node, "_coord_plan", None) is None):
        coord_obj.resolve_layout(node)


def _render_coord_root(root, outer=None) -> str:
    """Document-root render for a container-coord layout — the coord
    owns the entire strategy (overlay, ring stacking, …) and returns
    `(W, H, body)`; this wraps it in the top-level `<svg>`. The
    placement loop in `_emit_plan` calls `coord.render_layout` directly
    when embedding a coord-Layout inside a parent — there it wants the
    body, not a wrapper."""
    coord_obj = root._coordinate
    W, H, body = coord_obj.render_layout(root)
    ol = outer["left"]   if outer else 0
    ot = outer["top"]    if outer else 0
    or_ = outer["right"] if outer else 0
    ob = outer["bottom"] if outer else 0
    Wt, Ht = W + ol + or_, H + ot + ob
    wrap = f'<g transform="translate({ol},{ot})">' if (ol or ot) else ""
    close = "</g>" if (ol or ot) else ""
    # Match `_emit_plan`: root theme scopes the outer <svg> (so a themed
    # root gets the right figure background), and `_figure_root_attrs()`
    # carries the standard plotlet schema attrs so downstream tools can
    # identify the SVG. The background is a real first-child <rect> —
    # CSS `background` on the root element is ignored by non-browser
    # consumers (cairosvg).
    with _figure_style(root):
        root_fs = _FIGSPEC["root_font_size"]
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{Wt}" height="{Ht}" viewBox="0 0 {Wt} {Ht}" '
                f'font-family="{svg_family()}" font-size="{root_fs}"'
                f'{_figure_root_attrs()}>'
                f'<rect width="{Wt}" height="{Ht}" '
                f'fill="{SPEC["figure"]["background"]}"/>'
                f'{wrap}{body}{close}</svg>')


def _emit_plan(plan: RenderPlan, outer=None) -> str:
    """Emit pass: measure, allocate pixel rects, write the SVG. Consumes
    the `RenderPlan` — no re-resolution happens past this point."""
    root, panel_opts, states = plan.root, plan.panel_opts, plan.states
    W, H = _measure(root)
    W, H = int(round(W)), int(round(H))
    placements: list = []
    _allocate(root, 0, 0, W, H, placements)

    # Figure-level breathing room. Only the public root render passes a
    # non-None `outer`; embedded layouts (e.g. attachment routing through
    # this function) pass `None`.
    ol = outer["left"] if outer else 0
    ot = outer["top"]  if outer else 0
    or_ = outer["right"]  if outer else 0
    ob = outer["bottom"] if outer else 0
    Wt = W + ol + or_
    Ht = H + ot + ob

    # Root theme + font scope the outer <svg> emit — a root that funnels
    # to a single leaf (the lone-chart wrapper) puts the figure
    # background under that leaf's style so a dark chart gets a dark
    # canvas. Multi-panel roots take neither, and each leaf's own
    # `_node_style` block below still owns its chrome.
    with _figure_style(root):
        root_fs = _FIGSPEC["root_font_size"]
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wt}" height="{Ht}" '
            f'viewBox="0 0 {Wt} {Ht}" font-family="{svg_family()}" font-size="{root_fs}"'
            f'{_figure_root_attrs()}>',
            # Real first-child <rect>, not CSS `background` on the root —
            # non-browser consumers (cairosvg) ignore the CSS property.
            f'<rect width="{Wt}" height="{Ht}" '
            f'fill="{SPEC["figure"]["background"]}"/>',
        ]
    if ol or ot:
        parts.append(f'<g transform="translate({ol},{ot})">')
    # Two passes so legends can read color-cycle assignments off data
    # artists. _render_inner mutates each artist dict's `_color`; legends
    # then harvest those for their swatches. Diagram leaves render in
    # pass 1 (no dependency on data artists' colors) but via a separate
    # path that emits the stored debug SVG verbatim, with no panel
    # decorations.
    data_leaves: list = []
    # Shared across panels so each coord-clip `<clipPath id>` is unique
    # within this document. Reset per layout render → byte-identical output.
    clip_counter = count()
    for leaf, (x, y, w, h) in placements:
        if leaf._is_parent:
            lcoord = leaf._coordinate
            if lcoord is not None and hasattr(lcoord, "render_layout"):
                # Coord-bearing sub-Layout — `_is_atomic` kept the
                # placement system from descending into it, so we ask the
                # coord directly for its `(W, H, body)`. The body inlines
                # inside a translate group; we don't want the `<svg>`
                # wrapper here because we're not the document root.
                _W, _H, body = lcoord.render_layout(leaf)
                parts.append(
                    f'<g transform="translate({coord(x)},{coord(y)})">{body}</g>'
                )
            else:
                # Titled rect layout — `_allocate` recorded its band
                # rect; draw the centered title text there.
                with _regions.translate(ol, ot):
                    parts.append(_emit_layout_title(leaf, x, y, w))
            continue
        kind = leaf._leaf_kind
        if kind == "legend":
            continue
        if kind == "diagram":
            parts.append(
                f'<g transform="translate({coord(x)},{coord(y)})" '
                f'data-plotlet-kind="diagram">'
            )
            parts.append(leaf._diagram_inner)
            parts.append('</g>')
            continue
        layout_opts = panel_opts[id(leaf)]
        # Coordinated margin from `_compute_measured_margins` (hide-aware
        # `_required_margin`); copied so per-leaf mutation can't leak back.
        M_eff = dict(layout_opts.M_eff)
        iw = w - M_eff["left"] - M_eff["right"]
        ih = h - M_eff["top"] - M_eff["bottom"]
        state = states[id(leaf)]
        transform = f'translate({coord(x + M_eff["left"])},{coord(y + M_eff["top"])})'
        # Per-leaf theme + font wrap both panel-opening attrs and inner
        # render, so frame draws (spines, ticks, text) read the leaf's
        # style. `_regions.translate(...)` tracks this leaf's outer
        # offset on the sink so chrome bboxes land in outer-SVG coords;
        # multi-panel layouts get correct per-panel positions without
        # extra work.
        with _node_style(leaf):
            # panel-bbox attr is documented as outer-SVG coords; add the
            # outer offset (ol, ot) since we live inside a translate wrapper.
            parts.append(_panel_open(state, layout_opts, transform, M_eff, iw, ih,
                                     (x + ol, y + ot, w, h)))
            # Add the outer offset (ol, ot) so chrome bboxes land in
            # outer-SVG coords; matches the `<g transform="translate(ol, ot)">`
            # wrapper on the SVG side.
            with _regions.translate(x + M_eff["left"] + ol, y + M_eff["top"] + ot):
                parts.append(_render_inner(state, iw, ih, M_eff, layout_opts,
                                           clip_counter=clip_counter))
            parts.append('</g>')
        data_leaves.append(leaf)
    for leaf, (x, y, w, h) in placements:
        # Coord-bearing sub-Layouts were emitted in the data-leaf pass
        # above; skip them here (they have no `_leaf_kind` attribute).
        if leaf._is_parent or leaf._leaf_kind != "legend":
            continue
        from ._legend import _render_legend
        # Same `data-plotlet-kind` + bbox attrs the data-panel wrapper
        # carries, so `layout_diagram` can render an outline for the
        # legend leaf the way it does for charts (minus the data area).
        # legend-bbox attr is documented as outer-SVG coords; add the outer
        # offset (ol, ot) since we live inside a translate wrapper.
        parts.append(
            f'<g transform="translate({coord(x)},{coord(y)})" '
            f'data-plotlet-kind="legend" '
            f'data-plotlet-legend-bbox="{x + ol:.0f},{y + ot:.0f},'
            f'{w:.0f},{h:.0f}">'
        )
        with _regions.translate(x + ol, y + ot):
            parts.append(_render_legend(leaf, w, h, states, data_leaves))
        parts.append('</g>')
    if ol or ot:
        parts.append('</g>')
    parts.append('</svg>')
    return "".join(parts)


