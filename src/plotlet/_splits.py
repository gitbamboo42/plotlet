"""Group-split primitives for category-scale artists.

A 'split' takes a 1-D grouping vector (one label per band) and produces:

- a stable permutation that reorders bands so equal labels sit together,
- boundary indices in the permuted axis where each new block begins.

The category scale consumes those boundaries via `splits=` / `split_gap=`
([scales.py](scales.py)) to reserve gap px at each boundary. Any artist
that wants to render *flush internals per block* (e.g. the heatmap PNG
fallback, where one stretched image would smear colour across the gaps;
or a per-block dendrogram with its own scipy linkage) iterates with
`blocks()` / `block_bboxes_*()` — these yield one full-range block when
no boundaries are present, so the artist's draw code looks the same
shape split or not.

Pure functions: `group_order`, `permute`, `permute_2d`, `blocks`,
`partition`, `block_bbox_1d`, `block_bboxes_2d`. Pick the ones you need.
"""
from __future__ import annotations


def group_order(groups):
    """Grouping vector -> `(perm, boundaries)`.

    Stable: groups appear in first-seen order; original order preserved
    within each group. `perm[i]` is the original index of the band that
    ends up at position `i`. `boundaries` are indices in the permuted
    axis where each new block begins (excluding the implicit `0` and `n`
    edges).
    """
    order, buckets = [], {}
    for i, g in enumerate(groups):
        if g not in buckets:
            buckets[g] = []
            order.append(g)
        buckets[g].append(i)
    perm, boundaries = [], []
    for g in order:
        if perm:
            boundaries.append(len(perm))
        perm.extend(buckets[g])
    return perm, boundaries


def permute(seq, perm):
    """Reorder a 1-D sequence by `perm`."""
    return [seq[i] for i in perm]


def permute_2d(matrix, row_perm=None, col_perm=None):
    """Reorder rows and/or cols of a 2-D list. `None` skips that axis."""
    if row_perm:
        matrix = [matrix[i] for i in row_perm]
    if col_perm:
        matrix = [[r[i] for i in col_perm] for r in matrix]
    return matrix


def blocks(n, boundaries):
    """Iterate `(start, end)` ranges carved out by `boundaries`.

    With `boundaries=[]` yields one block `(0, n)` — so a split-aware
    inner loop covers the non-split case unchanged.
    """
    edges = [0, *boundaries, n]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def partition(seq, boundaries):
    """Slice a sequence into per-block sub-sequences.

    Useful for any artist that wants to compute something *within* each
    block (e.g. dendrogram running scipy linkage on each group's leaves
    independently). Returns `[seq[s:e] for each (s, e) in blocks(...)]`.
    """
    return [seq[s:e] for s, e in blocks(len(seq), boundaries)]


def block_bbox_1d(scale, cats, bw, bounds):
    """Yield `(i0, i1, lo, hi)` per contiguous block along one category axis.

    `(i0, i1)` is the half-open band-index range; `(lo, hi)` is the
    pixel extent from the first band's left edge to the last band's
    right edge (min/max'd so y-flipped scales also produce `lo < hi`).
    With `bounds=[]` yields one block spanning all of `cats`.
    """
    for i0, i1 in blocks(len(cats), bounds):
        a = scale(cats[i0])     - bw / 2
        b = scale(cats[i1 - 1]) + bw / 2
        yield i0, i1, min(a, b), max(a, b)


def block_bboxes_2d(ctx, rows, cols, bw, bh, row_bounds, col_bounds):
    """Yield `(r0, r1, c0, c1, sy_t, sy_b, sx_l, sx_r)` per row-col block.

    Outer loop varies rows, inner loop varies cols. With both bounds
    empty yields one full-range block — heatmap's no-split PNG fallback
    falls out of this for free.
    """
    for r0, r1, sy_t, sy_b in block_bbox_1d(ctx.y_scale, rows, bh, row_bounds):
        for c0, c1, sx_l, sx_r in block_bbox_1d(ctx.x_scale, cols, bw, col_bounds):
            yield r0, r1, c0, c1, sy_t, sy_b, sx_l, sx_r


