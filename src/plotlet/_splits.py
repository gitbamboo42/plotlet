"""Group-split primitive shared by category-scale artists.

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

Two levels of API:

- **Primitives** (`group_order`, `permute`, `permute_2d`, `blocks`,
  `partition`, `block_bbox_1d`, `block_bboxes_2d`) — pure functions; pick
  the ones you need. Useful for 1-axis artists (dendrogram) that don't
  fit the row+col bundle.
- **`Splits` bundle** — packages both axes for a 2-D artist (heatmap)
  so kwarg parsing, reorder, scale-extras and annot-permute collapse to
  one object passed around. `from_kwargs` does length validation with a
  configurable error prefix so the same class works for dendrogram, etc.
"""
from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass
class Splits:
    """Per-axis split state for a 2-D category artist (heatmap, future
    annotated-heatmap blocks).

    `row_perm` / `col_perm` are `None` when that axis isn't split, so
    `if sp.row_perm:` / `if sp.has_any:` are the natural guards.
    `row_bounds` / `col_bounds` are always lists (empty when not split),
    so they pass straight into the scale and into `blocks()` without
    `None`-guarding.
    """
    row_perm: list | None = None
    row_bounds: list = field(default_factory=list)
    col_perm: list | None = None
    col_bounds: list = field(default_factory=list)

    @classmethod
    def from_kwargs(cls, kw, rows, cols, *,
                    row_key="row_split", col_key="column_split",
                    artist="heatmap"):
        """Pull `row_split=` / `column_split=` out of `kw`, validate
        lengths against `rows` / `cols`, and build a `Splits`.

        `artist=` is the prefix on length-mismatch errors, so dendrogram
        etc. get their own name in the message.
        """
        rs, cs = kw.get(row_key), kw.get(col_key)
        if rs is not None and len(rs) != len(rows):
            raise ValueError(f"{artist}: {row_key} length ({len(rs)}) "
                             f"doesn't match rows ({len(rows)})")
        if cs is not None and len(cs) != len(cols):
            raise ValueError(f"{artist}: {col_key} length ({len(cs)}) "
                             f"doesn't match columns ({len(cols)})")
        row_perm, row_bounds = group_order(rs) if rs is not None else (None, [])
        col_perm, col_bounds = group_order(cs) if cs is not None else (None, [])
        return cls(row_perm, row_bounds, col_perm, col_bounds)

    @property
    def has_any(self):
        return bool(self.row_perm or self.col_perm)

    def apply(self, matrix=None, rows=None, cols=None):
        """Reorder `matrix` / `rows` / `cols` by the perms.

        Any arg passed as `None` is returned as `None` unchanged — so
        callers can permute just labels (frame_defaults) or the full
        triple (record) with the same method.
        """
        if matrix is not None and (self.row_perm or self.col_perm):
            matrix = permute_2d(matrix, self.row_perm, self.col_perm)
        if rows is not None and self.row_perm:
            rows = permute(rows, self.row_perm)
        if cols is not None and self.col_perm:
            cols = permute(cols, self.col_perm)
        return matrix, rows, cols

    def apply_2d(self, arr):
        """Reorder a 2-D array shaped like the matrix (e.g. annot)."""
        return permute_2d(arr, self.row_perm, self.col_perm)

    def scale_extras(self, gap):
        """Build `{splits, split_gap}` extras for x/y scale calls.

        Returns `(xkw, ykw)` — each is empty when that axis isn't split,
        so callers can `**`-merge unconditionally.
        """
        x = {"splits": self.col_bounds, "split_gap": gap} if self.col_bounds else {}
        y = {"splits": self.row_bounds, "split_gap": gap} if self.row_bounds else {}
        return x, y

    @property
    def n_row_blocks(self):
        return len(self.row_bounds) + 1 if self.row_bounds else 0

    @property
    def n_col_blocks(self):
        return len(self.col_bounds) + 1 if self.col_bounds else 0
