"""Subplot layout: rect computation + multi-panel SVG assembly.

A composed (parent) `Chart` is a tree of Charts. This module walks that tree,
allocates a pixel rect to each leaf, and emits one outer `<svg>` containing
one `<g transform>` per leaf — each calling `_render_inner` from `core.py`.

Composition is component-first: a parent's total size is the sum of its
children plus gaps; leaf size hints (`pt.chart(data_width=…)` —
preferred — or `canvas_width=…`) act as relative ratios when a parent
allocates space. When two leaves are connected by `share_x=` / `share_y=`,
the share pre-pass forces both panels onto a single shared scale so
domains line up, and inner-edge tick labels and axis labels on the
joined side are dropped — the joined-side margin collapses to just the
floor via the content-aware `_required_margin`. Spines and tick marks
remain so each panel still reads as a closed rectangle. Parent `gap`
applies uniformly (joined or not). See `docs/SUBPLOTS.md` for the
design rationale.
"""
from __future__ import annotations

from graphlib import CycleError, TopologicalSorter

from ._spec import SPEC, _LAYOUTSPEC, _FONTSPEC, active_theme
from .core import (
    _render_inner, _replay, _enforce_floors, _required_margin,
    _x_descriptor_multi, _y_descriptor_multi,
    _AxisDescriptor, _PanelOpts,
    _figure_root_attrs, _panel_open,
)
from .chart import Chart, _extract_theme

# Layout gaps stay captured — they're parent-level positional, not
# per-leaf-themable. Font family and background read live from the spec
# so a leaf's `c.theme(...)` propagates to the surrounding canvas.
_GAP = _LAYOUTSPEC["gap"]
_LEGEND_GAP = _LAYOUTSPEC["legend_gap"]


# ---------------------------------------------------------------------------
# pt.grid — irregular grid constructor
# ---------------------------------------------------------------------------

def grid(cells: list[list],
         share_x: bool | str = False,
         share_y: bool | str = False,
         gap: int | float | None = None,
         **kwargs) -> Chart:
    """Build a grid-layout parent Chart from a list-of-lists of cells.

    Each cell is either a `Chart` or `None` (empty). All rows must have
    the same number of columns. The grid does **no proportional
    redistribution** — each column's width is the max natural canvas
    width across cells in that column; each row's height is the max
    natural canvas height across cells in that row. To make a column
    twice as wide as another, set `data_width=` directly on the leaf
    charts; the grid then sums their natural canvases plus per-boundary
    gaps.

    Sharing kwargs (matching matplotlib's `subplots(sharex=...)` semantics):

    * `share_x=True` (or `"all"`) — every leaf in the grid shares x with
      the first leaf (top-left).
    * `share_x="col"` — each column is its own share class; the topmost
      leaf in each column is the anchor.
    * `share_x="row"` — each row is its own share class.
    * `share_x=False` (default) or `"none"` — no sharing.

    `share_y=` is symmetric. When sharing is active, non-anchor leaves'
    aspect ratios are preserved and scaled so the shared dimension matches
    the anchor's.
    """
    # Migration error — `widths=` / `heights=` were canvas-ratio overrides
    # in 0.1.x. With body-size-first composition there's no longer a
    # well-defined "redistribute the canvas" operation: leaves carry data,
    # parents derive canvas. Set per-leaf `data_width=` to control sizing.
    if "widths" in kwargs or "heights" in kwargs:
        raise TypeError(
            "pt.grid() no longer accepts `widths=` / `heights=` (changed "
            "in 0.2.0). To make a column 2× wider than another, set "
            "`data_width=` on each leaf — e.g. "
            "`pt.chart(data_width=200) | pt.chart(data_width=100)`. The grid "
            "sums each cell's natural canvas; per-leaf data sizes give you "
            "all the control ratios used to."
        )
    if kwargs:
        raise TypeError(f"pt.grid() got unexpected keyword arguments: {list(kwargs)!r}")
    if not cells or not isinstance(cells, list):
        raise ValueError("pt.grid expects a non-empty list of rows.")
    rows = len(cells)
    cols = len(cells[0])
    if any(len(row) != cols for row in cells):
        raise ValueError("pt.grid rows must all have the same number of columns.")

    flat: list[Chart | None] = []
    for row in cells:
        for cell in row:
            if cell is not None and not isinstance(cell, Chart):
                raise TypeError(
                    f"pt.grid cells must be Chart or None; got {type(cell).__name__}."
                )
            if cell is not None and cell._parent is not None:
                raise ValueError(
                    "Each chart can be in at most one parent. "
                    "Compose fresh charts, or copy your sub-assembly."
                )
            flat.append(cell)

    parent = Chart._new_parent("grid", [])
    parent._children = flat            # row-major; may contain None
    parent._grid_rows = rows
    parent._grid_cols = cols
    for cell in flat:
        if cell is not None:
            cell._parent = parent
    if gap is not None:
        parent._gap = float(gap)
    parent.share_x(share_x)
    parent.share_y(share_y)
    return parent


# ---------------------------------------------------------------------------
# Gap rules — when adjacent leaves coordinate on the orthogonal axis,
# the gap between them collapses to 0.
# ---------------------------------------------------------------------------

def _share_root(leaf: Chart, axis: str) -> Chart:
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


def _resolve_gap(a: Chart | None, b: Chart | None) -> float:
    """Pull the per-parent `gap` override off whichever cell is non-None;
    fall back to `spec.json:layout.gap`. Both-None happens when an entire
    grid boundary is empty cells; spec default is the right answer there."""
    parent = (a._parent if a is not None else None) \
          or (b._parent if b is not None else None)
    if parent is not None and parent._gap is not None:
        return parent._gap
    return _GAP


def _pair_gap(a: Chart | None, b: Chart | None, *, axis: str) -> float:
    """Gap between two adjacent cells.

    Two regimes:
      - Legend ↔ its source (or any data sibling, if the legend has no
        explicit source) → `legend_gap`, a small intentional separation
        that's not a share-pair joint and doesn't trigger spine/label
        suppression.
      - Anything else → the parent's gap (set via `(a | b).gap(N)` or
        `pt.grid(..., gap=N)`), or the spec default if unset. Joined
        share-pairs use this same gap too: their close-side breathing
        comes from the floor + content-aware `_required_margin` (joined
        sides have no tick labels / axis labels / title → just floor),
        so `gap` is genuinely extra inter-panel space layered on top.
    """
    default_gap = _resolve_gap(a, b)
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


def _gaps_h(children: list[Chart | None]) -> list[float]:
    return [_pair_gap(children[i], children[i + 1], axis="h")
            for i in range(len(children) - 1)]


def _gaps_v(children: list[Chart | None]) -> list[float]:
    return [_pair_gap(children[i], children[i + 1], axis="v")
            for i in range(len(children) - 1)]


def _grid_col_gap(children: list[Chart | None], rows: int, cols: int, c: int) -> float:
    """Gap between grid columns c and c+1: min over all rows. If any row
    has a joined pair across this column boundary, the whole boundary
    collapses — otherwise the default gap."""
    return min(
        _pair_gap(children[r * cols + c], children[r * cols + c + 1], axis="h")
        for r in range(rows)
    )


def _grid_row_gap(children: list[Chart | None], rows: int, cols: int, r: int) -> float:
    return min(
        _pair_gap(children[r * cols + c], children[(r + 1) * cols + c], axis="v")
        for c in range(cols)
    )


# ---------------------------------------------------------------------------
# Measurement — recursive (W, H) for a node, honoring leaf size hints.
# ---------------------------------------------------------------------------

def _leaf_rect_size(leaf: Chart) -> tuple[int, int]:
    """The leaf's intrinsic canvas size. For data leaves: data region
    + measure-driven margin (set by the layout pre-pass). For legend
    and diagram leaves: the explicit canvas dims set at construction.
    Doubles as the relative size hint when the parent allocates space."""
    return leaf._canvas_width, leaf._canvas_height


def _measure(node: Chart) -> tuple[int, int]:
    """The pixel (W, H) the node wants.

    Component-first: a leaf reports its declared size; a parent reports
    sum-of-children plus gaps in the layout direction, and max-of-children
    in the orthogonal direction. The figure size emerges from composition,
    so a 100-row heatmap stays 100 rows tall and an attached dendrogram
    sits next to it at its own natural width."""
    if not node._is_parent:
        return _leaf_rect_size(node)
    if node._layout_kind == "h":
        sizes = [_measure(c) for c in node._children]
        gaps = _gaps_h(node._children)
        W = sum(w for w, _ in sizes) + sum(gaps)
        H = max(h for _, h in sizes)
        return W, H
    if node._layout_kind == "v":
        sizes = [_measure(c) for c in node._children]
        gaps = _gaps_v(node._children)
        W = max(w for w, _ in sizes)
        H = sum(h for _, h in sizes) + sum(gaps)
        return W, H
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
    return W, H


def _natural_size(root: Chart) -> tuple[int, int]:
    """The figure's natural (W, H), including measure-driven margin growth
    and any share-scaling coordination between leaves. Runs the pre-pass
    so every data leaf's `_canvas_*` reflects the final body+margin total,
    then sums those across the composition.

    Mutates `root` — pass a deep copy if you need a non-destructive
    measurement. Used by `Chart.fit()`."""
    if not root._is_parent:
        # Single-leaf root: data leaves grow their canvas to fit content
        # via the solo `_effective_margin`; non-data leaves keep the
        # canvas they were constructed with.
        if root._leaf_kind == "data":
            from .core import _effective_margin as _solo_margin
            st = _replay(root._calls)
            st["insets"] = getattr(root, "_insets", [])
            M_eff = _solo_margin(root, st)
            root._canvas_width  = root._data_width  + M_eff["left"] + M_eff["right"]
            root._canvas_height = root._data_height + M_eff["top"]  + M_eff["bottom"]
        return _measure(root)
    _, states = _build_panel_opts(root)
    # Legend leaves harvest their content size from sibling data leaves;
    # without this, layouts containing a layout-level legend would report
    # a stale 1×1 placeholder canvas.
    from .legend import _size_legends
    _size_legends(root, states)
    return _measure(root)


def _data_total_size(node: Chart) -> tuple[float, float]:
    """Sum of `_data_width` / `_data_height` across all data leaves in
    the node's tree, combined the same way `_measure` combines canvases
    (sum along layout direction, max orthogonally). Non-data leaves
    contribute zero — their canvases live in the "overhead" budget that
    `Chart.fit()` subtracts when solving for the scale factor.

    Used so `fit()` can solve `target = s * data_total + overhead`
    directly in one pass instead of converging geometrically via
    `s = target / natural`."""
    if not node._is_parent:
        if node._leaf_kind == "data":
            return float(node._data_width), float(node._data_height)
        return 0.0, 0.0
    if node._layout_kind == "h":
        sizes = [_data_total_size(c) for c in node._children]
        return sum(w for w, _ in sizes), max((h for _, h in sizes), default=0.0)
    if node._layout_kind == "v":
        sizes = [_data_total_size(c) for c in node._children]
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

def _iter_leaves(node: Chart):
    if not node._is_parent:
        yield node
        return
    for c in node._children:
        if c is None:
            continue
        yield from _iter_leaves(c)


def _allocate(node: Chart, x: float, y: float, w: float, h: float, out: list):
    """Walk the tree, recording (leaf, rect) pairs into `out`. Leaf size hints
    (set via `pt.chart(data_width=, data_height=)` or the canvas_* form)
    act as relative ratios — so a narrow colorbar leaf in
    `hm | pt.colorbar(hm)` self-sizes without forcing the user to declare
    explicit widths."""
    if not node._is_parent:
        out.append((node, (x, y, w, h)))
        return
    if node._layout_kind == "h":
        gaps = _gaps_h(node._children)
        remaining = w - sum(gaps)
        sizes = [_measure(c)[0] for c in node._children]
        ratios = _hint_ratios(sizes, len(node._children))
        cx = x
        for i, c in enumerate(node._children):
            per = remaining * ratios[i]
            _allocate(c, cx, y, per, h, out)
            cx += per
            if i < len(gaps):
                cx += gaps[i]
        return
    if node._layout_kind == "v":
        gaps = _gaps_v(node._children)
        remaining = h - sum(gaps)
        sizes = [_measure(c)[1] for c in node._children]
        ratios = _hint_ratios(sizes, len(node._children))
        cy = y
        for i, c in enumerate(node._children):
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

def _apply_share_scaling(leaves: list[Chart]) -> None:
    """Mutate non-anchor leaves' `_data_width` / `_data_height` to
    coordinate with their share anchors. Reads from `_orig_data_*`
    each call so the operation is idempotent across re-renders."""
    # Reset to the user's original dims first so scaling is computed from a
    # clean baseline regardless of prior renders.
    for leaf in leaves:
        leaf._data_width  = leaf._orig_data_width
        leaf._data_height = leaf._orig_data_height

    # Apply scaling in topo order so anchors of chained share-classes
    # have settled before sharers depend on them.
    for leaf in _topo_order(leaves):
        sx = leaf._share_x
        sy = leaf._share_y
        if sx is None and sy is None:
            continue
        old_w = leaf._data_width
        old_h = leaf._data_height
        if sx is not None and sy is not None:
            # Both axes shared — force both, no aspect preservation
            new_w = sx._data_width
            new_h = sy._data_height
        elif sx is not None:
            # Width forced to anchor; height scales to preserve aspect
            new_w = sx._data_width
            new_h = old_h * (new_w / old_w) if old_w > 0 else old_h
        else:  # sy is not None
            new_h = sy._data_height
            new_w = old_w * (new_h / old_h) if old_h > 0 else old_w
        leaf._data_width  = new_w
        leaf._data_height = new_h
        # Refresh derived canvas dims so downstream `_measure` sees them.
        leaf._canvas_width  = new_w + leaf._margin["left"]   + leaf._margin["right"]
        leaf._canvas_height = new_h + leaf._margin["top"]    + leaf._margin["bottom"]


# ---------------------------------------------------------------------------
# Scale-share pre-pass — topo-sort leaves by share_x / share_y, then build
# one axis descriptor per share-equivalence class.
# ---------------------------------------------------------------------------

def _validate_share_targets(leaves: list[Chart]) -> None:
    """Every share target must itself be a leaf in the same composition."""
    leaf_ids = {id(l) for l in leaves}
    for leaf in leaves:
        for attr, axis in (("_share_x", "x"), ("_share_y", "y")):
            src = getattr(leaf, attr)
            if src is None:
                continue
            if not isinstance(src, Chart):
                raise TypeError(
                    f"share_{axis}= must be a Chart; got {type(src).__name__}."
                )
            if src._is_parent:
                raise ValueError(
                    f"share_{axis}= target must be a leaf chart, not a composed parent."
                )
            if id(src) not in leaf_ids:
                raise ValueError(
                    f"share_{axis}= target is not part of this composition. "
                    f"Both charts must be composed into the same parent."
                )


def _topo_order(leaves: list[Chart]) -> list[Chart]:
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


def _build_axis_descriptors(leaves: list[Chart],
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
    for axis, attr, multi_fn, out in (
        ("x", "_share_x", _x_descriptor_multi, x_desc),
        ("y", "_share_y", _y_descriptor_multi, y_desc),
    ):
        classes: dict[int, list[Chart]] = {}
        for leaf in leaves:
            root = _share_root(leaf, axis)
            classes.setdefault(id(root), []).append(leaf)
        for class_leaves in classes.values():
            anchor = next((l for l in class_leaves if getattr(l, attr) is None),
                          class_leaves[0])
            ordered = [anchor] + [l for l in class_leaves if l is not anchor]
            desc = multi_fn([states[id(l)] for l in ordered])
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

def _mark_joined_pair(a: Chart | None, b: Chart | None, *, axis: str,
                      out: dict[int, _PanelOpts]) -> None:
    """If `a` and `b` are joined along `axis` (i.e., share-equivalent on the
    orthogonal axis), set `hide_*` on both sides of the joint and
    `suppress_*_labels` on the side whose tick labels would duplicate the
    neighbor's. h-axis: y-tick labels live on the left, so the right panel
    suppresses. v-axis: x-tick labels live on the bottom, so the top panel
    suppresses."""
    if a is None or b is None or a._is_parent or b._is_parent:
        return
    if a._leaf_kind != "data" or b._leaf_kind != "data":
        return
    share_axis = "y" if axis == "h" else "x"
    if _share_root(a, share_axis) is not _share_root(b, share_axis):
        return
    if axis == "h":
        out[id(a)].hide_right = True
        out[id(b)].hide_left = True
        out[id(b)].suppress_left_labels = True
    else:
        out[id(a)].hide_bottom = True
        out[id(a)].suppress_bottom_labels = True
        out[id(b)].hide_top = True


def _annotate_collapses(node: Chart, out: dict[int, _PanelOpts]) -> None:
    """Walk the tree, marking joined-pair flags on every adjacent pair of
    leaves that share an axis (orthogonal to the layout direction)."""
    if not node._is_parent:
        return
    if node._layout_kind in ("h", "v"):
        axis = node._layout_kind
        for a, b in zip(node._children, node._children[1:]):
            _mark_joined_pair(a, b, axis=axis, out=out)
        for c in node._children:
            _annotate_collapses(c, out)
        return
    rows, cols = node._grid_rows, node._grid_cols
    children = node._children
    for r in range(rows):
        for c in range(cols - 1):
            _mark_joined_pair(children[r * cols + c],
                              children[r * cols + c + 1], axis="h", out=out)
    for c in range(cols):
        for r in range(rows - 1):
            _mark_joined_pair(children[r * cols + c],
                              children[(r + 1) * cols + c], axis="v", out=out)
    for cell in children:
        if cell is not None:
            _annotate_collapses(cell, out)


def _propagate_grid_joins(node: Chart, out: dict[int, _PanelOpts]) -> None:
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


def _build_panel_opts(root: Chart) -> tuple[dict[int, _PanelOpts], dict[int, dict]]:
    """One pass over the tree that produces (panel_opts, replayed states).

    For body-first leaves, also computes a measure-driven effective
    margin (per-leaf measurement, then per-column/row coordination so
    cells in the same grid column/row align), and mutates each leaf's
    `_canvas_width`/`_canvas_height` to match — `_measure` reads those
    when summing the parent's natural canvas, so layout sees the final
    grown-to-fit dimensions on the first walk.

    Legend leaves are skipped — they have no x/y axes, no artists, and
    render through their own pipeline (see `legend.py`)."""
    leaves = [l for l in _iter_leaves(root) if l._leaf_kind == "data"]
    _apply_share_scaling(leaves)
    # Replay each leaf under its own theme so state defaults (spine
    # visibility, tick direction) and any measurement reads pick up the
    # theme's values. Multi-panel layouts may mix themes; each leaf
    # carries its own context.
    states = {}
    for l in leaves:
        with active_theme(_extract_theme(l._calls)):
            st = _replay(l._calls)
            st["insets"] = getattr(l, "_insets", [])
            states[id(l)] = st
    x_desc, y_desc = _build_axis_descriptors(leaves, states)
    panel_opts = {
        id(l): _PanelOpts(x_axis=x_desc[id(l)], y_axis=y_desc[id(l)])
        for l in leaves
    }
    _annotate_collapses(root, panel_opts)
    _propagate_grid_joins(root, panel_opts)
    _compute_measured_margins(leaves, states, panel_opts)
    _coordinate_margins(root, panel_opts)
    _update_canvases_for_margins(leaves, panel_opts)
    return panel_opts, states


def _compute_measured_margins(leaves: list[Chart],
                              states: dict[int, dict],
                              panel_opts: dict[int, _PanelOpts]) -> None:
    """Per-leaf preliminary effective margin = floor + content-required.

    `_required_margin` reads the leaf's `panel_opts` so joined share-pair
    sides naturally drop their tick-label / xlabel / ylabel / title
    reservations (the renderer suppresses these via `hide_*` /
    `suppress_*_labels`). No separate joined-side override needed — the
    floor is what's left, just like any other empty side."""
    for leaf in leaves:
        po = panel_opts[id(leaf)]
        M_floor = _enforce_floors(leaf._margin)
        M_req = _required_margin(states[id(leaf)],
                                 leaf._data_width,
                                 leaf._data_height,
                                 po=po)
        po.M_eff = {side: M_floor[side] + M_req[side] for side in M_floor}


def _body_cell(cell: Chart | None, panel_opts: dict[int, _PanelOpts]) -> bool:
    """Cells eligible for per-column/row margin coordination — data
    leaves whose preliminary margin has been computed."""
    return (cell is not None
            and not cell._is_parent
            and cell._leaf_kind == "data"
            and panel_opts.get(id(cell)) is not None
            and panel_opts[id(cell)].M_eff is not None)


def _coordinate_pair(cells: list[Chart], panel_opts: dict[int, _PanelOpts],
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
        po = panel_opts[id(c)]
        po.M_eff = {**po.M_eff, s1: m1, s2: m2}


def _coordinate_margins(node: Chart, panel_opts: dict[int, _PanelOpts]) -> None:
    """Walk the tree; at each parent, push body-first cells in the same
    column/row to share the wider margin so their data regions align.

    Horizontal parents share top/bottom across all children (one row).
    Vertical parents share left/right (one column). Grids share
    left/right per column and top/bottom per row.

    Canvas-first cells, parents, and legend leaves are excluded — they
    have their own margin policy and shouldn't pull body-first siblings
    around. Joined share-pair sides already collapsed naturally during
    `_compute_measured_margins` (hide-aware `_required_margin`), so a max
    here just picks up the smaller-margin side as expected."""
    if not node._is_parent:
        return
    if node._layout_kind == "h":
        cells = [c for c in node._children if _body_cell(c, panel_opts)]
        _coordinate_pair(cells, panel_opts, ("top", "bottom"))
        _pad_canvases(cells, panel_opts, axis="h")
        for c in node._children:
            if c is not None:
                _coordinate_margins(c, panel_opts)
        return
    if node._layout_kind == "v":
        cells = [c for c in node._children if _body_cell(c, panel_opts)]
        _coordinate_pair(cells, panel_opts, ("left", "right"))
        _pad_canvases(cells, panel_opts, axis="v")
        for c in node._children:
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


def _pad_canvases(cells: list[Chart], panel_opts: dict[int, _PanelOpts],
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


def _update_canvases_for_margins(leaves: list[Chart],
                                 panel_opts: dict[int, _PanelOpts]) -> None:
    """Mutate each data leaf's `_canvas_width` / `_canvas_height` to
    match the coordinated effective margin. Layout's `_measure` reads
    the canvas, so this is what makes max-per-column/row see the
    grown-to-fit dimensions."""
    for leaf in leaves:
        po = panel_opts[id(leaf)]
        if po.M_eff is None:
            continue
        M = po.M_eff
        leaf._canvas_width  = leaf._data_width  + M["left"] + M["right"]
        leaf._canvas_height = leaf._data_height + M["top"]  + M["bottom"]


def _effective_margin(leaf: Chart, po: _PanelOpts, w: float, h: float) -> dict:
    """Margin used at render time. Data leaves read the coordinated margin
    from `po.M_eff` (computed by `_compute_measured_margins` with hide-
    aware `_required_margin`). The fallback path (`M_eff is None`) is
    reachable only if a leaf slipped through the pre-pass; falls back to
    the floor alone."""
    if po.M_eff is not None:
        return dict(po.M_eff)
    return _enforce_floors(leaf._margin)


def _render_layout(root: Chart) -> str:
    panel_opts, states = _build_panel_opts(root)
    # Override each legend leaf's intrinsic _fig size with its
    # content-driven size before measure runs.
    from .legend import _size_legends
    _size_legends(root, states)
    W, H = _measure(root)
    W, H = int(round(W)), int(round(H))
    placements: list = []
    _allocate(root, 0, 0, W, H, placements)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{_FONTSPEC["family"]}" font-size="11" '
        f'style="background:{SPEC["figure"]["background"]}"'
        f'{_figure_root_attrs("layout")}>'
    ]
    # Two passes so legends can read color-cycle assignments off data
    # artists. _render_inner mutates each artist dict's `_color`; legends
    # then harvest those for their swatches. Diagram leaves render in
    # pass 1 (no dependency on data artists' colors) but via a separate
    # path that emits the stored debug SVG verbatim, with no panel
    # decorations.
    data_leaves: list[Chart] = []
    for leaf, (x, y, w, h) in placements:
        kind = leaf._leaf_kind
        if kind == "legend":
            continue
        if kind == "diagram":
            parts.append(
                f'<g transform="translate({x:.2f},{y:.2f})" '
                f'data-plotlet-kind="diagram">'
            )
            parts.append(leaf._diagram_inner)
            parts.append('</g>')
            continue
        po = panel_opts[id(leaf)]
        M_eff = _effective_margin(leaf, po, w, h)
        iw = w - M_eff["left"] - M_eff["right"]
        ih = h - M_eff["top"] - M_eff["bottom"]
        st = states[id(leaf)]
        transform = f'translate({x + M_eff["left"]:.2f},{y + M_eff["top"]:.2f})'
        # Per-leaf theme wraps both panel-opening attrs and inner render,
        # so frame draws (spines, ticks, text) read the leaf's theme.
        with active_theme(_extract_theme(leaf._calls)):
            parts.append(_panel_open(st, po, transform, M_eff, iw, ih, (x, y, w, h)))
            parts.append(_render_inner(st, iw, ih, M_eff, po))
            parts.append('</g>')
        data_leaves.append(leaf)
    for leaf, (x, y, w, h) in placements:
        if leaf._leaf_kind != "legend":
            continue
        from .legend import _render_legend
        parts.append(f'<g transform="translate({x:.2f},{y:.2f})">')
        parts.append(_render_legend(leaf, w, h, states, data_leaves))
        parts.append('</g>')
    parts.append('</svg>')
    return "".join(parts)
