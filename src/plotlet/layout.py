"""Subplot layout: rect computation + multi-panel SVG assembly.

A composed (parent) `Chart` is a tree of Charts. This module walks that tree,
allocates a pixel rect to each leaf, and emits one outer `<svg>` containing
one `<g transform>` per leaf — each calling `_render_inner` from `core.py`.

Panel sizing is equal by default in each direction. `pt.grid([[...]])`
accepts optional `widths=` / `heights=` ratios. A future per-chart `width=`
hint (for self-sizing colorbars) is out of scope for step 1.

Auto-zero-gutter rule: when two adjacent leaves have a `share_x=` /
`share_y=` relationship across the relevant axis (horizontal neighbors with
matching y, vertical neighbors with matching x), the gutter between them
collapses to 0. Anything more elaborate — per-edge gaps, per-pair config —
is intentionally omitted; nest tighter via composition if you need finer
control.
"""
from __future__ import annotations

from ._spec import _LAYOUTSPEC, _SIZESPEC, _FONTSPEC
from .core import _render_inner
from .chart import Chart

_GUTTER = _LAYOUTSPEC["gutter"]
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
# rect computation + render
# ---------------------------------------------------------------------------

def _ratios(spec: list[float] | None, n: int) -> list[float]:
    """Return per-cell sizes as fractions of allocation (sums to 1)."""
    if spec is None:
        return [1.0 / n] * n
    total = float(sum(spec))
    if total <= 0:
        raise ValueError("ratios must sum to a positive value.")
    return [s / total for s in spec]


def _gutters_h(children: list[Chart | None]) -> list[float]:
    """Per-gap horizontal gutters between adjacent cells (length = n-1).

    A gap collapses to 0 when both sides exist and the right side is a leaf
    that share_y= the immediate left neighbor (or vice versa) — i.e. the two
    leaves coordinate on the y-axis, so they should sit flush horizontally.
    """
    n = len(children)
    out = []
    for i in range(n - 1):
        a, b = children[i], children[i + 1]
        out.append(_pair_gutter(a, b, axis="h"))
    return out


def _gutters_v(children: list[Chart | None]) -> list[float]:
    n = len(children)
    out = []
    for i in range(n - 1):
        a, b = children[i], children[i + 1]
        out.append(_pair_gutter(a, b, axis="v"))
    return out


def _pair_gutter(a: Chart | None, b: Chart | None, *, axis: str) -> float:
    """Decide the gutter between adjacent cells.

    Horizontal neighbor pair → look at share_y (they coordinate on y, so
    horizontal flush makes sense). Vertical neighbor pair → look at share_x.
    """
    if a is None or b is None:
        return _GUTTER
    if not (a._is_parent is False and b._is_parent is False):
        # At least one is a sub-layout; default gutter.
        # (More precise inspection — would either tightest leaf share? — is
        #  out of scope for step 1.)
        return _GUTTER
    share = "_share_y" if axis == "h" else "_share_x"
    if getattr(b, share, None) is a or getattr(a, share, None) is b:
        return 0.0
    return _GUTTER


def _leaf_rect_size(leaf: Chart) -> tuple[int, int]:
    """The leaf's intrinsic size (figure width, height). Used in step 1
    only as a fallback total when a parent has a single leaf — for now, just
    a hint we don't currently use; equal-share sizing is the rule."""
    return leaf._fig._width, leaf._fig._height


def _layout_total_size(node: Chart) -> tuple[int, int]:
    """Total (W, H) for the outer SVG of a composed parent.

    For step 1 we use a simple rule: take the max-width / max-height across
    all leaves and multiply by the count along each axis, plus gutters.
    Users who want a specific size should set `width=` / `height=` on the
    individual leaves (the leaf carries its own size today).
    """
    leaves = list(_iter_leaves(node))
    if not leaves:
        return _SIZESPEC["width"], _SIZESPEC["height"]
    # Pick the dominant size: each leaf contributes its own (W, H). For an
    # h-row of N leaves, we lay them out at full leaf height and stack widths;
    # for a v-column, vice versa; for a grid, both. Recursive walk:
    return _measure(node)


def _measure(node: Chart) -> tuple[int, int]:
    """Recursively measure the pixel (W, H) a node wants."""
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
    # Per-column width = max measured width over its column; per-row height
    # = max measured height over its row. Empty cells contribute 0.
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
    # Apply user-supplied ratios as scaling: if widths=[2, 1, ...], the
    # column widths are *redistributed* to those ratios while preserving the
    # total. Step-1 simple: if widths is given, use it as relative sizing
    # over the natural total.
    if node._grid_widths is not None:
        total = sum(col_widths) or sum(_ratios(node._grid_widths, cols)) * cols
        col_widths = [r * total for r in _ratios(node._grid_widths, cols)]
    if node._grid_heights is not None:
        total = sum(row_heights) or sum(_ratios(node._grid_heights, rows)) * rows
        row_heights = [r * total for r in _ratios(node._grid_heights, rows)]
    # Gutters: rows above each row except the first; cols left of each col
    # except the first. Step 1: full gutter everywhere (auto-zero-gutter in
    # grids checked per pair).
    h_gaps = [_pair_gutter(children[0 * cols + c], children[0 * cols + c + 1], axis="h")
              for c in range(cols - 1)]
    v_gaps = [_pair_gutter(children[r * cols + 0], children[(r + 1) * cols + 0], axis="v")
              for r in range(rows - 1)]
    W = int(round(sum(col_widths) + sum(h_gaps)))
    H = int(round(sum(row_heights) + sum(v_gaps)))
    return W, H


def _iter_leaves(node: Chart):
    if not node._is_parent:
        yield node
        return
    for c in node._children:
        if c is None:
            continue
        yield from _iter_leaves(c)


def _allocate(node: Chart, x: float, y: float, w: float, h: float, out: list):
    """Walk the tree, recording (leaf, rect) pairs into `out`."""
    if not node._is_parent:
        out.append((node, (x, y, w, h)))
        return
    if node._layout_kind == "h":
        gaps = _gutters_h(node._children)
        # Each child gets equal share of remaining width after gutters
        remaining = w - sum(gaps)
        per = remaining / len(node._children)
        cx = x
        for i, c in enumerate(node._children):
            _allocate(c, cx, y, per, h, out)
            cx += per
            if i < len(gaps):
                cx += gaps[i]
        return
    if node._layout_kind == "v":
        gaps = _gutters_v(node._children)
        remaining = h - sum(gaps)
        per = remaining / len(node._children)
        cy = y
        for i, c in enumerate(node._children):
            _allocate(c, x, cy, w, per, out)
            cy += per
            if i < len(gaps):
                cy += gaps[i]
        return
    # grid
    rows, cols = node._grid_rows, node._grid_cols
    children = node._children
    h_gaps = [_pair_gutter(children[0 * cols + c], children[0 * cols + c + 1], axis="h")
              for c in range(cols - 1)]
    v_gaps = [_pair_gutter(children[r * cols + 0], children[(r + 1) * cols + 0], axis="v")
              for r in range(rows - 1)]
    col_w = (w - sum(h_gaps)) / cols
    row_h = (h - sum(v_gaps)) / rows
    if node._grid_widths is not None:
        col_ws = [r * (w - sum(h_gaps)) for r in _ratios(node._grid_widths, cols)]
    else:
        col_ws = [col_w] * cols
    if node._grid_heights is not None:
        row_hs = [r * (h - sum(v_gaps)) for r in _ratios(node._grid_heights, rows)]
    else:
        row_hs = [row_h] * rows
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


def _render_layout(root: Chart) -> str:
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
        M = leaf._fig._margin
        iw = w - M["left"] - M["right"]
        ih = h - M["top"] - M["bottom"]
        st = leaf._fig._replay()
        parts.append(f'<g transform="translate({x + M["left"]:.2f},{y + M["top"]:.2f})">')
        parts.append(_render_inner(st, iw, ih, M))
        parts.append('</g>')
    parts.append('</svg>')
    return "".join(parts)
