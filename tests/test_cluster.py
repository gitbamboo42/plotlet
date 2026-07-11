"""Direct unit tests for `plotlet.cluster` — linkage ordering and split
behavior. The dendrogram baselines exercise the rendering; these pin
the clustering math itself (leaf order, block order, degenerate
inputs) so a scipy-wrapping regression can't hide behind a visually
plausible picture."""
import pytest

import plotlet as pt


# Three well-separated groups on a line: values near 0, near 10, near 100.
# Any sane linkage clusters them into exactly these groups.
ROWS = {
    "a1": [0.0], "a2": [0.4], "a3": [0.2],
    "b1": [10.0], "b2": [10.5],
    "c1": [100.0],
}


def _tree(method="single"):
    labels = list(ROWS)
    data = [ROWS[k] for k in labels]
    return pt.linkage(data, labels=labels, method=method)


def test_linkage_groups_similar_leaves():
    tree = _tree()
    assert tree.n_blocks == 1
    _z, labels = tree.blocks[0]
    order = list(labels)
    # scipy decides rotation; the invariant is contiguity of each group.
    for group in ("a", "b", "c"):
        idx = [i for i, l in enumerate(order) if l.startswith(group)]
        assert idx == list(range(min(idx), max(idx) + 1)), \
            f"group {group} not contiguous in {order}"


def test_linkage_deterministic():
    t1, t2 = _tree(), _tree()
    assert t1.blocks[0][1] == t2.blocks[0][1]
    assert (t1.blocks[0][0] == t2.blocks[0][0]).all()


def test_linkage_rejects_single_observation():
    with pytest.raises(ValueError, match="at least 2"):
        pt.linkage([[1.0]], labels=["only"])


def test_linkage_split_orders_blocks_by_centroid():
    labels = list(ROWS)
    data = [ROWS[k] for k in labels]
    # split is a per-row group-tag column, aligned with data.
    split = [lbl[0].upper() for lbl in labels]   # A A A B B C
    tree = pt.linkage_split(data, split, labels=labels)
    assert tree.n_blocks == 3
    # A single-observation block skips the within-block linkage.
    blocks_by_members = {frozenset(labs): z for z, labs in tree.blocks}
    assert blocks_by_members[frozenset({"c1"})] is None
    assert set(blocks_by_members) == {frozenset({"a1", "a2", "a3"}),
                                      frozenset({"b1", "b2"}),
                                      frozenset({"c1"})}
    # The between-order is a dendrogram leaf order over block centroids
    # (~0.2, ~10.25, ~100): rotation is scipy's choice, but the two most
    # similar blocks (A and B) must land adjacent, never split by C.
    display_groups = [tree.blocks[bi][1][0][0] for bi in tree.between_order]
    pos = {g: i for i, g in enumerate(display_groups)}
    assert abs(pos["a"] - pos["b"]) == 1, display_groups
