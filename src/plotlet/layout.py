"""Subplot layout: rect computation + multi-panel SVG assembly.

A composed (parent) `Chart` is a tree of Charts. This module walks that tree,
allocates a pixel rect to each leaf, and emits one outer `<svg>` containing
one `<g transform>` per leaf — each calling `_render_inner` from `core.py`.

Composition is component-first: a parent's total size is the sum of its
children plus gutters; leaf size hints (`pt.chart(width=…)`) act as
relative ratios when a parent allocates space. The auto-zero-gutter rule
collapses the gap between two leaves connected by `share_x=` / `share_y=`,
and the share pre-pass forces both panels onto a single shared scale so
domains line up. Inner-edge tick labels and axis labels on the collapsed
side are dropped; spines and tick marks remain so each panel still reads
as a closed rectangle. See `docs/SUBPLOTS.md` for the design rationale.
"""
from __future__ import annotations

from graphlib import CycleError, TopologicalSorter

from ._spec import _LAYOUTSPEC, _FONTSPEC
from .core import (
    _render_inner, _scaled_margin, _x_descriptor, _y_descriptor,
    _AxisDescriptor, _PanelOpts,
)
from .chart import Chart

_GUTTER = _LAYOUTSPEC["gutter"]
_FLUSH_MARGIN = _LAYOUTSPEC["flush_margin"]
_FONT = _FONTSPEC["family"]


# ---------------------------------------------------------------------------
# pt.grid — irregular grid constructor
# ---------------------------------------------------------------------------

def grid(cells: list[list], *, widths: list[float] | None = None,
         heights: list[float] | None = None) -> Chart:
    """Build a grid-layout parent Chart from a list-of-lists of cells.

    Each cell is either a `Chart` or `None` (empty). All rows must have the
    same number of columns. `widths` / `heights` give per-column / per-row
    relative ratios; default is equal sizing.
    """
    if not cells or not isinstance(cells, list):
        raise ValueError("pt.grid expects a non-empty list of rows.")
    rows = len(cells)
    cols = len(cells[0])
    if any(len(row) != cols for row in cells):
        raise ValueError("pt.grid rows must all have the same number of columns.")
    if widths is not None and len(widths) != cols:
        raise ValueError(f"widths must have {cols} entries; got {len(widths)}.")
    if heights is not None and len(heights) != rows:
        raise ValueError(f"heights must have {rows} entries; got {len(heights)}.")

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
    parent._grid_widths = widths       # None means equal
    parent._grid_heights = heights
    for cell in flat:
        if cell is not None:
            cell._parent = parent
    return parent


# ---------------------------------------------------------------------------
# Gutter rules — when adjacent leaves coordinate on the orthogonal axis,
# the gap between them collapses to 0.
# ---------------------------------------------------------------------------

def _pair_gutter(a: Chart | None, b: Chart | None, *, axis: str) -> float:
    """Gutter between two adjacent cells. Collapses to 0 only when both are
    leaves and one of them shares the orthogonal axis with the other —
    horizontal pairs check `_share_y`, vertical pairs check `_share_x`."""
    if a is None or b is None or a._is_parent or b._is_parent:
        return _GUTTER
    share = "_share_y" if axis == "h" else "_share_x"
    if getattr(b, share, None) is a or getattr(a, share, None) is b:
        return 0.0
    return _GUTTER


def _gutters_h(children: list[Chart | None]) -> list[float]:
    return [_pair_gutter(children[i], children[i + 1], axis="h")
            for i in range(len(children) - 1)]


def _gutters_v(children: list[Chart | None]) -> list[float]:
    return [_pair_gutter(children[i], children[i + 1], axis="v")
            for i in range(len(children) - 1)]


def _grid_col_gap(children: list[Chart | None], rows: int, cols: int, c: int) -> float:
    """Gutter between grid columns c and c+1: min over all rows. If any row
    has a flush share-pair across this column boundary, the whole boundary
    collapses — otherwise the default gutter."""
    return min(
        _pair_gutter(children[r * cols + c], children[r * cols + c + 1], axis="h")
        for r in range(rows)
    )


def _grid_row_gap(children: list[Chart | None], rows: int, cols: int, r: int) -> float:
    return min(
        _pair_gutter(children[r * cols + c], children[(r + 1) * cols + c], axis="v")
        for c in range(cols)
    )


# ---------------------------------------------------------------------------
# Measurement — recursive (W, H) for a node, honoring leaf size hints.
# ---------------------------------------------------------------------------

def _leaf_rect_size(leaf: Chart) -> tuple[int, int]:
    """The leaf's intrinsic size — set via `pt.chart(width=, height=)` or
    falling back to spec defaults. Doubles as the relative size hint when
    a parent allocates space without explicit widths/heights ratios."""
    return leaf._fig._width, leaf._fig._height


def _measure(node: Chart) -> tuple[int, int]:
    """The pixel (W, H) the node wants.

    Component-first: a leaf reports its declared size; a parent reports
    sum-of-children plus gutters in the layout direction, and max-of-children
    in the orthogonal direction. The figure size emerges from composition,
    so a 100-row heatmap stays 100 rows tall and an attached dendrogram
    sits next to it at its own natural width."""
    if not node._is_parent:
        return _leaf_rect_size(node)
    if node._layout_kind == "h":
        sizes = [_measure(c) for c in node._children]
        gaps = _gutters_h(node._children)
        W = sum(w for w, _ in sizes) + sum(gaps)
        H = max(h for _, h in sizes)
        return W, H
    if node._layout_kind == "v":
        sizes = [_measure(c) for c in node._children]
        gaps = _gutters_v(node._children)
        W = max(w for w, _ in sizes)
        H = sum(h for _, h in sizes) + sum(gaps)
        return W, H
    # grid
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
    if node._grid_widths is not None:
        total = sum(col_widths) or sum(_ratios(node._grid_widths, cols)) * cols
        col_widths = [r * total for r in _ratios(node._grid_widths, cols)]
    if node._grid_heights is not None:
        total = sum(row_heights) or sum(_ratios(node._grid_heights, rows)) * rows
        row_heights = [r * total for r in _ratios(node._grid_heights, rows)]
    h_gaps = [_grid_col_gap(children, rows, cols, c) for c in range(cols - 1)]
    v_gaps = [_grid_row_gap(children, rows, cols, r) for r in range(rows - 1)]
    W = int(round(sum(col_widths) + sum(h_gaps)))
    H = int(round(sum(row_heights) + sum(v_gaps)))
    return W, H


def _ratios(spec: list[float] | None, n: int) -> list[float]:
    """Return per-cell sizes as fractions of allocation (sums to 1)."""
    if spec is None:
        return [1.0 / n] * n
    total = float(sum(spec))
    if total <= 0:
        raise ValueError("ratios must sum to a positive value.")
    return [s / total for s in spec]


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
    (set via `pt.chart(width=, height=)`) act as relative ratios — so a
    narrow colorbar leaf in `hm | pt.colorbar(hm)` self-sizes without forcing
    the user to declare explicit widths."""
    if not node._is_parent:
        out.append((node, (x, y, w, h)))
        return
    if node._layout_kind == "h":
        gaps = _gutters_h(node._children)
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
        gaps = _gutters_v(node._children)
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
    if node._grid_widths is not None:
        col_ws = [r * rem_w for r in _ratios(node._grid_widths, cols)]
    else:
        col_meas = [0.0] * cols
        for r in range(rows):
            for c in range(cols):
                cell = children[r * cols + c]
                if cell is None: continue
                cw, _ = _measure(cell)
                if cw > col_meas[c]: col_meas[c] = cw
        col_ws = [rem_w * r for r in _hint_ratios(col_meas, cols)]
    if node._grid_heights is not None:
        row_hs = [r * rem_h for r in _ratios(node._grid_heights, rows)]
    else:
        row_meas = [0.0] * rows
        for r in range(rows):
            for c in range(cols):
                cell = children[r * cols + c]
                if cell is None: continue
                _, ch = _measure(cell)
                if ch > row_meas[r]: row_meas[r] = ch
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
    """Compute per-leaf x/y axis descriptors. Sharers copy from their source;
    non-sharers compute from their own state."""
    _validate_share_targets(leaves)
    order = _topo_order(leaves)
    x_desc: dict[int, _AxisDescriptor] = {}
    y_desc: dict[int, _AxisDescriptor] = {}
    for leaf in order:
        if leaf._share_x is not None:
            x_desc[id(leaf)] = x_desc[id(leaf._share_x)]
        else:
            x_desc[id(leaf)] = _x_descriptor(states[id(leaf)])
        if leaf._share_y is not None:
            y_desc[id(leaf)] = y_desc[id(leaf._share_y)]
        else:
            y_desc[id(leaf)] = _y_descriptor(states[id(leaf)])
    return x_desc, y_desc


# ---------------------------------------------------------------------------
# Per-leaf hide flags — wherever auto-zero-gutter fires, the inner side of
# each panel of the pair drops its spine + ticks + tick labels. The matching
# margin shrinks to flush_margin so the data areas truly butt up.
# ---------------------------------------------------------------------------

def _mark_flush_pair(a: Chart | None, b: Chart | None, *, axis: str,
                      out: dict[int, _PanelOpts]) -> None:
    """If `a` and `b` are flush along `axis`, set `hide_*` on both sides of
    the joint and `suppress_*_labels` on the side whose tick labels would
    duplicate the neighbor's. h-axis: y-tick labels live on the left, so the
    right panel suppresses. v-axis: x-tick labels live on the bottom, so the
    top panel suppresses."""
    if a is None or b is None or _pair_gutter(a, b, axis=axis) != 0.0:
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
    """Walk the tree, marking flush flags wherever auto-zero-gutter fires."""
    if not node._is_parent:
        return
    if node._layout_kind in ("h", "v"):
        axis = node._layout_kind
        for a, b in zip(node._children, node._children[1:]):
            _mark_flush_pair(a, b, axis=axis, out=out)
        for c in node._children:
            _annotate_collapses(c, out)
        return
    rows, cols = node._grid_rows, node._grid_cols
    children = node._children
    for r in range(rows):
        for c in range(cols - 1):
            _mark_flush_pair(children[r * cols + c],
                             children[r * cols + c + 1], axis="h", out=out)
    for c in range(cols):
        for r in range(rows - 1):
            _mark_flush_pair(children[r * cols + c],
                             children[(r + 1) * cols + c], axis="v", out=out)
    for cell in children:
        if cell is not None:
            _annotate_collapses(cell, out)


def _propagate_grid_flush(node: Chart, out: dict[int, _PanelOpts]) -> None:
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
        for c in range(cols):
            cells = [children[r * cols + c] for r in range(rows)
                     if children[r * cols + c] is not None]
            if not cells: continue
            any_l = any(out[id(cell)].hide_left  for cell in cells)
            any_r = any(out[id(cell)].hide_right for cell in cells)
            for cell in cells:
                if any_l: out[id(cell)].hide_left  = True
                if any_r: out[id(cell)].hide_right = True
        for r in range(rows):
            cells = [children[r * cols + c] for c in range(cols)
                     if children[r * cols + c] is not None]
            if not cells: continue
            any_t = any(out[id(cell)].hide_top    for cell in cells)
            any_b = any(out[id(cell)].hide_bottom for cell in cells)
            for cell in cells:
                if any_t: out[id(cell)].hide_top    = True
                if any_b: out[id(cell)].hide_bottom = True
    for cell in node._children:
        if cell is not None:
            _propagate_grid_flush(cell, out)


def _build_panel_opts(root: Chart) -> tuple[dict[int, _PanelOpts], dict[int, dict]]:
    """One pass over the tree that produces (panel_opts, replayed states)."""
    leaves = list(_iter_leaves(root))
    states = {id(l): l._fig._replay() for l in leaves}
    x_desc, y_desc = _build_axis_descriptors(leaves, states)
    panel_opts = {
        id(l): _PanelOpts(x_axis=x_desc[id(l)], y_axis=y_desc[id(l)])
        for l in leaves
    }
    _annotate_collapses(root, panel_opts)
    _propagate_grid_flush(root, panel_opts)
    return panel_opts, states


def _effective_margin(M: dict, po: _PanelOpts, w: float, h: float) -> dict:
    """Margin used at render time: scale by panel size, then force flush
    sides to `flush_margin` so share-pairs have a tight, predictable joint."""
    M_eff = _scaled_margin(M, w, h)
    if po.hide_left:   M_eff["left"]   = _FLUSH_MARGIN
    if po.hide_right:  M_eff["right"]  = _FLUSH_MARGIN
    if po.hide_top:    M_eff["top"]    = _FLUSH_MARGIN
    if po.hide_bottom: M_eff["bottom"] = _FLUSH_MARGIN
    return M_eff


def _render_layout(root: Chart) -> str:
    panel_opts, states = _build_panel_opts(root)
    W, H = _measure(root)
    W, H = int(round(W)), int(round(H))
    placements: list = []
    _allocate(root, 0, 0, W, H, placements)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{_FONT}" font-size="11" '
        f'style="background:#fff">'
    ]
    for leaf, (x, y, w, h) in placements:
        po = panel_opts[id(leaf)]
        M_eff = _effective_margin(leaf._fig._margin, po, w, h)
        iw = w - M_eff["left"] - M_eff["right"]
        ih = h - M_eff["top"] - M_eff["bottom"]
        st = states[id(leaf)]
        parts.append(f'<g transform="translate({x + M_eff["left"]:.2f},{y + M_eff["top"]:.2f})">')
        parts.append(_render_inner(st, iw, ih, M_eff, po))
        parts.append('</g>')
    parts.append('</svg>')
    return "".join(parts)
