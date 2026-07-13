"""Custom artist: dendrogram with curved (Bezier) branches.

Same data contract and cluster-aware behavior as the built-in
`c.dendrogram(...)`, but each merge is rendered as a cubic Bezier
between its two children instead of the orthogonal upside-down-U.
Visual flourish — no algorithmic difference.

Lives in extensions to demonstrate that an alternative tree renderer
can be built using only the public clustering API
(`pt.linkage_split` / `pt.cluster.layout_tree` / `pt.add_artist`) —
no private symbols, no plotlet-core changes.

API mirrors `dendrogram`:

    c.curved_tree(data, labels=..., orientation="top",
                  clusters=groups, method="ward")

`clusters=` is the parallel grouping vector that drives the two-level
cluster (per-group within + centroid between); the resulting leaf order
is exposed via `axis_order` so a peer heatmap follows automatically. The
visual gap whitespace between blocks lives on the panel as
`c.sectors(...)` — declare it once and any peer category-scale artist
inherits the gaps.
"""
SUMMARY = "Dendrogram variant rendering each merge as a cubic Bezier curve."
import math

import plotlet as pt
from plotlet.cluster import (layout_tree, layout_parent, leaf_position,
                             block_apex_centers, parent_leaf_px, fit_parent,
                             build_tree, tree_frame_defaults)
from plotlet.registry import ArtistSpec, add_artist
from ..draw import coord, stroke_w



_ORIENTS = ("top", "bottom", "left", "right")
_DEFAULTS = pt.SPEC["defaults"]   # public path to spec defaults


def _curved_record(args, kw):
    kw = dict(kw)
    orient = kw.pop("orientation", "top")
    if orient not in _ORIENTS:
        raise ValueError(
            f"curved_tree(): orientation={orient!r}; expected one of {_ORIENTS}"
        )
    leaf_on_x = orient in ("top", "bottom")
    split = kw.pop("clusters", None)
    parent_kw = kw.pop("parent", False)

    tree, had_labels = build_tree(args, kw, split)
    blocks, offsets, final_labels = layout_tree(tree)
    parent_block = None
    if parent_kw and tree.between_Z is not None:
        parent_frac = (_DEFAULTS["tree_parent_height"] if parent_kw is True
                       else float(parent_kw))
        if not (0.0 < parent_frac < 0.8):
            raise ValueError(
                f"curved_tree(): parent= must be in (0, 0.8); got {parent_frac}"
            )
        blocks, parent_block = fit_parent(
            blocks, layout_parent(tree), parent_frac,
            gap_frac=_DEFAULTS["tree_parent_gap"],
        )
    all_dc = [v for _, dc, _ in blocks for row in dc for v in row]
    if parent_block is not None:
        all_dc.extend(v for row in parent_block[1] for v in row)
    max_h = max(all_dc, default=1.0) or 1.0
    return {
        "type": "curved_tree",
        "_blocks": blocks,
        "_offsets": offsets,
        "_parent": parent_block,
        "_n_leaves": sum(len(lv) for _, _, lv in blocks),
        "_max_h": max_h,
        "_leaf_labels": final_labels if had_labels else None,
        "orientation": orient,
        "opts": kw,
    }


def _curved_xdomain(a):
    if a["orientation"] in ("top", "bottom"):
        return (a["_leaf_labels"] if a["_leaf_labels"] is not None
                else [0.0, a["_n_leaves"]])
    return [0.0, a["_max_h"]]


def _curved_ydomain(a):
    if a["orientation"] in ("top", "bottom"):
        return [0.0, a["_max_h"]]
    return (a["_leaf_labels"] if a["_leaf_labels"] is not None
            else [0.0, a["_n_leaves"]])


def _orient_xy(orient, ic, dc, max_h):
    if orient == "top":    return ic, dc
    if orient == "bottom": return ic, [max_h - v for v in dc]
    if orient == "right":  return dc, ic
    return [max_h - v for v in dc], ic   # left


def _bezier_path(x_l, x_r, y_l, y_r, y_t, color, width, leaf_on_x):
    """Single cubic Bezier between (x_l, y_l) and (x_r, y_r), with
    control points pulled toward the merge apex `y_t` (or `x_t` when
    leaves are on y) — produces an organic curve instead of an
    upside-down-U.
    """
    if leaf_on_x:
        d = (f"M{coord(x_l)},{coord(y_l)} "
             f"C{coord(x_l)},{coord(y_t)} {coord(x_r)},{coord(y_t)} "
             f"{coord(x_r)},{coord(y_r)}")
    else:
        d = (f"M{coord(x_l)},{coord(y_l)} "
             f"C{coord(y_t)},{coord(y_l)} {coord(y_t)},{coord(y_r)} "
             f"{coord(x_r)},{coord(y_r)}")
    return (f'<path d="{d}" stroke="{color}" '
            f'stroke-width="{stroke_w(width)}" fill="none"/>')


def _curved_draw(a, ctx):
    color = a["opts"].get("color", "#3a1a8a")
    width = a["opts"].get("linewidth", 1.4)
    orient = a["orientation"]
    max_h = a["_max_h"]
    labels = a["_leaf_labels"]
    leaf_on_x = orient in ("top", "bottom")
    out = []
    # Per-block trees: 4-point U-shape -> one cubic Bezier.
    for offset, (ic_block, dc_block, _) in zip(a["_offsets"], a["_blocks"]):
        for ic, dc in zip(ic_block, dc_block):
            xs, ys = _orient_xy(orient, ic, dc, max_h)
            if leaf_on_x:
                x_l = leaf_position(ctx.x_scale, labels, offset + xs[0])
                x_r = leaf_position(ctx.x_scale, labels, offset + xs[3])
                y_l = ctx.y_scale(ys[0])
                y_r = ctx.y_scale(ys[3])
                y_t = ctx.y_scale(ys[1])
                out.append(_bezier_path(x_l, x_r, y_l, y_r, y_t, color, width, True))
            else:
                y_l = leaf_position(ctx.y_scale, labels, offset + ys[0])
                y_r = leaf_position(ctx.y_scale, labels, offset + ys[3])
                x_l = ctx.x_scale(xs[0])
                x_r = ctx.x_scale(xs[3])
                x_t = ctx.x_scale(xs[1])
                out.append(_bezier_path(x_l, x_r, y_l, y_r, x_t, color, width, False))
    # Parent tree (optional): same curve recipe, but leaves sit at
    # block midpoints on the leaf axis.
    parent = a.get("_parent")
    if parent is not None:
        p_ic, p_dc, _ = parent
        midpoints = block_apex_centers(
            ctx.x_scale if leaf_on_x else ctx.y_scale,
            labels, a["_offsets"], a["_blocks"],
        )
        for ic, dc in zip(p_ic, p_dc):
            xs, ys = _orient_xy(orient, ic, dc, max_h)
            if leaf_on_x:
                x_l = parent_leaf_px(midpoints, xs[0])
                x_r = parent_leaf_px(midpoints, xs[3])
                y_l = ctx.y_scale(ys[0])
                y_r = ctx.y_scale(ys[3])
                y_t = ctx.y_scale(ys[1])
                out.append(_bezier_path(x_l, x_r, y_l, y_r, y_t, color, width, True))
            else:
                y_l = parent_leaf_px(midpoints, ys[0])
                y_r = parent_leaf_px(midpoints, ys[3])
                x_l = ctx.x_scale(xs[0])
                x_r = ctx.x_scale(xs[3])
                x_t = ctx.x_scale(xs[1])
                out.append(_bezier_path(x_l, x_r, y_l, y_r, x_t, color, width, False))
    return "".join(out)


def _curved_axis_order(a):
    if a["_leaf_labels"] is None:
        return None
    axis = "x" if a["orientation"] in ("top", "bottom") else "y"
    return {axis: a["_leaf_labels"]}


def _curved_frame_defaults(args, kw):
    return tree_frame_defaults(kw)


add_artist(ArtistSpec(
    name="curved_tree",
    accepts_data_positional=False,
    record=_curved_record,
    xdomain=_curved_xdomain,
    ydomain=_curved_ydomain,
    draw=_curved_draw,
    uses_color_cycle=False,
    axis_order=_curved_axis_order,
    frame_defaults=_curved_frame_defaults,
    tight_domain=True,
))


def demo():
    """Curved-tree variant of the split-heatmap recipe: per-group
    within-cluster + between-group centroid cluster, with each merge
    rendered as a cubic Bezier. Heatmap below picks up the leaf order
    via the standard `axis_order` precedence."""
    import random
    rng = random.Random(7)
    nrows_hm, ncols_hm = 6, 12
    col_labels = [f"c{i+1}" for i in range(ncols_hm)]
    col_groups = ["X", "Y", "Z", "X", "Y", "Z", "Y", "Z",
                  "X", "Y", "Z", "Y"]
    sig = {"X": 0.0, "Y": 5.0, "Z": 10.0}
    matrix = [[sig[col_groups[c]] + rng.gauss(0, 0.3)
               for c in range(ncols_hm)]
              for _ in range(nrows_hm)]
    data_t = [[matrix[r][c] for r in range(nrows_hm)]
              for c in range(ncols_hm)]

    col_clusters = {}
    for c, g in zip(col_labels, col_groups):
        col_clusters.setdefault(g, []).append(c)

    tree = pt.chart(data_height=60)
    tree.curved_tree(data_t, labels=col_labels,
                     clusters=col_groups, method="ward")

    hm = pt.chart(title="curved-tree-driven split heatmap",
                  data_width=420, data_height=180)
    hm.sectors(col_clusters, axis="x", divider=False, label=False)
    row_labels = [f"r{i+1}" for i in range(nrows_hm)]
    hm_df = {"col": col_labels}
    for i, name in enumerate(row_labels):
        hm_df[name] = matrix[i]
    hm.heatmap(data=hm_df, x="col", values=row_labels,
               cmap="viridis", legend={"label": "value"})
    hm.attach_above(tree)
    return pt.grid([[hm, pt.legend()]]).gap(0)
