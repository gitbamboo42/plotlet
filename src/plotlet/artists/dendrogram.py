"""Hierarchical-clustering tree renderer.

The artist is a *tree renderer*: it consumes a `cluster.SplitTree`
(N linkage matrices + their display order) and emits the SVG. The
clustering math lives in [`cluster.py`](../cluster.py).

Three input paths, all funnel into the same SplitTree → layout → draw
pipeline:

- `data=` (+ optional `clusters=` for two-level clustering) →
  `linkage()` or `linkage_split()` builds the tree.
- `linkage_matrix=` → one-block tree wrap (user already has a raw scipy Z).
- `tree=` → use a pre-built SplitTree directly (lets the same cluster
  result drive multiple charts without redoing scipy work).

`clusters=` is a parallel list of group labels (one per row of `data`,
aligned with `labels=`) — it drives the two-level cluster (per-block
linkage + per-centroid linkage). The visual gap whitespace between
blocks is a separate concern: declare `c.sectors({cluster: [members]},
axis=...)` on the panel for that — the dendrogram and any peer heatmap
on the same shared scale pick up the gaps automatically.

When clusters are in play, the dendrogram exposes its final leaf order
via `axis_order`, so a peer heatmap with the same grouping vector picks
up the two-level block order automatically — artist `axis_order` beats
`frame_defaults` order in core's precedence rule.

`palette=` (a `{group: color}` map) colors each block's branches by its
group, leaving the between-cluster trunk neutral — driven off the same
two-level block structure. Needs `clusters=` (or a `tree=` from
`linkage_split`).

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
from ..utils import pack_opts
from .._spec import _D
from ..cluster import (layout_tree, layout_parent,
                       leaf_position, block_apex_centers, parent_leaf_px,
                       fit_parent, build_tree, tree_frame_defaults)
from ..draw import polyline
from ..draw import resolve_color


_ORIENTS = ("top", "bottom", "left", "right")


def _dendrogram_record(data=None,
                       # tree input — consumed by `build_tree`
                       tree=None, linkage_matrix=None,
                       method="single", metric="euclidean", labels=None,
                       # layout
                       clusters=None, parent=False, orientation="top",
                       # style — packed into opts for the draw side
                       color=None, palette=None,
                       linewidth=None, label=None, legend=None):
    if orientation not in _ORIENTS:
        raise ValueError(
            f"dendrogram(): orientation={orientation!r}; "
            f"expected one of {_ORIENTS}"
        )
    # ``clusters=`` is the parallel list (label-per-row) that drives
    # two-level clustering. The visual gap whitespace between blocks
    # lives on the panel as ``c.sectors(...)`` — not duplicated here.
    #
    # `parent=` opt-in: False (default) = today's behavior; True = enable
    # with default 0.30 height fraction; float = custom fraction.
    # Silently a no-op when the tree has no `between_Z` (single block).
    tree_obj, had_labels = build_tree(data, clusters, tree=tree,
                                      linkage_matrix=linkage_matrix,
                                      method=method, metric=metric,
                                      labels=labels)
    blocks, offsets, final_labels = layout_tree(tree_obj)

    parent_block = None
    if parent and tree_obj.between_Z is not None:
        parent_frac = (_D["tree_parent_height"] if parent is True
                       else float(parent))
        if not (0.0 < parent_frac < 0.8):
            raise ValueError(
                f"dendrogram(): parent= must be in (0, 0.8); got {parent_frac}"
            )
        blocks, parent_block = fit_parent(
            blocks, layout_parent(tree_obj), parent_frac,
            gap_frac=_D["tree_parent_gap"],
        )
    # No user-supplied labels = numeric leaf axis. `linkage` /
    # `linkage_split` fabricate string indices in this case, but the
    # renderer keeps the unlabeled path active so `_leaf_axis_pos` uses
    # scale.idx instead of cat lookup.
    leaf_labels = final_labels if had_labels else None
    # Per-group branch color: `palette` maps a cluster/group label to a
    # color. Each block's branches take its group's color; blocks whose
    # group isn't in the palette (and the between-cluster "trunk") stay
    # the neutral `color`. Needs a two-level tree — `clusters=` (or a
    # `tree=` from `linkage_split`) carries the per-block group labels.
    block_colors = None
    if palette is not None:
        if tree_obj.block_groups is None:
            raise ValueError(
                "dendrogram(): palette= colors branches by group, which "
                "needs a two-level tree — pass clusters= (or a tree= built "
                "with linkage_split)."
            )
        # `blocks` is in display order (between_order); map each back to
        # its group label, then to a palette color (None = keep neutral).
        block_colors = [palette.get(tree_obj.block_groups[b])
                        for b in tree_obj.between_order]
    all_dc = [v for _, dc, _ in blocks for row in dc for v in row]
    if parent_block is not None:
        all_dc.extend(v for row in parent_block[1] for v in row)
    max_h = max(all_dc, default=1.0) or 1.0
    return {
        "type": "dendrogram",
        "_blocks": blocks,
        "_block_offsets": offsets,
        "_block_colors": block_colors,
        "_parent": parent_block,
        "_n_leaves": sum(len(lv) for _, _, lv in blocks),
        "_max_h": max_h,
        "_leaf_labels": leaf_labels,
        "orientation": orientation,
        "opts": pack_opts(color=color, linewidth=linewidth,
                          label=label, legend=legend),
    }


def _dendrogram_xdomain(a):
    if a["orientation"] in ("top", "bottom"):
        if a["_leaf_labels"] is not None:
            return a["_leaf_labels"]
        return [0.0, a["_n_leaves"]]
    return [0.0, a["_max_h"]]


def _dendrogram_ydomain(a):
    if a["orientation"] in ("top", "bottom"):
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
    orient = a["orientation"]
    max_h = a["_max_h"]
    labels = a["_leaf_labels"]
    leaf_on_x = orient in ("top", "bottom")
    # Per-group colors (display order), aligned with `_blocks`. `None`
    # entry (or no palette) → the neutral `col` for that block.
    block_colors = a.get("_block_colors")
    out = []
    # One pass over blocks (single tree = one block, so this loop also
    # covers the unsplit case). Per-block leaf indices are local to the
    # block; `offset` shifts them into the global display coordinate.
    # The gap-aware scale lookup then places them at the right pixel.
    for bi, (offset, (ic_block, dc_block, _)) in enumerate(
            zip(a["_block_offsets"], a["_blocks"])):
        bcol = col
        if block_colors is not None:
            bcol = resolve_color(block_colors[bi]) or col
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
            out.append(polyline(pts, color=bcol, width=lw, project=ctx.warp))
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
            out.append(polyline(pts, color=col, width=lw, project=ctx.warp))
    return "".join(out)


def _dendrogram_frame_defaults(args, kw):
    return tree_frame_defaults(kw)


def _dendrogram_axis_order(a):
    if a["_leaf_labels"] is None:
        return None
    axis = "x" if a["orientation"] in ("top", "bottom") else "y"
    return {axis: a["_leaf_labels"]}


def _dendrogram_data_attrs(a):
    out = {
        "orientation": a["orientation"],
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
    accepts_data_positional=False,
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
    # Between-cluster joins (parent=True) span sector boundaries;
    # within-block trees don't, but the inter-block gap whitespace
    # already shows the partition — walls just add visual noise.
    crosses_sectors=True,
))
