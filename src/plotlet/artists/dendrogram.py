"""Hierarchical-clustering tree renderer.

The artist is a *tree renderer*: it consumes a `cluster.SplitTree`
(N linkage matrices + their display order) and emits the SVG. The
clustering math lives in [`cluster.py`](../cluster.py).

Three input paths, all funnel into the same SplitTree → layout → draw
pipeline:

- `data=` (+ optional `column_split=` / `row_split=`) → `cluster()` or
  `cluster_split()` builds the tree.
- `linkage=` → one-block tree wrap (skip scipy.linkage, user has Z).
- `tree=` → use a pre-built SplitTree directly (lets the same cluster
  result drive multiple charts without redoing scipy work).

When split is in play, the dendrogram exposes its final leaf order via
`axis_order`, so a peer heatmap with the same grouping vector picks up
the ComplexHeatmap-style block order automatically — artist
`axis_order` beats `frame_defaults` order in core's precedence rule.

**`labels=` indexes the ORIGINAL input order, NOT the display order.**
scipy's Z matrix uses original observation indices throughout; so
`labels[i]` must still refer to original observation `i` after the
tree reorders things. The renderer applies the scipy leaf permutation
internally — the user supplies labels aligned with `data=` (row-by-row)
and never has to reorder them. This is also what makes it safe for a
peer heatmap to share a category x/y axis by name: both artists see the
same labels (in original input order); the SplitTree's `axis_order`
hook then drives the *final* display order downstream.
"""
from __future__ import annotations

import math

from ..registry import ArtistSpec, add_artist
from .._spec import _D
from ..cluster import (layout_tree, layout_parent,
                       leaf_position, block_apex_centers, parent_leaf_px,
                       fit_parent, build_tree, tree_frame_defaults)
from ..draw import polyline
from ..draw import resolve_color


_ORIENTS = ("top", "bottom", "left", "right")


def _dendrogram_record(args, kw):
    kw = dict(kw)
    orient = kw.pop("orient", "top")
    if orient not in _ORIENTS:
        raise ValueError(
            f"dendrogram(): orient={orient!r}; expected one of {_ORIENTS}"
        )
    # Split kwarg follows the leaf axis: column_split for top/bottom
    # (leaves on x), row_split for left/right (leaves on y) — matches the
    # heatmap naming so the same grouping vector flows to both artists.
    split_key = "column_split" if orient in ("top", "bottom") else "row_split"
    split = kw.pop(split_key, None)
    kw.pop("split_gap", None)  # consumed by frame_defaults
    # `parent=` opt-in: False (default) = today's behavior; True = enable
    # with default 0.30 height fraction; float = custom fraction.
    # Silently a no-op when the tree has no `between_Z` (single block).
    parent_kw = kw.pop("parent", False)

    tree, had_labels = build_tree(args, kw, split)
    blocks, offsets, final_labels = layout_tree(tree)

    parent_block = None
    if parent_kw and tree.between_Z is not None:
        parent_frac = (_D["tree_parent_height"] if parent_kw is True
                       else float(parent_kw))
        if not (0.0 < parent_frac < 0.8):
            raise ValueError(
                f"dendrogram(): parent= must be in (0, 0.8); got {parent_frac}"
            )
        blocks, parent_block = fit_parent(
            blocks, layout_parent(tree), parent_frac,
            gap_frac=_D["tree_parent_gap"],
        )
    # No user-supplied labels = numeric leaf axis (legacy fallback);
    # `cluster` / `cluster_split` fabricate string indices in this case,
    # but the renderer keeps the unlabeled path active so `_leaf_axis_pos`
    # uses scale.idx instead of cat lookup.
    leaf_labels = final_labels if had_labels else None
    all_dc = [v for _, dc, _ in blocks for row in dc for v in row]
    if parent_block is not None:
        all_dc.extend(v for row in parent_block[1] for v in row)
    max_h = max(all_dc, default=1.0) or 1.0
    return {
        "type": "dendrogram",
        "_blocks": blocks,
        "_block_offsets": offsets,
        "_parent": parent_block,
        "_n_leaves": sum(len(lv) for _, _, lv in blocks),
        "_max_h": max_h,
        "_leaf_labels": leaf_labels,
        "orient": orient,
        "opts": kw,
    }


def _dendrogram_xdomain(a):
    if a["orient"] in ("top", "bottom"):
        if a["_leaf_labels"] is not None:
            return a["_leaf_labels"]
        return [0.0, a["_n_leaves"]]
    return [0.0, a["_max_h"]]


def _dendrogram_ydomain(a):
    if a["orient"] in ("top", "bottom"):
        return [0.0, a["_max_h"]]
    if a["_leaf_labels"] is not None:
        return a["_leaf_labels"]
    return [0.0, a["_n_leaves"]]


def _orient_xy(orient, ic, dc, max_h):
    if orient == "top":
        return ic, dc
    if orient == "bottom":
        return ic, [max_h - v for v in dc]
    if orient == "right":
        return dc, ic
    return [max_h - v for v in dc], ic  # left


def _dendrogram_draw(a, ctx):
    col = resolve_color(a["opts"].get("color")) or ctx.color or _D["dendrogram_color"]
    lw = a["opts"].get("linewidth", _D["dendrogram_linewidth"])
    orient = a["orient"]
    max_h = a["_max_h"]
    labels = a["_leaf_labels"]
    leaf_on_x = orient in ("top", "bottom")
    out = []
    # One pass over blocks (single tree = one block, so this loop also
    # covers the unsplit case). Per-block leaf indices are local to the
    # block; `offset` shifts them into the global display coordinate.
    # The gap-aware scale lookup then places them at the right pixel.
    for offset, (ic_block, dc_block, _) in zip(a["_block_offsets"], a["_blocks"]):
        for ic, dc in zip(ic_block, dc_block):
            xs, ys = _orient_xy(orient, ic, dc, max_h)
            pts = []
            ok = True
            for x, y in zip(xs, ys):
                if leaf_on_x:
                    px = leaf_position(ctx.x_scale, labels, offset + x)
                    py = ctx.y_scale(y)
                else:
                    px = ctx.x_scale(x)
                    py = leaf_position(ctx.y_scale, labels, offset + y)
                if not (math.isfinite(px) and math.isfinite(py)):
                    ok = False
                    break
                pts.append((px, py))
            if not ok:
                continue
            out.append(polyline(pts, color=col, width=lw))
    # Parent tree (optional, opt-in via `parent=True`/`parent=<frac>`):
    # leaves sit at block midpoints on the leaf axis; merges live above
    # the per-block region thanks to `_apply_parent_layout`'s dcoord
    # rescale. Same draw shape as per-block — just a different leaf-
    # position function.
    parent = a.get("_parent")
    if parent is not None:
        p_ic, p_dc, _ = parent
        midpoints = block_apex_centers(
            ctx.x_scale if leaf_on_x else ctx.y_scale,
            labels, a["_block_offsets"], a["_blocks"],
        )
        for ic, dc in zip(p_ic, p_dc):
            xs, ys = _orient_xy(orient, ic, dc, max_h)
            pts = []
            ok = True
            for x, y in zip(xs, ys):
                if leaf_on_x:
                    px = parent_leaf_px(midpoints, x)
                    py = ctx.y_scale(y)
                else:
                    px = ctx.x_scale(x)
                    py = parent_leaf_px(midpoints, y)
                if not (math.isfinite(px) and math.isfinite(py)):
                    ok = False
                    break
                pts.append((px, py))
            if not ok:
                continue
            out.append(polyline(pts, color=col, width=lw))
    return "".join(out)


def _dendrogram_frame_defaults(args, kw):
    return tree_frame_defaults(kw, split_gap_default=_D["category_split_gap"])


def _dendrogram_axis_order(a):
    if a["_leaf_labels"] is None:
        return None
    axis = "x" if a["orient"] in ("top", "bottom") else "y"
    return {axis: a["_leaf_labels"]}


def _dendrogram_data_attrs(a):
    out = {
        "orient": a["orient"],
        "n-leaves": a["_n_leaves"],
        "max-height": round(a["_max_h"], 6),
        # Concatenated scipy leaves across blocks (one block in the unsplit case).
        "leaves": [int(i) for _, _, lv in a["_blocks"] for i in lv],
    }
    if a["_leaf_labels"] is not None:
        out["leaf-labels"] = a["_leaf_labels"]
    if len(a["_blocks"]) > 1:
        out["blocks"] = len(a["_blocks"])
    return out


add_artist(ArtistSpec(
    name="dendrogram",
    record=_dendrogram_record,
    xdomain=_dendrogram_xdomain,
    ydomain=_dendrogram_ydomain,
    draw=_dendrogram_draw,
    uses_color_cycle=False,
    default_color=_D["dendrogram_color"],
    data_attrs=_dendrogram_data_attrs,
    axis_order=_dendrogram_axis_order,
    frame_defaults=_dendrogram_frame_defaults,
    tight_domain=True,
))
