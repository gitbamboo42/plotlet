"""Helpers for chart-level attachments — sub-charts placed in the host
chart's margin space, like extended axis decorations.

The public API lives on `Chart`: `attach_left/right/above/below`. This
module owns the layout-time concerns those methods imply:

  * **Size discovery** — how much extra horizontal/vertical space the
    figure needs beyond the host's own canvas to fit the attachments.
  * **Allocation** — positioning each attachment so its data area lines
    up with the host's data area on the shared axis.
  * **Joined-pair hiding** — suppressing duplicated tick / axis labels
    on each host-attachment seam (and along chained attachments).

The render engine in `_layout_engine.py` calls into here from a few
small hook points (`_iter_leaves`, `_measure`, `_allocate`, the
panel-opts pre-pass). Engine internals that this module needs
(`_allocate`, `_mark_joined_pair`) are lazy-imported inside the
functions to keep the import graph one-way: engine imports
attachments, attachments imports engine only at call time.
"""
from __future__ import annotations

from .chart import Chart
from .core import _PanelOpts


_DEFAULT_M = {"left": 0, "right": 0, "top": 0, "bottom": 0}


def _M_eff(leaf: Chart) -> dict:
    """Per-side margin for a leaf, defaulting to zeros before the
    pre-pass has run. Returns a fresh dict-shaped value so callers can
    treat the four sides uniformly."""
    return leaf._last_M_eff or _DEFAULT_M


def has_attachments(chart: Chart) -> bool:
    """True if `chart` is a host with any side attachments."""
    return bool(chart._attached_left or chart._attached_right
                or chart._attached_above or chart._attached_below)


def all_attachments(chart: Chart) -> list[Chart]:
    return (chart._attached_left + chart._attached_right
            + chart._attached_above + chart._attached_below)


def _gap(c: Chart) -> float:
    """Per-attachment gap to inward neighbor (host or previous attachment).
    Returns 0 for unattached charts (defensive — placement only iterates
    over already-attached lists)."""
    return getattr(c, "_attachment_gap", 0.0)


def attached_size_h(host: Chart) -> tuple[float, float]:
    """Extra horizontal space the figure needs beyond `host`'s own canvas
    to fit left/right attachments AND any perpendicular-margin overflow
    from above/below attachments. Left/right attachments occupy the
    host's collapsed left/right margin first (their innermost right edge
    sits at the host's data-area left edge minus its `gap`), so they
    only grow the figure once cumulative width-plus-gaps exceeds it.
    Above/below attachments keep their own left/right margins; if a top
    track's left margin exceeds the host's, its labels need extra figure
    space unless a left attachment already provides it.
    Returns (left_extra, right_extra)."""
    M = _M_eff(host)
    sum_left  = sum(c._canvas_width + _gap(c) for c in host._attached_left)
    sum_right = sum(c._canvas_width + _gap(c) for c in host._attached_right)
    stack = host._attached_above + host._attached_below
    max_left_overflow  = max((_M_eff(c)["left"]  - M["left"]
                              for c in stack), default=0.0)
    max_right_overflow = max((_M_eff(c)["right"] - M["right"]
                              for c in stack), default=0.0)
    return (max(sum_left  - M["left"],  max_left_overflow,  0.0),
            max(sum_right - M["right"], max_right_overflow, 0.0))


def attached_size_v(host: Chart) -> tuple[float, float]:
    """Extra vertical space beyond `host`'s canvas needed for above/below
    attachments AND for left/right attachments whose own top/bottom
    margins overflow the host's. Returns (above_extra, below_extra)."""
    M = _M_eff(host)
    sum_above = sum(c._canvas_height + _gap(c) for c in host._attached_above)
    sum_below = sum(c._canvas_height + _gap(c) for c in host._attached_below)
    side = host._attached_left + host._attached_right
    max_top_overflow    = max((_M_eff(c)["top"]    - M["top"]
                               for c in side), default=0.0)
    max_bottom_overflow = max((_M_eff(c)["bottom"] - M["bottom"]
                               for c in side), default=0.0)
    return (max(sum_above - M["top"],    max_top_overflow,    0.0),
            max(sum_below - M["bottom"], max_bottom_overflow, 0.0))


def allocate(host: Chart, host_x: float, host_y: float,
             host_w: float, host_h: float, out: list) -> None:
    """Place each attachment so its DATA area aligns with the host's data
    area on the shared axis; the attachment's own margins are independent
    and do not push the host's margins out. Canvases may extend beyond
    the host's canvas on the perpendicular axis — those overflows visually
    sit in the left/right attachment columns (above/below) or top/bottom
    rows (left/right), at a different position on the other axis, so they
    don't visually collide with sibling attachments' content."""
    from ._layout_engine import _allocate

    host_M = _M_eff(host)
    host_data_x = host_x + host_M["left"]
    host_data_y = host_y + host_M["top"]

    # Each side places the attachment so its DATA area edge is flush against
    # the host's data area edge. The attachment's inner-facing margin floor
    # (cM["right"] for left, cM["bottom"] for above, etc.) overlaps into the
    # host's collapsed inner margin floor — both are blank floor regions,
    # so no visible collision; this matches the symmetric right/below path.

    # Each side advances a cursor inward-to-outward. The cursor holds the
    # next "data edge to align to" — initially the host's data edge, then
    # each placed attachment's outward data edge. Per-attachment `gap` is
    # applied by stepping the cursor outward by `gap` BEFORE placing
    # (zero gap → flush join; positive gap → visible separation).

    # Left: walk outward (decreasing x). Data y/h locks to host (share_y);
    # canvas y is offset so the attachment's data area starts at host_data_y.
    cx_right = host_x + host_M["left"]
    for c in host._attached_left:
        cx_right -= _gap(c)
        cM = _M_eff(c)
        cw = c._data_width + cM["left"] + cM["right"]
        ch = c._data_height + cM["top"] + cM["bottom"]
        c_canvas_x = cx_right - cM["left"] - c._data_width
        c_canvas_y = host_data_y - cM["top"]
        _allocate(c, c_canvas_x, c_canvas_y, cw, ch, out)
        cx_right = c_canvas_x + cM["left"]   # c's data-left becomes next reference
    # Right: walk outward (increasing x).
    cx_left = host_x + host_w - host_M["right"]
    for c in host._attached_right:
        cx_left += _gap(c)
        cM = _M_eff(c)
        cw = c._data_width + cM["left"] + cM["right"]
        ch = c._data_height + cM["top"] + cM["bottom"]
        c_canvas_x = cx_left - cM["left"]
        c_canvas_y = host_data_y - cM["top"]
        _allocate(c, c_canvas_x, c_canvas_y, cw, ch, out)
        cx_left = c_canvas_x + cM["left"] + c._data_width   # c's data-right
    # Above: walk outward (decreasing y). Data x/w locks to host (share_x).
    cy_bottom = host_y + host_M["top"]
    for c in host._attached_above:
        cy_bottom -= _gap(c)
        cM = _M_eff(c)
        cw = c._data_width + cM["left"] + cM["right"]
        ch = c._data_height + cM["top"] + cM["bottom"]
        c_canvas_x = host_data_x - cM["left"]
        c_canvas_y = cy_bottom - cM["top"] - c._data_height
        _allocate(c, c_canvas_x, c_canvas_y, cw, ch, out)
        cy_bottom = c_canvas_y + cM["top"]   # c's data-top
    # Below: walk outward (increasing y).
    cy_top = host_y + host_h - host_M["bottom"]
    for c in host._attached_below:
        cy_top += _gap(c)
        cM = _M_eff(c)
        cw = c._data_width + cM["left"] + cM["right"]
        ch = c._data_height + cM["top"] + cM["bottom"]
        c_canvas_x = host_data_x - cM["left"]
        c_canvas_y = cy_top - cM["top"]
        _allocate(c, c_canvas_x, c_canvas_y, cw, ch, out)
        cy_top = c_canvas_y + cM["top"] + c._data_height   # c's data-bottom


def annotate_joined_pairs(leaves: list[Chart],
                          panel_opts: dict[int, _PanelOpts]) -> None:
    """For each host with attachments, mark the inner-facing edge of each
    host-attachment pair (and each adjacent pair along a chain of
    same-side attachments) as a joined-pair side — duplicated tick
    labels and axis labels suppress on the host-facing edge. Reuses
    `_layout_engine._mark_joined_pair`; the share auto-wired by
    `attach_*` satisfies its share-equivalence precondition. The
    per-leaf `_share_hide_labels_*` flag (set when an attachment opts
    out via `hide_labels=False`) lets either side cancel the
    suppression."""
    from ._layout_engine import _mark_joined_pair

    for host in leaves:
        if not has_attachments(host):
            continue
        if host._attached_left:
            _mark_joined_pair(host._attached_left[0], host,
                              axis="h", out=panel_opts)
        if host._attached_right:
            _mark_joined_pair(host, host._attached_right[0],
                              axis="h", out=panel_opts)
        if host._attached_above:
            _mark_joined_pair(host._attached_above[0], host,
                              axis="v", out=panel_opts)
        if host._attached_below:
            _mark_joined_pair(host, host._attached_below[0],
                              axis="v", out=panel_opts)
        # Chained attachments on the same side: each adjacent pair is a
        # joint. Index 0 is innermost; higher indices extend outward.
        for chain, axis, outward in (
            (host._attached_left,  "h", "left"),
            (host._attached_right, "h", "right"),
            (host._attached_above, "v", "above"),
            (host._attached_below, "v", "below"),
        ):
            for i in range(len(chain) - 1):
                inner, outer = chain[i], chain[i + 1]
                if outward in ("left", "above"):
                    _mark_joined_pair(outer, inner, axis=axis, out=panel_opts)
                else:
                    _mark_joined_pair(inner, outer, axis=axis, out=panel_opts)


def promote_titles(leaves: list[Chart], states: dict[int, dict]) -> None:
    """`c.title("...")` is a figure-title gesture: it should render above
    everything stacked on top of `c`, not buried inside `c`'s own title
    margin under the attached panels. When `c` has `_attached_above` and
    sets a title, move the title's render state to the outermost
    attached_above chart so the layout reserves margin in the right
    panel. The host's own state has the title cleared so the renderer
    doesn't draw it twice.

    Only the top side is promoted — title is conventionally above the
    data. xlabel/ylabel are not symmetric concepts (axis labels belong
    to the axis they describe, not to the figure), so they stay put.
    """
    for leaf in leaves:
        if not leaf._attached_above:
            continue
        host_st = states.get(id(leaf))
        if host_st is None or not host_st.get("title"):
            continue
        # Index 0 = innermost, last = outermost — title goes to the very top.
        outermost = leaf._attached_above[-1]
        outer_st = states.get(id(outermost))
        if outer_st is None:
            continue
        outer_st["title"] = host_st["title"]
        host_st["title"] = ""
