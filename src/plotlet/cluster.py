"""Hierarchical-clustering helpers.

These build a `SplitTree` — N scipy linkage matrices plus the order to
display them in. The dendrogram artist renders it and drives the shared
category scale's order (`axis_order`), so a heatmap on the same panel
picks up the clustered row/column order automatically.

Two entry points:

- `linkage(data, labels, ...)` — one observation set, one linkage.
- `linkage_split(data, split, labels, ...)` — two-level cluster: per-
  group linkage for within-block leaf order, plus a centroid linkage to
  pick the between-group order. Equivalent to calling `linkage` per
  group and reordering the groups by similarity.

Both return a `SplitTree`. Single-cluster trees are just multi-block
trees with one block — so the dendrogram artist (and anything else
consuming the tree) doesn't need a split / no-split branch.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from scipy.cluster.hierarchy import linkage as _scipy_linkage
from scipy.cluster.hierarchy import dendrogram as _scipy_dendrogram

from . import _splits


@dataclass
class SplitTree:
    """Per-block linkages + the order to display them.

    - `blocks[i] = (Z, labels)`: scipy linkage Z for block i, plus the
      observation labels in that block (in within-block input order).
      `Z` is `None` for a single-observation block (no merges).
    - `between_order`: indices into `blocks`; the order blocks render
      left-to-right (or top-to-bottom for orientation=left/right).
    - `between_Z`: the linkage matrix computed on per-block centroids,
      whose leaves are `between_order`. Renderers can draw it as a
      "parent tree" above the per-block trees. `None` for single-block
      trees (no between-cluster needed). Off by default in the
      dendrogram artist — opt in via `parent=True`/`parent=<frac>`.
    - `block_groups`: the group label each block came from, in block
      order (aligned with `blocks`). Set only by `linkage_split` (the
      two-level path); `None` for single-cluster trees. Lets a renderer
      color each block's branches by its group — see the dendrogram
      artist's `palette=`.
    """
    blocks: list = field(default_factory=list)
    between_order: list = field(default_factory=list)
    between_Z: object = None
    block_groups: list = None

    @property
    def n_blocks(self):
        return len(self.blocks)


def _centroid(rows):
    n = len(rows)
    d = len(rows[0])
    return [sum(r[c] for r in rows) / n for c in range(d)]


def linkage(data, labels=None, method="single", metric="euclidean") -> SplitTree:
    """Single linkage on `data`. Returns a one-block `SplitTree`."""
    if hasattr(data, "tolist"):
        data = data.tolist()
    if len(data) < 2:
        raise ValueError(
            f"linkage(): need at least 2 observations, got {len(data)}"
        )
    labs = (list(labels) if labels is not None
            else [str(i) for i in range(len(data))])
    if len(labs) != len(data):
        raise ValueError(
            f"linkage(): labels has {len(labs)} entries but data has "
            f"{len(data)} observations"
        )
    Z = _scipy_linkage(data, method=method, metric=metric)
    return SplitTree(blocks=[(Z, labs)], between_order=[0])


def linkage_split(data, split, labels=None,
                  method="single", metric="euclidean") -> SplitTree:
    """Two-level cluster: within-group + between-group centroid order.

    Within each group: scipy linkage on the group's observations →
    block tree + leaf order within block. Between groups: scipy linkage
    on the per-group centroids → order of the groups themselves on the
    display axis.

    Single-observation groups skip the within-block linkage (`Z=None`);
    a single group skips the between-block linkage. Returns a
    `SplitTree` with `n_blocks == n_unique_groups_in_first_seen_order`.
    """
    if hasattr(data, "tolist"):
        data = data.tolist()
    if len(split) != len(data):
        raise ValueError(
            f"linkage_split(): split length ({len(split)}) doesn't "
            f"match data length ({len(data)})"
        )
    labs = (list(labels) if labels is not None
            else [str(i) for i in range(len(data))])
    if len(labs) != len(data):
        raise ValueError(
            f"linkage_split(): labels has {len(labs)} entries but data "
            f"has {len(data)} observations"
        )

    # Group + partition (first-seen). The between-cluster pass below
    # picks the *display* order; this step just collects each group's
    # observations together so we can run scipy on each.
    perm, bounds = _splits.group_order(split)
    # Group label per block, in first-seen (block) order — so a renderer
    # can color each block by its group. Mirrors `group_order`'s ordering.
    block_groups = list(dict.fromkeys(split))
    data_c = _splits.permute(data, perm)
    labs_c = _splits.permute(labs, perm)
    block_data = _splits.partition(data_c, bounds)
    block_labs = _splits.partition(labs_c, bounds)

    block_Zs = []
    for blk in block_data:
        if len(blk) < 2:
            block_Zs.append(None)
        else:
            block_Zs.append(_scipy_linkage(blk, method=method, metric=metric))

    if len(block_data) >= 2:
        centroids = [_centroid(blk) for blk in block_data]
        Z_between = _scipy_linkage(centroids, method=method, metric=metric)
        between_order = [int(v) for v in
                         _scipy_dendrogram(Z_between, no_plot=True)["leaves"]]
    else:
        Z_between = None
        between_order = [0]

    return SplitTree(blocks=list(zip(block_Zs, block_labs)),
                     between_order=between_order,
                     between_Z=Z_between,
                     block_groups=block_groups)


# ---------------------------------------------------------------------------
# Layout helpers — turn a SplitTree into drawable coords. Useful for any
# tree renderer (dendrogram, fancy variants in extensions): a
# custom artist can `pt.cluster.layout_tree(tree)` and skip reimplementing
# the scipy.dendrogram call + per-block walk.
# ---------------------------------------------------------------------------

def layout(Z):
    """scipy.dendrogram → raw `(icoord, dcoord, scipy_leaves)` from a Z.

    icoord values are rescaled so leaf endpoints land at integer
    category positions 0..n-1 (matching a category scale's band
    centers). dcoord is raw scipy merge heights — caller decides
    whether to normalise (see `layout_tree`, which pools across blocks).
    `scipy_leaves` is the leaf permutation: `leaves[k]` is the
    original-data index of the k-th leaf from left.
    """
    info = _scipy_dendrogram(Z, no_plot=True)
    icoord = [[(float(v) - 5.0) / 10.0 for v in row] for row in info["icoord"]]
    dcoord = [[float(v) for v in row] for row in info["dcoord"]]
    leaves = [int(v) for v in info["leaves"]]
    return icoord, dcoord, leaves


def _normalize_heights(dcoord_blocks):
    """Rescale non-zero merge heights across *all* blocks to a shared
    range — so per-block trees stay comparable when drawn against one
    y axis. Zero entries stay zero (leaf endpoints).
    """
    all_nz = [v for dc in dcoord_blocks for row in dc for v in row if v != 0.0]
    if not all_nz:
        return [list(dc) for dc in dcoord_blocks]
    y_min, y_max = min(all_nz), max(all_nz)
    interval = y_max - y_min
    if interval == 0.0:
        return [list(dc) for dc in dcoord_blocks]
    return [
        [[((v - y_min) / interval + 0.2) if v != 0.0 else 0.0 for v in row]
         for row in dc]
        for dc in dcoord_blocks
    ]


def layout_tree(tree):
    """`SplitTree` → drawable `(blocks, offsets, final_labels)`.

    - `blocks[i] = (icoord, dcoord, scipy_leaves)`: per-block coords in
      *display* order. `icoord` values are leaf-axis positions in
      `[0, n_block - 1]`; merge dcoord values share a pooled-normalised
      y range across all blocks.
    - `offsets[i]`: leaf-position offset where block `i` starts in the
      concatenated display. A renderer adds it to the block's `icoord`
      values to get the global leaf position.
    - `final_labels`: every leaf label in final display order
      (between-cluster × within-cluster). Suitable as an `axis_order`
      hint for a category scale.

    Singleton-leaf blocks (`Z is None`) produce empty `(icoord,
    dcoord)` and a one-element `scipy_leaves=[0]` — the renderer can
    skip them or draw a stub.
    """
    raw = [(([], [], [0]) if Z is None else layout(Z))
           for Z, _ in tree.blocks]
    blocks, offsets, final_labels = [], [], []
    offset = 0
    for b in tree.between_order:
        ic, dc, lv = raw[b]
        _, block_labs = tree.blocks[b]
        offsets.append(offset)
        for leaf_idx in lv:
            final_labels.append(str(block_labs[leaf_idx]))
        blocks.append((ic, dc, lv))
        offset += len(lv)
    normed = _normalize_heights([dc for _, dc, _ in blocks])
    blocks = [(ic, dc_n, lv) for (ic, _, lv), dc_n in zip(blocks, normed)]
    return blocks, offsets, final_labels


def layout_parent(tree):
    """Layout for the between-block (parent / centroid) tree.

    Returns `(icoord, dcoord, leaves)` from scipy.dendrogram on
    `tree.between_Z`, or `None` if the tree has no parent (single block
    or constructed without a between_Z). `dcoord` is normalized to the
    same `[0, ~1.2]` range as `layout_tree` so a tree renderer can drop
    both into one panel without re-normalizing.

    `leaves` matches `tree.between_order` (same scipy call).
    """
    if tree.between_Z is None:
        return None
    ic, dc, lv = layout(tree.between_Z)
    return ic, _normalize_heights([dc])[0], lv


# ---------------------------------------------------------------------------
# Leaf-axis positioning — pixel lookup for a leaf at float position `disp`.
# Lives here (not the dendrogram artist) so any tree renderer in
# extensions can call it without reaching into private modules.
# ---------------------------------------------------------------------------

def leaf_position(scale, labels, disp):
    """Float leaf-position -> pixel x (or y, on a y-leaf scale).

    Categorical path (labels supplied): integer `disp` looks up via
    `scale(labels[disp])` — gap-aware on a split scale. Fractional
    `disp` interpolates with `scale.step` (only safe within one block,
    since scale.step doesn't include split gaps; scipy.dendrogram only
    emits fractional midpoints between siblings, which are always in
    the same block).

    Numeric path (labels=None): each leaf sits in cell `[i, i+1]` in
    axis units, centred at `i + 0.5`.
    """
    if labels is None:
        return scale(disp + 0.5)
    n = len(labels)
    lo = int(math.floor(disp))
    if disp == lo and 0 <= lo < n:
        return scale(labels[lo])
    lo = max(0, min(n - 2, lo))
    return scale(labels[lo]) + (disp - lo) * scale.step


def block_apex_centers(scale, labels, offsets, blocks):
    """Pixel center of each block's apex (topmost merge's horizontal bar).

    Parent-tree renderers use this so each parent leaf lands directly
    above the bar of the merge it sits above — not above the geometric
    midpoint of the block's leaf range. For an asymmetric per-block
    tree the two differ, and visually the apex-bar center is what reads
    as "connected to the tree below." Single-leaf blocks (no merges)
    fall back to the leaf's position.
    """
    out = []
    for b, (ic, dc, lv) in enumerate(blocks):
        if not ic:  # single-leaf block — no merges, no apex bar
            out.append(leaf_position(scale, labels, offsets[b]))
            continue
        # Pick the row with the highest merge top (dc[i][1] is the top
        # of the i-th U). icoord row is [x_l, x_l, x_r, x_r]; the
        # horizontal top bar runs from x_l to x_r.
        top_idx = max(range(len(dc)), key=lambda i: dc[i][1])
        top_ic = ic[top_idx]
        center_local = (top_ic[0] + top_ic[3]) / 2
        out.append(leaf_position(scale, labels, offsets[b] + center_local))
    return out


def parent_leaf_px(midpoints, x):
    """Pixel for a parent-tree x value in `[0, n_blocks - 1]`.

    Integer `x` returns `midpoints[x]` exactly; fractional `x`
    (scipy.dendrogram emits midpoints between sibling parent-leaves)
    interpolates linearly between two adjacent block midpoints.
    """
    n = len(midpoints)
    lo = int(math.floor(x))
    if x == lo and 0 <= lo < n:
        return midpoints[lo]
    lo = max(0, min(n - 2, lo))
    return midpoints[lo] + (x - lo) * (midpoints[lo + 1] - midpoints[lo])


# Used as a fixed reference for the upper end of `_normalize_heights`'s
# output range. Tree renderers use this to size the parent tree region.
HEIGHT_NORM_MAX = 1.2


def fit_parent(blocks, parent_layout, parent_frac, gap_frac=0.10):
    """Place per-block trees + parent tree in one panel.

    Shrinks per-block dcoords to the bottom `(1 - parent_frac -
    gap_frac)` of the panel. Then rewrites each *parent* dcoord
    point in place:

    - **Leaves** (dc == 0 in scipy's centroid tree) drop to the
      *apex of their corresponding block*. So a short per-block tree
      gets a parent leaf close to its top — no big visual disconnect.
    - **Merges** (dc > 0) linearly map into
      `[max_apex + gap, HEIGHT_NORM_MAX]` so the parent tree's
      relative merge heights are preserved.

    Returns `(blocks_modified, parent_modified)` — both ready to
    render against the same y axis.
    """
    per_block_factor = 1.0 - parent_frac - gap_frac
    blocks = [(ic, [[v * per_block_factor for v in row] for row in dc], lv)
              for ic, dc, lv in blocks]
    apexes = [max((v for row in dc for v in row), default=0.0)
              for _, dc, _ in blocks]
    max_apex = max(apexes, default=0.0)
    gap = HEIGHT_NORM_MAX * gap_frac
    parent_top = HEIGHT_NORM_MAX

    p_ic, p_dc, p_lv = parent_layout
    nz = [v for row in p_dc for v in row if v != 0.0]
    # `_normalize_heights` leaves a single-value dcoord unchanged (e.g.
    # a 2-leaf parent tree has one merge — no normalisation possible).
    # Map that pathological case to a flat top so the U still draws.
    dc_min = min(nz) if nz else 0.0
    dc_span = (max(nz) - dc_min) if len(nz) > 1 else 0.0

    def remap(dc_v, ic_v):
        if dc_v == 0.0:
            return apexes[int(round(ic_v))]
        if dc_span == 0.0:
            return parent_top
        return max_apex + gap + (dc_v - dc_min) * (parent_top - max_apex - gap) / dc_span

    new_p_dc = [[remap(d, ic_row[i]) for i, d in enumerate(dc_row)]
                for ic_row, dc_row in zip(p_ic, p_dc)]
    return blocks, (p_ic, new_p_dc, p_lv)


# ---------------------------------------------------------------------------
# Artist-side helpers — shared by any tree renderer following plotlet's
# {leaf axis, height axis} convention. Extracted so extension
# authors writing a new tree variant get the standard input dispatch +
# frame-defaults wiring without copy-pasting from dendrogram.py.
# ---------------------------------------------------------------------------

def build_tree(data, split, tree=None, linkage_matrix=None,
               method="single", metric="euclidean", labels=None):
    """Resolve a tree artist's input → `(SplitTree, had_labels)`.

    Dispatches in priority order:
    - `tree=`     → use directly (must be a `SplitTree`); the other
      input parameters are ignored.
    - `linkage_matrix=` → wrap a raw scipy Z as a one-block `SplitTree`.
    - `data` + `split` → `linkage_split(...)`.
    - `data`             → `linkage(...)`.

    `had_labels` tracks whether `labels=` was explicitly supplied. Tree
    renderers use it to decide between a categorical leaf axis (labels
    drive the scale) and a numeric one (unlabeled case) — `linkage()` /
    `linkage_split()` fabricate `str(i)` defaults when labels are
    omitted, so the returned `SplitTree.blocks` always carries labels,
    but the artist still wants to render the unlabeled case differently.
    """
    had_labels = labels is not None
    if tree is not None:
        if not isinstance(tree, SplitTree):
            raise TypeError(
                f"tree= must be a SplitTree; got {type(tree).__name__}."
            )
        return tree, True
    if data is not None and hasattr(data, "tolist"):
        data = data.tolist()
    Z = linkage_matrix
    if Z is not None:
        if split is not None:
            raise ValueError(
                "linkage_matrix= and split= are mutually exclusive — split "
                "needs per-block linkages; pass data= instead."
            )
        n = len(Z) + 1
        labs = list(labels) if had_labels else [str(i) for i in range(n)]
        if len(labs) != n:
            raise ValueError(
                f"labels has {len(labs)} entries but linkage implies "
                f"{n} observations"
            )
        return SplitTree(blocks=[(Z, labs)], between_order=[0]), had_labels
    if data is None:
        raise ValueError("pass data=, linkage_matrix=, or tree=")
    if split is not None:
        return (linkage_split(data, split, labels=labels,
                              method=method, metric=metric),
                had_labels)
    return linkage(data, labels=labels, method=method, metric=metric), had_labels


def tree_frame_defaults(kw, *,
                        root_expand_frac=0.05):
    """Standard `frame_defaults` for a tree-shaped artist.

    Returns the list of `(name, args, kw)` tuples that any dendrogram-
    style renderer needs: spines off, hide the height-axis ticks, hide
    the leaf-axis ticks when there are no labels, and a small root-side
    data expand so the topmost merge doesn't clip against the inner clip.

    Block gap whitespace and the scale's `splits` are owned by
    `c.sectors({cluster: [members]}, axis=...)` on the panel — any peer
    category-scale artist (dendrogram, heatmap, annotation_strip)
    inherits the gaps via the shared scale.
    """
    orient = kw.get("orientation", "top")
    leaf_on_x = orient in ("top", "bottom")
    has_labels = kw.get("labels") is not None
    out = [("spines", [], {"top": False, "right": False,
                            "bottom": False, "left": False}),
           ("yticks" if leaf_on_x else "xticks", [[]], {})]
    if not has_labels:
        out.append(("xticks" if leaf_on_x else "yticks", [[]], {}))
    expand_axis, expand_args = (
        ("y_expand", [0, root_expand_frac]) if orient == "top" else
        ("y_expand", [root_expand_frac, 0]) if orient == "bottom" else
        ("x_expand", [0, root_expand_frac]) if orient == "right" else
        ("x_expand", [root_expand_frac, 0])  # left
    )
    out.append((expand_axis, expand_args, {}))
    return out
