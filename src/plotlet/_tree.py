"""Shared tree walkers over the node duck protocol.

Both halves walk the same tree shape — the recording side at
validation time (over `Chart` / `Layout`), the render side when
deriving field state and building share classes (over the render
nodes in `render/_nodes.py`). The protocol is structural:
`_is_parent`, `_children`, `_effective_children()`, `_layout_kind`,
`_grid_rows` / `_grid_cols`, `_leaf_kind`, and the `_attached_*`
lists. Nothing here imports either half.
"""
from __future__ import annotations


def normalize_share_mode(axis: str, mode) -> str:
    """Map share_x / share_y param to one of "all" / "col" / "row" / "none".
    Accepts True ("all"), False / None ("none"), or the four literal strings."""
    if mode is True:
        return "all"
    if mode is False or mode is None:
        return "none"
    if isinstance(mode, str) and mode in ("all", "col", "row", "none"):
        return mode
    raise ValueError(
        f"share_{axis}=: expected True, False, or one of "
        f"'all', 'col', 'row', 'none'; got {mode!r}"
    )


def iter_leaves(node):
    """Depth-first yield of every leaf under `node`, including a leaf's
    attached charts — attachments are leaves of the composition too
    (they participate in share validation, descriptor building, etc.).
    At record-time validation the `_attached_*` lists are still empty
    (they're derived at render), so attachments simply don't appear —
    matching how share validation has always scoped."""
    if not getattr(node, "_is_parent", False):
        yield node
        for c in (node._attached_left + node._attached_right
                  + node._attached_above + node._attached_below):
            yield from iter_leaves(c)
        return
    for c in node._children:
        if c is None:
            continue
        yield from iter_leaves(c)


def compute_share_classes(node, mode: str) -> list[list]:
    """Share-equivalence classes for `share_x/y(mode)` declared on
    `node`. Raises on layout shapes that make the column/row mapping
    ambiguous — called for its raises at record-time validation, and
    for its result by the render-side apply pass."""

    def cell_leaves(cell):
        if cell is None:
            return []
        if cell._is_parent:
            return [l for l in iter_leaves(cell) if l._leaf_kind == "data"]
        return [cell] if cell._leaf_kind == "data" else []

    if mode == "all":
        return [[l for l in iter_leaves(node) if l._leaf_kind == "data"]]

    # Grid layout: original semantics — children laid out in row-major
    # order with explicit (rows, cols) shape.
    if node._layout_kind == "grid":
        rows, cols = node._grid_rows, node._grid_cols
        children = node._children
        if mode == "col":
            return [
                [l for r in range(rows) for l in cell_leaves(children[r * cols + c])]
                for c in range(cols)
            ]
        return [
            [l for c in range(cols) for l in cell_leaves(children[r * cols + c])]
            for r in range(rows)
        ]

    # Composition layout treated as a virtual grid:
    #   share_x("col") on v-of-h → group by column index across rows.
    #   share_y("row") on h-of-v → group by row index across columns.
    # Every child must be a same-kind parent and all must agree on
    # cell count — otherwise the column/row mapping is ambiguous.
    # `_effective_children()` is the post-flatten engine view; sub-
    # layouts also expose their flat children so column indexing
    # honors `(a|b) | c` reading as one row of three.
    inner = "h" if node._layout_kind == "v" else "v"
    axis_word = "x" if mode == "col" else "y"
    outer_children = node._effective_children()
    sub_children = []
    counts = []
    for ch in outer_children:
        if ch is None or not ch._is_parent or ch._layout_kind != inner:
            what = (f"{ch._layout_kind!r} layout" if ch is not None and ch._is_parent
                    else "bare chart")
            raise ValueError(
                f"share_{axis_word}({mode!r}) on a {node._layout_kind!r} "
                f"composition requires every child to be an {inner!r} "
                f"sub-layout; found a {what}."
            )
        flat = ch._effective_children()
        sub_children.append(flat)
        counts.append(len(flat))
    if len(set(counts)) != 1:
        raise ValueError(
            f"share_{axis_word}({mode!r}): every sub-layout must have "
            f"the same number of cells; got {counts}."
        )
    n = counts[0]
    return [
        [l for sub in sub_children for l in cell_leaves(sub[i])]
        for i in range(n)
    ]
